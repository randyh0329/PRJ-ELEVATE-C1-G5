"""Heading-aware chunking, footnote handling and chunk-id stability."""

from __future__ import annotations

import pytest

from src.grounding.policy_rag.chunking import chunk_document, slugify
from src.grounding.policy_rag.config import ChunkingConfig
from src.grounding.policy_rag.documents import Document, SourceRef


def _doc(body: str, doc_type: str = "policy", **overrides) -> Document:
    base = {
        "doc_id": "doc-1",
        "corpus_id": "okf-handbook",
        "path": "okf/altostrat-sg-handbook/leave/vacation.md",
        "title": "Vacation Leave",
        "doc_type": doc_type,
        "authority": "governing",
        "entitlement": "general",
        "body": body,
    }
    base.update(overrides)
    return Document(**base)


CFG = ChunkingConfig(max_chars=400, overlap_chars=40, min_chars=20)


def test_sections_split_on_atx_headings():
    chunks = chunk_document(_doc("# Accrual\n\nA" * 1 + "\n\n# Booking\n\nBook in Workday well ahead.\n"), CFG)
    trails = [c.heading_trail for c in chunks]
    assert "Booking" in trails


def test_heading_path_nests():
    body = "# Accrual\n\nAccrual body text that is long enough to survive min_chars.\n\n## Proration\n\nProrated for part-year joiners, rounded up.\n"
    chunks = chunk_document(_doc(body), CFG)
    nested = next(c for c in chunks if c.heading_path[-1] == "Proration")
    assert nested.heading_path == ["Accrual", "Proration"]
    assert nested.anchor == "proration"


def test_handbook_bold_pseudo_headings_are_headings():
    body = "**20.1 Eligibility** All confirmed employees qualify for the full annual allowance.\n\n**20.1.1 Interns** Interns accrue on a pro-rata basis only.\n"
    chunks = chunk_document(_doc(body, doc_type="handbook"), CFG)
    trails = [c.heading_path for c in chunks]
    assert ["20.1 Eligibility"] in trails
    # `20.1.1` is one level deeper than `20.1`.
    assert ["20.1 Eligibility", "20.1.1 Interns"] in trails


def test_bold_heading_trailing_text_is_not_lost():
    body = "**20.1 Eligibility** All confirmed employees qualify for the full annual allowance.\n"
    chunk = chunk_document(_doc(body, doc_type="handbook"), CFG)[0]
    assert "All confirmed employees qualify" in chunk.text


def test_footnote_definitions_are_stripped_but_sources_survive():
    body = (
        "# Accrual\n\nEmployees accrue fourteen days of paid vacation each year.[^hb-20]\n\n"
        "[^hb-20]: Handbook Section 20 - Vacation Leave\n"
    )
    document = _doc(body)
    document.sources = [
        SourceRef(id="hb-20", title="Handbook Section 20", resource="https://example/hb#20"),
        SourceRef(id="hb-1-2", title="Handbook Section 1.2", resource="https://example/hb#1.2"),
    ]
    chunk = chunk_document(document, CFG)[0]
    assert "[^hb-20]: Handbook Section 20" not in chunk.text
    # Only the footnote actually cited in this chunk is carried on it.
    assert [s.id for s in chunk.sources] == ["hb-20"]


def test_oversized_section_splits_with_overlap():
    paragraph = "Vacation accrues monthly and is credited on the first of the month. " * 12
    chunks = chunk_document(_doc(f"# Accrual\n\n{paragraph}\n"), CFG)
    assert len(chunks) > 1
    assert all(len(c.text) <= CFG.max_chars for c in chunks)
    assert all(c.heading_path == ["Accrual"] for c in chunks)


def test_conflict_and_gap_headings_are_flagged():
    body = (
        "# Accrual\n\nEmployees accrue fourteen days of paid vacation each year.\n\n"
        "# Conflict: which section governs\n\nSections 1.2 and 20 disagree on the figure.\n\n"
        "# Gaps in the source\n\nThe handbook does not say how part-days are rounded.\n"
    )
    chunks = chunk_document(_doc(body), CFG)
    by_trail = {c.heading_trail: c for c in chunks}
    assert by_trail["Conflict: which section governs"].is_conflict
    assert by_trail["Gaps in the source"].is_gap
    assert not by_trail["Accrual"].is_conflict


def test_chunk_ids_are_stable_and_unique():
    body = "# Accrual\n\nEmployees accrue fourteen days of paid vacation each year.\n\n# Booking\n\nBook leave in Workday ahead of time.\n"
    first = chunk_document(_doc(body), CFG)
    second = chunk_document(_doc(body), CFG)
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
    assert len({c.chunk_id for c in first}) == len(first)


def test_chunk_ids_differ_across_documents_sharing_a_path():
    """The handbook loader emits many documents from one path (see test_loaders)."""
    body = "# Accrual\n\nEmployees accrue fourteen days of paid vacation each year.\n"
    a = chunk_document(_doc(body, doc_id="section-20"), CFG)
    b = chunk_document(_doc(body, doc_id="section-21"), CFG)
    assert a[0].chunk_id != b[0].chunk_id


def test_embedding_text_prepends_context():
    chunk = chunk_document(_doc("# Accrual\n\nUnused days carry over for one additional year.\n"), CFG)[0]
    assert chunk.embedding_text().startswith("Vacation Leave - Accrual")


def test_vector_id_is_positive_and_deterministic():
    chunk = chunk_document(_doc("# Accrual\n\nUnused days carry over for one additional year.\n"), CFG)[0]
    assert 0 < chunk.vector_id < 2**63


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Carryover and payout", "carryover-and-payout"),
        ("Conflict: which section governs?", "conflict-which-section-governs"),
        ("20.1 Eligibility", "201-eligibility"),
    ],
)
def test_slugify_matches_github_anchors(text, expected):
    assert slugify(text) == expected


def test_real_corpus_produces_no_duplicate_ids(chunks):
    assert len({c.chunk_id for c in chunks}) == len(chunks)
