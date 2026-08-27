"""Command line entry point.

    python -m policy_rag.cli ingest
    python -m policy_rag.cli query "how much vacation after 8 years?"
    python -m policy_rag.cli search "bereavement" --top-k 3 --json
    python -m policy_rag.cli stats
    python -m policy_rag.cli drift
    python -m policy_rag.cli serve --port 8080
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import GENERAL_ENTITLEMENT, load_config
from .ingest import detect_drift, ingest
from .service import PolicyRagService


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default=None, help="path to corpus.yaml")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")


def _add_query_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("question", help="the question to ask")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument(
        "--entitlement",
        action="append",
        dest="entitlements",
        default=None,
        help=f"caller entitlement, repeatable (default: {GENERAL_ENTITLEMENT})",
    )
    parser.add_argument(
        "--corpus",
        action="append",
        dest="corpora",
        default=None,
        help="corpus id to search, repeatable (default: the config's default set)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="policy-rag", description="Altostrat HR policy RAG")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="build the FAISS index from the corpora")
    _add_common(p_ingest)
    p_ingest.add_argument("--no-verify", action="store_true", help="skip the canary retrieval probe")

    p_query = sub.add_parser("query", help="ask a question and get a grounded answer")
    _add_common(p_query)
    _add_query_args(p_query)
    p_query.add_argument("--composer", default=None, choices=["extractive", "gemini"])

    p_search = sub.add_parser("search", help="retrieval only - no guards, no composition")
    _add_common(p_search)
    _add_query_args(p_search)

    p_stats = sub.add_parser("stats", help="index contents and build provenance")
    _add_common(p_stats)

    p_drift = sub.add_parser("drift", help="list sources that changed since the index was built")
    _add_common(p_drift)

    p_serve = sub.add_parser("serve", help="run the A2A server")
    _add_common(p_serve)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8080)
    p_serve.add_argument("--public-url", default=None, help="URL advertised in the agent card")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s",
    )

    if args.command == "ingest":
        config = load_config(args.config)
        report = ingest(config, verify=not args.no_verify)
        print(report.render())
        return 0

    if args.command == "stats":
        service = PolicyRagService.from_config(args.config)
        print(json.dumps(service.stats(), indent=2))
        return 0

    if args.command == "drift":
        config = load_config(args.config)
        drifted = detect_drift(config)
        if not drifted:
            print("index is current with all ingested sources")
            return 0
        print("sources changed since the index was built:")
        for entry in drifted:
            print(f"  {entry}")
        # Non-zero so a CI job can gate on it.
        return 1

    if args.command == "search":
        service = PolicyRagService.from_config(args.config)
        result = service.search(
            args.question,
            entitlements=args.entitlements,
            top_k=args.top_k,
            corpora=args.corpora,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
            return 0
        print(f"query      : {result.query}")
        print(f"gate       : {result.gate}   best relevance: {result.best_relevance:.3f}")
        print(f"corpora    : {', '.join(result.searched_corpora)}")
        if not result.hits:
            print("\nno hit cleared the relevance gate")
            return 0
        for i, hit in enumerate(result.hits, start=1):
            print(f"\n[{i}] {hit.relevance:.3f}  (dense {hit.dense_score:.3f} / lexical {hit.lexical_score:.3f})")
            print(f"    {hit.chunk.doc_title} - {hit.chunk.heading_trail}")
            print(f"    {hit.citation.uri}")
            snippet = " ".join(hit.chunk.text.split())
            print(f"    {snippet[:280]}{'...' if len(snippet) > 280 else ''}")
        return 0

    if args.command == "query":
        service = PolicyRagService.from_config(args.config, composer=args.composer)
        answer = service.answer(
            args.question,
            entitlements=args.entitlements,
            top_k=args.top_k,
            corpora=args.corpora,
        )
        if args.json:
            print(json.dumps(answer.to_dict(), indent=2))
            return 0
        print(f"[{answer.decision}]"
              f" relevance={answer.relevance:.3f} groundedness={answer.groundedness:.2f}\n")
        print(answer.text)
        return 0

    if args.command == "serve":
        from .a2a_app.server import run

        run(host=args.host, port=args.port, config_path=args.config, public_url=args.public_url)
        return 0

    raise AssertionError(f"unhandled command {args.command!r}")


if __name__ == "__main__":
    sys.exit(main())
