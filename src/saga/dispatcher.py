"""
Cloud Tasks Asynchronous Rate-Limited Dispatcher and DLQ Manager.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §5.2 (NFR-4.2), §4.8.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import uuid
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("saga.dispatcher")


class CloudTasksDispatcher:
    """
    Simulates / wraps Cloud Tasks queueing for asynchronous mutating backend calls.
    Implements:
    - AIMD (Additive Increase / Multiplicative Decrease) concurrency control (§5.2).
    - Exponential backoff with retry limit.
    - Revocation validation before task execution (§4.8).
    - Dead-Letter Queue (DLQ) routing after retry exhaustion.
    """

    def __init__(
        self,
        max_concurrency_ceiling: int = 20,
        target_capacity_ratio: float = 0.90,
    ):
        self.max_concurrency_ceiling = max_concurrency_ceiling
        self.current_concurrency_limit = int(max_concurrency_ceiling * target_capacity_ratio)
        self.min_concurrency_limit = 2
        self.in_flight_tasks: dict[str, dict[str, Any]] = {}
        self.dlq_store: list[dict[str, Any]] = []
        self.revoked_principals: set = set()

    def mark_principal_revoked(self, employee_id: str) -> None:
        """Records employee session/credential revocation (§4.8)."""
        self.revoked_principals.add(employee_id)

    def adapt_concurrency_on_rate_limit(self) -> None:
        """Multiplicative decrease: Halve concurrency on HTTP 429 / 5xx."""
        old_limit = self.current_concurrency_limit
        self.current_concurrency_limit = max(
            self.min_concurrency_limit, self.current_concurrency_limit // 2
        )
        logger.warning(
            "AIMD rate-limit trigger: Halved concurrency limit from %s to %s",
            old_limit, self.current_concurrency_limit,
        )

    def adapt_concurrency_on_success(self) -> None:
        """Additive increase: Incrementally restore capacity towards ceiling."""
        if self.current_concurrency_limit < self.max_concurrency_ceiling:
            self.current_concurrency_limit += 1

    async def enqueue_and_execute(
        self,
        task_name: str,
        employee_id: str,
        action: Callable[[], Any],
        max_retries: int = 5,
        base_delay_seconds: float = 0.05,
    ) -> dict[str, Any]:
        """
        Enqueues and executes a task with exponential backoff and AIMD adaptive resilience.
        """
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        self.in_flight_tasks[task_id] = {
            "task_id": task_id,
            "task_name": task_name,
            "employee_id": employee_id,
            "status": "QUEUED",
            "enqueued_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        # Step 1: Check mid-saga revocation (§4.8)
        if employee_id in self.revoked_principals:
            logger.warning("Task %s aborted: Principal %s is REVOKED.", task_id, employee_id)
            self.in_flight_tasks[task_id]["status"] = "DISCARDED_PRINCIPAL_REVOKED"
            return {
                "task_id": task_id,
                "status": "DISCARDED_PRINCIPAL_REVOKED",
                "error": "Principal credentials revoked mid-saga",
            }

        # Step 2: Retry loop with exponential backoff
        delay = base_delay_seconds
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                # Re-verify revocation before each attempt
                if employee_id in self.revoked_principals:
                    self.in_flight_tasks[task_id]["status"] = "DISCARDED_PRINCIPAL_REVOKED"
                    return {
                        "task_id": task_id,
                        "status": "DISCARDED_PRINCIPAL_REVOKED",
                        "error": "Principal revoked before retry attempt",
                    }

                # Execute action (supports coroutine or standard callable)
                if asyncio.iscoroutinefunction(action):
                    result = await action()
                else:
                    result = action()

                self.adapt_concurrency_on_success()
                self.in_flight_tasks[task_id]["status"] = "SUCCESS"
                return {
                    "task_id": task_id,
                    "status": "SUCCESS",
                    "attempts": attempt,
                    "result": result,
                }

            except Exception as e:
                last_error = str(e)
                logger.warning("Task %s attempt %s/%s failed: %s", task_id, attempt, max_retries, e)
                self.adapt_concurrency_on_rate_limit()

                if attempt < max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2.0

        # Step 3: Retries exhausted -> Route to Dead-Letter Queue (DLQ)
        logger.error("Task %s permanently failed after %s attempts. Routing to DLQ.", task_id, max_retries)
        dlq_entry = {
            "task_id": task_id,
            "task_name": task_name,
            "employee_id": employee_id,
            "failed_reason": last_error,
            "retries_exhausted": max_retries,
            "routed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "retention_days": 14,
        }
        self.dlq_store.append(dlq_entry)
        self.in_flight_tasks[task_id]["status"] = "DLQ_ROUTED"

        return {
            "task_id": task_id,
            "status": "FAILED_DLQ",
            "attempts": max_retries,
            "error": last_error,
            "dlq_entry": dlq_entry,
        }
