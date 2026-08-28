"""Corpus loading: OKF frontmatter, handbook section splitting, ACL assignment."""

from __future__ import annotations

import pytest

from src.grounding.policy_rag.config import AclOverride, CorpusConfig
from src.grounding.policy_rag.loaders import (
    load_corpus,
    load_handbook_corpus,
    load_okf_corpus,
    split_frontmatter,
)


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


# --- frontmatter that is not what it claims to be ----------------------------


def test_unparseable_frontmatter_degrades_to_bare_markdown():
    """A YAML typo in one policy file must not take the whole ingest down. The
    document still loads; it simply arrives without its declared metadata."""
    text = "---\ntitle: [unclosed\n---\n\n# Vacation\n\ntext\n"

    meta, body = split_frontmatter(text)

    assert meta == {}
    assert body == text


def test_a_frontmatter_block_that_is_not_a_mapping_is_ignored():
    text = "---\n- just\n- a list\n---\n\n# Vacation\n"

    meta, body = split_frontmatter(text)

    assert meta == {}
    assert body == text


def test_an_empty_frontmatter_block_yields_no_metadata():
    meta, body = split_frontmatter("---\n\n---\n# Vacation\n")

    assert meta == {}
    assert body == "# Vacation\n"


# --- OKF bundle edge cases ----------------------------------------------------


def _okf(tmp_path, **overrides) -> CorpusConfig:
    fields = {
        "id": "okf-test",
        "kind": "okf",
        "authority": "governing",
        "default_search": True,
        "root": "bundle",
    }
    fields.update(overrides)
    return CorpusConfig(**fields)


def test_an_okf_corpus_without_a_root_is_a_configuration_error(tmp_path):
    with pytest.raises(ValueError, match="needs a `root`"):
        load_okf_corpus(_okf(tmp_path, root=None), tmp_path)


def test_a_missing_okf_root_is_reported_rather_than_loading_nothing(tmp_path):
    """An empty result would read as "this corpus has no policies", and the
    index would build and publish without them."""
    with pytest.raises(FileNotFoundError, match="OKF corpus root not found"):
        load_okf_corpus(_okf(tmp_path), tmp_path)


def test_a_document_with_no_frontmatter_title_falls_back_to_its_first_heading(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "vacation.md").write_text("# Paid Vacation Leave\n\nBody text.\n", encoding="utf-8")

    documents = load_okf_corpus(_okf(tmp_path), tmp_path)

    assert documents[0].title == "Paid Vacation Leave"
    assert documents[0].doc_type == "nav"


def test_a_document_with_neither_title_nor_heading_falls_back_to_its_filename(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "vacation.md").write_text("Just body text, no heading.\n", encoding="utf-8")

    assert load_okf_corpus(_okf(tmp_path), tmp_path)[0].title == "vacation"


def test_frontmatter_sources_that_are_not_well_formed_are_skipped(tmp_path):
    """A source ref without an id cannot be cited, so keeping it would put an
    unresolvable reference into an answer's **Sources** block."""
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "vacation.md").write_text(
        "---\n"
        "type: HR policy\n"
        "title: Vacation\n"
        "sources:\n"
        "  - not-a-mapping\n"
        "  - title: An entry with no id\n"
        "  - id: hb-20\n"
        "    title: Handbook Section 20\n"
        "    resource: handbook.md\n"
        "---\n\nBody.\n",
        encoding="utf-8",
    )

    sources = load_okf_corpus(_okf(tmp_path), tmp_path)[0].sources

    assert [s.id for s in sources] == ["hb-20"]


def test_frontmatter_sources_that_are_not_a_list_are_ignored(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "vacation.md").write_text(
        "---\ntype: HR policy\ntitle: Vacation\nsources: handbook.md\n---\n\nBody.\n",
        encoding="utf-8",
    )

    assert load_okf_corpus(_okf(tmp_path), tmp_path)[0].sources == []


def test_a_source_ref_defaults_its_title_to_its_own_id(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    (root / "vacation.md").write_text(
        "---\ntype: HR policy\ntitle: Vacation\nsources:\n  - id: hb-20\n---\n\nBody.\n",
        encoding="utf-8",
    )

    source = load_okf_corpus(_okf(tmp_path), tmp_path)[0].sources[0]
    assert source.title == "hb-20"
    assert source.resource == ""


def test_files_the_bundle_does_not_declare_are_left_alone(tmp_path):
    """Only `.md` and `.py` are policy-bearing; a stray asset is not indexed."""
    root = tmp_path / "bundle"
    (root / "sub").mkdir(parents=True)
    (root / "notes.txt").write_text("scratch", encoding="utf-8")
    (root / "diagram.png").write_bytes(b"\x89PNG")
    (root / "sub" / "attester.py").write_text("VALUE = 1\n", encoding="utf-8")

    documents = load_okf_corpus(_okf(tmp_path), tmp_path)

    assert [d.doc_type for d in documents] == ["code"]
    assert documents[0].title == "Source file: attester.py"


def test_an_acl_override_applies_to_the_path_it_names(tmp_path):
    root = tmp_path / "bundle"
    (root / "references").mkdir(parents=True)
    (root / "references" / "defects.md").write_text("# Defects\n", encoding="utf-8")
    (root / "vacation.md").write_text("# Vacation\n", encoding="utf-8")

    documents = load_okf_corpus(
        _okf(
            tmp_path,
            acl_overrides=[AclOverride(path_prefix="references/", entitlement="hr_operational")],
        ),
        tmp_path,
    )

    by_name = {d.path.rsplit("/", 1)[-1]: d.entitlement for d in documents}
    assert by_name == {"defects.md": "hr_operational", "vacation.md": "general"}


# --- handbook edge cases ------------------------------------------------------


def _handbook(**overrides) -> CorpusConfig:
    fields = {
        "id": "handbook-test",
        "kind": "handbook",
        "authority": "source",
        "default_search": True,
        "path": "handbook.md",
    }
    fields.update(overrides)
    return CorpusConfig(**fields)


def test_a_handbook_corpus_without_a_path_is_a_configuration_error(tmp_path):
    with pytest.raises(ValueError, match="needs a `path`"):
        load_handbook_corpus(_handbook(path=None), tmp_path)


def test_a_missing_handbook_file_is_reported(tmp_path):
    with pytest.raises(FileNotFoundError, match="handbook not found"):
        load_handbook_corpus(_handbook(), tmp_path)


def test_a_handbook_with_no_preamble_produces_no_front_matter_document(tmp_path):
    """The flush before the first SECTION has an empty buffer; emitting a
    document for it would put a titleless empty section into the index."""
    (tmp_path / "handbook.md").write_text(
        "**SECTION 1: Vacation Leave**\n\nFourteen days.\n", encoding="utf-8"
    )

    documents = load_handbook_corpus(_handbook(), tmp_path)

    assert [d.title for d in documents] == ["Handbook Section 1: Vacation Leave"]
    assert documents[0].extra["section"] == "1"


def test_a_section_containing_only_blank_lines_is_dropped(tmp_path):
    (tmp_path / "handbook.md").write_text(
        "**SECTION 1: Reserved**\n\n   \n\n**SECTION 2: Vacation Leave**\n\nFourteen days.\n",
        encoding="utf-8",
    )

    documents = load_handbook_corpus(_handbook(), tmp_path)

    assert [d.title for d in documents] == ["Handbook Section 2: Vacation Leave"]


def test_text_before_the_first_section_becomes_the_front_matter_document(tmp_path):
    (tmp_path / "handbook.md").write_text(
        "Last updated 2026-07-01.\n\n**SECTION 1: Vacation Leave**\n\nFourteen days.\n",
        encoding="utf-8",
    )

    documents = load_handbook_corpus(_handbook(), tmp_path)

    assert documents[0].title == "Handbook Front matter"
    assert documents[0].extra["section"] is None


def test_an_unknown_corpus_kind_is_refused(tmp_path):
    """The dispatcher is exhaustive by design - a typo in `corpus.yaml` must not
    silently contribute zero documents to the index."""
    with pytest.raises(ValueError, match="unknown corpus kind: 'notion'"):
        load_corpus(_handbook(kind="notion"), tmp_path)
