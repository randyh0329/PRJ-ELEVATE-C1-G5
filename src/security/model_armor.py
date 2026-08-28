"""
Google Cloud Model Armor Inbound and Outbound Safety Sanitizer.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §4.3, §4.5, §4.9, §5.5, §7.5 (FR-1.3, NFR-1.1, NFR-2.1, ALRT-08).
"""

from __future__ import annotations

import collections
import logging
import os
import re
import shutil
import subprocess
import time
from typing import Any, ClassVar, Literal

import httpx
from pydantic import BaseModel, Field

from config.settings import get_settings

logger = logging.getLogger("security.model_armor")


class ModelArmorResult(BaseModel):
    """Structured inspection verdict from Model Armor."""
    is_safe: bool = True
    verdict: Literal["ALLOW", "BLOCK"] = "ALLOW"
    refusal_message: str | None = None
    threat_category: str | None = None
    processing_time_ms: float = 0.0
    filter_details: dict[str, Any] = Field(default_factory=dict)
    deadline_exceeded: bool = False
    circuit_breaker_tripped: bool = False

    def __iter__(self):
        """Enable backward-compatible tuple unpacking: `verdict, refusal_msg = res`."""
        yield self.verdict
        yield self.refusal_message


class SafetyCircuitBreaker:
    """
    Sliding-window circuit breaker for safety dependencies (§4.3, §7.5 ALRT-08).
    Trips to OPEN into fail-closed degraded mode when error or timeout rate > threshold.
    """

    def __init__(self, window_seconds: int = 300, error_threshold: float = 0.02, min_samples: int = 5) -> None:
        self.window_seconds = window_seconds
        self.error_threshold = error_threshold
        self.min_samples = min_samples
        self._events: collections.deque[tuple[float, bool]] = collections.deque()
        self._state: Literal["CLOSED", "OPEN", "HALF_OPEN"] = "CLOSED"
        self._opened_at: float = 0.0

    def record_success(self) -> None:
        now = time.time()
        self._cleanup(now)
        self._events.append((now, True))
        if self._state == "HALF_OPEN":
            self._state = "CLOSED"
            logger.info("Safety circuit breaker recovered: state is now CLOSED.")

    def record_failure(self, is_deadline: bool = False) -> None:
        now = time.time()
        self._cleanup(now)
        self._events.append((now, False))
        fail_rate = self.failure_rate(now)
        if len(self._events) >= self.min_samples and fail_rate > self.error_threshold:
            if self._state != "OPEN":
                self._state = "OPEN"
                self._opened_at = now
                logger.error(
                    "ALRT-08: Safety circuit breaker TRIPPED to OPEN (failure rate: %.2f%% > %.2f%% threshold). "
                    "Entering fail-closed degraded mode.",
                    fail_rate * 100.0,
                    self.error_threshold * 100.0,
                )

    def is_open(self) -> bool:
        now = time.time()
        self._cleanup(now)
        if self._state == "OPEN":
            # Test recovery after window has passed
            if now - self._opened_at > self.window_seconds:
                self._state = "HALF_OPEN"
                logger.info("Safety circuit breaker entered HALF_OPEN state.")
                return False
            return True
        return False

    def failure_rate(self, now: float | None = None) -> float:
        current_time = now or time.time()
        self._cleanup(current_time)
        if not self._events:
            return 0.0
        failures = sum(1 for _, success in self._events if not success)
        return failures / len(self._events)

    def _cleanup(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def reset(self) -> None:
        """Reset breaker for testing."""
        self._events.clear()
        self._state = "CLOSED"
        self._opened_at = 0.0


class LocalModelArmorStandin:
    """
    High-fidelity local stand-in and fallback classifier (§4.3, DEP-09).
    Detects adversarial prompts, jailbreaks, RAI violations, and outbound data leakage.
    """

    ADVERSARIAL_PATTERNS: ClassVar[list[tuple[re.Pattern[str], str]]] = [
        (re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE), "PROMPT_INJECTION_OR_JAILBREAK"),
        (re.compile(r"system\s+prompt\s+(override|leak|dump|reveal)", re.IGNORECASE), "PROMPT_INJECTION_OR_JAILBREAK"),
        (re.compile(r"override\s+(all\s+)?(system|safety)\s+(rules|prompts|guardrails)", re.IGNORECASE), "PROMPT_INJECTION_OR_JAILBREAK"),
        (re.compile(r"you\s+are\s+now\s+(?:in\s+)?(dan(\s+mode)?|unrestricted|god\s+mode|developer\s+mode)", re.IGNORECASE), "PROMPT_INJECTION_OR_JAILBREAK"),
        (re.compile(r"disregard\s+(all\s+)?guardrails?", re.IGNORECASE), "PROMPT_INJECTION_OR_JAILBREAK"),
        (re.compile(r"disregard\s+(the\s+)?above", re.IGNORECASE), "PROMPT_INJECTION_OR_JAILBREAK"),
        (re.compile(r"reveal\s+(the\s+|your\s+)?(secret\s+key|hidden\s+instructions|system\s+prompt)", re.IGNORECASE), "PROMPT_INJECTION_OR_JAILBREAK"),
        (re.compile(r"bypass\s+security\s+controls?", re.IGNORECASE), "PROMPT_INJECTION_OR_JAILBREAK"),
        (re.compile(r"base64\s*(decode|payload|eval)", re.IGNORECASE), "PROMPT_INJECTION_OR_JAILBREAK"),
        (re.compile(r"<!--\s*system_override\s*-->", re.IGNORECASE), "PROMPT_INJECTION_OR_JAILBREAK"),
        (re.compile(r"(?:how\s+to\s+)?(?:build|make|create)\s+(?:a\s+|an\s+)?(?:bomb|weapon|explosive|chemical)", re.IGNORECASE), "RESPONSIBLE_AI_DANGEROUS_CONTENT"),
        (re.compile(r"explosive\s+device", re.IGNORECASE), "RESPONSIBLE_AI_DANGEROUS_CONTENT"),
    ]

    UNSAFE_OUTPUT_PATTERNS: ClassVar[list[tuple[re.Pattern[str], str]]] = [
        (re.compile(r"BEGIN\s+(RSA|OPENSSH|EC|DSA|PGP)?\s*PRIVATE\s+KEY", re.IGNORECASE), "PRIVATE_KEY_LEAK"),
        (re.compile(r"(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{16,}['\"]?", re.IGNORECASE), "CREDENTIAL_LEAK"),
        (re.compile(r"password\s*[:=]\s*['\"]?\S+['\"]?", re.IGNORECASE), "PASSWORD_LEAK"),
        (re.compile(r"DROP\s+TABLE\s+", re.IGNORECASE), "SQL_DESTRUCTIVE_STATEMENT"),
        (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "UNMASKED_SSN_LEAK"),
        (re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"), "UNMASKED_CREDIT_CARD_LEAK"),
    ]

    def scan_prompt(self, prompt: str) -> tuple[bool, str | None, str | None]:
        for pattern, threat_type in self.ADVERSARIAL_PATTERNS:
            if pattern.search(prompt):
                return False, threat_type, "I am unable to process this request as it falls outside acceptable corporate usage policies."
        return True, None, None

    def scan_response(self, response_text: str) -> tuple[bool, str | None, str | None]:
        for pattern, threat_type in self.UNSAFE_OUTPUT_PATTERNS:
            if pattern.search(response_text):
                return False, threat_type, "I could not produce a safe answer to that request. Please contact the HR helpdesk directly."
        return True, None, None


class LiveModelArmorClient:
    """
    Live Google Cloud Model Armor REST Client (§4.3, §4.9).
    Interacts with Model Armor sanitizeUserPrompt and sanitizeModelResponse API endpoints.
    """

    def __init__(self, project_id: str, location: str, user_template_id: str, model_template_id: str) -> None:
        self.project_id = project_id
        self.location = location
        self.user_template_id = user_template_id
        self.model_template_id = model_template_id
        self._cached_token: str | None = None
        self._token_expiry: float = 0.0
        self._http_client = httpx.Client(timeout=10.0)

    def _get_auth_token(self) -> str:
        now = time.time()
        if self._cached_token and now < self._token_expiry:
            return self._cached_token

        env_token = os.environ.get("VERTEX_AI_TOKEN") or os.environ.get("GCP_ACCESS_TOKEN")
        if env_token:
            self._cached_token = env_token
            self._token_expiry = now + 3600
            return env_token

        try:
            with httpx.Client(timeout=1.0) as client:
                res = client.get(
                    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
                    headers={"Metadata-Flavor": "Google"},
                )
                if res.status_code == 200:
                    data = res.json()
                    token = data.get("access_token")
                    if token:
                        self._cached_token = token
                        self._token_expiry = now + data.get("expires_in", 3600) - 60
                        return token
        except Exception:
            pass

        candidate_paths = [
            shutil.which("gcloud"),
            os.path.expanduser("~/google-cloud-sdk/bin/gcloud"),
            "/usr/bin/gcloud",
        ]
        gcloud_bin = next((p for p in candidate_paths if p and os.path.isfile(p) and os.access(p, os.X_OK)), None)
        if gcloud_bin:
            try:
                proc = subprocess.run(
                    [gcloud_bin, "auth", "print-access-token"],
                    capture_output=True,
                    text=True,
                    timeout=4.0,
                    check=False,
                )
                if proc.returncode == 0:
                    lines = [l.strip() for l in proc.stdout.splitlines() if l.strip() and not l.startswith("WARNING")]
                    if lines:
                        self._cached_token = lines[-1]
                        self._token_expiry = now + 3300
                        return lines[-1]
            except Exception:
                pass

        raise PermissionError("Unable to acquire Google Cloud authentication token for Model Armor.")

    def sanitize_user_prompt(self, prompt: str, timeout_seconds: float = 0.15) -> dict[str, Any]:
        """Calls Google Cloud Model Armor sanitizeUserPrompt REST API."""
        token = self._get_auth_token()
        url = (
            f"https://modelarmor.{self.location}.rep.googleapis.com/v1/projects/{self.project_id}/"
            f"locations/{self.location}/templates/{self.user_template_id}:sanitizeUserPrompt"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {"userPromptData": {"text": prompt}}
        resp = self._http_client.post(url, json=payload, headers=headers, timeout=timeout_seconds)
        if resp.status_code != 200:
            raise RuntimeError(f"Model Armor API error: {resp.status_code} {resp.text}")
        return resp.json()

    def sanitize_model_response(self, response_text: str, timeout_seconds: float = 0.15) -> dict[str, Any]:
        """Calls Google Cloud Model Armor sanitizeModelResponse REST API."""
        token = self._get_auth_token()
        url = (
            f"https://modelarmor.{self.location}.rep.googleapis.com/v1/projects/{self.project_id}/"
            f"locations/{self.location}/templates/{self.model_template_id}:sanitizeModelResponse"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {"modelResponseData": {"text": response_text}}
        resp = self._http_client.post(url, json=payload, headers=headers, timeout=timeout_seconds)
        if resp.status_code != 200:
            raise RuntimeError(f"Model Armor API error: {resp.status_code} {resp.text}")
        return resp.json()


class ModelArmorSanitizer:
    """
    Unified Model Armor Service managing Inbound Prompt and Outbound Response sanitization.
    Compliant with SDD §4.3, §4.5, §5.5, §7.5 (FR-1.3, NFR-1.1, NFR-2.1, ALRT-08).
    """

    DEFAULT_INBOUND_REFUSAL = "I am unable to process this request as it falls outside acceptable corporate usage policies."
    DEFAULT_OUTBOUND_REFUSAL = "I could not produce a safe answer to that request. Please contact the HR helpdesk directly."

    def __init__(
        self,
        use_live_service: bool | None = None,
        circuit_breaker: SafetyCircuitBreaker | None = None,
        local_standin: LocalModelArmorStandin | None = None,
    ) -> None:
        settings = get_settings()
        self.use_live = (
            use_live_service
            if use_live_service is not None
            else getattr(settings, "USE_LIVE_MODEL_ARMOR", False)
        )
        self.circuit_breaker = circuit_breaker or SafetyCircuitBreaker(
            window_seconds=300,
            error_threshold=getattr(settings, "MODEL_ARMOR_CIRCUIT_BREAKER_RATE", 0.02),
        )
        self.local_standin = local_standin or LocalModelArmorStandin()
        self.project_id = getattr(settings, "PROJECT_ID", "pe-group5")
        self.location = getattr(settings, "REGION", "us-central1")
        self.user_template = getattr(settings, "MODEL_ARMOR_USER_TEMPLATE", "hr-ingress-template")
        self.model_template = getattr(settings, "MODEL_ARMOR_MODEL_TEMPLATE", "hr-egress-template")

        self._live_client: LiveModelArmorClient | None = None
        if self.use_live:
            try:
                self._live_client = LiveModelArmorClient(
                    project_id=self.project_id,
                    location=self.location,
                    user_template_id=self.user_template,
                    model_template_id=self.model_template,
                )
            except Exception as e:
                logger.warning("Failed to initialize live Model Armor client: %s. Using local standin.", e)

    def sanitize_user_prompt(
        self, prompt: str, timeout_ms: int = 150
    ) -> ModelArmorResult:
        """
        Model Armor SanitizeUserPrompt inspection (§4.3, FR-1.3).
        Runs within 150ms hard deadline and fails closed.
        """
        start_time = time.perf_counter()

        # Check circuit breaker (§7.5 ALRT-08)
        if self.circuit_breaker.is_open():
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ModelArmorResult(
                is_safe=False,
                verdict="BLOCK",
                refusal_message=self.DEFAULT_INBOUND_REFUSAL,
                threat_category="CIRCUIT_BREAKER_OPEN",
                processing_time_ms=round(elapsed_ms, 3),
                circuit_breaker_tripped=True,
            )

        # 1. Live Google Cloud Model Armor Inspection
        if self.use_live and self._live_client:
            try:
                raw_res = self._live_client.sanitize_user_prompt(prompt, timeout_seconds=timeout_ms / 1000.0)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                if elapsed_ms > timeout_ms:
                    logger.warning("ARMOR_IN_DEADLINE: Model Armor inbound call exceeded %d ms (%0.2f ms)", timeout_ms, elapsed_ms)
                    self.circuit_breaker.record_failure(is_deadline=True)
                    return ModelArmorResult(
                        is_safe=False,
                        verdict="BLOCK",
                        refusal_message=self.DEFAULT_INBOUND_REFUSAL,
                        threat_category="ARMOR_IN_DEADLINE",
                        processing_time_ms=round(elapsed_ms, 3),
                        deadline_exceeded=True,
                    )

                sanitization = raw_res.get("sanitizationResult", {})
                match_state = sanitization.get("filterMatchState", "NO_MATCH_FOUND")
                if match_state == "MATCH_FOUND":
                    self.circuit_breaker.record_success()
                    filter_results = sanitization.get("filterResults", {})
                    threat = "PROMPT_INJECTION_OR_JAILBREAK"
                    return ModelArmorResult(
                        is_safe=False,
                        verdict="BLOCK",
                        refusal_message=self.DEFAULT_INBOUND_REFUSAL,
                        threat_category=threat,
                        processing_time_ms=round(elapsed_ms, 3),
                        filter_details=filter_results,
                    )

                self.circuit_breaker.record_success()
                return ModelArmorResult(
                    is_safe=True,
                    verdict="ALLOW",
                    refusal_message=None,
                    threat_category=None,
                    processing_time_ms=round(elapsed_ms, 3),
                    filter_details=sanitization,
                )
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                logger.warning("Live Model Armor Inbound API failed (%s); evaluating local fallback.", e)
                self.circuit_breaker.record_failure()

        # 2. Local High-Fidelity Stand-in Inspection (§4.3, DEP-09)
        is_safe, threat_category, refusal_msg = self.local_standin.scan_prompt(prompt)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        if elapsed_ms > timeout_ms:
            logger.warning("ARMOR_IN_DEADLINE: Local inbound check exceeded %d ms (%0.2f ms)", timeout_ms, elapsed_ms)
            self.circuit_breaker.record_failure(is_deadline=True)
            return ModelArmorResult(
                is_safe=False,
                verdict="BLOCK",
                refusal_message=self.DEFAULT_INBOUND_REFUSAL,
                threat_category="ARMOR_IN_DEADLINE",
                processing_time_ms=round(elapsed_ms, 3),
                deadline_exceeded=True,
            )

        if not is_safe:
            self.circuit_breaker.record_success()
            return ModelArmorResult(
                is_safe=False,
                verdict="BLOCK",
                refusal_message=refusal_msg or self.DEFAULT_INBOUND_REFUSAL,
                threat_category=threat_category or "PROMPT_INJECTION_OR_JAILBREAK",
                processing_time_ms=round(elapsed_ms, 3),
            )

        self.circuit_breaker.record_success()
        return ModelArmorResult(
            is_safe=True,
            verdict="ALLOW",
            refusal_message=None,
            threat_category=None,
            processing_time_ms=round(elapsed_ms, 3),
        )

    def sanitize_model_response(
        self, response_text: str, timeout_ms: int = 150
    ) -> ModelArmorResult:
        """
        Model Armor SanitizeModelResponse inspection (§4.3, FR-1.3).
        Runs within 150ms hard deadline and fails closed.
        """
        start_time = time.perf_counter()

        # Check circuit breaker (§7.5 ALRT-08)
        if self.circuit_breaker.is_open():
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return ModelArmorResult(
                is_safe=False,
                verdict="BLOCK",
                refusal_message=self.DEFAULT_OUTBOUND_REFUSAL,
                threat_category="CIRCUIT_BREAKER_OPEN",
                processing_time_ms=round(elapsed_ms, 3),
                circuit_breaker_tripped=True,
            )

        # 1. Live Google Cloud Model Armor Inspection
        if self.use_live and self._live_client:
            try:
                raw_res = self._live_client.sanitize_model_response(response_text, timeout_seconds=timeout_ms / 1000.0)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                if elapsed_ms > timeout_ms:
                    logger.warning("ARMOR_OUT_DEADLINE: Model Armor outbound call exceeded %d ms (%0.2f ms)", timeout_ms, elapsed_ms)
                    self.circuit_breaker.record_failure(is_deadline=True)
                    return ModelArmorResult(
                        is_safe=False,
                        verdict="BLOCK",
                        refusal_message=self.DEFAULT_OUTBOUND_REFUSAL,
                        threat_category="ARMOR_OUT_DEADLINE",
                        processing_time_ms=round(elapsed_ms, 3),
                        deadline_exceeded=True,
                    )

                sanitization = raw_res.get("sanitizationResult", {})
                match_state = sanitization.get("filterMatchState", "NO_MATCH_FOUND")
                if match_state == "MATCH_FOUND":
                    self.circuit_breaker.record_success()
                    return ModelArmorResult(
                        is_safe=False,
                        verdict="BLOCK",
                        refusal_message=self.DEFAULT_OUTBOUND_REFUSAL,
                        threat_category="UNSAFE_OUTPUT_OR_SPII_LEAK",
                        processing_time_ms=round(elapsed_ms, 3),
                        filter_details=sanitization.get("filterResults", {}),
                    )

                self.circuit_breaker.record_success()
                return ModelArmorResult(
                    is_safe=True,
                    verdict="ALLOW",
                    refusal_message=None,
                    threat_category=None,
                    processing_time_ms=round(elapsed_ms, 3),
                    filter_details=sanitization,
                )
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                logger.warning("Live Model Armor Outbound API failed (%s); evaluating local fallback.", e)
                self.circuit_breaker.record_failure()

        # 2. Local High-Fidelity Stand-in Inspection (§4.3, DEP-09)
        is_safe, threat_category, refusal_msg = self.local_standin.scan_response(response_text)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        if elapsed_ms > timeout_ms:
            logger.warning("ARMOR_OUT_DEADLINE: Local outbound check exceeded %d ms (%0.2f ms)", timeout_ms, elapsed_ms)
            self.circuit_breaker.record_failure(is_deadline=True)
            return ModelArmorResult(
                is_safe=False,
                verdict="BLOCK",
                refusal_message=self.DEFAULT_OUTBOUND_REFUSAL,
                threat_category="ARMOR_OUT_DEADLINE",
                processing_time_ms=round(elapsed_ms, 3),
                deadline_exceeded=True,
            )

        if not is_safe:
            self.circuit_breaker.record_success()
            return ModelArmorResult(
                is_safe=False,
                verdict="BLOCK",
                refusal_message=refusal_msg or self.DEFAULT_OUTBOUND_REFUSAL,
                threat_category=threat_category or "UNSAFE_OUTPUT_OR_SPII_LEAK",
                processing_time_ms=round(elapsed_ms, 3),
            )

        self.circuit_breaker.record_success()
        return ModelArmorResult(
            is_safe=True,
            verdict="ALLOW",
            refusal_message=None,
            threat_category=None,
            processing_time_ms=round(elapsed_ms, 3),
        )


# Global singleton instance
model_armor_sanitizer = ModelArmorSanitizer()

