import asyncio
import math
import random
import time
from typing import Dict, Any, Optional
import yaml
from fastapi import Request, HTTPException, status
from src.config import settings


class MockFidelityEngine:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or (settings.mocks_dir / "fidelity-profile.yaml")
        self.profile = "integration-test"
        self.latency_config: Dict[str, Any] = {}
        self.faults_config: Dict[str, Any] = {}
        self.rate_limit_config: Dict[str, Any] = {}
        self.idempotency_cache: Dict[str, Dict[str, Any]] = {}
        self.rate_limit_tokens: float = 50.0
        self.last_token_refill: float = time.time()
        self.load_profile()

    def load_profile(self):
        try:
            if self.config_path.exists():
                with open(self.config_path, "r") as f:
                    data = yaml.safe_load(f)
                    spec = data.get("spec", {})
                    self.profile = data.get("metadata", {}).get("profile", "integration-test")
                    self.latency_config = spec.get("latency", {})
                    self.faults_config = spec.get("faults", {})
                    self.rate_limit_config = spec.get("rate_limit", {})
                    self.rate_limit_tokens = float(self.rate_limit_config.get("burst", 100))
        except Exception:
            self.profile = "unit"

    def set_profile(self, profile_name: str):
        self.profile = profile_name

    async def apply_fidelity(self, request: Request, operation_id: str):
        # 1. Deterministic Fault Triggers via Header
        test_fault = request.headers.get("X-Test-Fault")
        if test_fault:
            if test_fault == "429":
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="WorkWeek rate limit exceeded. Retry after 30s.",
                    headers={"Retry-After": "30"}
                )
            elif test_fault == "503-permanent" or test_fault == "503":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Backend service temporarily unavailable."
                )
            elif test_fault == "500":
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal server error in backend system."
                )

        # In unit profile, bypass latency, probabilistic faults, and rate limits
        if self.profile == "unit":
            return

        # 2. Token Bucket Rate Limiting
        now = time.time()
        sustained_rps = self.rate_limit_config.get("sustained_rps", 50)
        burst = self.rate_limit_config.get("burst", 100)
        elapsed = now - self.last_token_refill
        self.rate_limit_tokens = min(burst, self.rate_limit_tokens + elapsed * sustained_rps)
        self.last_token_refill = now

        if self.rate_limit_tokens < 1.0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Too many requests.",
                headers={"Retry-After": "30"}
            )
        self.rate_limit_tokens -= 1.0

        # 3. Probabilistic Fault Injection
        injections = self.faults_config.get("injection", {})
        if injections:
            rand_val = random.random()
            cumulative = 0.0
            for fault_type, prob in injections.items():
                cumulative += prob
                if rand_val < cumulative:
                    if fault_type == "http_429":
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="WorkWeek rate limit exceeded.",
                            headers={"Retry-After": "30"}
                        )
                    elif fault_type in ("http_500", "http_503"):
                        code = 500 if fault_type == "http_500" else 503
                        raise HTTPException(status_code=code, detail="Simulated downstream backend failure.")
                    elif fault_type == "timeout":
                        await asyncio.sleep(3.5)
                        raise HTTPException(status_code=504, detail="Gateway timeout.")
                    break

        # 4. Latency Distribution
        percentiles = self.latency_config.get("percentiles_ms", {"p50": 180, "p95": 900, "p99": 2500})
        p50 = percentiles.get("p50", 180)
        # Sample lightweight latency for test responsiveness
        sleep_ms = max(5, int(random.gauss(p50 * 0.1, 10)))
        await asyncio.sleep(sleep_ms / 1000.0)

    def check_and_record_idempotency(self, idempotency_key: Optional[str], response_payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if not idempotency_key:
            return None
        if idempotency_key in self.idempotency_cache:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate transaction detected. Idempotency key already executed."
            )
        if response_payload is not None:
            self.idempotency_cache[idempotency_key] = {
                "response": response_payload,
                "recorded_at": time.time()
            }
        return None

    def record_idempotency_result(self, idempotency_key: Optional[str], response_payload: Dict[str, Any]):
        if idempotency_key:
            self.idempotency_cache[idempotency_key] = {
                "response": response_payload,
                "recorded_at": time.time()
            }

    def clear(self):
        self.idempotency_cache.clear()
        self.rate_limit_tokens = float(self.rate_limit_config.get("burst", 100))
        self.last_token_refill = time.time()


fidelity_engine = MockFidelityEngine()
