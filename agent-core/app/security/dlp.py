"""
Cloud DLP Pre-LLM De-identification and Re-identification Interceptor.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §4.3, §4.4, §4.5 (FR-1.3, NFR-1.1).
"""

from __future__ import annotations

import re
from typing import Dict, Tuple


class CloudDLPInterceptor:
    """
    Performs deterministic Pre-LLM PII/SPII de-identification and trust-boundary re-identification.
    Enforces §4.4 element classes and §4.5 infoType rules.
    """

    PATTERNS = {
        "EMAIL": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        "PHONE": r"(\+?[1-9]\d{1,14}|\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b)",
        "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
        "STREET_ADDRESS": r"\b\d{1,5}\s+[A-Za-z0-9.\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Way)\b",
    }

    def deidentify(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        De-identifies sensitive user input before feeding to the LLM.
        Returns:
            (masked_text, surrogate_to_original_map)
        """
        surrogate_map: Dict[str, str] = {}
        masked_text = text

        for info_type, regex in self.PATTERNS.items():
            counter = 1
            for match in re.finditer(regex, masked_text, flags=re.IGNORECASE):
                val = match.group(0)
                # Ignore if already masked
                if val.startswith("[") and val.endswith("]"):
                    continue
                surrogate = f"[{info_type}_{counter}]"
                surrogate_map[surrogate] = val
                masked_text = masked_text.replace(val, surrogate, 1)
                counter += 1

        return masked_text, surrogate_map

    def reidentify(self, response_text: str, surrogate_map: Dict[str, str]) -> str:
        """
        Re-identifies surrogate tokens back into original values within the security trust boundary.
        """
        reidentified = response_text
        for surrogate, original in surrogate_map.items():
            reidentified = reidentified.replace(surrogate, original)
        return reidentified
