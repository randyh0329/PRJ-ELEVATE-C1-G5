"""The ADK golden-evalset runner.

The runner decides what "passing" means for every tier, so a mistake in it is
invisible: the report says PASS either way. These tests pin the classification
rules and the arithmetic in the report against a stub graph, which is also the
offline path around the live Vertex project the real run needs.

The four tiers are not scored the same way, and that is the point. Tiers 1, 2
and 4 pass when the system produced *an* answer. Tier 3 passes only when the
system produced a *refusal* - a fluent, confident, wrong answer to a question
with no answer in the corpus is the specific failure NFR-3.1 exists to prevent,
and it would score as a pass under any of the other three rules.
"""

from __future__ import annotations

import json

import pytest

from eval import run_eval_suite as suite


class StubGraph:
    """Returns a canned final state per prompt, recording what it was asked."""

    def __init__(self, responses: dict[str, dict] | None = None):
        self.responses = responses or {}
        self.seen: list[dict] = []

    async def invoke(self, state):
        self.seen.append(state)
        merged = dict(state)
        merged.update(self.responses.get(state["user_input"], {"final_response": "ok"}))
        return merged


def _state(**overrides) -> dict:
    base = {"route": "policy", "saga_ledger": [], "final_response": "here you go"}
    base.update(overrides)
    return base


# --- prompt resolution -------------------------------------------------------


def test_a_bare_prompt_is_used_directly():
    assert suite.resolve_prompt({"prompt": "how much leave"}) == "how much leave"


def test_an_adk_conversation_envelope_is_unwrapped():
    case = {
        "conversation": [{"user_content": {"parts": [{"text": "how much leave"}]}}]
    }
    assert suite.resolve_prompt(case) == "how much leave"


def test_a_case_with_neither_yields_an_empty_prompt():
    assert suite.resolve_prompt({}) == ""


# --- tool attribution --------------------------------------------------------


def test_recorded_saga_steps_are_the_executed_tools():
    class Step:
        action = "ww.submit_leave"

    assert suite.executed_tools(_state(saga_ledger=[Step(), Step()])) == [
        "ww.submit_leave",
        "ww.submit_leave",
    ]


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        ("policy", ["agent_search.query"]),
        ("hcm", ["ww.get_balances"]),
        ("itsm", ["si.get_incident"]),
    ],
)
def test_a_turn_with_no_ledger_is_attributed_to_its_route(route, expected):
    """A read-only lookup records no saga step but did call a tool."""
    assert suite.executed_tools(_state(route=route)) == expected


def test_a_contained_turn_is_credited_with_no_tools():
    """Domain containment (FR-5.4) means nothing downstream ran at all."""
    assert suite.executed_tools(_state(route="end")) == []


# --- tier classification -----------------------------------------------------


@pytest.mark.parametrize(
    ("eval_id", "state", "tier"),
    [
        ("probe_python_help", _state(), suite.PROBES),
        ("t_out_of_scope_1", _state(), suite.PROBES),
        ("t_boundary_2", _state(), suite.PROBES),
        # Inferred from the trajectory when the id says nothing.
        ("case_9", _state(route="end"), suite.PROBES),
        ("bait_unicorn_policy", _state(final_response="I could not find that"), suite.BAITS),
        ("t_hallucination_1", _state(final_response="I could not find that"), suite.BAITS),
        ("t_unsupported_2", _state(final_response="I could not find that"), suite.BAITS),
        ("gotcha_routing", _state(), suite.GOTCHAS),
        ("t_violation_1", _state(), suite.GOTCHAS),
        ("t_override_2", _state(), suite.GOTCHAS),
        ("case_3", _state(saga_ledger=[1, 2]), suite.GOTCHAS),
        ("t_leave_balance", _state(), suite.HAPPY_PATH),
    ],
)
def test_cases_land_in_the_right_tier(eval_id, state, tier):
    assert suite.classify(eval_id, state)[0] == tier


def test_a_probe_passes_by_being_answered_at_all():
    assert suite.classify("probe_x", _state(final_response="I only handle HR topics."))[1]


def test_an_unanswered_turn_fails_its_tier():
    assert not suite.classify("t_leave_balance", _state(final_response=None))[1]


def test_a_hallucination_bait_passes_only_on_a_refusal():
    """Tier 3 inverts the rule: an answer is the failure."""
    confident = suite.classify("bait_x", _state(final_response="You get 30 days of moon leave."))
    refusal = suite.classify("bait_x", _state(final_response="I could not find that policy."))
    portal = suite.classify("bait_x", _state(final_response="Please check the HR Portal."))

    assert not confident[1]
    assert refusal[1]
    assert portal[1]


def test_an_unanswered_bait_is_not_credited_as_a_refusal():
    """Regression: `.get("final_response", "")` returns None, not "", for a null.

    Silence is not a refusal, and the previous form raised AttributeError on the
    way to deciding that - so a single unanswered bait crashed the whole run.
    """
    tier, passed = suite.classify("bait_x", _state(final_response=None))
    assert tier == suite.BAITS
    assert not passed


# --- aggregation and rendering -----------------------------------------------


def _result(tier: str, passed: bool, eval_id: str = "t-1") -> dict:
    return {
        "eval_id": eval_id,
        "tier": tier,
        "prompt": "q",
        "route": "policy",
        "guardrail_verdict": "ALLOW",
        "grounding_score": 0.9,
        "executed_tools": ["agent_search.query"],
        "passed": passed,
        "response_snippet": "...",
    }


def test_tally_counts_every_tier_including_the_empty_ones():
    stats = suite.tally([_result(suite.HAPPY_PATH, True), _result(suite.HAPPY_PATH, False)])

    assert stats[suite.HAPPY_PATH] == {"total": 2, "passed": 1}
    # Present with zeroes rather than absent: the report indexes all four.
    assert stats[suite.BAITS] == {"total": 0, "passed": 0}


def test_the_report_states_the_real_pass_rate():
    results = [_result(suite.HAPPY_PATH, True, "a"), _result(suite.BAITS, False, "b")]

    report = suite.render_report(
        {"eval_set_id": "es-1", "name": "Golden"}, results, suite.tally(results), "TS"
    )

    assert "| **2** | **1** | **1** | **50.0%** |" in report
    assert "`TS`" in report
    assert "| 1 | `a` |" in report and "✅ PASS" in report
    assert "| 2 | `b` |" in report and "❌ FAIL" in report


def test_a_tier_with_no_cases_renders_zero_rather_than_dividing_by_zero():
    report = suite.render_report({"name": "Golden"}, [], suite.tally([]), "TS")
    assert "**0.0%**" in report
    assert "0.0%" in report


def test_a_contained_turn_renders_as_a_domain_gate():
    results = [{**_result(suite.PROBES, True), "executed_tools": []}]
    report = suite.render_report({"name": "G"}, results, suite.tally(results), "TS")
    assert "None (Domain Gate)" in report


# --- end to end --------------------------------------------------------------


@pytest.fixture
def evalset(tmp_path):
    path = tmp_path / "evalset.json"
    path.write_text(
        json.dumps(
            {
                "eval_set_id": "es-offline",
                "name": "Offline Golden",
                "eval_cases": [
                    {"eval_id": "t_leave_balance", "prompt": "how many leave days do I have"},
                    {"eval_id": "bait_moon_leave", "prompt": "how much moon leave do I get"},
                    {
                        "eval_id": "probe_python",
                        "prompt": "write me a python quicksort",
                        "session_input": {"user_id": "E7741903"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


async def test_the_suite_runs_offline_and_writes_its_report(evalset, tmp_path):
    """The whole point of taking `graph` as an argument: no live Vertex project."""
    graph = StubGraph(
        {
            "how much moon leave do I get": {"final_response": "I could not find that policy."},
            "write me a python quicksort": {"route": "end", "final_response": "HR topics only."},
        }
    )
    report_path = tmp_path / "nested" / "eval_report.md"

    summary = await suite.run_full_evaluation(evalset, report_path, graph=graph)

    assert summary["total"] == 3
    assert summary["passed"] == 3
    assert summary["pass_rate"] == 100.0
    # The parent directory did not exist; the runner is responsible for it.
    assert report_path.exists()
    assert "Offline Golden" in report_path.read_text(encoding="utf-8")


async def test_each_case_gets_a_distinct_seeded_state(evalset, tmp_path):
    graph = StubGraph()
    await suite.run_full_evaluation(evalset, tmp_path / "r.md", graph=graph)

    assert [s["turn_id"] for s in graph.seen] == ["turn-1", "turn-2", "turn-3"]
    assert graph.seen[0]["session_id"] == "sess-eval-t_leave_balance"
    # The employee id comes from the case when it names one, and falls back.
    assert graph.seen[0]["employee_id"] == "EMP-44210"
    assert graph.seen[2]["employee_id"] == "E7741903"


def test_the_cli_gates_ci_on_the_pass_rate(monkeypatch, evalset, tmp_path):
    """`--min-pass-rate` is what makes this runnable as a build step."""
    monkeypatch.setattr(suite, "AgentOrchestrationGraph", StubGraph)
    args = ["--evalset", str(evalset), "--out", str(tmp_path / "r.md")]

    # The bait case is answered rather than refused, so one of three fails.
    assert suite.main(args) == 0
    assert suite.main([*args, "--min-pass-rate", "50"]) == 0
    assert suite.main([*args, "--min-pass-rate", "100"]) == 1


def test_the_defaults_point_at_the_repo_evalset_and_report():
    assert suite.DEFAULT_EVALSET.name == "golden_mas_eval.evalset.json"
    assert suite.DEFAULT_EVALSET.exists()
    assert suite.DEFAULT_REPORT.parts[-3:] == ("artifacts", "docs", "eval_report.md")
