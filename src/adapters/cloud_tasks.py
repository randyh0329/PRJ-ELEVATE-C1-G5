import asyncio
import time
from typing import Dict, Any, Callable, Optional, List
from fastapi import HTTPException
from src.storage.firestore import firestore_store


class CloudTasksBuffer:
    def __init__(self):
        self.queue: List[Dict[str, Any]] = []
        self.dlq: List[Dict[str, Any]] = []
        self.max_retries = 4
        self.initial_backoff_seconds = 0.5
        self.staleness_bound_seconds = 1800  # 30 minutes bound (SDD §5.2)

    async def enqueue_and_execute(
        self,
        task_id: str,
        operation_name: str,
        fn: Callable[[], Any],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes operation with exponential backoff retry.
        Handles transient 429 and 5xx errors per SDD §5.2 & §5.5.
        """
        now = time.time()
        attempt = 0
        backoff = self.initial_backoff_seconds

        while attempt <= self.max_retries:
            # Check staleness bound (30 minutes)
            if (time.time() - now) > self.staleness_bound_seconds:
                dlq_record = {
                    "taskId": task_id,
                    "operation": operation_name,
                    "reason": "STALE_INTENT",
                    "payload": payload,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }
                self.dlq.append(dlq_record)
                raise HTTPException(
                    status_code=504,
                    detail="Task discarded due to 30-minute staleness bound. Manual submission required."
                )

            try:
                result = await fn()
                return result
            except HTTPException as e:
                # Retry on 429, 500, 503
                if e.status_code in (429, 500, 503) and attempt < self.max_retries:
                    attempt += 1
                    retry_after = e.headers.get("Retry-After") if e.headers else None
                    sleep_time = float(retry_after) if retry_after else backoff
                    await asyncio.sleep(min(sleep_time, 2.0))  # cap in tests
                    backoff *= 2.0
                else:
                    if attempt >= self.max_retries:
                        self.dlq.append({
                            "taskId": task_id,
                            "operation": operation_name,
                            "reason": f"RETRIES_EXHAUSTED_{e.status_code}",
                            "payload": payload,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        })
                    raise e
            except Exception as ex:
                if attempt < self.max_retries:
                    attempt += 1
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                else:
                    self.dlq.append({
                        "taskId": task_id,
                        "operation": operation_name,
                        "reason": f"EXCEPTION_{type(ex).__name__}",
                        "payload": payload,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    })
                    raise ex

        raise HTTPException(status_code=503, detail="Task retry budget exhausted.")


tasks_buffer = CloudTasksBuffer()
