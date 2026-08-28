"""Safety perimeter: Cloud DLP SPII Redactor and Google Cloud Model Armor filter."""
import re
import time
from typing import ClassVar

from pydantic import BaseModel, Field

from src.security.model_armor import ModelArmorResult, ModelArmorSanitizer, model_armor_sanitizer


class RedactionResult(BaseModel):
    """Result of DLP sanitization."""
    sanitized_text: str
    original_text: str
    detected_types: list[str]
    processing_time_ms: float


class SafetyScanResult(BaseModel):
    """Result of Model Armor input/output inspection."""
    is_safe: bool
    refusal_reason: str | None = None
    threat_category: str | None = None
    processing_time_ms: float
    verdict: str = "ALLOW"
    filter_details: dict = Field(default_factory=dict)
    deadline_exceeded: bool = False
    circuit_breaker_tripped: bool = False


class DLPRedactor:
    """Simulates Cloud DLP Streaming Proxy for sub-15ms real-time SPII redaction."""

    # Regex patterns for high-risk SPII
    NRIC_PATTERN = re.compile(r"\b[STFGM]\d{7}[A-Z]\b", re.IGNORECASE)
    SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{4}\b")
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

    def redact(self, text: str) -> RedactionResult:
        """De-identify sensitive SPII into typed surrogate tokens."""
        start_time = time.perf_counter()
        detected_types: list[str] = []
        sanitized = text

        # 1. Singapore NRIC / FIN
        if self.NRIC_PATTERN.search(sanitized):
            detected_types.append("SINGAPORE_NRIC")
            sanitized = self.NRIC_PATTERN.sub("[REDACTED_NRIC]", sanitized)

        # 2. US Social Security Number
        if self.SSN_PATTERN.search(sanitized):
            detected_types.append("US_SSN")
            sanitized = self.SSN_PATTERN.sub("[REDACTED_SSN]", sanitized)

        # 3. Email addresses
        if self.EMAIL_PATTERN.search(sanitized):
            detected_types.append("EMAIL_ADDRESS")
            sanitized = self.EMAIL_PATTERN.sub("[REDACTED_CONTACT_INFO]", sanitized)

        # 4. Phone numbers
        if self.PHONE_PATTERN.search(sanitized):
            detected_types.append("PHONE_NUMBER")
            sanitized = self.PHONE_PATTERN.sub("[REDACTED_CONTACT_INFO]", sanitized)

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return RedactionResult(
            sanitized_text=sanitized,
            original_text=text,
            detected_types=detected_types,
            processing_time_ms=round(duration_ms, 3)
        )


class ModelArmor:
    """Adapter wrapping ModelArmorSanitizer for prompt and response safety screening."""

    def __init__(self, sanitizer: ModelArmorSanitizer | None = None) -> None:
        self._sanitizer = sanitizer or model_armor_sanitizer

    def scan_prompt(self, prompt: str, timeout_ms: int = 150) -> SafetyScanResult:
        """Scan inbound user prompt for prompt injections and malicious overrides."""
        res: ModelArmorResult = self._sanitizer.sanitize_user_prompt(prompt, timeout_ms=timeout_ms)
        return SafetyScanResult(
            is_safe=res.is_safe,
            refusal_reason=res.refusal_message,
            threat_category=res.threat_category,
            processing_time_ms=res.processing_time_ms,
            verdict=res.verdict,
            filter_details=res.filter_details,
            deadline_exceeded=res.deadline_exceeded,
            circuit_breaker_tripped=res.circuit_breaker_tripped,
        )

    def scan_response(self, response_text: str, timeout_ms: int = 150) -> SafetyScanResult:
        """Scan outbound model response for toxicity, credentials, and data leakage."""
        res: ModelArmorResult = self._sanitizer.sanitize_model_response(response_text, timeout_ms=timeout_ms)
        return SafetyScanResult(
            is_safe=res.is_safe,
            refusal_reason=res.refusal_message,
            threat_category=res.threat_category,
            processing_time_ms=res.processing_time_ms,
            verdict=res.verdict,
            filter_details=res.filter_details,
            deadline_exceeded=res.deadline_exceeded,
            circuit_breaker_tripped=res.circuit_breaker_tripped,
        )

    def sanitize_user_prompt(self, prompt: str, timeout_ms: int = 150) -> ModelArmorResult:
        return self._sanitizer.sanitize_user_prompt(prompt, timeout_ms=timeout_ms)

    def sanitize_model_response(self, response_text: str, timeout_ms: int = 150) -> ModelArmorResult:
        return self._sanitizer.sanitize_model_response(response_text, timeout_ms=timeout_ms)


# Global singleton instances
dlp_redactor = DLPRedactor()
model_armor = ModelArmor()

