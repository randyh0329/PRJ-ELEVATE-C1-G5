"""Safety perimeter: Cloud DLP SPII Redactor and Vertex AI Model Armor filter."""
import re
import time
from typing import ClassVar

from pydantic import BaseModel


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
    """Simulates Vertex AI Model Armor for prompt injection & jailbreak prevention."""

    # Adversarial & Jailbreak patterns
    INJECTION_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+(DAN|unrestricted|god\s+mode)", re.IGNORECASE),
        re.compile(r"override\s+(all\s+)?(system|safety)\s+(rules|prompts|guardrails)", re.IGNORECASE),
        re.compile(r"reveal\s+(your\s+)?(system\s+prompt|hidden\s+instructions)", re.IGNORECASE),
        re.compile(r"disregard\s+(the\s+)?above", re.IGNORECASE),
        re.compile(r"bypass\s+security\s+controls?", re.IGNORECASE),
    ]

    def scan_prompt(self, prompt: str) -> SafetyScanResult:
        """Scan inbound user prompt for prompt injections and malicious overrides."""
        start_time = time.perf_counter()

        for pattern in self.INJECTION_PATTERNS:
            if pattern.search(prompt):
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                return SafetyScanResult(
                    is_safe=False,
                    refusal_reason="I cannot process this request as it violates enterprise AI safety policies.",
                    threat_category="PROMPT_INJECTION_OR_JAILBREAK",
                    processing_time_ms=round(duration_ms, 3)
                )

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return SafetyScanResult(
            is_safe=True,
            refusal_reason=None,
            threat_category=None,
            processing_time_ms=round(duration_ms, 3)
        )


# Global singleton instances
dlp_redactor = DLPRedactor()
model_armor = ModelArmor()
