"""Starlette app exposing the RAG service over A2A JSON-RPC.

Routes:
    GET  /.well-known/agent-card.json   agent card (discovery)
    POST /                              A2A JSON-RPC: message/send, tasks/get, ...
    GET  /healthz                       liveness, index-aware
"""

from __future__ import annotations

import logging
from pathlib import Path

from a2a.server.request_handlers import DefaultRequestHandlerV2
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.utils.constants import DEFAULT_RPC_URL
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from src.grounding.policy_rag.a2a_app.card import build_agent_card
from src.grounding.policy_rag.a2a_app.executor import PolicyRagExecutor
from src.grounding.policy_rag.service import PolicyRagService

logger = logging.getLogger(__name__)


def build_app(
    service: PolicyRagService | None = None,
    *,
    config_path: str | Path | None = None,
    public_url: str = "http://127.0.0.1:8080",
) -> Starlette:
    """Build the ASGI app.

    The index is loaded once at startup, not per request: it is a read-only
    artefact and the embedding model load is the expensive part. That also means
    a corpus republish requires a restart or a rolling deploy - the same
    trade-off as any immutable-artefact serving path.
    """
    service = service or PolicyRagService.from_config(config_path)
    card = build_agent_card(public_url)

    handler = DefaultRequestHandlerV2(
        agent_executor=PolicyRagExecutor(service),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )

    async def healthz(_request) -> JSONResponse:
        return JSONResponse({"status": "ok", "chunks": len(service.index)})

    routes: list[Route] = [
        *create_agent_card_routes(card),
        # `enable_v0_3_compat` accepts the spec method names (`message/send`,
        # `tasks/get`) alongside the SDK's native gRPC-style ones (`SendMessage`).
        # Consumers of this knowledge base are other teams' agents, and which
        # A2A client generation they are on is not ours to dictate.
        *create_jsonrpc_routes(handler, DEFAULT_RPC_URL, enable_v0_3_compat=True),
        Route("/healthz", healthz, methods=["GET"]),
    ]

    app = Starlette(routes=routes)
    app.state.policy_rag_service = service
    app.state.agent_card = card
    return app


def run(
    host: str = "127.0.0.1",
    port: int = 8080,
    config_path: str | Path | None = None,
    public_url: str | None = None,
) -> None:  # pragma: no cover - process entry point
    import uvicorn

    advertised = public_url or f"http://{host}:{port}"
    app = build_app(config_path=config_path, public_url=advertised)
    logger.info("agent card: %s/.well-known/agent-card.json", advertised)
    uvicorn.run(app, host=host, port=port)
