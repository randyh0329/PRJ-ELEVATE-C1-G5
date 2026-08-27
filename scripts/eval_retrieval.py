#!/usr/bin/env python3
"""Derive the retrieval tuning constants in `config/corpus.yaml` from the golden set.

Three of them are properties of the embedding model rather than of the corpus -
`cosine_floor`, `cosine_ceiling` and `lexical_boost`. They exist because SDD §3.3
fixes the relevance gate at **0.80**, and a raw cosine of 0.80 means something
different for every bi-encoder. Calibration is what makes the SDD's number
portable.

Until now those constants were guessed, and the guess was wrong in a way that is
easy to miss: a query whose correct document came back at rank 1 still scored
below the gate, so the service refused to answer a question it had already
answered correctly. That reads in the eval output as a retrieval failure and it
is not one.

Two more are admissibility rules rather than calibration - `max_link_density`
and `min_lexical_corroboration`. They are swept as an ablation by default (each
dimension carries its configured value and a value that disables the rule) so
that the output shows whether each rule is still earning its place, rather than
only how it should be set.

    PYTHONPATH=. python scripts/eval_retrieval.py --sweep
    PYTHONPATH=. python scripts/eval_retrieval.py --sweep --apply

**The sweep is constrained, not maximising.** Widening the calibration until
every answerable question passes would also drag out-of-domain questions over
the gate, and a system that answers those has not improved - it has started
hallucinating. So a candidate is only admissible if it keeps refusal and
escalation accuracy at 100%, and among admissible candidates the objective is
answer accuracy. The constraint is the point; the maximisation is secondary.

**Overfitting.** These constants are fitted on the same 45 questions the eval
reports against, so the reported score is optimistic and is not an estimate of
field accuracy. That is a tolerable trade for the calibration triple, which has
two degrees of freedom against a monotone score and is re-derived whenever the
model changes. It is a weaker position for the two admissibility rules, which
were introduced *after* looking at which cases failed. `max_link_density` has an
argument that does not depend on the golden set at all - a passage made of links
states no rule, so it cannot ground a citation under FR-5.2 - and would be worth
keeping even at zero measured gain. `min_lexical_corroboration` does not: it is
a threshold chosen because the binding negative sat below it and every positive
sat above it. Treat it as provisional, and re-derive it against held-out
questions before reading anything into the margin it buys.

Re-run this whenever `embedding.model` changes.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.run_policy_rag_eval import DEFAULT_GOLDEN, run, summarise  # noqa: E402
from src.grounding.policy_rag.config import load_config  # noqa: E402
from src.grounding.policy_rag.service import PolicyRagService  # noqa: E402

#: The gate is not swept. SDD §3.3 fixes it, and a sweep that moves it is
#: answering a different question than the one this script exists to answer.
SDD_RELEVANCE_GATE = 0.80


#: `max_link_density` above 1.0 can never fire - every chunk is at most 100%
#: link characters - so this is how the ablation switches the rule off.
RULE_DISABLED_LINK_DENSITY = 1.01


@dataclass(frozen=True)
class Candidate:
    cosine_floor: float
    cosine_ceiling: float
    lexical_boost: float
    max_link_density: float
    min_lexical_corroboration: float

    def __str__(self) -> str:
        return (
            f"floor={self.cosine_floor:.2f} ceiling={self.cosine_ceiling:.2f} "
            f"boost={self.lexical_boost:.2f} link<{self.max_link_density:.2f} "
            f"minlex={self.min_lexical_corroboration:.2f}"
        )


def _grid(
    floors: list[float],
    ceilings: list[float],
    boosts: list[float],
    link_densities: list[float],
    min_lexicals: list[float],
) -> list[Candidate]:
    """The full product, minus calibrations too narrow to discriminate."""
    return [
        Candidate(floor, ceiling, boost, link_density, min_lexical)
        for floor, ceiling, boost, link_density, min_lexical in itertools.product(
            floors, ceilings, boosts, link_densities, min_lexicals
        )
        # A span below 0.05 makes the calibration a step function: every hit
        # lands at 0.0 or 1.0 and the gate stops discriminating at all.
        if ceiling - floor >= 0.05
    ]


def score(service: PolicyRagService, questions: list[dict], candidate: Candidate) -> dict:
    """Evaluate one configuration against the golden set at the SDD gate."""
    retrieval = service.retriever.config.retrieval
    retrieval.cosine_floor = candidate.cosine_floor
    retrieval.cosine_ceiling = candidate.cosine_ceiling
    retrieval.lexical_boost = candidate.lexical_boost
    retrieval.max_link_density = candidate.max_link_density
    retrieval.min_lexical_corroboration = candidate.min_lexical_corroboration
    return summarise(run(service, questions, SDD_RELEVANCE_GATE))


def admissible(stats: dict) -> bool:
    """A calibration that starts answering unanswerable questions is not a fix."""
    return stats["refusal_accuracy"] == 1.0 and stats["escalate_accuracy"] == 1.0


def rank_key(row: dict) -> tuple:
    """Answer accuracy first, then MRR, then the two conservatism tiebreaks.

    Among equals, prefer the narrowest calibration span and the *weakest*
    admissibility rules. Both preferences point the same way: take the least
    aggressive configuration that achieves the score, so that a rule only stays
    tight where the measurement actually required it.
    """
    candidate: Candidate = row["candidate"]
    span = candidate.cosine_ceiling - candidate.cosine_floor
    return (
        row["answer_accuracy"],
        row["mrr"],
        -span,
        candidate.max_link_density,
        -candidate.min_lexical_corroboration,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--sweep", action="store_true", help="search the calibration grid")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="print the corpus.yaml block for the winning calibration",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--floors", type=float, nargs="+", default=[0.40, 0.45, 0.50, 0.55, 0.60]
    )
    parser.add_argument(
        "--ceilings", type=float, nargs="+", default=[0.64, 0.66, 0.68, 0.70, 0.72]
    )
    parser.add_argument("--boosts", type=float, nargs="+", default=[0.25, 0.30, 0.35, 0.40])
    parser.add_argument(
        "--link-densities",
        type=float,
        nargs="+",
        default=[0.35, RULE_DISABLED_LINK_DENSITY],
        help="max_link_density values; >1.0 disables the rule",
    )
    parser.add_argument(
        "--min-lexicals",
        type=float,
        nargs="+",
        default=[0.0, 0.12],
        help="min_lexical_corroboration values; 0.0 disables the rule",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    service = PolicyRagService.from_config(config)
    questions = json.loads(args.golden.read_text(encoding="utf-8"))["questions"]

    current = Candidate(
        config.retrieval.cosine_floor,
        config.retrieval.cosine_ceiling,
        config.retrieval.lexical_boost,
        config.retrieval.max_link_density,
        config.retrieval.min_lexical_corroboration,
    )

    if not args.sweep:
        stats = score(service, questions, current)
        print(f"current calibration: {current}")
        print(f"  {stats['passed']}/{stats['total']} at gate {SDD_RELEVANCE_GATE:.2f}")
        return 0

    candidates = _grid(
        args.floors, args.ceilings, args.boosts, args.link_densities, args.min_lexicals
    )
    print(f"sweeping {len(candidates)} configurations at the fixed §3.3 gate {SDD_RELEVANCE_GATE:.2f}\n")

    rows = []
    for candidate in candidates:
        stats = score(service, questions, candidate)
        rows.append({"candidate": candidate, **stats})

    viable = [r for r in rows if admissible(r)]
    header = (
        f"{'floor':>6}{'ceil':>7}{'boost':>7}{'link<':>7}{'minlex':>8}  "
        f"{'pass':>7}  {'answer':>7}  {'MRR':>6}"
    )
    print(header)
    print("-" * len(header))
    for row in sorted(viable, key=rank_key, reverse=True)[:12]:
        c: Candidate = row["candidate"]
        print(
            f"{c.cosine_floor:>6.2f}{c.cosine_ceiling:>7.2f}{c.lexical_boost:>7.2f}"
            f"{c.max_link_density:>7.2f}{c.min_lexical_corroboration:>8.2f}  "
            f"{row['passed']:>3}/{row['total']:<3}  {row['answer_accuracy']:>7.1%}  {row['mrr']:>6.3f}"
        )

    rejected = len(rows) - len(viable)
    print(f"\n{rejected} of {len(rows)} rejected for answering questions that have no answer")

    if not viable:
        print("no admissible calibration - the corpus or the gate is the problem, not this")
        return 1

    best = max(viable, key=rank_key)
    winner: Candidate = best["candidate"]
    print(f"\nbest admissible: {winner} -> {best['passed']}/{best['total']}")

    if args.json:
        print(
            json.dumps(
                {
                    "gate": SDD_RELEVANCE_GATE,
                    "cosine_floor": winner.cosine_floor,
                    "cosine_ceiling": winner.cosine_ceiling,
                    "lexical_boost": winner.lexical_boost,
                    "max_link_density": winner.max_link_density,
                    "min_lexical_corroboration": winner.min_lexical_corroboration,
                    "summary": {k: v for k, v in best.items() if k != "candidate"},
                },
                indent=2,
            )
        )
    if args.apply:
        print("\n# config/corpus.yaml -> retrieval:")
        print(f"  lexical_boost: {winner.lexical_boost}")
        print("  calibration:")
        print(f"    cosine_floor: {winner.cosine_floor}")
        print(f"    cosine_ceiling: {winner.cosine_ceiling}")
        print(f"  max_link_density: {winner.max_link_density}")
        print(f"  min_lexical_corroboration: {winner.min_lexical_corroboration}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
