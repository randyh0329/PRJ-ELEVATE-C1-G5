"""The OKF register: how it loads the bundle, and how it quotes from it.

`test_runtime_primitives.py` pins what the register *says* - the handbook's real
figures against the four wrong ones it replaced. This module pins the machinery
underneath: what happens to a concept file that cannot be read, a bundle that is
not there, a document with no handbook section number, and a question the
register must decline rather than answer.

The loader's failure modes are worth their own tests because every one of them
has a tempting wrong answer. A missing bundle could return placeholders; an
unreadable file could abort the load; a concept with no `Section N` in its
sources could be dropped. Each of those trades a visible refusal for an
invisible gap, and an invisible gap in a policy register is quoted as policy.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.grounding.okf_store import (
    OKFPolicyStore,
    PolicyDocument,
    _blocks,
    _document_from_file,
    _first_source_url,
    _sections_from_sources,
    okf_store,
)

CONCEPT = """---
type: hr policy
title: Widget Allowance
description: What the company pays for widgets.
tags: [workplace, widgets, widget allowance]
status: draft
stale_after: 2027-01-01
sources:
  - title: "Handbook Section 42: Widgets"
    resource: "https://example.test/handbook#s42"
  - title: "Handbook Section 7.9: Widgets, summarised"
---

# Entitlement

* **Widget allowance:** staff with an approved 'Remote' or 'Hybrid' location
  status may claim **US$40 per widget**.[^hb-42]

# Conflict

Section 7.9 says US$45. Unresolved.

[^hb-42]: Handbook Section 42
"""


@pytest.fixture
def bundle(tmp_path: Path) -> Path:
    root = tmp_path / "okf" / "bundle"
    (root / "workplace").mkdir(parents=True)
    (root / "workplace" / "widgets.md").write_text(CONCEPT, encoding="utf-8")
    return root


# --- loading ------------------------------------------------------------------


def test_a_concept_becomes_a_document_with_its_metadata_intact(bundle: Path):
    doc = OKFPolicyStore(bundle).get_policy_by_section("42")

    assert doc is not None
    assert doc.title == "Widget Allowance"
    assert doc.category == "WORKPLACE"
    assert doc.status == "draft"
    assert doc.stale_after == "2027-01-01"
    assert doc.source_url == "https://example.test/handbook#s42"
    assert doc.has_conflict is True
    assert doc.citation_title == "Widget Allowance - Handbook Section 42"


def test_footnotes_are_stripped_from_the_quotable_body(bundle: Path):
    """They label provenance for a corpus reader and read as noise to an employee."""
    details = OKFPolicyStore(bundle).get_policy_by_section("42").details

    assert "[^hb-42]" not in details
    assert "US$40 per widget" in details


def test_a_summary_layer_section_is_registered_as_an_alias(bundle: Path):
    store = OKFPolicyStore(bundle)

    assert store.get_policy_by_section("7.9") is store.get_policy_by_section("42")


def test_a_concept_the_register_cannot_answer_from_is_not_loaded(bundle: Path):
    """Only `hr policy` and `orientation` concepts are answerable. A computation
    or reference note is corpus scaffolding and must not be quoted as a rule."""
    (bundle / "workplace" / "note.md").write_text(
        "---\ntype: reference\ntitle: Notes\n---\n\nScaffolding.\n", encoding="utf-8"
    )

    assert len(OKFPolicyStore(bundle).all_policies()) == 1


def test_a_concept_without_a_handbook_section_is_keyed_on_its_slug(bundle: Path):
    """No section number is not a reason to lose a real policy."""
    (bundle / "workplace" / "gizmos.md").write_text(
        "---\ntype: hr policy\ntitle: Gizmos\n---\n\nGizmos are provided.\n", encoding="utf-8"
    )

    doc = OKFPolicyStore(bundle).get_policy_by_section("gizmos")

    assert doc is not None
    # Nothing to link to a section, so the citation is just the title.
    assert doc.citation_title == "Gizmos"


def test_an_unreadable_concept_is_skipped_rather_than_aborting_the_load(bundle: Path, caplog):
    """One bad file must not empty the register: the other 30 policies are fine,
    and a store that raises here takes the whole agent down with it."""
    broken = bundle / "workplace" / "broken.md"
    broken.mkdir()  # a directory named `*.md` - `read_text` raises OSError

    with caplog.at_level(logging.WARNING):
        store = OKFPolicyStore(bundle)

    assert len(store.all_policies()) == 1
    assert "unreadable concept file" in caplog.text


def test_a_missing_bundle_yields_an_empty_register_and_an_error(tmp_path: Path, caplog):
    """Empty beats invented. Every caller of an empty register refuses, which is
    true; a caller handed placeholder documents would quote them as entitlements."""
    with caplog.at_level(logging.ERROR):
        store = OKFPolicyStore(tmp_path / "nowhere")

    assert store.all_policies() == []
    assert store.search_policies("widget allowance") == []
    assert "OKF bundle not found" in caplog.text


def test_two_concepts_naming_one_section_both_survive(bundle: Path):
    """The bundle really does this - onboarding and performance-and-discipline
    both cite Section 30. The first loader dropped the loser and reported a
    healthy count, which removed a whole policy without reporting a fault."""
    (bundle / "workplace" / "widgets-b.md").write_text(
        CONCEPT.replace("Widget Allowance", "Widget Disposal"), encoding="utf-8"
    )

    store = OKFPolicyStore(bundle)

    # `widgets-b.md` sorts first, so it takes Section 42 and the incumbent is
    # re-keyed on its slug. Which one wins does not matter; that neither
    # disappears does.
    assert len(store.all_policies()) == 2
    assert store.get_policy_by_section("42").title == "Widget Disposal"
    assert store.get_policy_by_section("widgets").title == "Widget Allowance"


# --- lookup and search --------------------------------------------------------


def test_a_document_is_retrievable_by_its_repo_relative_path(bundle: Path):
    """Retrieval reports chunk paths, so the register has to accept one."""
    store = OKFPolicyStore(bundle)
    path = store.get_policy_by_section("42").path

    assert store.get_policy_by_path(path).section_id == "42"
    assert store.get_policy_by_path("/" + path).section_id == "42"
    assert store.get_policy_by_path("okf/nope.md") is None


def test_a_query_of_nothing_but_stopwords_matches_nothing(bundle: Path):
    """"what is the policy" carries no topic. Scoring it would rank on noise."""
    assert OKFPolicyStore(bundle).search_policies("what is the policy") == []


def test_a_document_added_by_a_caller_is_searchable_immediately(tmp_path: Path):
    """`add_policy` has to build the vocabulary too, or the document is
    retrievable by section and invisible to search - a split that reads as a
    corpus gap rather than as a bug."""
    store = OKFPolicyStore(tmp_path / "empty")
    store.add_policy(
        PolicyDocument(
            section_id="99.1",
            title="Kite Flying Allowance",
            category="WORKPLACE",
            summary="Kite flying during core hours.",
            details="Kite flying is permitted on the roof terrace.",
            citation_title="Kite Flying Allowance - Handbook Section 99.1",
            citation_url="https://example.test/kites.md",
            tags=["kite", "kite flying"],
        )
    )

    assert [d.section_id for d in store.search_policies("kite flying allowance")] == ["99.1"]


# --- quoting one rule out of a long document ----------------------------------


def test_an_excerpt_rejoins_a_bullet_wrapped_across_lines(bundle: Path):
    """Concept files are hard-wrapped, so the keyword and the figure routinely
    land on different physical lines. Matching per line would conclude the
    document states no widget allowance while quoting one."""
    doc = OKFPolicyStore(bundle).get_policy_by_section("42")

    quote = doc.excerpt("widget allowance", "US$")

    assert quote == (
        "* **Widget allowance:** staff with an approved 'Remote' or 'Hybrid' location "
        "status may claim **US$40 per widget**."
    )


def test_an_excerpt_is_none_when_no_single_block_carries_every_keyword(bundle: Path):
    """The keywords appear in the document, just not together - and a caller
    that treated that as a match would quote an unrelated sentence as the rule."""
    doc = OKFPolicyStore(bundle).get_policy_by_section("42")

    assert doc.excerpt("widget allowance", "US$45") is None
    assert doc.excerpt("bereavement") is None


def test_blocks_joins_indented_continuations_and_nothing_else():
    """Indentation is the bundle's wrap convention, so it is the only thing that
    marks a continuation. Two unindented lines are two blocks even when they read
    as one sentence - joining those would let a keyword on the first line pair
    with a figure from an unrelated rule on the second."""
    details = "# Heading\n\n* one\n  wrapped\n* two\n\n| a | b |\nnot a continuation\n"

    assert _blocks(details) == [
        "# Heading",
        "* one wrapped",
        "* two",
        "| a | b |",
        "not a continuation",
    ]


def test_citation_markdown_is_a_link_to_the_cited_file(bundle: Path):
    doc = OKFPolicyStore(bundle).get_policy_by_section("42")

    assert doc.citation_markdown == f"[{doc.citation_title}]({doc.citation_url})"
    assert doc.citation_url.endswith("okf/bundle/workplace/widgets.md") or doc.path in doc.citation_url


# --- frontmatter that is not shaped the way the bundle promises ---------------


@pytest.mark.parametrize("sources", [None, "Handbook Section 42", [], ["bare string"], [{}]])
def test_malformed_sources_degrade_to_no_section_and_no_url(sources):
    """The frontmatter is hand-maintained. A `sources:` block that is a string,
    or a list of strings, must leave the concept usable rather than raise."""
    assert _sections_from_sources(sources) == []
    assert _first_source_url(sources) == ""


def test_a_repeated_section_number_is_listed_once():
    sources = [
        {"title": "Handbook Section 42: Widgets"},
        {"title": "Handbook Section 42: Widgets again"},
        {"title": "Handbook Section 7.9: Summary"},
    ]

    assert _sections_from_sources(sources) == ["42", "7.9"]


def test_a_file_outside_the_answerable_types_parses_to_nothing(tmp_path: Path):
    path = tmp_path / "c.md"
    path.write_text("---\ntype: computation\ntitle: Sums\n---\n\nx\n", encoding="utf-8")

    assert _document_from_file(path, tmp_path) is None


def test_a_trailing_block_with_no_newline_after_it_is_still_emitted():
    """Concept files usually end with a newline. One that does not must not lose
    its last rule - which is where a figure is as likely to be as anywhere."""
    assert _blocks("* only\n  wrapped") == ["* only wrapped"]
    assert _blocks("* only\n\n") == ["* only"]
    assert _blocks("") == []


# --- the two ways the register declines ---------------------------------------
#
# They are not redundant, and the real corpus is the only place to tell them
# apart: a bait question can be the *only* candidate, in which case the margin
# is maximal and coverage is the sole thing standing between the employee and a
# confident wrong entitlement.


def test_a_lone_off_topic_candidate_is_refused_on_coverage():
    """"corporate card" really is in Travel & Expense, so this scores - and it is
    the only document that does, so the decisiveness margin is no help at all.
    Two thirds of the question is about something the handbook never addresses,
    which is what the coverage floor is measuring."""
    assert okf_store.search_policies("can i buy bitcoin with the corporate card") == []


def test_a_near_tie_between_two_plausible_documents_is_refused_on_the_margin():
    """Both the expense policy and the pet-at-work policy have a claim on this,
    and neither has a good one. Returning whichever sorted first would present a
    coin-flip as a determinate answer."""
    assert okf_store.search_policies("reimbursement for personal pet helicopter transport") == []


def test_a_topical_query_that_scores_nothing_returns_nothing(bundle: Path):
    """Content words that appear in no document at all. Distinct from the
    stopword case: there is something to score here, and it scores zero."""
    assert OKFPolicyStore(bundle).search_policies("helicopter cryptocurrency yacht") == []


def test_a_draft_concept_is_answered_with_the_draft_caveat(bundle: Path):
    """OKF `status: draft` means the rules carry producer assumptions. Quoting
    them as settled policy is the thing the marker exists to prevent."""
    from src.core.agents.policy import PolicySpecialistNode

    doc = OKFPolicyStore(bundle).get_policy_by_section("42")

    assert "is a draft" in PolicySpecialistNode._compose(doc)


def test_a_settled_concept_is_answered_without_caveats(bundle: Path):
    """The caveats have to be *rare* to be read. A note on every answer is a
    banner, and a banner is furniture."""
    from src.core.agents.policy import PolicySpecialistNode

    (bundle / "workplace" / "clean.md").write_text(
        "---\ntype: hr policy\ntitle: Clean\ndescription: Settled.\n"
        'sources:\n  - title: "Handbook Section 50: Clean"\n---\n\nThe rule is settled.\n',
        encoding="utf-8",
    )

    composed = PolicySpecialistNode._compose(OKFPolicyStore(bundle).get_policy_by_section("50"))

    assert composed == "Settled.\n\nThe rule is settled."


def test_an_entitlement_rule_the_document_does_not_state_stops_the_saga():
    """Documents and a citation, but no block carrying the keywords. The caller
    must get `None` rather than a tuple quoting some other paragraph."""
    from src.core.agent import HREnterpriseAgent
    from src.grounding.policy_engine import PolicyQueryResult

    result = PolicyQueryResult(
        is_grounded=True,
        answer_text="...",
        citations=["[Fake](https://example.invalid/f.md)"],
        confidence_score=0.9,
        documents=[
            PolicyDocument(
                section_id="1",
                title="T",
                category="WORKPLACE",
                summary="s",
                details="* Nothing about allowances here.",
                citation_title="T",
                citation_url="https://example.invalid/f.md",
            )
        ],
    )

    assert HREnterpriseAgent._entitlement_rule(result, "relocation allowance") is None
