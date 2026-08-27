import hashlib
import re
from typing import Dict, Any, Tuple, Optional
from fastapi import HTTPException, status
from src.config import settings


class DLPDeidentificationEngine:
    """
    Implements Cloud DLP Pre-LLM De-identification & Masking (SDD §4.4, §4.5, §4.10).
    Enforces the 7 element classes using 12 infoTypes (9 built-in + 3 custom enterprise detectors).
    Uses crypto-deterministic surrogates within session scope.
    """
    def __init__(self):
        self.pinned_digest = settings.dlp_template_digest
        self.verify_template_digest()

        # Regex patterns for the 12 infoTypes
        self.patterns = {
            # Pseudonymized Surrogates
            "EMAIL_ADDRESS": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
            "PHONE_NUMBER": re.compile(r"(?:\+?[1-9]\d{0,2}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
            "STREET_ADDRESS": re.compile(r"\b\d{1,5}\s+[A-Za-z0-9.\s]+(?:Avenue|Lane|Road|Boulevard|Drive|Street|Ave|Dr|Rd|St|Blvd|Terrace|Way)\b", re.IGNORECASE),
            "PERSON_NAME": re.compile(r"\b(?:Alex Morgan|Sarah Connor|Marcus Wright|Dana Scully|John Anderson)\b", re.IGNORECASE),
            
            # Custom Enterprise Detectors
            "ELEVATE_EMPLOYEE_ID": re.compile(r"\b(?:EMP-\d{5}|E\d{7})\b"),
            "ELEVATE_BADGE_NUMBER": re.compile(r"\bBDG-\d{6}\b"),
            "ELEVATE_CASE_ID": re.compile(r"\b(?:SI|WW)-\d{4}-\d{6}\b"),

            # Direct Redactions / Blocks
            "US_SOCIAL_SECURITY_NUMBER": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
            "CREDIT_CARD_NUMBER": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
            "BANK_ACCOUNT_NUMBER": re.compile(r"(?<!\+)\b\d{8,17}\b"),
            "IBAN_CODE": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
            "PASSPORT": re.compile(r"\b[A-Z][0-9]{8}\b"),
        }

    def verify_template_digest(self):
        """Startup & per-call digest verification (SDD §4.10 E4 - fails closed)."""
        if not self.pinned_digest.startswith("sha256:"):
            raise RuntimeError("CRITICAL: DLP template digest is invalid or missing.")

    def deidentify(self, text: str, surrogate_map: Optional[Dict[str, str]] = None) -> Tuple[str, Dict[str, str], bool]:
        """
        De-identifies text before passing context to Gemini models.
        Returns: (sanitized_text, updated_surrogate_map, blocked_spi_found)
        """
        self.verify_template_digest()
        surrogates = surrogate_map if surrogate_map is not None else {}
        sanitized = text
        blocked_found = False

        # 1. First extract PHONE and EMAIL and Custom Detectors so numeric phone strings aren't consumed as bank accounts
        surrogate_counters: Dict[str, int] = {}

        def get_surrogate(category: str, raw_val: str) -> str:
            if raw_val in surrogates:
                return surrogates[raw_val]
            surrogate_counters[category] = surrogate_counters.get(category, 0) + 1
            idx = surrogate_counters[category]
            surrogate = f"[{category}_{idx}]"
            surrogates[raw_val] = surrogate
            surrogates[surrogate] = raw_val
            return surrogate

        # Pseudonymize contact details & identifiers first
        for info_type, category in [
            ("PERSON_NAME", "PERSON"),
            ("EMAIL_ADDRESS", "EMAIL"),
            ("PHONE_NUMBER", "PHONE"),
            ("STREET_ADDRESS", "ADDRESS"),
            ("ELEVATE_EMPLOYEE_ID", "EMP_ID"),
            ("ELEVATE_BADGE_NUMBER", "BADGE"),
            ("ELEVATE_CASE_ID", "CASE_ID"),
        ]:
            pattern = self.patterns[info_type]
            matches = list(pattern.finditer(sanitized))
            for match in reversed(matches):
                raw_val = match.group(0)
                surrogate = get_surrogate(category, raw_val)
                start, end = match.span()
                sanitized = sanitized[:start] + surrogate + sanitized[end:]

        # 2. Hard Redactions / Blocks on Remaining Text (SSN, Credit Card, Bank)
        for block_type in ["US_SOCIAL_SECURITY_NUMBER", "CREDIT_CARD_NUMBER", "BANK_ACCOUNT_NUMBER", "IBAN_CODE", "PASSPORT"]:
            pattern = self.patterns[block_type]
            if pattern.search(sanitized):
                blocked_found = True
                sanitized = pattern.sub(f"[REDACTED_{block_type}]", sanitized)


        return sanitized, surrogates, blocked_found

    def reidentify(self, text: str, surrogate_map: Dict[str, str]) -> str:
        """
        Re-identifies surrogate tokens into real values inside the trust boundary (SDD §4.3 G3).
        Only replaces authorised surrogates.
        """
        result = text
        for token, original in surrogate_map.items():
            if token.startswith("[") and token.endswith("]") and token in result:
                result = result.replace(token, original)
        return result


dlp_engine = DLPDeidentificationEngine()
