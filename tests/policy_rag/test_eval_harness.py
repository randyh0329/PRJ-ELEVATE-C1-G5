"""The two offline evaluation entry points.

`eval/run_policy_rag_eval.py` reports the numbers the BRD asks for and gates CI
on them; `scripts/eval_retrieval.py` derives the tuning constants in
`config/corpus.yaml` from the same golden set. Neither had any test, which is an
awkward place to be for the code that decides whether everything else is
working - a harness that silently miscounts reports a green build.

These run on the hermetic `hash` embedder, so retrieval quality is meaningless
here and none of it is asserted. What is asserted is the arithmetic, the
pass/fail classification, the CI exit codes and the admissibility constraint -
all of which are model-independent, and all of which are the parts that would
turn a real regression into a passing run.
"""

from __future__ import annotations

import json

import pytest

from eval import run_policy_rag_eval as harness
from scripts import eval_retrieval as sweeper


@pytest.fixture(autouse=True)
def _restore_retrieval_config(config):
    """Undo the sweep's in-place mutation of the session-scoped config.

    `sweeper.score` rewrites `service.retriever.config.retrieval` and does not
    put it back - deliberately, because the sweep evaluates hundreds of
    candidates against one loaded index and copying the service each time would
    reload the embedder. Harmless in the script, corrosive in a test session
    where that config object is shared, so the restore lives here.
    """
    before = vars(config.retrieval).copy()
    yield
    vars(config.retrieval).update(before)

# --- Outcome classification --------------------------------------------------


def test_rank_of_finds_the_first_expected_path():
    paths = ["okf/leave/sick.md", "okf/leave/vacation.md", "okf/pay/bonus.md"]
    assert harness._rank_of(["leave/vacation.md"], paths) == 2
    # Substring match, so a golden entry can name a directory.
    assert harness._rank_of(["okf/pay/"], paths) == 3


def test_rank_of_is_none_when_nothing_matches():
    assert harness._rank_of(["okf/travel.md"], ["okf/leave/sick.md"]) is None
    assert harness._rank_of(["okf/travel.md"], []) is None


@pytest.mark.parametrize(
    ("expect", "should_pass"),
    [("answer", True), ("escalate", False), ("refuse", False)],
)
def test_an_answered_question_only_passes_when_that_was_wanted(service, expect, should_pass):
    """The same retrieval is a pass or a failure depending on what was asked for.

    Refusal and escalation are not interchangeable: both withhold an answer, but
    escalating a question the corpus genuinely cannot answer sends a human a
    question they cannot answer either.
    """
    question = {
        "id": "t-1",
        "query": "how much vacation leave do I accrue",
        "expect": expect,
        "expect_paths": ["vacation.md"],
    }
    outcome = harness.evaluate_one(service, question, gate=0.0)

    assert outcome.action == "ANSWER"
    assert outcome.passed is should_pass
    assert (outcome.note == "") is should_pass


def test_a_refusal_is_scored_against_what_was_wanted(service):
    """Gate at 1.0: nothing can clear it, so the action is a refusal by construction."""
    refuse = harness.evaluate_one(
        service, {"id": "t-2", "query": "who won the 1998 world cup", "expect": "refuse"}, gate=1.0
    )
    assert refuse.passed
    assert refuse.rank is None

    wanted_answer = harness.evaluate_one(
        service,
        {"id": "t-3", "query": "vacation leave", "expect": "answer", "expect_paths": ["vacation.md"]},
        gate=1.0,
    )
    assert not wanted_answer.passed
    assert "rank=None" in wanted_answer.note


def test_an_unknown_expect_value_is_a_hard_error(service):
    """A typo in the golden file must not quietly score as a pass."""
    with pytest.raises(ValueError, match="unknown expect value 'anwser'"):
        harness.evaluate_one(service, {"id": "t-4", "query": "leave", "expect": "anwser"}, gate=0.0)


# --- Aggregation -------------------------------------------------------------


def _outcome(expect: str, passed: bool, rank: int | None) -> harness.Outcome:
    return harness.Outcome(
        question={"id": f"g-{expect}", "expect": expect, "query": "q"},
        action="ANSWER",
        hit_paths=[],
        best_relevance=0.5,
        rank=rank,
        passed=passed,
        note="" if passed else "note",
    )


def test_summarise_computes_the_reported_metrics():
    outcomes = [
        _outcome("answer", True, 1),
        _outcome("answer", True, 2),
        _outcome("answer", False, None),
        _outcome("escalate", True, None),
        _outcome("refuse", False, None),
    ]

    stats = harness.summarise(outcomes)

    assert stats == {
        "total": 5,
        "passed": 3,
        # One of three answerable questions came back at rank 1.
        "recall@1": pytest.approx(1 / 3),
        "recall@k": pytest.approx(2 / 3),
        "mrr": pytest.approx((1.0 + 0.5) / 3),
        "answer_accuracy": pytest.approx(2 / 3),
        "escalate_accuracy": 1.0,
        "refusal_accuracy": 0.0,
    }


def test_summarise_of_nothing_is_zero_not_a_crash():
    """Every rate divides by a count that can legitimately be empty."""
    stats = harness.summarise([])
    assert stats["total"] == 0
    assert stats["mrr"] == 0.0
    assert stats["answer_accuracy"] == 0.0
    assert stats["refusal_accuracy"] == 0.0


# --- CLI ---------------------------------------------------------------------


@pytest.fixture
def golden(tmp_path):
    """A two-question golden file: one answerable, one that must be refused."""
    path = tmp_path / "golden.json"
    path.write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "id": "g-answer",
                        "query": "how much vacation leave do I accrue",
                        "expect": "answer",
                        "expect_paths": ["vacation.md"],
                    },
                    {"id": "g-refuse", "query": "who won the 1998 world cup", "expect": "refuse"},
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def offline(monkeypatch, service):
    """Point both entry points at the hermetic in-memory service."""
    for module in (harness, sweeper):
        monkeypatch.setattr(
            module.PolicyRagService, "from_config", classmethod(lambda cls, *a, **k: service)
        )
    return service


def test_the_harness_prints_a_summary(offline, golden, capsys):
    assert harness.main(["--golden", str(golden), "--gate", "0.80"]) == 0

    out = capsys.readouterr().out
    assert "gate = 0.80" in out
    assert "refusal accuracy" in out


def test_show_failures_explains_each_failure(offline, golden, capsys):
    """A bare failure list names the case; --show-failures says why it failed."""
    assert harness.main(["--golden", str(golden), "--gate", "1.0", "--show-failures"]) == 0

    out = capsys.readouterr().out
    assert "g-answer" in out
    assert "best_relevance=" in out
    assert "q: how much vacation leave do I accrue" in out


def test_show_failures_lists_what_was_wrongly_retrieved(offline, golden, monkeypatch, capsys):
    """The other failure direction: the gate let something through that it should not.

    Diagnosing an over-answer needs the paths that cleared the gate, which is
    the half of --show-failures a refusal case never reaches.
    """
    # The corroboration rule would withhold the out-of-domain question on its
    # own, and then there would be no over-answer to diagnose.
    monkeypatch.setattr(offline.retriever.config.retrieval, "min_lexical_corroboration", 0.0)

    assert harness.main(["--golden", str(golden), "--gate", "0.0", "--show-failures"]) == 0

    out = capsys.readouterr().out
    assert "g-refuse" in out
    assert ".md" in out


def test_json_output_is_machine_readable(offline, golden, capsys):
    assert harness.main(["--golden", str(golden), "--json", "--gate", "0.80"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["gate"] == 0.80
    assert {o["id"] for o in payload["outcomes"]} == {"g-answer", "g-refuse"}
    assert payload["summary"]["total"] == 2


def test_sweep_reports_every_gate_and_names_a_best(offline, golden, capsys):
    assert harness.main(["--golden", str(golden), "--sweep"]) == 0

    out = capsys.readouterr().out
    assert " 0.40 " in out
    assert " 0.95 " in out
    assert "best overall pass rate at gate" in out


def test_min_pass_rate_gates_ci(offline, golden, capsys):
    """The flag exists so a CI job fails on a retrieval regression."""
    # Gate at 1.0 refuses everything, so the answerable question fails.
    assert harness.main(["--golden", str(golden), "--gate", "1.0", "--min-pass-rate", "1.0"]) == 1
    assert "below required" in capsys.readouterr().err

    assert harness.main(["--golden", str(golden), "--gate", "1.0", "--min-pass-rate", "0.5"]) == 0


# --- The calibration sweep ---------------------------------------------------


def _candidate(floor=0.50, ceiling=0.70, boost=0.25, link=0.35, minlex=0.12) -> sweeper.Candidate:
    return sweeper.Candidate(floor, ceiling, boost, link, minlex)


def test_the_gate_is_not_swept():
    """SDD §3.3 fixes it. A sweep that moves it answers a different question."""
    assert sweeper.SDD_RELEVANCE_GATE == 0.80


def test_the_grid_rejects_spans_too_narrow_to_discriminate():
    grid = sweeper._grid([0.50], [0.52, 0.60], [0.25], [0.35], [0.12])
    # 0.52 - 0.50 = 0.02 makes calibration a step function; 0.60 - 0.50 does not.
    assert [c.cosine_ceiling for c in grid] == [0.60]


def test_the_grid_is_the_full_product_of_the_five_dimensions():
    grid = sweeper._grid([0.50], [0.70, 0.72], [0.25, 0.35], [0.35, 1.01], [0.0, 0.12])
    assert len(grid) == 2 * 2 * 2 * 2
    assert len(set(grid)) == len(grid)


def test_a_candidate_prints_all_five_constants():
    assert str(_candidate()) == "floor=0.50 ceiling=0.70 boost=0.25 link<0.35 minlex=0.12"


def test_scoring_a_candidate_applies_it_to_the_live_retriever(offline):
    """`score` mutates the service in place - the sweep depends on that sticking."""
    candidate = _candidate(floor=0.31, ceiling=0.61, boost=0.29, link=0.41, minlex=0.11)
    questions = [{"id": "q", "query": "vacation leave", "expect": "refuse"}]

    stats = sweeper.score(offline, questions, candidate)

    retrieval = offline.retriever.config.retrieval
    assert retrieval.cosine_floor == 0.31
    assert retrieval.cosine_ceiling == 0.61
    assert retrieval.lexical_boost == 0.29
    assert retrieval.max_link_density == 0.41
    assert retrieval.min_lexical_corroboration == 0.11
    assert stats["total"] == 1


def test_admissibility_is_the_constraint_not_the_objective():
    """A configuration that starts answering unanswerable questions is not a fix."""
    assert sweeper.admissible({"refusal_accuracy": 1.0, "escalate_accuracy": 1.0})
    assert not sweeper.admissible({"refusal_accuracy": 0.99, "escalate_accuracy": 1.0})
    assert not sweeper.admissible({"refusal_accuracy": 1.0, "escalate_accuracy": 0.5})


def test_an_absent_category_is_not_a_failed_one():
    """`summarise` scores an empty category 0.0, which here would mean the wrong thing.

    A golden subset with no escalation questions must not be reported as
    inadmissible at every setting - that makes the sweep blame the corpus for a
    gap in the question set.
    """
    stats = {"refusal_accuracy": 1.0, "escalate_accuracy": 0.0}
    assert not sweeper.admissible(stats)
    assert sweeper.admissible(stats, has_escalations=False)


def test_a_question_set_with_no_negatives_says_so(offline, tmp_path, capsys):
    golden = tmp_path / "positives-only.json"
    golden.write_text(
        json.dumps(
            {"questions": [{"id": "g-a", "query": "vacation leave", "expect": "answer"}]}
        ),
        encoding="utf-8",
    )

    code = sweeper.main(
        [
            "--golden", str(golden), "--sweep",
            "--floors", "0.50", "--ceilings", "0.70", "--boosts", "0.25",
            "--link-densities", "0.35", "--min-lexicals", "0.12",
        ]
    )

    assert code == 0
    assert "the sweep is unconstrained" in capsys.readouterr().out


def test_ranking_prefers_accuracy_then_mrr_then_the_least_aggressive_config():
    def row(candidate, accuracy=1.0, mrr=0.9):
        return {"candidate": candidate, "answer_accuracy": accuracy, "mrr": mrr}

    accurate = row(_candidate(), accuracy=1.0)
    inaccurate = row(_candidate(floor=0.40), accuracy=0.5, mrr=1.0)
    assert sweeper.rank_key(accurate) > sweeper.rank_key(inaccurate)

    # Equal accuracy and MRR: the narrower calibration span wins.
    narrow = row(_candidate(floor=0.55, ceiling=0.70))
    wide = row(_candidate(floor=0.40, ceiling=0.70))
    assert sweeper.rank_key(narrow) > sweeper.rank_key(wide)

    # Equal again: prefer the weaker admissibility rules, so a rule only stays
    # tight where the measurement required it.
    permissive = row(_candidate(link=0.50, minlex=0.05))
    strict = row(_candidate(link=0.20, minlex=0.30))
    assert sweeper.rank_key(permissive) > sweeper.rank_key(strict)


def test_the_sweeper_reports_the_current_configuration_by_default(offline, golden, capsys):
    assert sweeper.main(["--golden", str(golden)]) == 0

    out = capsys.readouterr().out
    assert "current calibration:" in out
    assert "link<" in out


def test_the_sweeper_emits_a_pastable_yaml_block(offline, golden, capsys):
    # `min_lexicals 0.9` is what makes the refusal hold under the hash embedder,
    # whose scores carry no semantics: an out-of-domain question shares no
    # vocabulary with any chunk, so the corroboration rule withholds it whatever
    # the dense score happens to be.
    code = sweeper.main(
        [
            "--golden", str(golden), "--sweep", "--apply", "--json",
            "--floors", "0.50", "--ceilings", "0.70", "--boosts", "0.25",
            "--link-densities", "0.35", "--min-lexicals", "0.9",
        ]
    )
    assert code == 0

    out = capsys.readouterr().out
    assert "best admissible:" in out
    assert "# config/corpus.yaml -> retrieval:" in out
    assert "  max_link_density: 0.35" in out
    assert "    cosine_ceiling: 0.7" in out

    payload = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert payload["gate"] == sweeper.SDD_RELEVANCE_GATE
    assert payload["min_lexical_corroboration"] == 0.9


def test_the_sweeper_fails_rather_than_recommending_an_inadmissible_config(
    offline, tmp_path, capsys
):
    """No admissible candidate means the corpus or the gate is the problem.

    Reported as a non-zero exit rather than a best-effort recommendation: the
    one thing this tool must never do is hand back a calibration that answers
    questions the corpus cannot answer.
    """
    golden = tmp_path / "impossible.json"
    # A question the corpus must refuse, at a calibration wide enough that
    # something will always clear the gate.
    golden.write_text(
        json.dumps({"questions": [{"id": "g-x", "query": "leave", "expect": "refuse"}]}),
        encoding="utf-8",
    )

    code = sweeper.main(
        [
            "--golden", str(golden), "--sweep",
            "--floors", "0.0", "--ceilings", "0.05", "--boosts", "0.9",
            "--link-densities", "1.01", "--min-lexicals", "0.0",
        ]
    )

    assert code == 1
    assert "no admissible calibration" in capsys.readouterr().out
