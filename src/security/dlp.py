"""Cloud DLP Pre-LLM De-identification and Re-identification Interceptor.

Compliant with Enterprise Agentic Solution Design Document (MVP 1) §4.3, §4.4,
§4.5 (FR-1.3, FR-1.4, NFR-1.1).

This is the local stand-in for the managed `deidentifyTemplate` in §4.5. It
implements the same two transformation classes over the same twelve infoType
detectors, so that a test asserting "no raw value survives" is asserting against
the shape the real template enforces:

* **`replaceWithInfoTypeConfig`** - irreversible. §4.4 classifies SSN, card and
  bank data as *blocked in this channel*, not pseudonymised. These values never
  enter the surrogate map, so `reidentify` physically cannot put them back.
* **`cryptoDeterministicConfig`** - reversible pseudonyms. Names, contact details,
  addresses and the three `ELEVATE_*` internal identifiers become stable
  surrogates the model can reason over, and only code inside the trust boundary
  can resolve them.

The real detectors are Google's; these are regexes, and a regex cannot do what
`PERSON_NAME` does. The deliberate choice is to under-detect names rather than
over-detect: `masked_input` is what the policy retriever searches, so a detector
that swallowed "Bereavement Leave" as a person would silently destroy grounding.
That trade-off is why `PERSON_NAME` here is context-anchored only, and it is the
residual risk the SDD already tracks as RSK-11.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Sentinel for the irreversible class. A detector carrying this is redacted in
#: place and is never offered to `reidentify`.
REDACT = None


@dataclass(frozen=True)
class InfoTypeDetector:
    """One §4.5 infoType detector.

    `pattern` may match more than the sensitive value - a keyword-anchored
    detector such as `BANK_ACCOUNT_NUMBER` has to see "account no." to know what
    it is looking at. When the pattern defines a group named `v`, only that group
    is transformed and the surrounding context is preserved verbatim.
    """

    info_type: str
    pattern: re.Pattern[str]
    #: Surrogate label for the reversible class, or `REDACT` for the irreversible
    #: one. `[PHONE_1]`, `[REDACTED_SSN]` - the forms §4.4 tabulates.
    label: str | None

    @property
    def reversible(self) -> bool:
        return self.label is not REDACT


def _d(info_type: str, pattern: str, label: str | None, flags: int = 0) -> InfoTypeDetector:
    return InfoTypeDetector(info_type, re.compile(pattern, flags), label)


class CloudDLPInterceptor:
    """Deterministic pre-LLM de-identification and trust-boundary re-identification.

    Enforces the §4.4 element classes through the §4.5 infoType detectors.
    """

    #: The twelve §4.5 detectors, **in precedence order**. Order is load-bearing,
    #: not cosmetic: a single left-to-right non-overlapping pass takes the
    #: highest-precedence detector that matches at a position, so SSN is claimed
    #: before the phone detector can shred `123-45-6789` into three fragments.
    #:
    #: Nine Google built-in equivalents followed by the three enterprise custom
    #: detectors, whose regexes are quoted from §4.5.
    DETECTORS: tuple[InfoTypeDetector, ...] = (
        # --- enterprise custom (most specific literal formats first) ----------
        _d("ELEVATE_CASE_ID", r"\b(?:SI|WW)-\d{4}-\d{6}\b", "CASE_ID"),
        _d("ELEVATE_BADGE_NUMBER", r"\bBDG-\d{6}\b", "BADGE"),
        # --- irreversible: §4.4 "blocked / redacted completely" ---------------
        # `\b` is not enough on either of these: it holds between `-` and a
        # digit, so a run like "543-21-9876 4111 1111 1111 1111" lets the card
        # pattern start at "9876" and swallow only three of the card's four
        # groups. `_scan` then drops that candidate as overlapping the SSN and
        # the real card survives in the clear. The digit/dash lookarounds stop a
        # number from being matched from the middle of another one.
        _d("US_SOCIAL_SECURITY_NUMBER", r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])", REDACT),
        _d("CREDIT_CARD_NUMBER", r"(?<![\d-])(?:\d{4}[ -]?){3}\d{4}(?![\d-])", REDACT),
        _d("IBAN_CODE", r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", REDACT),
        _d(
            "BANK_ACCOUNT_NUMBER",
            r"\b(?:bank\s+)?(?:account|acct|a/c)\s*(?:no\.?|number|#)?\s*:?\s*(?P<v>\d{8,17})\b",
            REDACT,
            re.IGNORECASE,
        ),
        # The keyword is case-insensitive but the value is not: an inline `(?i:)`
        # group rather than a pattern-wide flag, because `re.IGNORECASE` would
        # also make `[A-Z]` match lowercase and widen the value class.
        _d(
            "PASSPORT",
            r"\b(?i:passport\s*(?:no\.?|number|#)?\s*:?\s*)(?P<v>[A-Z]{1,2}\d{6,9})\b",
            REDACT,
        ),
        # --- reversible pseudonyms -------------------------------------------
        _d("ELEVATE_EMPLOYEE_ID", r"\bE\d{7}\b", "EMP_ID"),
        _d("EMAIL_ADDRESS", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "EMAIL"),
        _d(
            "PHONE_NUMBER",
            # Either compact E.164, or a separated grouping. Separators are
            # required for the non-E.164 form so that bare integers in policy
            # prose ("20 work days", "2026") are not mistaken for numbers.
            r"(?<![\w-])(?:\+\d{8,15}|(?:\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3,4}[-.\s]\d{4})(?![\w-])",
            "PHONE",
        ),
        _d(
            "STREET_ADDRESS",
            r"\b\d{1,5}\s+(?:[A-Z][A-Za-z.]*\s+){0,4}"
            r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Way|Terrace|Ter"
            r"|Court|Ct|Place|Pl|Crescent|Close|Walk|Highway|Hwy)\b",
            "ADDRESS",
        ),
        _d(
            "PERSON_NAME",
            # Context-anchored by design - see the module docstring. The name
            # itself stays case-sensitive so that the Title-Case requirement
            # still does the work of bounding the match.
            r"\b(?i:my name is|i am|i'm|named)\s+(?P<v>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
            "PERSON",
        ),
    )

    def deidentify(
        self,
        text: str,
        surrogate_map: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, str]]:
        """De-identify user input before it reaches the model.

        Pass the previous turn's `surrogate_map` back in to get the §4.4
        guarantee that surrogates are *stable within a session* - the same phone
        number keeps the same `[PHONE_1]` across turns, so the model can reason
        about "the same person" without ever seeing the value. Omit it and each
        call numbers from scratch.

        The map holds only the reversible class and is the caller's to discard at
        end of turn; §4.4 requires it is never persisted.

        Returns:
            `(masked_text, surrogate_to_original_map)`
        """
        surrogates: dict[str, str] = dict(surrogate_map) if surrogate_map else {}
        #: Reverse index so a repeated value resolves to its existing surrogate
        #: rather than minting a second one.
        existing = {original: token for token, original in surrogates.items()}

        out: list[str] = []
        cursor = 0
        for detector, start, end in self._scan(text):
            out.append(text[cursor:start])
            value = text[start:end]
            if detector.reversible:
                token = existing.get(value)
                if token is None:
                    token = self._mint(detector.label, surrogates)
                    surrogates[token] = value
                    existing[value] = token
                out.append(token)
            else:
                out.append(f"[REDACTED_{detector.info_type}]")
            cursor = end
        out.append(text[cursor:])

        return "".join(out), surrogates

    def reidentify(self, response_text: str, surrogate_map: dict[str, str]) -> str:
        """Resolve surrogates back to real values inside the trust boundary.

        Only the reversible class is resolvable, because only it was ever put in
        the map. A redacted SSN cannot be restored by construction rather than by
        convention - which is the property §4.4 actually asks for.
        """
        reidentified = response_text
        for surrogate, original in surrogate_map.items():
            reidentified = reidentified.replace(surrogate, original)
        return reidentified

    # --- internals -----------------------------------------------------------

    def _scan(self, text: str) -> list[tuple[InfoTypeDetector, int, int]]:
        """Non-overlapping spans to transform, left to right.

        Every detector is run over the whole text, then the candidates are
        resolved greedily: earliest span wins, ties broken by detector
        precedence. Running them independently and resolving afterwards - rather
        than masking with one detector then re-scanning - is what stops a
        surrogate emitted by an earlier detector from being re-matched by a later
        one.
        """
        candidates: list[tuple[int, int, int, InfoTypeDetector]] = []
        for rank, detector in enumerate(self.DETECTORS):
            for match in detector.pattern.finditer(text):
                span = match.span("v") if "v" in match.groupdict() else match.span()
                if span[0] >= 0:
                    candidates.append((span[0], rank, span[1], detector))

        candidates.sort(key=lambda c: (c[0], c[1]))

        accepted: list[tuple[InfoTypeDetector, int, int]] = []
        consumed_to = 0
        for start, _rank, end, detector in candidates:
            if start >= consumed_to:
                accepted.append((detector, start, end))
                consumed_to = end
        return accepted

    @staticmethod
    def _mint(label: str, surrogates: dict[str, str]) -> str:
        """Next free `[LABEL_n]` token for this session."""
        n = 1
        while f"[{label}_{n}]" in surrogates:
            n += 1
        return f"[{label}_{n}]"
