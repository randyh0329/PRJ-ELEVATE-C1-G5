"""The `saga_compensation_event` audit record (SDD §4.11).

This is the Z2 audit-zone record for a saga compensation decision. It is a
**closed schema**, and that is the whole design: `extra="forbid"` means a field
nobody reviewed cannot be serialised into the 365-day archive. §4.11 states the
reasoning plainly - a redaction blocklist fails open on the field nobody thought
of, an allow-list fails closed on it.

Three fields carry the guarantee, and none of them is the payload:

- `payload_pointer` locates the original arguments in Firestore (Z3, masked,
  30-day TTL) instead of copying them into a store with a 365-day retention.
- `payload_digest` keeps the record tamper-evident without containing the data.
- `field_names_only` records *which* fields were involved, never their values.
  "A medical leave request with a start date was rolled back" is auditable; the
  date itself does not belong in Z2.

The pointer dangles once the Firestore TTL expires. That is intended: the
compliance record outlives the personal data rather than preserving it.

`emit_compensation_event` is the only write path. §4.11's write-time layer
forbids a bare `logger.info(payload)` elsewhere, because a free-form dictionary
would reintroduce exactly the open schema this module exists to prevent.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.core.clock import business_now

logger = logging.getLogger("saga.compensation.audit")

# Surrogates are prefixed so an auditor reading the archive can tell at a glance
# that a field holds a pseudonym and not a value that merely looks opaque.
_DIGEST_PREFIX = "sha256:"


def surrogate(value: str | None) -> str | None:
    """Crypto-deterministic pseudonym for an identifier (§4.11 Z2: surrogates only).

    Deterministic so the same employee is the same surrogate across records -
    which is what makes the archive queryable - and one-way so the archive
    cannot be resolved back to a person without the identifier already in hand.
    """
    if value is None:
        return None
    return _DIGEST_PREFIX + hashlib.sha256(value.encode("utf-8")).hexdigest()


def payload_digest(payload: dict[str, Any] | None) -> str | None:
    """Tamper-evidence for a payload the record deliberately does not contain."""
    if payload is None:
        return None
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return _DIGEST_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def field_names_only(payload: dict[str, Any] | None) -> list[str]:
    """The keys of a payload, sorted, with every value discarded."""
    if not payload:
        return []
    return sorted(payload.keys())


class PriorStepRef(BaseModel):
    """What was done to one already-successful step when a later step failed.

    `action_taken` is the §5.4 disposition - `LEFT_IN_PLACE` for anything
    HUMAN_CONSEQUENTIAL, `ROLLED_BACK` for REVERSIBLE_SAFE.
    """

    model_config = ConfigDict(extra="forbid")

    index: int
    system: str
    ref: str | None = None
    step_class: str = Field(serialization_alias="class")
    action_taken: str


class SagaCompensationEvent(BaseModel):
    """The Z2 record. Every field here is on the §4.11 allow-list."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    event_type: Literal["saga_compensation_event"] = "saga_compensation_event"
    trace_id: str | None = None
    saga_id: str
    session_id: str | None = None
    employee_id_hash: str | None = None
    trigger: str = "STEP_FAILED"
    failed_step_index: int
    failed_step_action: str
    compensation_class: str
    compensation_decision: str
    compensation_target_system: str | None = None
    external_reference_id: str | None = None
    prior_step_refs: list[PriorStepRef] = Field(default_factory=list)
    payload_pointer: str | None = None
    payload_digest: str | None = None
    field_names_only: list[str] = Field(default_factory=list)
    human_followup_ticket: str | None = None
    outcome: str
    timestamp: str = Field(default_factory=lambda: business_now().isoformat())


def emit_compensation_event(event: SagaCompensationEvent) -> SagaCompensationEvent:
    """Write the record to the Z2 sink. The only sanctioned emission path."""
    logger.info(event.model_dump_json(by_alias=True))
    return event
