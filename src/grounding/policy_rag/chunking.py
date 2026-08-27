"""Heading-aware chunking.

Policy text is answered section by section, so the chunk boundary that matters
is the heading, not a fixed token count. A section is only split further when it
exceeds `max_chars`, and then on paragraph boundaries with a small overlap so a
table or a bulleted list is not cut mid-row.
"""

from __future__ import annotations

import re

from src.grounding.policy_rag.config import ChunkingConfig
from src.grounding.policy_rag.documents import Chunk, Document, SourceRef, make_chunk_id

_ATX_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")
#: Handbook pseudo-heading: `**20.1 Eligibility**` optionally followed by body text.
_BOLD_HEADING_RE = re.compile(r"^\*\*(\d+(?:\.\d+)*)\s+(.+?)\*\*\s*(.*)$")
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^[^\]]+\]:")
_FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]]+)\]")

_CONFLICT_HEADING_RE = re.compile(r"^conflicts?\b", re.IGNORECASE)
_GAP_HEADING_RE = re.compile(r"^gaps\b", re.IGNORECASE)


def slugify(text: str) -> str:
    """GitHub-flavoured heading anchor."""
    slug = text.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug.strip("-")


class _Section:
    __slots__ = ("heading_path", "lines")

    def __init__(self, heading_path: list[str]) -> None:
        self.heading_path = heading_path
        self.lines: list[str] = []

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


def _split_sections(document: Document) -> list[_Section]:
    """Break a document body into heading-delimited sections."""
    use_bold_headings = document.doc_type == "handbook"
    sections: list[_Section] = []
    stack: list[tuple[int, str]] = []
    current = _Section([])

    def push(section: _Section) -> None:
        if section.text:
            sections.append(section)

    for raw_line in document.body.splitlines():
        line = raw_line.rstrip()
        heading_level: int | None = None
        heading_text: str | None = None
        trailing = ""

        atx = _ATX_RE.match(line)
        if atx:
            heading_level = len(atx.group(1))
            heading_text = atx.group(2).strip()
        elif use_bold_headings:
            bold = _BOLD_HEADING_RE.match(line.strip())
            if bold:
                # `20.1` is depth 2, `20.1.1` is depth 3 - keeps the trail honest.
                heading_level = bold.group(1).count(".") + 1
                heading_text = f"{bold.group(1)} {bold.group(2).strip()}"
                trailing = bold.group(3).strip()

        if heading_level is not None and heading_text:
            push(current)
            while stack and stack[-1][0] >= heading_level:
                stack.pop()
            stack.append((heading_level, heading_text))
            current = _Section([h for _, h in stack])
            if trailing:
                current.lines.append(trailing)
            continue

        if _FOOTNOTE_DEF_RE.match(line):
            # Footnote definitions are provenance metadata already captured on
            # the Document; keeping them in chunk text only dilutes the embedding.
            continue

        current.lines.append(line)

    push(current)
    return sections


def _split_oversized(text: str, cfg: ChunkingConfig) -> list[str]:
    """Split one section into <= max_chars pieces on paragraph boundaries."""
    if len(text) <= cfg.max_chars:
        return [text]

    paragraphs = [p for p in re.split(r"\n{2,}", text) if p.strip()]
    pieces: list[str] = []
    buffer = ""

    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= cfg.max_chars or not buffer:
            buffer = candidate
        else:
            pieces.append(buffer)
            tail = buffer[-cfg.overlap_chars :] if cfg.overlap_chars else ""
            buffer = f"{tail}\n\n{paragraph}" if tail else paragraph

    if buffer:
        pieces.append(buffer)

    # A single paragraph longer than max_chars (a wide table, typically) still
    # has to be cut; do it on line boundaries rather than mid-row.
    final: list[str] = []
    for piece in pieces:
        while len(piece) > cfg.max_chars:
            cut = piece.rfind("\n", 0, cfg.max_chars)
            if cut <= 0:
                cut = cfg.max_chars
            final.append(piece[:cut].strip())
            piece = piece[max(0, cut - cfg.overlap_chars) :].strip()
        if piece:
            final.append(piece)
    return final


def _sources_for(text: str, document: Document) -> list[SourceRef]:
    """Narrow the document's source list to those footnoted in this chunk."""
    by_id = {s.id: s for s in document.sources}
    referenced = [by_id[label] for label in dict.fromkeys(_FOOTNOTE_REF_RE.findall(text)) if label in by_id]
    return referenced or list(document.sources)


def chunk_document(document: Document, cfg: ChunkingConfig) -> list[Chunk]:
    chunks: list[Chunk] = []
    ordinal = 0

    for section in _split_sections(document):
        top_heading = section.heading_path[0] if section.heading_path else ""
        is_conflict = bool(_CONFLICT_HEADING_RE.match(top_heading))
        is_gap = bool(_GAP_HEADING_RE.match(top_heading))
        anchor = slugify(section.heading_path[-1]) if section.heading_path else ""

        for piece in _split_oversized(section.text, cfg):
            if len(piece.strip()) < cfg.min_chars:
                continue
            chunk_id = make_chunk_id(document.doc_id, section.heading_path, ordinal)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=document.doc_id,
                    corpus_id=document.corpus_id,
                    path=document.path,
                    doc_title=document.title,
                    doc_type=document.doc_type,
                    authority=document.authority,
                    entitlement=document.entitlement,
                    heading_path=list(section.heading_path),
                    anchor=anchor,
                    text=piece.strip(),
                    ordinal=ordinal,
                    tags=list(document.tags),
                    status=document.status,
                    stale_after=document.stale_after,
                    sources=_sources_for(piece, document),
                    is_conflict=is_conflict,
                    is_gap=is_gap,
                )
            )
            ordinal += 1

    return chunks
