"""Turn source files into `Document` objects.

Two formats are handled, because the repo holds the same policy content twice:

* `okf`      - the OKF v0.2 bundle. YAML frontmatter, ATX headings, footnote
               provenance labels. This is the governing presentation.
* `handbook` - the raw handbook markdown. No frontmatter, and its headings are
               bold text lines (`**SECTION 20: ...**`) rather than ATX headings,
               so it needs its own structural parser.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from src.grounding.policy_rag.config import CorpusConfig
from src.grounding.policy_rag.documents import Document, SourceRef, _stable_id

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]]+)\]:\s*(.+)$", re.MULTILINE)

#: OKF frontmatter `type:` -> internal doc_type.
_OKF_TYPE_MAP = {
    "hr policy": "policy",
    "corpus datasheet": "datasheet",
    "attested computation": "computation",
    "reference": "reference",
    "skill": "skill",
    "orientation": "nav",
}


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return `(frontmatter_dict, body)`. Missing frontmatter yields `({}, text)`."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        logger.warning("unparseable frontmatter, treating document as bare markdown")
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    return data, text[match.end() :]


def _as_str(value: object) -> str | None:
    """YAML turns bare ISO timestamps into datetimes; normalise back to text."""
    if value is None:
        return None
    return str(value)


def _parse_sources(raw: object) -> list[SourceRef]:
    if not isinstance(raw, list):
        return []
    refs: list[SourceRef] = []
    for entry in raw:
        if not isinstance(entry, dict) or "id" not in entry:
            continue
        refs.append(
            SourceRef(
                id=str(entry["id"]),
                title=str(entry.get("title", entry["id"])),
                resource=str(entry.get("resource", "")),
                last_modified=_as_str(entry.get("last_modified")),
            )
        )
    return refs


def _parse_footnotes(body: str) -> dict[str, str]:
    return {label: text.strip() for label, text in _FOOTNOTE_DEF_RE.findall(body)}


def _title_from_body(body: str, fallback: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def load_okf_corpus(corpus: CorpusConfig, repo_root: Path) -> list[Document]:
    """Load every markdown and python file under an OKF bundle root."""
    if not corpus.root:
        raise ValueError(f"corpus {corpus.id!r} of kind 'okf' needs a `root`")
    root = repo_root / corpus.root
    if not root.is_dir():
        raise FileNotFoundError(f"OKF corpus root not found: {root}")

    documents: list[Document] = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file() or file_path.suffix not in {".md", ".py"}:
            continue
        rel_to_root = file_path.relative_to(root).as_posix()
        rel_to_repo = file_path.relative_to(repo_root).as_posix()
        entitlement = corpus.entitlement_for(rel_to_root)

        if file_path.suffix == ".py":
            documents.append(
                Document(
                    doc_id=_stable_id(corpus.id, rel_to_repo),
                    corpus_id=corpus.id,
                    path=rel_to_repo,
                    title=f"Source file: {file_path.name}",
                    doc_type="code",
                    authority=corpus.authority,
                    entitlement=entitlement,
                    body=file_path.read_text(encoding="utf-8"),
                    description="Attested computation or attester source file.",
                    tags=["code", "computation"],
                    status="stable",
                )
            )
            continue

        raw_text = file_path.read_text(encoding="utf-8")
        front, body = split_frontmatter(raw_text)

        if front:
            declared = str(front.get("type", "")).strip().lower()
            doc_type = _OKF_TYPE_MAP.get(declared, "policy")
            title = str(front.get("title") or _title_from_body(body, file_path.stem))
        else:
            # The only frontmatter-free markdown in the bundle is the folder
            # index pages and log.md - navigation, not policy claims.
            doc_type = "nav"
            title = _title_from_body(body, file_path.stem)

        if file_path.name == "index.md":
            doc_type = "nav"

        documents.append(
            Document(
                doc_id=_stable_id(corpus.id, rel_to_repo),
                corpus_id=corpus.id,
                path=rel_to_repo,
                title=title,
                doc_type=doc_type,
                authority=corpus.authority,
                entitlement=entitlement,
                body=body,
                description=str(front.get("description", "")),
                tags=[str(t) for t in front.get("tags", []) or []],
                status=str(front.get("status", "unknown")),
                stale_after=_as_str(front.get("stale_after")),
                sources=_parse_sources(front.get("sources")),
                footnotes=_parse_footnotes(body),
                extra={
                    k: v
                    for k, v in front.items()
                    if k not in {"type", "title", "description", "tags", "status", "sources", "stale_after"}
                },
            )
        )

    return documents


# --- raw handbook -----------------------------------------------------------

_SECTION_RE = re.compile(r"^\*\*SECTION\s+(\d+)\s*:\s*(.+?)\*\*\s*$", re.IGNORECASE)
#: `**1.2 Paid Vacation Leave (Singapore)**` and the variant where the bold run
#: closes mid-line and body text continues after it on the same line.
_SUBSECTION_RE = re.compile(r"^\*\*(\d+\.\d+)\s+(.+?)\*\*\s*(.*)$")
_ATX_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _strip_md_emphasis(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).strip()


def load_handbook_corpus(corpus: CorpusConfig, repo_root: Path) -> list[Document]:
    """Load the raw handbook as one document per numbered SECTION.

    Splitting at SECTION level rather than loading the whole file gives every
    chunk a real `doc_title` ("SECTION 20: Vacation Leave (Singapore)") to embed
    alongside its text, and makes citations point at a section rather than at a
    1,100-line file.
    """
    if not corpus.path:
        raise ValueError(f"corpus {corpus.id!r} of kind 'handbook' needs a `path`")
    file_path = repo_root / corpus.path
    if not file_path.is_file():
        raise FileNotFoundError(f"handbook not found: {file_path}")

    rel_to_repo = file_path.relative_to(repo_root).as_posix()
    lines = file_path.read_text(encoding="utf-8").splitlines()

    source_ref = SourceRef(
        id="handbook",
        title="ALTOSTRAT SINGAPORE EMPLOYEE POLICY HANDBOOK & CONDUCT GUIDELINES",
        resource=rel_to_repo,
        last_modified="2026-07-01T00:00:00Z",
    )

    documents: list[Document] = []
    current_number: str | None = None
    current_title = "Front matter"
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        body = "\n".join(buffer).strip()
        if not body:
            return
        label = f"Section {current_number}: {current_title}" if current_number else current_title
        documents.append(
            Document(
                doc_id=_stable_id(corpus.id, rel_to_repo, label),
                corpus_id=corpus.id,
                path=rel_to_repo,
                title=f"Handbook {label}",
                doc_type="handbook",
                authority=corpus.authority,
                entitlement=corpus.entitlement_for(rel_to_repo),
                body=body,
                description="Verbatim handbook text (summary and detail layers unresolved).",
                tags=["handbook", "source"],
                status="stable",
                stale_after=None,
                sources=[source_ref],
                extra={"section": current_number},
            )
        )

    for line in lines:
        section = _SECTION_RE.match(line.strip())
        if section:
            flush()
            buffer = []
            current_number = section.group(1)
            current_title = _strip_md_emphasis(section.group(2))
            continue
        buffer.append(line)

    flush()
    return documents


def load_corpus(corpus: CorpusConfig, repo_root: Path) -> list[Document]:
    if corpus.kind == "okf":
        return load_okf_corpus(corpus, repo_root)
    if corpus.kind == "handbook":
        return load_handbook_corpus(corpus, repo_root)
    raise ValueError(f"unknown corpus kind: {corpus.kind!r}")
