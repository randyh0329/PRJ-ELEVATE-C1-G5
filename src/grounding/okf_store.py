"""Open Knowledge Format (OKF) curated policy catalog.

This register is built by reading the OKF v0.2 bundle under
`okf/altostrat-sg-handbook/` at construction time. It is the deterministic half
of `DualGroundingEngine`: same input, same document, same citation, no model and
no index. That is what makes it usable where a citation has to be *stable*
rather than *best-matching* - the entitlement rule authorising a transaction.

It used to be four `PolicyDocument`s typed out by hand as a pre-corpus demo
fixture, and every one of them was wrong once the real handbook arrived:

| Section | Fixture said | Handbook says |
|---------|--------------|---------------|
| Bereavement | 5 days immediate family, 3 extended | **4 weeks (20 work days) per event**, no such split |
| Home office equipment | US$350, `REMOTE_FULL_TIME` only | **US$500**, approved **Remote _or Hybrid_** status |
| Hospitalisation | 60 days | **46 work days** |
| Relocation | £5,000 | **US$10,000** |

None of those were reachable by reading the fixture - it was internally
consistent, confidently worded, and cited `https://hr.corp.internal/policies/...`
URLs that do not exist, so the citation could not be followed to the text that
would have contradicted it. Deriving the register from the bundle is what makes
the figures answerable to a source; `citations.blob_url` is what makes the
citation followable. See `src/grounding/citations.py` for why the second half
matters as much as the first.

The bundle is checked into git, unlike the FAISS index under `var/`, so this
register is available in a fresh clone with no build step. That is the whole
reason it survives as a fallback.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from src.grounding.citations import blob_url
from src.grounding.policy_rag.loaders import split_frontmatter

logger = logging.getLogger("grounding.okf_store")

#: Repo root, four levels up from `src/grounding/okf_store.py`.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_ROOT = _REPO_ROOT / "okf" / "altostrat-sg-handbook"

#: OKF `type:` values that state rules an employee can be answered with. Folder
#: index pages carry no claims, the datasheet describes the corpus rather than
#: the policy, and `Attested Computation` is a worked calculation whose inputs
#: come from elsewhere - none of them belong in a register whose entries are
#: quoted back as entitlements.
_ANSWERABLE_TYPES = frozenset({"hr policy", "orientation"})

#: `Handbook Section 22: Bereavement Leave (Global) - detail layer, governing`
_SECTION_RE = re.compile(r"Section\s+(\d+(?:\.\d+)*)")
#: Footnote provenance labels, e.g. `[^hb-22]`. Useful inside the bundle,
#: meaningless once the text is quoted to an employee.
_FOOTNOTE_REF_RE = re.compile(r"\[\^[^\]]+\]")
_BLANK_RUN_RE = re.compile(r"\n{3,}")

#: A tag or title hit alone clears this; incidental body overlap alone does not.
_RELEVANCE_FLOOR = 3.0

#: Fraction of a question's content words that must appear *somewhere* in a
#: document before it may be offered as the answer to that question.
#:
#: The score alone cannot express this. "Reimbursement for personal pet
#: helicopter transport" hits the `reimbursement` tag on Travel & Expense and
#: clears the relevance floor on that one word, and the register would then quote
#: real expense rules at a question about a helicopter - a near-miss answer, the
#: failure FR-5.2 is written against. A keyword register has no notion of "not in
#: the corpus", and the previous implementation papered over it with a literal
#: list of bait words (`helicopter`, `yacht`, `bitcoin`), which only ever caught
#: the baits someone had thought of.
#:
#: Coverage is the deterministic analogue of the retriever's
#: `min_lexical_corroboration`: score decides ordering, this decides
#: admissibility. Same split, same reason.
_COVERAGE_FLOOR = 0.6

#: How far the best document must outscore the runner-up to count as chosen
#: rather than guessed.
#:
#: Coverage cannot catch ambiguity, because an ambiguous question is fully
#: covered by every candidate. "Tell me about leave" reduces to the single word
#: `leave`, which eleven concepts match perfectly and identically - and the
#: register would hand back whichever sorted first, presenting a coin-flip as a
#: determinate answer. Requiring a margin turns that tie into a refusal.
#:
#: The value is empirical. Measured over the register, ambiguous and off-topic
#: questions peak at a 1.23 margin and answerable ones resume at 1.38, so 1.25
#: sits in the gap rather than on either edge. Margin and `_COVERAGE_FLOOR`
#: catch different things and neither is redundant: "can I buy bitcoin with the
#: corporate card" matches exactly one document and is therefore maximally
#: decisive - coverage is what refuses it.
#:
#: One known false refusal at this setting: "carers leave for a sick relative"
#: ranks Carer's Leave first but only 1.12 ahead of Sick Leave, and is declined
#: as ambiguous. Two adjacent leave policies genuinely are hard to separate on
#: keywords, and a wrong entitlement is worse than a deferral - NFR-3.1 ranks
#: them that way. This is a keyword register's ceiling, not a tuning defect; the
#: semantic path in `policy_rag` is what this falls back *from*.
_DECISIVENESS_MARGIN = 1.25

_WORD_RE = re.compile(r"[a-z0-9]+")

#: Words that carry no topic. The list has to be *complete* rather than
#: representative, because `_COVERAGE_FLOOR` divides by the number of content
#: words: one stray `is` in a two-word question halves its coverage and refuses
#: an answer the register holds. An earlier draft omitted `is`, `do` and `i`,
#: and "what is the bereavement policy" came back empty while the bereavement
#: document sat in the register scoring 5.0.
_STOPWORDS = frozenset(
    {
        "a", "about", "all", "am", "an", "and", "any", "are", "as", "at", "be",
        "been", "but", "by", "can", "company", "corporate", "could", "day", "days",
        "did", "do", "does", "doing", "entitled", "for", "from", "get", "give",
        "given", "has", "have", "how", "i", "if", "in", "into", "is", "it", "its",
        "long", "many", "may", "me", "much", "must", "my", "need", "not", "of",
        "office", "on", "or", "our", "out", "please", "policy", "regarding",
        "should", "so", "some", "tell", "than", "that", "the", "their", "them",
        "then", "there", "these", "they", "this", "to", "under", "up", "us", "was",
        "we", "were", "what", "when", "where", "which", "who", "why", "will",
        "with", "would", "you", "your",
    }
)

#: Crude stemming length for coverage. Long enough that `leave` and `leaving`
#: collapse without `expense` and `expedite` doing the same. Used only for the
#: coverage test - never for scoring, where a loose match would let one vague
#: word outrank an exact one.
_STEM = 5


def _stems(words: frozenset[str] | set[str]) -> frozenset[str]:
    return frozenset(w[:_STEM] for w in words if len(w) >= _STEM)

#: Top-level folder -> the `category` this store has always reported. Kept as a
#: coarse vocabulary because callers filter on it; the folder is the corpus's
#: own grouping, so nothing is invented here.
_CATEGORIES = {
    "leave": "LEAVE",
    "workplace": "WORKPLACE",
    "conduct": "CONDUCT",
    "ethics": "ETHICS",
    "people-ops": "PEOPLE_OPS",
    "computations": "COMPUTATION",
    "references": "REFERENCE",
}


class PolicyDocument(BaseModel):
    """Structure for an OKF curated policy rule and handbook section."""

    section_id: str
    title: str
    category: str
    summary: str
    details: str
    entitlement_limits: dict[str, str] = Field(default_factory=dict)
    citation_title: str
    citation_url: str
    tags: list[str] = Field(default_factory=list)
    #: Repo-relative path of the concept file this was read from. Empty for
    #: documents registered through `add_policy` by a caller.
    path: str = ""
    #: The handbook URL the concept's governing source points at - the layer
    #: *behind* the concept, for a reader who wants the original wording.
    source_url: str = ""
    #: OKF lifecycle marker: `stable` or `draft`. A draft concept's rules
    #: include producer assumptions and should not be quoted as settled.
    status: str = "stable"
    #: ISO date after which the producer no longer vouches for the content.
    stale_after: str = ""
    #: True when the concept records a documented disagreement between handbook
    #: layers. Surfaced rather than resolved: the register does not get to pick
    #: a side the source itself does not pick.
    has_conflict: bool = False

    @property
    def citation_markdown(self) -> str:
        return f"[{self.citation_title}]({self.citation_url})"

    def excerpt(self, *keywords: str) -> str | None:
        """The document's own bullet naming every keyword, rejoined onto one line.

        For quoting *one* rule inside a longer message - a saga confirmation that
        has to state an allowance cap without reproducing four screens of travel
        policy. The text returned is the corpus's, word for word.

        `None` means no single block carries all the keywords, and the caller
        must read that as "the corpus does not say here", not as licence to state
        the figure anyway. That distinction is the entire point: the relocation
        cap used to be written into the response string in `src/core/agent.py` as
        "£5,000", against a handbook that says US$10,000 - a wrong number in the
        wrong currency, in prose no retrieval result could contradict.
        """
        wanted = [k.lower() for k in keywords]
        for block in _blocks(self.details):
            lowered = block.lower()
            if all(word in lowered for word in wanted):
                return block
        return None


def _blocks(details: str) -> list[str]:
    """Concept body split into logical blocks - bullets, rows, headings, paragraphs.

    Concept files are hard-wrapped, so a bullet routinely spans three physical
    lines and the figure sits on the second of them. Matching per line would
    therefore find "relocation allowance" and "US$10,000" in different strings
    and conclude the document does not state a relocation cap. A continuation
    line is an indented one, which is the convention the whole bundle follows.
    """
    blocks: list[str] = []
    current: list[str] = []
    for line in details.splitlines():
        stripped = line.strip()
        if (not stripped or not line.startswith(" ")) and current:
            blocks.append(" ".join(current))
            current = []
        if stripped:
            current.append(stripped)
    if current:
        blocks.append(" ".join(current))
    return blocks


def _normalise_body(body: str) -> str:
    """Concept body as quotable prose.

    Footnote references and their definitions are stripped - they label
    provenance for a corpus reader and read as noise to an employee - and blank
    runs are collapsed. Headings, tables and emphasis stay: they carry the
    structure of the rule, and reflowing policy text is how figures drift.
    """
    lines = [ln for ln in body.splitlines() if not ln.lstrip().startswith("[^")]
    text = _FOOTNOTE_REF_RE.sub("", "\n".join(lines))
    return _BLANK_RUN_RE.sub("\n\n", text).strip()


def _sections_from_sources(sources: object) -> list[str]:
    """Handbook section numbers named by a concept's `sources:` block, in order.

    Order is load-bearing. The bundle lists the governing detail layer first, so
    `sources[0]` is the section this concept is primarily *about*; the rest are
    summary layers and cross-references that merely mention it.
    """
    if not isinstance(sources, list):
        return []
    numbers: list[str] = []
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        match = _SECTION_RE.search(str(entry.get("title", "")))
        if match and match.group(1) not in numbers:
            numbers.append(match.group(1))
    return numbers


def _first_source_url(sources: object) -> str:
    if not isinstance(sources, list):
        return ""
    for entry in sources:
        if isinstance(entry, dict) and entry.get("resource"):
            return str(entry["resource"])
    return ""


def _document_from_file(path: Path, corpus_root: Path) -> tuple[PolicyDocument, list[str]] | None:
    """Parse one concept file. Returns `(document, secondary_section_ids)`."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("unreadable concept file, skipping: %s", path)
        return None

    front, body = split_frontmatter(raw)
    if str(front.get("type", "")).strip().lower() not in _ANSWERABLE_TYPES:
        return None

    title = str(front.get("title") or path.stem.replace("-", " ").title())
    sections = _sections_from_sources(front.get("sources"))
    # No handbook section number is not a reason to drop a real policy; the
    # slug is a stable key and reads sensibly in a log line.
    section_id = sections[0] if sections else path.stem

    try:
        relative = path.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        # `corpus_root` is a public parameter, so the bundle need not live inside
        # the checkout - a mounted volume or a test fixture will not. There is no
        # blob URL for a file this repository does not contain, so the key falls
        # back to the path within the bundle and the citation points at that. It
        # will not resolve, which is honest; raising here would instead take down
        # every caller of a store that was configured exactly as documented.
        relative = path.relative_to(corpus_root.parent).as_posix()
    folder = path.relative_to(corpus_root).parts[0] if path.parent != corpus_root else ""

    document = PolicyDocument(
        section_id=section_id,
        title=title,
        category=_CATEGORIES.get(folder, "GENERAL"),
        summary=str(front.get("description") or "").strip(),
        details=_normalise_body(body),
        citation_title=(
            f"{title} - Handbook Section {section_id}" if sections else title
        ),
        citation_url=blob_url(relative),
        tags=[str(t) for t in (front.get("tags") or []) if str(t)],
        path=relative,
        source_url=_first_source_url(front.get("sources")),
        status=str(front.get("status") or "stable"),
        stale_after=str(front.get("stale_after") or ""),
        # The bundle's convention for a recorded disagreement is a `# Conflict`
        # heading; `guards.py` keys the same fact off chunk metadata.
        has_conflict=bool(re.search(r"^#+\s*Conflict\b", body, re.MULTILINE)),
    )
    return document, sections[1:]


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if len(w) > 1 and w not in _STOPWORDS}


class _Vocabulary(BaseModel):
    """A document's searchable words, split by field weight.

    Precomputed on insert. Recomputing these regexes over 30 full policy bodies
    on every query is the kind of cost that never shows up in a unit test and
    shows up immediately behind a graph node.
    """

    tags: frozenset[str]
    tag_phrases: frozenset[str]
    title: frozenset[str]
    summary: frozenset[str]
    body: frozenset[str]

    @classmethod
    def of(cls, doc: PolicyDocument) -> _Vocabulary:
        tag_words: set[str] = set()
        for tag in doc.tags:
            tag_words |= set(_WORD_RE.findall(tag.lower()))
        return cls(
            tags=frozenset(tag_words),
            tag_phrases=frozenset(t.lower() for t in doc.tags),
            title=frozenset(_content_words(doc.title)),
            summary=frozenset(_content_words(doc.summary)),
            # Long words only: an unweighted body match on "the" or "work"
            # attaches every document to every question.
            body=frozenset(w for w in _content_words(doc.details) if len(w) > 4),
        )

    @property
    def everything(self) -> frozenset[str]:
        return self.tags | self.title | self.summary | self.body

    def covers(self, query_words: set[str]) -> float:
        """Fraction of `query_words` this document mentions, allowing for stems.

        Stemming matters here and not in scoring: without it, "how much vacation
        leave do I *accrue*" scored `vacation.md` highest and then failed it on
        coverage, because the concept spells the same idea "accrual" - handing
        the question to sick leave, which happens to use the word. A near-miss
        that the correct document was disqualified in favour of.
        """
        vocabulary = self.everything
        stems = _stems(vocabulary)
        covered = sum(
            1 for w in query_words if w in vocabulary or (len(w) >= _STEM and w[:_STEM] in stems)
        )
        return covered / len(query_words) if query_words else 0.0


class OKFPolicyStore:
    """Curated enterprise HR policies, read from the OKF bundle on disk."""

    def __init__(self, corpus_root: Path | str | None = None) -> None:
        self._policies: dict[str, PolicyDocument] = {}
        self._vocabularies: dict[str, _Vocabulary] = {}
        #: Secondary handbook section -> the section_id that owns the concept.
        #: A summary-layer reference such as `3.1` should still find the
        #: bereavement concept, but must not outrank the detail layer that
        #: governs it, so aliases are resolved only after a direct miss.
        self._aliases: dict[str, str] = {}
        self._corpus_root = Path(corpus_root) if corpus_root else DEFAULT_CORPUS_ROOT
        self._load_corpus_policies()

    # --- loading ------------------------------------------------------------

    def _load_corpus_policies(self) -> None:
        """Read every answerable concept in the bundle into the register."""
        root = self._corpus_root
        if not root.is_dir():
            # Empty beats invented. A caller that gets no documents falls
            # through to "I could not find an approved policy", which is true;
            # a caller handed placeholders would quote them as entitlements.
            logger.error(
                "OKF bundle not found at %s - the curated policy register is empty. "
                "Policy questions will fall back to a refusal until it is restored.",
                root,
            )
            return

        secondary: list[tuple[str, str]] = []
        for path in sorted(root.rglob("*.md")):
            parsed = _document_from_file(path, root)
            if parsed is None:
                continue
            document, aliases = parsed
            if document.section_id in self._policies:
                # Two concepts can name the same governing section: onboarding
                # and performance-and-discipline both cite Section 30. Re-key
                # the loser on its slug rather than dropping it - the first
                # version of this loader did drop it, which quietly removed the
                # only description of a new hire's first week from the register
                # while reporting a healthy document count.
                incumbent = self._policies[document.section_id]
                slug = Path(document.path).stem
                logger.info(
                    "handbook section %s already owned by %s; filing %s under %r",
                    document.section_id, incumbent.path, document.path, slug,
                )
                aliases = [a for a in aliases if a != document.section_id]
                document = document.model_copy(update={"section_id": slug})
            self.add_policy(document)
            secondary.extend((alias, document.section_id) for alias in aliases)

        # Applied after the main pass so that a section owned outright by one
        # concept is never shadowed by another concept's passing reference to it.
        for alias, owner in secondary:
            if alias not in self._policies:
                self._aliases.setdefault(alias, owner)

        logger.info(
            "loaded %d curated policy documents (%d section aliases) from %s",
            len(self._policies), len(self._aliases), root,
        )

    # --- public API ---------------------------------------------------------

    def add_policy(self, doc: PolicyDocument) -> None:
        """Add or update a policy document."""
        self._policies[doc.section_id] = doc
        self._vocabularies[doc.section_id] = _Vocabulary.of(doc)

    def get_policy_by_section(self, section_id: str) -> PolicyDocument | None:
        """Fetch policy document by handbook section ID, e.g. `22` or `5.4`.

        Summary-layer section numbers resolve to the concept that governs them,
        so `3.1` and `22` both return the bereavement policy.
        """
        direct = self._policies.get(section_id)
        if direct is not None:
            return direct
        owner = self._aliases.get(section_id)
        return self._policies.get(owner) if owner else None

    def get_policy_by_path(self, path: str) -> PolicyDocument | None:
        """Fetch by repo-relative concept path, the key retrieval reports."""
        wanted = path.strip("/")
        return next((d for d in self._policies.values() if d.path == wanted), None)

    def all_policies(self) -> list[PolicyDocument]:
        """Every document in the register, ordered by section for stable output."""
        return sorted(self._policies.values(), key=lambda d: (d.category, d.section_id))

    def search_policies(self, query: str) -> list[PolicyDocument]:
        """Search policy repository by keyword relevance.

        Deliberately a scored keyword match rather than anything cleverer. The
        point of this register is determinism - the same question must return
        the same rule and the same citation on every call - and the semantic
        path already exists next door in `policy_rag`.
        """
        q_lower = query.lower()
        q_words = _content_words(q_lower)
        if not q_words:
            return []

        candidates = []
        for section_id in self._policies:
            score = self._score(section_id, q_lower, q_words)
            if score < _RELEVANCE_FLOOR:
                continue
            coverage = self._vocabularies[section_id].covers(q_words)
            # Coverage multiplies the score rather than filtering on it. As a
            # filter it discarded candidates before they could be compared, and
            # comparison is where it does its real work: "time off in lieu"
            # beats unpaid leave 9.0 to 7.0 on raw overlap - a 1.29 near-tie
            # that reads as ambiguous - but 1.00 to 0.67 on coverage, which is
            # the fact that makes TOIL the answer and unpaid leave a bystander.
            candidates.append((score * coverage, coverage, section_id))

        # `section_id` breaks ties so that equal scores order the same way on
        # every run; a citation that moves between calls is the exact failure
        # this register exists to avoid.
        candidates.sort(key=lambda c: (-c[0], c[2]))
        if not candidates:
            return []
        if len(candidates) > 1 and candidates[0][0] < _DECISIVENESS_MARGIN * candidates[1][0]:
            return []
        if candidates[0][1] < _COVERAGE_FLOOR:
            return []

        return [self._policies[section_id] for _, _, section_id in candidates]

    def _score(self, section_id: str, q_lower: str, q_words: set[str]) -> float:
        """Field-weighted term overlap. Tags are curated, so a tag hit is strong."""
        vocab = self._vocabularies[section_id]
        # Both directions are checked: the `remote-work` tag should match the
        # word "remote", and a multi-word tag should match when quoted in full.
        score = 3.0 * len(vocab.tags & q_words)
        score += 3.0 * sum(1 for phrase in vocab.tag_phrases if " " in phrase and phrase in q_lower)
        score += 2.0 * len(vocab.title & q_words)
        score += 1.5 * len(vocab.summary & q_words)
        return score + 1.0 * len(vocab.body & q_words)


# Global singleton OKF store
okf_store = OKFPolicyStore()
