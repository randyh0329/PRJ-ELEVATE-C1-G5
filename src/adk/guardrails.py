"""
ADK Security Guardrails and Middleware Hooks.
Enforces DLP PII Redaction, Model Armor Threat Scanning, and Audit Logging per SDD §5.5.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.core.safety import DLPRedactor, ModelArmor, dlp_redactor, model_armor
from src.telemetry.audit_logger import AuditLogger, audit_logger

logger = logging.getLogger("adk.guardrails")


@dataclass
class GuardrailResult:
    """Outcome of pre-execution guardrail evaluation."""
    is_safe: bool
    sanitized_prompt: str
    original_prompt: str
    refusal_reason: str | None = None
    threat_category: str | None = None
    detected_pii: list[str] = field(default_factory=list)
    dlp_latency_ms: float = 0.0
    armor_latency_ms: float = 0.0


class ADKGuardrailsPipeline:
    """Pre- and Post-execution guardrail pipeline for ADK Agents."""

    def __init__(
        self,
        dlp: DLPRedactor | None = None,
        armor: ModelArmor | None = None,
        logger_instance: AuditLogger | None = None
    ) -> None:
        self.dlp = dlp or dlp_redactor
        self.armor = armor or model_armor
        self.audit = logger_instance or audit_logger

    def evaluate_ingress(self, prompt: str, caller_id: str = "EMP-1001") -> GuardrailResult:
        """
        Executes Ingress Stage 1 (<120ms):
        1. Cloud DLP PII Redaction / Masking
        2. Vertex AI Model Armor Prompt Injection / Jailbreak scanning
        """
        # 1. DLP Scan
        dlp_res = self.dlp.redact(prompt)
        sanitized = dlp_res.sanitized_text

        # 2. Model Armor Threat Scan
        armor_res = self.armor.scan_prompt(sanitized)
        if not armor_res.is_safe:
            self.audit.log_event(
                caller_employee_id=caller_id,
                action_type="SAFETY_VIOLATION_BLOCKED",
                status="REFUSED",
                details={
                    "reason": armor_res.refusal_reason,
                    "threat": armor_res.threat_category,
                    "raw_prompt": sanitized[:200]
                }
            )
            return GuardrailResult(
                is_safe=False,
                sanitized_prompt=sanitized,
                original_prompt=prompt,
                refusal_reason=armor_res.refusal_reason or "Request blocked by safety guardrails.",
                threat_category=armor_res.threat_category,
                detected_pii=dlp_res.detected_types,
                dlp_latency_ms=dlp_res.processing_time_ms,
                armor_latency_ms=armor_res.processing_time_ms
            )

        return GuardrailResult(
            is_safe=True,
            sanitized_prompt=sanitized,
            original_prompt=prompt,
            detected_pii=dlp_res.detected_types,
            dlp_latency_ms=dlp_res.processing_time_ms,
            armor_latency_ms=armor_res.processing_time_ms
        )

    def log_egress(
        self,
        caller_id: str,
        action_type: str,
        status: str,
        details: dict[str, Any] | None = None
    ) -> None:
        """Log structured audit trail event."""
        self.audit.log_event(
            caller_employee_id=caller_id,
            action_type=action_type,
            status=status,
            details=details or {}
        )


# Global instance
adk_guardrails = ADKGuardrailsPipeline()
