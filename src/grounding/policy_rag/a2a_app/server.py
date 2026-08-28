"""Starlette app exposing the RAG service over A2A JSON-RPC.

Routes:
    GET  /.well-known/agent-card.json   agent card (discovery)
    POST /                              A2A JSON-RPC: message/send, tasks/get, ...
    GET  /healthz                       liveness, index-aware
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

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


class _DeferredService:
    """A `PolicyRagService` that loads off the critical path to the port bind.

    Constructing the service loads the embedding model, which is ~85% of a cold
    start (5.05s of 5.95s measured warm, with the weights already on local
    disk). Doing that inside `build_app` means uvicorn's `--factory` has not yet
    bound port 8080 while it happens, so a platform health check gets no TCP
    connection at all - `ERROR_CONNECTION_FAILED`, which reads as a container
    that crashed rather than one that is still coming up. That is how revision
    `hr-policy-rag-service-00009-vgq` was rejected.

    Loading in a background thread lets the port open in well under a second.
    The service is still not *ready* any sooner - but "not ready" is now
    something the process can say out loud, over HTTP, instead of something an
    operator has to infer from a refused connection.

    Attribute access forwards to the real service and blocks until it exists, so
    a request that arrives early waits rather than failing. `PolicyRagExecutor`
    only touches the service per-request, never at construction.
    """

    def __init__(self, factory: Callable[[], PolicyRagService]) -> None:
        self._factory = factory
        self._service: PolicyRagService | None = None
        self._error: BaseException | None = None
        self._done = threading.Event()
        self._started = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._started:
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._load, name="policy-rag-warmup", daemon=True
            )
            self._thread.start()

    def _load(self) -> None:
        try:
            self._service = self._factory()
        except BaseException as exc:
            # Swallowed here only so the thread does not die silently; `resolve`
            # re-raises it, and `/healthz` reports it as 500 rather than leaving
            # the container to look healthy while answering nothing.
            self._error = exc
            logger.exception("policy RAG service failed to load")
        finally:
            self._done.set()

    @property
    def ready(self) -> bool:
        return self._service is not None

    @property
    def error(self) -> BaseException | None:
        return self._error

    def resolve(self, timeout: float | None = None) -> PolicyRagService:
        self.start()
        self._done.wait(timeout)
        if self._error is not None:
            raise self._error
        if self._service is None:
            raise TimeoutError("policy RAG service is still loading")
        return self._service

    def __getattr__(self, name: str) -> Any:
        # Only reached for names not found on the instance, so the private
        # attributes above never recurse through here.
        return getattr(self.resolve(), name)


def build_app(
    service: PolicyRagService | None = None,
    *,
    config_path: str | Path | None = None,
    public_url: str = "http://127.0.0.1:8080",
) -> Starlette:
    """Build the ASGI app.

    The index is loaded once per process, not per request: it is a read-only
    artefact and the embedding model load is the expensive part. That also means
    a corpus republish requires a restart or a rolling deploy - the same
    trade-off as any immutable-artefact serving path.

    "Once per process" is not the same as "before we accept connections",
    though, and this function is what uvicorn `--factory` runs *before* it binds
    the port. So when we are constructing the service ourselves it loads in a
    background thread and this returns immediately. An injected `service` is
    used as given: callers that pass one - the tests, the eval harness - have
    already paid for it and want it ready.
    """
    deferred: _DeferredService | None = None
    if service is None:
        deferred = _DeferredService(lambda: PolicyRagService.from_config(config_path))
        deferred.start()
        service = deferred  # type: ignore[assignment]  # forwards by __getattr__

    card = build_agent_card(public_url)

    handler = DefaultRequestHandlerV2(
        agent_executor=PolicyRagExecutor(service),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )

    async def healthz(_request) -> JSONResponse:
        """Honest about the three states, rather than 200 for two of them.

        A startup probe reading this gets a real answer while the model loads,
        so a slow start is reported as a slow start. Returning 200 early would
        pass the probe sooner, at the cost of routing the first real request
        into a service that cannot answer it yet.
        """
        if deferred is None:
            return JSONResponse({"status": "ok", "chunks": len(service.index)})
        if deferred.error is not None:
            return JSONResponse(
                {"status": "error", "detail": str(deferred.error)}, status_code=500
            )
        if not deferred.ready:
            return JSONResponse(
                {"status": "loading", "detail": "embedding model and index still loading"},
                status_code=503,
            )
        return JSONResponse({"status": "ok", "chunks": len(deferred.resolve().index)})

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
