#!/usr/bin/env python3
"""Retrieval and guard evaluation against the golden question set.

Reports the three things the BRD actually asks for:

* **Recall@k / MRR** on the questions that should be answerable (FR-5.2).
* **Refusal correctness** - how often the gate rejects a question that has no
  answer in the corpus, and how often it wrongly rejects one that does (NFR-3.1
  cares about the first; usefulness cares about the second).
* **Guard correctness** - conflict, extended-workforce and absent-section
  questions must escalate, not answer (corpus datasheet, "what must not be
  answered").

The `--sweep` mode is how `retrieval.relevance_gate` and the `calibration`
block in `config/corpus.yaml` are derived. Those numbers are model-specific:
re-run the sweep whenever `embedding.model` changes, because a fused score of
0.80 means nothing across two different bi-encoders.

    python policy-rag/scripts/eval_retrieval.py
    python policy-rag/scripts/eval_retrieval.py --sweep
    python policy-rag/scripts/eval_retrieval.py --show-failures
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from policy_rag.config import GENERAL_ENTITLEMENT, load_config  # noqa: E402
from policy_rag.guards import GuardAction  # noqa: E402
from policy_rag.service import PolicyRagService  # noqa: E402

DEFAULT_GOLDEN = Path(__file__).resolve().parents[1] / "tests" / "eval" / "golden-questions.json"


@dataclass
class Outcome:
    question: dict
    action: str
    hit_paths: list[str]
    best_relevance: float
    #: 1-based rank of the first expected path, or None.
    rank: int | None
    passed: bool
    note: str


def _rank_of(expected: list[str], paths: list[str]) -> int | None:
    for position, path in enumerate(paths, start=1):
        if any(path.endswith(e) or e in path for e in expected):
            return position
    return None


def evaluate_one(service: PolicyRagService, question: dict, gate: float | None) -> Outcome:
    entitlements = question.get("entitlements") or [GENERAL_ENTITLEMENT]
    result = service.answer(
        question["query"],
        entitlements=entitlements,
        relevance_gate=gate,
    )
    paths = [h.chunk.path for h in result.hits]
    expected = question.get("expect_paths") or []
    rank = _rank_of(expected, paths) if expected else None
    want = question["expect"]

    if want == "answer":
        passed = result.action == GuardAction.ANSWER.value and rank is not None
        note = "" if passed else f"action={result.action} rank={rank}"
    elif want == "escalate":
        passed = result.action == GuardAction.ESCALATE.value
        note = "" if passed else f"action={result.action} (wanted escalate)"
    elif want == "refuse":
        # A refusal and an escalation both withhold an answer, but only a
        # refusal is correct when the corpus genuinely has nothing: escalating
        # sends a human a question they cannot answer either.
        passed = result.action == GuardAction.REFUSE.value
        note = "" if passed else f"action={result.action} paths={paths[:2]}"
    else:
        raise ValueError(f"unknown expect value {want!r} on {question['id']}")

    return Outcome(
        question=question,
        action=result.action,
        hit_paths=paths,
        best_relevance=result.retrieval.best_relevance,
        rank=rank,
        passed=passed,
        note=note,
    )


def summarise(outcomes: list[Outcome]) -> dict:
    answerable = [o for o in outcomes if o.question["expect"] == "answer"]
    escalations = [o for o in outcomes if o.question["expect"] == "escalate"]
    refusals = [o for o in outcomes if o.question["expect"] == "refuse"]

    ranked = [o.rank for o in answerable if o.rank]
    recall_1 = sum(1 for r in ranked if r == 1) / len(answerable) if answerable else 0.0
    recall_k = len(ranked) / len(answerable) if answerable else 0.0
    mrr = sum(1.0 / r for r in ranked) / len(answerable) if answerable else 0.0

    def rate(items: list[Outcome]) -> float:
        return sum(1 for o in items if o.passed) / len(items) if items else 0.0

    return {
        "total": len(outcomes),
        "passed": sum(1 for o in outcomes if o.passed),
        "recall@1": recall_1,
        "recall@k": recall_k,
        "mrr": mrr,
        "answer_accuracy": rate(answerable),
        "escalate_accuracy": rate(escalations),
        "refusal_accuracy": rate(refusals),
    }


def run(service: PolicyRagService, questions: list[dict], gate: float | None) -> list[Outcome]:
    return [evaluate_one(service, q, gate) for q in questions]


def _print_summary(stats: dict, gate: float) -> None:
    print(f"gate = {gate:.2f}")
    print(f"  overall            {stats['passed']}/{stats['total']}")
    print(f"  recall@1           {stats['recall@1']:.2%}")
    print(f"  recall@k           {stats['recall@k']:.2%}")
    print(f"  MRR                {stats['mrr']:.3f}")
    print(f"  answer accuracy    {stats['answer_accuracy']:.2%}")
    print(f"  escalate accuracy  {stats['escalate_accuracy']:.2%}")
    print(f"  refusal accuracy   {stats['refusal_accuracy']:.2%}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--gate", type=float, default=None, help="override the configured relevance gate")
    parser.add_argument("--sweep", action="store_true", help="sweep the gate from 0.40 to 0.95")
    parser.add_argument("--show-failures", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=None,
        help="exit non-zero below this overall pass rate (for CI)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    service = PolicyRagService.from_config(config)
    payload = json.loads(args.golden.read_text(encoding="utf-8"))
    questions = payload["questions"]

    if args.sweep:
        # Retrieval is the expensive part and it does not depend on the gate, so
        # in principle this could score once and re-threshold. It re-runs instead
        # because the guards read the surviving hit set, and that is the thing
        # being measured.
        rows = []
        for step in range(40, 100, 5):
            gate = step / 100
            stats = summarise(run(service, questions, gate))
            rows.append({"gate": gate, **stats})
        header = f"{'gate':>5}  {'pass':>7}  {'rec@1':>6}  {'MRR':>5}  {'answer':>7}  {'escal':>7}  {'refuse':>7}"
        print(header)
        print("-" * len(header))
        for row in rows:
            print(
                f"{row['gate']:>5.2f}  {row['passed']:>3}/{row['total']:<3}  "
                f"{row['recall@1']:>6.1%}  {row['mrr']:>5.3f}  "
                f"{row['answer_accuracy']:>7.1%}  {row['escalate_accuracy']:>7.1%}  {row['refusal_accuracy']:>7.1%}"
            )
        best = max(rows, key=lambda r: (r["passed"], r["gate"]))
        print(f"\nbest overall pass rate at gate {best['gate']:.2f} ({best['passed']}/{best['total']})")
        return 0

    gate = args.gate if args.gate is not None else config.retrieval.relevance_gate
    outcomes = run(service, questions, gate)
    stats = summarise(outcomes)

    if args.json:
        print(
            json.dumps(
                {
                    "gate": gate,
                    "summary": stats,
                    "outcomes": [
                        {
                            "id": o.question["id"],
                            "expect": o.question["expect"],
                            "action": o.action,
                            "rank": o.rank,
                            "best_relevance": round(o.best_relevance, 4),
                            "passed": o.passed,
                            "paths": o.hit_paths,
                        }
                        for o in outcomes
                    ],
                },
                indent=2,
            )
        )
    else:
        _print_summary(stats, gate)
        failures = [o for o in outcomes if not o.passed]
        if failures:
            print(f"\n{len(failures)} failing:")
            for o in failures:
                print(f"  {o.question['id']:<14} {o.question['expect']:<8} {o.note}")
                if args.show_failures:
                    print(f"      q: {o.question['query']}")
                    print(f"      best_relevance={o.best_relevance:.3f}")
                    for path in o.hit_paths[:3]:
                        print(f"      - {path}")

    if args.min_pass_rate is not None:
        rate = stats["passed"] / stats["total"] if stats["total"] else 0.0
        if rate < args.min_pass_rate:
            print(f"\nFAIL: pass rate {rate:.1%} below required {args.min_pass_rate:.1%}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
