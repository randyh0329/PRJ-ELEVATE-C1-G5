import httpx
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from src.config import settings
from src.adapters.circuit_breaker import itsm_breaker, CircuitBreakerOpenException
from src.adapters.rules_engine import rules_engine
from src.adapters.cloud_tasks import tasks_buffer
from src.storage.firestore import firestore_store
from src.models.serviceimmediately import (
    IncidentDetails,
    CreateIncidentResponse,
    UpdateStatusResponse,
    PriorityEnum,
    TicketStateEnum,
)


class ServiceImmediatelyAdapter:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.itsm_mock_url).rstrip("/")

    def _get_headers(self, subject_assertion: str, idempotency_key: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Authorization": "Bearer workload-oidc-token",
            "X-Subject-Assertion": subject_assertion,
            "X-Agent-Origin": "itsm-1.4.0",
        }
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if settings.mock_build:
            from src.mocks.app import mock_app
            return httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://test/api/v1", timeout=5.0)
        return httpx.AsyncClient(base_url=self.base_url, timeout=5.0)

    async def get_incident(self, ticket_id: str, subject_assertion: str) -> IncidentDetails:
        if not itsm_breaker.can_execute():
            raise CircuitBreakerOpenException()

        try:
            async with self._get_client() as client:
                resp = await client.get(
                    f"/incidents/{ticket_id}",
                    headers=self._get_headers(subject_assertion)
                )
                if resp.status_code == 200:
                    itsm_breaker.record_success()
                    return IncidentDetails(**resp.json())
                elif resp.status_code >= 500:
                    itsm_breaker.record_failure()
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                else:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.RequestError as exc:
            itsm_breaker.record_failure()
            raise HTTPException(status_code=503, detail=f"ServiceImmediately connection error: {str(exc)}")


    async def create_incident(
        self,
        category: str,
        short_description: str,
        priority: PriorityEnum,
        description: Optional[str] = None,
        subject_assertion: str = "EMP-44210",
        idempotency_key: Optional[str] = None
    ) -> CreateIncidentResponse:
        if not itsm_breaker.can_execute():
            raise CircuitBreakerOpenException()

        # 1. Deterministic Business Rules Pre-check (FR-4.3)
        rules_engine.validate_incident_creation(category, short_description, priority, description)

        # 2. Idempotency Lock in Firestore (SDD §5.8.2)
        acquired, lock_key, cached_result = firestore_store.acquire_lock(
            employee_id=subject_assertion,
            action="create_incident",
            params={"category": category, "desc": short_description, "priority": priority.value}
        )
        if not acquired and cached_result:
            return CreateIncidentResponse(**cached_result)
        elif not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Incident creation in progress. Duplicate rejected."
            )

        payload = {
            "category": category,
            "shortDescription": short_description,
            "description": description or "",
            "priority": priority.value
        }
        effective_idem_key = idempotency_key or lock_key

        async def _call():
            async with self._get_client() as client:
                resp = await client.post(
                    "/incidents",
                    json=payload,
                    headers=self._get_headers(subject_assertion, effective_idem_key)
                )
                if resp.status_code == 201:
                    itsm_breaker.record_success()
                    data = resp.json()
                    firestore_store.release_or_complete_lock(lock_key, data)
                    return CreateIncidentResponse(**data)
                elif resp.status_code >= 500:
                    itsm_breaker.record_failure()
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                else:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)

        return await tasks_buffer.enqueue_and_execute(
            task_id=f"si_create_{lock_key[:8]}",
            operation_name="si.create_incident",
            fn=_call,
            payload=payload
        )

    async def post_comment(self, ticket_id: str, body: str, subject_assertion: str = "EMP-44210") -> Dict[str, Any]:
        if not itsm_breaker.can_execute():
            raise CircuitBreakerOpenException()

        try:
            async with self._get_client() as client:
                resp = await client.post(
                    f"/incidents/{ticket_id}/comments",
                    json={"body": body},
                    headers=self._get_headers(subject_assertion)
                )
                if resp.status_code == 201:
                    itsm_breaker.record_success()
                    return resp.json()
                elif resp.status_code >= 500:
                    itsm_breaker.record_failure()
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                else:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.RequestError as exc:
            itsm_breaker.record_failure()
            raise HTTPException(status_code=503, detail=f"ServiceImmediately connection error: {str(exc)}")

    async def update_status(
        self,
        ticket_id: str,
        state: TicketStateEnum,
        resolution_notes: Optional[str] = None,
        subject_assertion: str = "EMP-44210"
    ) -> UpdateStatusResponse:
        if not itsm_breaker.can_execute():
            raise CircuitBreakerOpenException()

        # 1. Check current state for lifecycle transition
        current_inc = await self.get_incident(ticket_id, subject_assertion)
        rules_engine.validate_status_transition(current_inc.state.value, state.value)

        payload = {
            "state": state.value,
            "resolutionNotes": resolution_notes or ""
        }

        try:
            async with self._get_client() as client:
                resp = await client.patch(
                    f"/incidents/{ticket_id}/status",
                    json=payload,
                    headers=self._get_headers(subject_assertion)
                )
                if resp.status_code == 200:
                    itsm_breaker.record_success()
                    return UpdateStatusResponse(**resp.json())
                elif resp.status_code >= 500:
                    itsm_breaker.record_failure()
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                else:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.RequestError as exc:
            itsm_breaker.record_failure()
            raise HTTPException(status_code=503, detail=f"ServiceImmediately connection error: {str(exc)}")



itsm_adapter = ServiceImmediatelyAdapter()
