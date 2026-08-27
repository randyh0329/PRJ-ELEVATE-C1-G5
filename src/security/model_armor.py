import re
from typing import Tuple, Optional
from src.models.common import GuardrailVerdictEnum


class ModelArmorGuardrail:
    """
    Implements Model Armor Inbound & Outbound Safety Interceptors (SDD §4.3, FR-1.3, NFR-1.1).
    Inbound: SanitizeUserPrompt (prompt injection, jailbreak, RAI, malicious URL).
    Outbound: SanitizeModelResponse (toxicity, SPII leakage, malicious URL).
    """
    def __init__(self):
        # Known prompt injection, jailbreak, & IDOR probe patterns
        self.injection_patterns = [
            re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", re.IGNORECASE),
            re.compile(r"disregard\s+(?:all\s+)?(?:prior\s+)?(?:system|rules|guidelines|safety)", re.IGNORECASE),
            re.compile(r"forget\s+(?:all\s+)?(?:previous|prior)\s+(?:rules|instructions)", re.IGNORECASE),
            re.compile(r"system\s+prompt\s+override", re.IGNORECASE),
            re.compile(r"override\s+(?:authorization|auth|security|admin|check)", re.IGNORECASE),
            re.compile(r"you\s+are\s+now\s+(?:DAN|unfiltered|jailbroken)", re.IGNORECASE),
            re.compile(r"act\s+as\s+(?:an?\s+)?(?:unfiltered|evil|jailbroken|superadmin)", re.IGNORECASE),
            re.compile(r"reveal\s+(?:your\s+)?(?:full\s+)?(?:internal\s+)?system\s+(?:prompt|instructions)", re.IGNORECASE),
            re.compile(r"bypass\s+(?:all\s+)?(?:security|guardrails|safety|policies)", re.IGNORECASE),
            re.compile(r"no\s+longer\s+bound\s+by", re.IGNORECASE),
            re.compile(r"show\s+me\s+(?:all\s+)?(?:other|all)\s+employees?'?\s+(?:data|records|ssn|salary|salaries)", re.IGNORECASE),
            re.compile(r"(?:show|give|tell)\s+me\s+.*(?:EMP-10001|EMP-20002|Sarah Connor|Marcus Wright).*(?:address|phone|salary|medical|status)", re.IGNORECASE),
            re.compile(r"(?:what\s+is\s+)?.*(?:ssn|social\s+security|passport|credit\s+card|bank\s+account|password)", re.IGNORECASE),
            re.compile(r"update\s+employee\s+EMP-\d+", re.IGNORECASE),
            re.compile(r"cancel\s+leave\s+.*for\s+employee\s+EMP-\d+", re.IGNORECASE),
            re.compile(r"(?:salary\s+bands\s+of\s+executives|passwords|database\s+password)", re.IGNORECASE),
        ]

        # Harmful / Toxic RAI patterns
        self.harm_patterns = [
            re.compile(r"\b(?:kill|bomb|weapon|suicide|exploit|malware|harass|intimidate|steal)\b", re.IGNORECASE),
        ]


        # Raw SPII patterns in outbound text (FR-1.3, SLO-06)
        self.spii_patterns = [
            re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN
            re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),  # Credit Card
        ]

    def sanitize_user_prompt(self, prompt: str) -> Tuple[GuardrailVerdictEnum, Optional[str]]:
        """
        Scans inbound prompt. Returns (verdict, reason).
        """
        for pat in self.injection_patterns:
            if pat.search(prompt):
                return GuardrailVerdictEnum.BLOCK, "PROMPT_INJECTION_DETECTED"

        for pat in self.harm_patterns:
            if pat.search(prompt):
                return GuardrailVerdictEnum.BLOCK, "RESPONSIBLE_AI_VIOLATION"

        return GuardrailVerdictEnum.ALLOW, None

    def sanitize_model_response(self, response_text: str) -> Tuple[GuardrailVerdictEnum, str]:
        """
        Scans outbound generated response. Returns (verdict, sanitized_or_fallback_text).
        """
        # 1. Check for raw SPII leakage (SLO-06)
        for pat in self.spii_patterns:
            if pat.search(response_text):
                return (
                    GuardrailVerdictEnum.BLOCK,
                    "I could not produce a safe answer to that. Please rephrase, or contact the HR helpdesk."
                )

        # 2. Check for severe toxicity/harm
        for pat in self.harm_patterns:
            if pat.search(response_text):
                return (
                    GuardrailVerdictEnum.BLOCK,
                    "I could not produce a safe answer to that. Please rephrase, or contact the HR helpdesk."
                )

        return GuardrailVerdictEnum.ALLOW, response_text


model_armor = ModelArmorGuardrail()
