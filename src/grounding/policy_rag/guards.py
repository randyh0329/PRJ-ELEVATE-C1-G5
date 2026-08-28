"""Answerability guards.

The corpus datasheet has a section titled "What must not be answered from this
bundle". These guards are that section turned into code. They run *after*
retrieval and *before* an answer is composed, and they can only ever make the
service more conservative: downgrade an answer to an escalation, or annotate it.

Guards never pick a side in a source contradiction. Where the handbook disagrees
with itself, the correct output is "the handbook is inconsistent here, go to
People Ops" - which is what `CONFLICT` produces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from src.grounding.policy_rag.config import GuardConfig
from src.grounding.policy_rag.documents import Hit


class GuardAction(str, Enum):
    ANSWER = "ANSWER"
    #: Route to a human; the corpus holds the question but cannot settle it.
    ESCALATE = "ESCALATE"
    #: The corpus does not hold the answer at all.
    REFUSE = "REFUSE"


@dataclass
class GuardDecision:
    action: GuardAction = GuardAction.ANSWER
    #: Machine-readable guard id, e.g. `source_conflict`.
    reason: str | None = None
    #: Text shown to the caller when the action is not ANSWER.
    message: str | None = None
    #: Caveats appended to an otherwise normal answer.
    notices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "message": self.message,
            "notices": list(self.notices),
        }


# Handbook sections 11 and 15 do not exist. Their subject matter is unknown, and
# the gap is not evidence that the topic is unregulated.
_MISSING_SECTIONS = {"11", "15"}
_SECTION_REF_RE = re.compile(r"\bsections?\s+(\d{1,2})\b", re.IGNORECASE)

_EXTENDED_WORKFORCE_RE = re.compile(
    r"\b(contractor|contractors|vendor|vendors|temp|temps|temporary staff|agency worker|"
    r"extended workforce|freelancer|freelancers|consultant|consultants)\b",
    re.IGNORECASE,
)
_LEAVE_TOPIC_RE = re.compile(
    r"\b(leave|vacation|annual leave|pto|sick|hospitalisation|hospitalization|childcare|"
    r"maternity|paternity|bereavement|carer|toil|time off|entitlement|entitled|holiday)\b",
    re.IGNORECASE,
)

#: Literal strings the source never filled in. Presenting these as real contact
#: routes is the failure the datasheet calls out by name.
_PLACEHOLDER_LITERALS = ("abc@altostrat.com",)
_PLACEHOLDER_TOKENS_RE = re.compile(
    r"`(email|company intranet|Company Website|ITSM and open a case)`", re.IGNORECASE
)
PLACEHOLDER_REDACTION = "[unresolved placeholder in the source handbook]"


def _escalation(reason: str, message: str) -> GuardDecision:
    return GuardDecision(action=GuardAction.ESCALATE, reason=reason, message=message)


def evaluate(
    query: str,
    hits: list[Hit],
    cfg: GuardConfig,
    now: datetime | None = None,
) -> GuardDecision:
    """Decide whether the retrieved hits may be turned into an answer."""
    contact = cfg.escalation_contact
    notices: list[str] = []

    # 1. Sections the source does not contain.
    for number in _SECTION_REF_RE.findall(query):
        if number in _MISSING_SECTIONS:
            return _escalation(
                "absent_section",
                f"Handbook Section {number} does not exist in the source document. Its subject "
                f"matter is unknown - the gap is not evidence that the topic is unregulated. "
                f"Please ask {contact}.",
            )

    # 2. Extended workforce leave. The source excludes temps, vendors and
    #    contractors from every Singapore leave policy and carries no substitute
    #    figures, so any number retrieved here would be the wrong number.
    if cfg.extended_workforce_leave and _EXTENDED_WORKFORCE_RE.search(query) and _LEAVE_TOPIC_RE.search(query):
        return _escalation(
            "extended_workforce_leave",
            "Temps, vendors and contractors are explicitly excluded from every Singapore leave "
            "policy in this handbook, and it carries no substitute figures for them. Members of "
            "the extended workforce must contact their direct employer about leave entitlements.",
        )

    if not hits:
        return GuardDecision(action=GuardAction.REFUSE, reason="no_hits")

    # 3. Source contradiction. Answering would mean picking a side the handbook
    #    itself does not pick.
    #
    #    The trigger is "the best-matching passage *is* the Conflict note", which
    #    is what happens when the question is actually about the contested point.
    #    Widening it to "any Conflict section of the answering document matched"
    #    was tried and over-fires: a concept file can cover two rules and be
    #    contested on only one of them, so a procedural question about the sound
    #    rule got escalated on the strength of its neighbour.
    #
    #    Residual risk: a question about a contested point phrased so the policy
    #    text outranks the Conflict note is answered with a caveat rather than
    #    escalated. The durable fix is to match the query against the source
    #    defect register instead of relying on chunk ranking - see the README.
    if cfg.conflict_sections and hits[0].chunk.is_conflict:
        top = hits[0]
        return _escalation(
            "source_conflict",
            f"The handbook is inconsistent on this point. {top.chunk.doc_title} records the "
            f"conflict under \"{top.chunk.heading_trail}\" and this corpus does not resolve it, "
            f"so there is no answer to give. Please raise it with {contact}. "
            f"Detail: {top.citation.uri}",
        )

    if cfg.conflict_sections and any(h.chunk.is_conflict for h in hits):
        notices.append(
            "Part of the retrieved material sits in a documented source conflict; "
            f"confirm with {contact} before relying on it."
        )

    # 4. Gap sections describe what the source fails to specify. Useful context,
    #    never a basis for a figure.
    if any(h.chunk.is_gap for h in hits):
        notices.append("The handbook leaves part of this rule unspecified; the answer states only what it does say.")

    # 5. Freshness. `stale_after` is a producer commitment, not a source fact.
    if cfg.staleness:
        moment = now or datetime.now(timezone.utc)
        for hit in hits:
            if _is_stale(hit.chunk.stale_after, moment):
                notices.append(
                    f"{hit.chunk.doc_title} passed its review-by date ({hit.chunk.stale_after}); "
                    f"verify with {contact}."
                )
                break

    # 6. Draft concepts are incomplete by declaration.
    if any(h.chunk.status == "draft" for h in hits):
        notices.append("Part of this answer comes from a draft concept whose rules include producer assumptions.")

    return GuardDecision(action=GuardAction.ANSWER, notices=notices)


def _is_stale(stale_after: str | None, now: datetime) -> bool:
    if not stale_after:
        return False
    try:
        parsed = datetime.fromisoformat(stale_after.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return now > parsed


def redact_placeholders(text: str, cfg: GuardConfig) -> tuple[str, list[str]]:
    """Strip unresolved contact placeholders and report what was found.

    `abc@altostrat.com` is replaced outright because it looks like a working
    address; the backticked tokens are left in place - they are quoted *as*
    placeholders in the corpus - but they raise a notice so the caller is never
    told to go somewhere that does not exist.
    """
    if not cfg.placeholder_contacts:
        return text, []

    notices: list[str] = []
    redacted = text
    for literal in _PLACEHOLDER_LITERALS:
        if literal.lower() in redacted.lower():
            redacted = re.sub(re.escape(literal), PLACEHOLDER_REDACTION, redacted, flags=re.IGNORECASE)
            notices.append(
                f"The source gives `{literal}` as a contact address, but it is an unresolved "
                f"placeholder, not a real address. Ask {cfg.escalation_contact} for the correct route."
            )

    if _PLACEHOLDER_TOKENS_RE.search(redacted):
        notices.append(
            "The contact channel quoted above is an unresolved placeholder in the source handbook, "
            f"not a usable route. Ask {cfg.escalation_contact}."
        )

    return redacted, notices
