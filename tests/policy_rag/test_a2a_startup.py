"""Startup ordering: the port must open before the embedding model is loaded.

Cloud Run rejected revision `hr-policy-rag-service-00009-vgq` with
`ERROR_CONNECTION_FAILED` after three startup probes. Nothing had crashed - the
process was inside `build_app`, loading the embedding model, and uvicorn's
`--factory` had therefore not yet bound port 8080. A probe that cannot open a
TCP connection is indistinguishable, from the platform's side, from a container
that died on startup.

These tests pin the ordering that makes the difference, and the honesty of
`/healthz` about which of the three states it is in. They use a stub service so
nothing here loads a real model.
"""

from __future__ import annotations

import asyncio
import threading
import time

import httpx
import pytest

from src.grounding.policy_rag.a2a_app.server import build_app
from src.grounding.policy_rag.service import PolicyRagService

#: `build_app` must return in far less than the time the load takes. Generous
#: against a loaded CI runner while still being nowhere near `_LOAD_SECONDS`.
_BIND_BUDGET_SECONDS = 2.0

#: How long the stub load blocks if the test never releases it. Bounded rather
#: than indefinite so that a regression - `build_app` loading eagerly again -
#: fails on the elapsed-time assertion, which names the actual problem, instead
#: of deadlocking until the stub gives up and reporting that instead.
_LOAD_SECONDS = 5.0


class _StubIndex:
    def __len__(self) -> int:
        return 480


class _StubService:
    """Stands in for a loaded `PolicyRagService`; only `/healthz` reads it."""

    index = _StubIndex()


@pytest.fixture
def slow_load(monkeypatch):
    """Make service construction block until the test releases it.

    Substituting for the model load rather than performing it keeps the test
    hermetic and fast, and lets us observe the window that matters: the interval
    where the app is serving but the service is not ready.
    """
    release = threading.Event()
    entered = threading.Event()

    def blocking_from_config(config_path=None, composer=None):
        entered.set()
        release.wait(_LOAD_SECONDS)
        return _StubService()

    monkeypatch.setattr(PolicyRagService, "from_config", blocking_from_config)
    return release, entered


async def _healthz(app) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/healthz")


def test_build_app_returns_before_the_service_finishes_loading(slow_load):
    """The regression itself.

    If this blocks, uvicorn does not bind, the probe gets no connection, and the
    revision is rejected with a message about the container rather than about
    the load.
    """
    release, entered = slow_load
    try:
        start = time.perf_counter()
        build_app(public_url="http://testserver")
        elapsed = time.perf_counter() - start

        assert entered.wait(_BIND_BUDGET_SECONDS), "the load never started in the background"
        assert elapsed < _BIND_BUDGET_SECONDS, (
            f"build_app blocked for {elapsed:.2f}s while the service loaded; uvicorn "
            "cannot bind the port until it returns, so the startup probe gets "
            "ERROR_CONNECTION_FAILED and the revision is rejected"
        )
    finally:
        release.set()


async def test_healthz_says_loading_rather_than_refusing_the_connection(slow_load):
    """503 with a reason beats no answer at all.

    The point of binding early is not to pass the probe sooner - it is that a
    slow start becomes something the operator can read.
    """
    release, entered = slow_load
    try:
        app = build_app(public_url="http://testserver")
        assert entered.wait(_BIND_BUDGET_SECONDS)

        response = await _healthz(app)

        assert response.status_code == 503
        assert response.json()["status"] == "loading"
    finally:
        release.set()


async def test_healthz_reports_ok_once_the_service_is_loaded(slow_load):
    release, _ = slow_load
    app = build_app(public_url="http://testserver")
    release.set()

    deadline = time.monotonic() + _BIND_BUDGET_SECONDS
    while time.monotonic() < deadline:
        response = await _healthz(app)
        if response.status_code == 200:
            break
        await asyncio.sleep(0.02)

    assert response.status_code == 200, f"still {response.status_code} after warmup"
    assert response.json() == {"status": "ok", "chunks": 480}


async def test_healthz_surfaces_a_failed_load_instead_of_reporting_healthy(monkeypatch):
    """A container that will never answer must not advertise itself as ready.

    Without this the pod passes its probe, takes traffic, and fails every
    request - the failure moves from the deploy, where someone is watching, to
    production, where the symptom is an agent that has no policies.
    """

    def exploding_from_config(config_path=None, composer=None):
        raise RuntimeError("index unreadable")

    monkeypatch.setattr(PolicyRagService, "from_config", exploding_from_config)

    app = build_app(public_url="http://testserver")

    deadline = time.monotonic() + _BIND_BUDGET_SECONDS
    while time.monotonic() < deadline:
        response = await _healthz(app)
        if response.status_code != 503:
            break
        await asyncio.sleep(0.02)

    assert response.status_code == 500
    assert response.json()["status"] == "error"
    assert "index unreadable" in response.json()["detail"]


def test_an_injected_service_is_used_directly(config, index):
    """Callers that pass a service have already paid for the load.

    The deferral is for the process that constructs its own service. A test or
    an eval harness handing one in gets it used as given, and `/healthz` reports
    it ready immediately.
    """
    from src.grounding.policy_rag.embeddings import build_provider

    service = PolicyRagService(config, index, build_provider(config.embedding))
    app = build_app(service=service, public_url="http://testserver")

    assert app.state.policy_rag_service is service
