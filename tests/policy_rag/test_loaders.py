"""Corpus loading: OKF frontmatter, handbook section splitting, ACL assignment."""

from __future__ import annotations

from src.grounding.policy_rag.loaders import split_frontmatter


def test_split_frontmatter_parses_yaml_block():
    meta, body = split_frontmatter("---\ntype: HR policy\ntitle: Vacation\n---\n\n# Accrual\n\ntext\n")
    assert meta["type"] == "HR policy"
    assert meta["title"] == "Vacation"
    assert body.lstrip().startswith("# Accrual")


def test_split_frontmatter_tolerates_absent_block():
    meta, body = split_frontmatter("# Just a heading\n\ntext\n")
    assert meta == {}
    assert body.startswith("# Just a heading")


def test_okf_documents_carry_provenance(documents):
    vacation = next(d for d in documents if d.path.endswith("leave/vacation.md"))
    assert vacation.doc_type == "policy"
    assert vacation.authority == "governing"
    assert vacation.sources, "OKF concepts must carry sources[] frontmatter"
    assert all(s.id and s.resource for s in vacation.sources)


def test_handbook_splits_into_one_document_per_section(documents):
    handbook = [d for d in documents if d.corpus_id == "handbook-source"]
    assert len(handbook) > 20, "the handbook has ~35 numbered sections"
    # Plus one document for the applicability/last-updated preamble ahead of
    # Section 1, which the corpus datasheet cites as `hb-header`.
    assert sum(1 for d in handbook if d.title == "Handbook Front matter") == 1
    numbered = [d for d in handbook if d.title != "Handbook Front matter"]
    assert all(d.title.startswith("Handbook Section ") for d in numbered)
    # Every section document shares the one source path; the doc_id is what
    # distinguishes them, which is why chunk ids are keyed on doc_id.
    assert len({d.path for d in handbook}) == 1
    assert len({d.doc_id for d in handbook}) == len(handbook)


def test_references_prefix_requires_hr_operational(documents):
    """SDD §4.7: the defect register is not general-employee material."""
    defects = next(d for d in documents if d.path.endswith("references/source-defects.md"))
    assert defects.entitlement == "hr_operational"

    vacation = next(d for d in documents if d.path.endswith("leave/vacation.md"))
    assert vacation.entitlement == "general"


def test_index_pages_are_nav_not_policy(documents):
    leave_index = next(d for d in documents if d.path.endswith("leave/index.md"))
    assert leave_index.doc_type == "nav"


def test_draft_status_is_preserved(documents):
    """The vacation computation is genuinely incomplete and must say so."""
    computation = next(d for d in documents if d.path.endswith("computations/vacation-entitlement.md"))
    assert computation.status == "draft"
