"""The `policy-rag` command line surface.

Every subcommand is exercised through `main(argv)` rather than a subprocess, so
the assertions can be about behaviour instead of about text on a pipe. The
service is the hermetic in-memory one; what is under test is the wiring - that
each subcommand reaches the right call with the right arguments, and that the
exit codes mean what a CI job would assume they mean.

`drift` is the one that matters most for exit codes: it returns 1 when the
corpus has moved on from the index, so a scheduled job can catch a stale index
before an employee gets an answer from a superseded policy.
"""

from __future__ import annotations

import json

import pytest

from src.grounding.policy_rag import cli


@pytest.fixture
def offline_cli(monkeypatch, service, config):
    """Point the CLI at the in-memory service and config, not at `var/index`."""
    monkeypatch.setattr(
        cli.PolicyRagService, "from_config", classmethod(lambda klass, *a, **k: service)
    )
    monkeypatch.setattr(cli, "load_config", lambda path=None: config)
    return service


# --- argument parsing --------------------------------------------------------


def test_a_subcommand_is_required(capsys):
    """Bare `policy-rag` must not silently default to anything destructive."""
    with pytest.raises(SystemExit) as exit_info:
        cli.build_parser().parse_args([])
    assert exit_info.value.code == 2


def test_repeatable_flags_accumulate():
    args = cli.build_parser().parse_args(
        ["search", "q", "--entitlement", "general", "--entitlement", "hr_operational",
         "--corpus", "okf-handbook"]
    )
    assert args.entitlements == ["general", "hr_operational"]
    assert args.corpora == ["okf-handbook"]


def test_unset_repeatable_flags_stay_none_rather_than_empty():
    """`None` means "use the config default"; `[]` would mean "search nothing"."""
    args = cli.build_parser().parse_args(["search", "q"])
    assert args.entitlements is None
    assert args.corpora is None


# --- search ------------------------------------------------------------------


@pytest.fixture
def open_gate(monkeypatch, config):
    """Drop the relevance gate to 0.

    The hash embedder produces no semantic signal, so nothing clears the real
    §3.3 gate of 0.80 and every rendering path below would go untested. What is
    under test here is the rendering, not the retrieval.
    """
    monkeypatch.setattr(config.retrieval, "relevance_gate", 0.0)
    monkeypatch.setattr(config.retrieval, "min_lexical_corroboration", 0.0)


def test_search_prints_each_hit_with_its_scores(offline_cli, open_gate, capsys):
    assert cli.main(["search", "vacation leave accrual", "--top-k", "3"]) == 0

    out = capsys.readouterr().out
    assert "query      : vacation leave accrual" in out
    assert "dense" in out and "lexical" in out


def test_search_says_so_when_nothing_clears_the_gate(offline_cli, monkeypatch, config, capsys):
    monkeypatch.setattr(config.retrieval, "relevance_gate", 1.01)

    assert cli.main(["search", "who won the 1998 world cup"]) == 0
    assert "no hit cleared the relevance gate" in capsys.readouterr().out


def test_search_json_is_parseable(offline_cli, open_gate, capsys):
    assert cli.main(["search", "vacation leave", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "vacation leave"
    assert payload["hits"]
    assert "gate" in payload


# --- query -------------------------------------------------------------------


def test_query_prints_the_decision_and_its_scores(offline_cli, capsys):
    assert cli.main(["query", "how much vacation leave do I accrue", "-v"]) == 0

    out = capsys.readouterr().out
    assert "relevance=" in out
    assert "groundedness=" in out


def test_query_json_carries_the_full_answer(offline_cli, capsys):
    assert cli.main(["query", "vacation leave", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"]
    assert "citations" in payload


def test_the_composer_choice_is_passed_through(monkeypatch, service, capsys):
    """`--composer gemini` must reach the factory, not be parsed and dropped."""
    seen = {}

    def _from_config(klass, path=None, composer=None):
        seen["composer"] = composer
        return service

    monkeypatch.setattr(cli.PolicyRagService, "from_config", classmethod(_from_config))
    assert cli.main(["query", "vacation leave", "--composer", "extractive"]) == 0
    assert seen["composer"] == "extractive"


# --- stats, ingest, drift ----------------------------------------------------


def test_stats_reports_the_index_provenance(offline_cli, capsys):
    assert cli.main(["stats"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["chunks"] > 0


def test_ingest_renders_its_report(monkeypatch, config, capsys):
    captured = {}

    class _Report:
        def render(self) -> str:
            return "indexed 480 chunks"

    def _ingest(cfg, verify):
        captured["verify"] = verify
        return _Report()

    monkeypatch.setattr(cli, "load_config", lambda path=None: config)
    monkeypatch.setattr(cli, "ingest", _ingest)

    assert cli.main(["ingest"]) == 0
    assert captured["verify"] is True
    assert "indexed 480 chunks" in capsys.readouterr().out


def test_no_verify_skips_the_canary_probe(monkeypatch, config):
    """The probe fails closed when the calibration no longer fits the model.

    That is the correct default, and `--no-verify` is the documented escape
    hatch for deliberately reindexing with a model whose calibration has not
    been re-derived yet.
    """
    captured = {}
    monkeypatch.setattr(cli, "load_config", lambda path=None: config)
    monkeypatch.setattr(
        cli, "ingest", lambda cfg, verify: captured.setdefault("verify", verify) or _Rendered()
    )

    class _Rendered:
        def render(self) -> str:
            return ""

    assert cli.main(["ingest", "--no-verify"]) == 0
    assert captured["verify"] is False


def test_drift_is_silent_and_zero_when_the_index_is_current(monkeypatch, config, capsys):
    monkeypatch.setattr(cli, "load_config", lambda path=None: config)
    monkeypatch.setattr(cli, "detect_drift", lambda cfg: [])

    assert cli.main(["drift"]) == 0
    assert "index is current" in capsys.readouterr().out


def test_drift_exits_non_zero_so_ci_can_gate_on_it(monkeypatch, config, capsys):
    monkeypatch.setattr(cli, "load_config", lambda path=None: config)
    monkeypatch.setattr(cli, "detect_drift", lambda cfg: ["leave/vacation.md", "pay/bonus.md"])

    assert cli.main(["drift"]) == 1

    out = capsys.readouterr().out
    assert "sources changed since the index was built" in out
    assert "leave/vacation.md" in out


# --- serve -------------------------------------------------------------------


def test_serve_forwards_the_bind_address_and_advertised_url(monkeypatch):
    """The public URL is separate from the bind host: behind a load balancer the
    agent card must advertise the outside address, not 0.0.0.0."""
    captured = {}
    from src.grounding.policy_rag.a2a_app import server

    monkeypatch.setattr(server, "run", lambda **kwargs: captured.update(kwargs))

    code = cli.main(
        ["serve", "--host", "0.0.0.0", "--port", "9999", "--public-url", "https://rag.example"]
    )

    assert code == 0
    assert captured == {
        "host": "0.0.0.0",
        "port": 9999,
        "config_path": None,
        "public_url": "https://rag.example",
    }
