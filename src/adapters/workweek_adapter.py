import httpx
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from src.config import settings
from src.adapters.circuit_breaker import workweek_breaker, CircuitBreakerOpenException
from src.adapters.rules_engine import rules_engine
from src.adapters.cloud_tasks import tasks_buffer
from src.storage.firestore import firestore_store
from src.models.workweek import (
    EmployeeProfile,
    ContactUpdateResponse,
    BalancesResponse,
    LeaveResponse,
)


class WorkWeekAdapter:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.workweek_mock_url).rstrip("/")

    def _get_headers(self, subject_assertion: str, idempotency_key: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Authorization": "Bearer workload-oidc-token",
            "X-Subject-Assertion": subject_assertion,
            "X-Agent-Origin": "hcm-1.4.0",
        }
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if settings.mock_build:
            from src.mocks.app import mock_app
            return httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://test/api/v1", timeout=5.0)
        return httpx.AsyncClient(base_url=self.base_url, timeout=5.0)

    async def get_profile(self, subject_assertion: str) -> EmployeeProfile:
        if not workweek_breaker.can_execute():
            raise CircuitBreakerOpenException()

        try:
            async with self._get_client() as client:
                resp = await client.get(
                    "/employees/me/profile",
                    headers=self._get_headers(subject_assertion)
                )
                if resp.status_code == 200:
                    workweek_breaker.record_success()
                    return EmployeeProfile(**resp.json())
                elif resp.status_code >= 500:
                    workweek_breaker.record_failure()
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                else:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.RequestError as exc:
            workweek_breaker.record_failure()
            raise HTTPException(status_code=503, detail=f"WorkWeek connection error: {str(exc)}")

    async def get_balances(self, subject_assertion: str) -> BalancesResponse:
        if not workweek_breaker.can_execute():
            raise CircuitBreakerOpenException()

        try:
            async with self._get_client() as client:
                resp = await client.get(

                    "/employees/me/balances",
                    headers=self._get_headers(subject_assertion)
                )
                if resp.status_code == 200:
                    workweek_breaker.record_success()
                    return BalancesResponse(**resp.json())
                elif resp.status_code >= 500:
                    workweek_breaker.record_failure()
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                else:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.RequestError as exc:
            workweek_breaker.record_failure()
            raise HTTPException(status_code=503, detail=f"WorkWeek connection error: {str(exc)}")

    async def update_contact(
        self,
        subject_assertion: str,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> ContactUpdateResponse:
        if not workweek_breaker.can_execute():
            raise CircuitBreakerOpenException()

        # 1. Deterministic Business Rules Pre-check (FR-3.3)
        rules_engine.validate_contact_update(address, phone)

        # 2. Idempotency Lock in Firestore (SDD §5.8.2)
        acquired, lock_key, cached_result = firestore_store.acquire_lock(
            employee_id=subject_assertion,
            action="update_contact",
            params={"address": address, "phone": phone}
        )
        if not acquired and cached_result:
            return ContactUpdateResponse(**cached_result)
        elif not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transaction in progress. Duplicate request rejected."
            )

        payload = {}
        if address is not None:
            payload["homeAddress"] = address
        if phone is not None:
            payload["phoneNumber"] = phone

        effective_idem_key = idempotency_key or lock_key

        async def _call():
            async with self._get_client() as client:
                resp = await client.patch(
                    "/employees/me/contact",
                    json=payload,
                    headers=self._get_headers(subject_assertion, effective_idem_key)
                )
                if resp.status_code == 200:
                    workweek_breaker.record_success()
                    data = resp.json()
                    firestore_store.release_or_complete_lock(lock_key, data)
                    return ContactUpdateResponse(**data)
                elif resp.status_code >= 500:
                    workweek_breaker.record_failure()
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                else:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)

        return await tasks_buffer.enqueue_and_execute(
            task_id=f"ww_contact_{lock_key[:8]}",
            operation_name="ww.update_contact",
            fn=_call,
            payload=payload
        )

    async def submit_leave(
        self,
        subject_assertion: str,
        start_date: str,
        end_date: str,
        leave_type: str,
        work_days: float,
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> LeaveResponse:
        if not workweek_breaker.can_execute():
            raise CircuitBreakerOpenException()

        # 1. Fetch live balance for pre-validation (FR-3.4)
        if leave_type.lower() != "medical":
            balances = await self.get_balances(subject_assertion)
            cat_balance = balances.vacation.remainingHours if leave_type.lower() == "vacation" else balances.sick.remainingHours
            rules_engine.validate_leave_request(start_date, end_date, leave_type, work_days, cat_balance)

        # 2. Idempotency Lock in Firestore (SDD §5.8.2)
        acquired, lock_key, cached_result = firestore_store.acquire_lock(
            employee_id=subject_assertion,
            action="submit_leave",
            params={"startDate": start_date, "endDate": end_date, "type": leave_type, "days": work_days}
        )
        if not acquired and cached_result:
            return LeaveResponse(**cached_result)
        elif not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Leave submission currently in progress. Duplicate rejected."
            )

        payload = {
            "startDate": start_date,
            "endDate": end_date,
            "leaveType": leave_type,
            "workDays": work_days,
            "reason": reason or ""
        }
        effective_idem_key = idempotency_key or lock_key

        async def _call():
            async with self._get_client() as client:
                resp = await client.post(
                    "/employees/me/leaves",
                    json=payload,
                    headers=self._get_headers(subject_assertion, effective_idem_key)
                )
                if resp.status_code == 201:
                    workweek_breaker.record_success()
                    data = resp.json()
                    firestore_store.release_or_complete_lock(lock_key, data)
                    return LeaveResponse(**data)
                elif resp.status_code >= 500:
                    workweek_breaker.record_failure()
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                else:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)

        return await tasks_buffer.enqueue_and_execute(
            task_id=f"ww_leave_{lock_key[:8]}",
            operation_name="ww.submit_leave",
            fn=_call,
            payload=payload
        )

    async def cancel_leave(self, subject_assertion: str, leave_id: str) -> Dict[str, Any]:
        if not workweek_breaker.can_execute():
            raise CircuitBreakerOpenException()

        try:
            async with self._get_client() as client:
                resp = await client.delete(
                    f"/employees/me/leaves/{leave_id}",
                    headers=self._get_headers(subject_assertion)
                )
                if resp.status_code == 200:
                    workweek_breaker.record_success()

                    return resp.json()
                elif resp.status_code >= 500:
                    workweek_breaker.record_failure()
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                else:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.RequestError as exc:
            workweek_breaker.record_failure()
            raise HTTPException(status_code=503, detail=f"WorkWeek connection error: {str(exc)}")


workweek_adapter = WorkWeekAdapter()
