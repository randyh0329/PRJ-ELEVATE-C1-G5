"""The two privacy gates the SDD makes blocking build steps.

§4.10 E6 - the de-identification template cannot be bypassed on the way to the
model. §4.11 - no compensation record can carry a raw value into the 365-day
audit archive. Both are specified as *observations of output* rather than code
inspections, and these tests keep them that way: they drive real flows and then
inspect what came out, so a future change that leaks by a route nobody
anticipated still trips them.

The inspector both tests use is the §4.5 detector set itself, run at a
deliberately lower bar than the transformation path uses. That mirrors the
RSK-11 mitigation - scanning at `minLikelihood: POSSIBLE` so near-misses
surface, rather than trusting the same threshold twice.
"""

from __future__ import annotations

import json
import logging

import pytest
from pydantic import ValidationError

from src.core.state import (
    AgentState,
    SagaCompensationClass,
    SagaStepRecord,
    SagaStepStatus,
)
from src.saga.compensation import SagaCompensationDecisionMatrix
from src.saga.ledger import SagaLedgerManager
from src.security.dlp import CloudDLPInterceptor
from src.telemetry.compensation_event import (
    PriorStepRef,
    SagaCompensationEvent,
    surrogate,
)

# One specimen per §4.4 element class, covering all twelve §4.5 infoTypes. The
# values are synthetic but structurally real - a detector that only matches
# `XXX-XX-XXXX` would pass a test built from obviously-fake data.
PII_SPECIMENS: dict[str, str] = {
    "US_SOCIAL_SECURITY_NUMBER": "543-21-9876",
    "CREDIT_CARD_NUMBER": "4111 1111 1111 1111",
    "IBAN_CODE": "SG21DBSS01234567890123",
    "BANK_ACCOUNT_NUMBER": "account number: 0072451983",
    "PASSPORT": "passport no: K1234567",
    "ELEVATE_EMPLOYEE_ID": "E7741903",
    "ELEVATE_BADGE_NUMBER": "BDG-448120",
    "ELEVATE_CASE_ID": "SI-2026-114377",
    "EMAIL_ADDRESS": "priya.raman@altostrat.example",
    "PHONE_NUMBER": "+6581234567",
    "STREET_ADDRESS": "88 Marina Boulevard",
    "PERSON_NAME": "my name is Priya Raman",
}

# The substrings that must not survive. For the anchored detectors the specimen
# includes its own trigger phrase, which is not itself sensitive - only the
# value it introduces is.
RAW_VALUES: tuple[str, ...] = (
    "543-21-9876",
    "4111 1111 1111 1111",
    "SG21DBSS01234567890123",
    "0072451983",
    "K1234567",
    "E7741903",
    "BDG-448120",
    "SI-2026-114377",
    "priya.raman@altostrat.example",
    "+6581234567",
    "88 Marina Boulevard",
    "Priya Raman",
)


def _inspect(text: str) -> list[str]:
    """Return the infoTypes found in `text` - the §4.11 re-inspection job, offline."""
    interceptor = CloudDLPInterceptor()
    return [detector.info_type for detector, _start, _end in interceptor._scan(text)]


# ---------------------------------------------------------------------------
# §4.10 E6 - the bypass test
# ---------------------------------------------------------------------------


def test_the_dlp_specimens_are_all_actually_detected():
    """Guard the guard: an E6 that silently stopped matching would pass vacuously.

    If a detector regresses, this fails first and names the infoType, rather
    than leaving the bypass test below to pass because nothing was found in
    either the input or the output.
    """
    found = set(_inspect(" ; ".join(PII_SPECIMENS.values())))
    missing = set(PII_SPECIMENS) - found
    assert not missing, f"§4.5 detectors no longer match: {sorted(missing)}"


def test_no_raw_pii_reaches_the_model_client():
    """§4.10 E6: a payload with all twelve infoTypes leaves zero raw values behind."""
    interceptor = CloudDLPInterceptor()
    prompt = "Please help. " + " ".join(PII_SPECIMENS.values())

    masked, surrogates = interceptor.deidentify(prompt)

    for raw in RAW_VALUES:
        assert raw not in masked, f"{raw!r} survived de-identification"
    # The surrogate map is the session-scoped key material of §4.5. It may hold
    # reversible pseudonyms, but nothing irreversibly-classed may appear in it.
    assert "543-21-9876" not in json.dumps(surrogates)


def test_the_deidentified_prompt_is_still_answerable():
    """Masking that destroys the question is not a passing control (RSK-11).

    `masked_input` is what the policy retriever searches on. A detector that
    over-matches turns a working grounding pipeline into a silent one, so the
    bypass gate is only meaningful alongside this.
    """
    interceptor = CloudDLPInterceptor()
    prompt = "My name is Priya Raman. How many days of bereavement leave am I entitled to?"

    masked, _ = interceptor.deidentify(prompt)

    assert "Priya Raman" not in masked
    assert "bereavement leave" in masked
    assert "How many days" in masked


def test_surrogates_are_stable_within_a_session():
    """§4.5: the reversible transformation is deterministic for the session."""
    interceptor = CloudDLPInterceptor()

    first, surrogates = interceptor.deidentify("Reach me at +6581234567.")
    second, surrogates = interceptor.deidentify("Still +6581234567 today.", surrogates)

    token = next(iter(surrogates))
    assert token in first
    assert token in second


# ---------------------------------------------------------------------------
# §4.11 - the compensation allow-list
# ---------------------------------------------------------------------------


def _state() -> AgentState:
    return {
        "session_id": "sess-privacy-01",
        "turn_id": "turn-1",
        "employee_id": "E7741903",
        "saga_type": "UC-2.2-MEDICAL-LEAVE",
    }


def _ledger_with(steps: list[SagaStepRecord]) -> tuple[SagaLedgerManager, str]:
    ledger = SagaLedgerManager(in_memory=True)
    saga_id = ledger.init_saga(
        session_id="sess-privacy-01",
        employee_id="E7741903",
        workflow_type="UC-2.2-MEDICAL-LEAVE",
    )
    for step in steps:
        ledger.record_step(saga_id, step)
    return ledger, saga_id


# A payload full of exactly the values §4.11 says must never reach Z2.
SENSITIVE_PAYLOAD = {
    "leaveType": "MEDICAL",
    "startDate": "2026-09-01",
    "employeeEmail": "priya.raman@altostrat.example",
    "contactPhone": "+6581234567",
    "homeAddress": "88 Marina Boulevard",
    "badgeNumber": "BDG-448120",
}


def _prior(index: int, comp_class: SagaCompensationClass, ref: str) -> SagaStepRecord:
    return SagaStepRecord(
        step_index=index,
        target_system="WorkWeek",
        action="SUBMIT_LEAVE",
        compensation_class=comp_class,
        status=SagaStepStatus.SUCCESS,
        external_ref_id=ref,
        compensation_payload=dict(SENSITIVE_PAYLOAD),
    )


def _failed(index: int, comp_class: SagaCompensationClass) -> SagaStepRecord:
    return SagaStepRecord(
        step_index=index,
        target_system="ServiceImmediately",
        action="CREATE_ROUTING_TICKET",
        compensation_class=comp_class,
        status=SagaStepStatus.FAILED,
        compensation_payload=dict(SENSITIVE_PAYLOAD),
    )


# Every compensation class in the failed-step position, each with a prior-step
# history that exercises a different branch of the §5.4 decision tree.
COMPENSATION_SCENARIOS = [
    pytest.param(
        [_prior(1, SagaCompensationClass.HUMAN_CONSEQUENTIAL, "LV-4012")],
        _failed(2, SagaCompensationClass.ANCILLARY),
        id="ancillary-failure-over-a-consequential-prior",
    ),
    pytest.param(
        [_prior(1, SagaCompensationClass.REVERSIBLE_SAFE, "PR-9001")],
        _failed(2, SagaCompensationClass.REVERSIBLE_SAFE),
        id="reversible-failure-rolled-back",
    ),
    pytest.param(
        [
            _prior(1, SagaCompensationClass.HUMAN_CONSEQUENTIAL, "LV-4012"),
            _prior(2, SagaCompensationClass.REVERSIBLE_SAFE, "PR-9001"),
        ],
        _failed(3, SagaCompensationClass.HUMAN_CONSEQUENTIAL),
        id="mixed-history-consequential-preserved",
    ),
    pytest.param(
        [_prior(1, SagaCompensationClass.READ_ONLY, "RD-1")],
        _failed(2, SagaCompensationClass.REVERSIBLE_SAFE),
        id="read-only-prior-left-in-place",
    ),
]


@pytest.mark.parametrize(("priors", "failed"), COMPENSATION_SCENARIOS)
async def test_compensation_emits_no_raw_pii(priors, failed, caplog):
    """NFR-1.2 / §4.11: drive compensation to failure and inspect every log line.

    Named in the SDD traceability matrix and in the §4.11 build-time enforcement
    layer. The assertion is not "the emitter looks careful" - it is that the
    §4.5 inspector finds nothing in what was actually written.
    """
    ledger, saga_id = _ledger_with([*priors, failed])
    matrix = SagaCompensationDecisionMatrix(ledger=ledger)

    with caplog.at_level(logging.DEBUG):
        await matrix.handle_step_failure(
            saga_id=saga_id,
            failed_step_index=failed.step_index,
            # Vendor error text is a realistic carrier of leaked values.
            error_reason="Upstream 500 while filing for priya.raman@altostrat.example",
            state=_state(),
        )

    emitted = "\n".join(record.getMessage() for record in caplog.records)
    findings = _inspect(emitted)
    assert not findings, f"raw PII in compensation logs: {sorted(set(findings))}"

    for raw in RAW_VALUES:
        assert raw not in emitted, f"{raw!r} reached the audit log"


@pytest.mark.parametrize(("priors", "failed"), COMPENSATION_SCENARIOS)
async def test_the_compensation_record_still_says_what_happened(priors, failed, caplog):
    """Privacy that erases the audit trail is not compliance either.

    §4.11's claim is that the record stays *complete for its own purpose* -
    what happened, to whom by surrogate, with what outcome - while holding no
    personal data. Both halves have to be true or the allow-list is just a
    delete.
    """
    ledger, saga_id = _ledger_with([*priors, failed])
    matrix = SagaCompensationDecisionMatrix(ledger=ledger)

    with caplog.at_level(logging.INFO, logger="saga.compensation.audit"):
        await matrix.handle_step_failure(
            saga_id=saga_id,
            failed_step_index=failed.step_index,
            error_reason="Upstream 500",
            state=_state(),
        )

    events = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "saga.compensation.audit"
    ]
    assert len(events) == 1
    event = events[0]

    assert event["event_type"] == "saga_compensation_event"
    assert event["saga_id"] == saga_id
    assert event["failed_step_index"] == failed.step_index
    assert event["failed_step_action"] == failed.action
    assert event["outcome"] in {"ESCALATED_TO_HUMAN", "ROLLED_BACK"}
    # Who, by surrogate only.
    assert event["employee_id_hash"] == surrogate("E7741903")
    # The payload is present as a pointer, a digest and its field names.
    assert event["payload_pointer"].startswith("firestore://sagas/")
    assert event["payload_digest"].startswith("sha256:")
    assert event["field_names_only"] == sorted(SENSITIVE_PAYLOAD)
    assert len(event["prior_step_refs"]) == len(priors)
    for ref in event["prior_step_refs"]:
        assert ref["action_taken"] in {"ROLLED_BACK", "LEFT_IN_PLACE"}


def test_a_human_consequential_prior_is_never_reported_as_rolled_back():
    """§5.4's first guarantee, read off the audit record rather than the ledger."""
    priors = [
        _prior(1, SagaCompensationClass.HUMAN_CONSEQUENTIAL, "LV-4012"),
        _prior(2, SagaCompensationClass.REVERSIBLE_SAFE, "PR-9001"),
    ]
    ledger, saga_id = _ledger_with([*priors, _failed(3, SagaCompensationClass.HUMAN_CONSEQUENTIAL)])
    matrix = SagaCompensationDecisionMatrix(ledger=ledger)

    captured: list[SagaCompensationEvent] = []
    original = matrix._emit_audit_event

    def _capture(**kwargs):
        event = original(**kwargs)
        captured.append(event)
        return event

    matrix._emit_audit_event = _capture

    import asyncio

    asyncio.run(
        matrix.handle_step_failure(
            saga_id=saga_id, failed_step_index=3, error_reason="boom", state=_state()
        )
    )

    dispositions = {r.index: r.action_taken for r in captured[0].prior_step_refs}
    assert dispositions[1] == "LEFT_IN_PLACE"
    assert dispositions[2] == "ROLLED_BACK"


def test_the_emitter_forbids_unreviewed_fields():
    """§4.11 build-time layer, second test: `extra="forbid"` on the emitter model.

    An allow-list only fails closed if adding a field is impossible without
    editing the schema - which is what puts it in front of a reviewer.
    """
    assert SagaCompensationEvent.model_config["extra"] == "forbid"
    assert PriorStepRef.model_config["extra"] == "forbid"

    with pytest.raises(ValidationError):
        SagaCompensationEvent(
            saga_id="saga-1",
            failed_step_index=1,
            failed_step_action="SUBMIT_LEAVE",
            compensation_class="ANCILLARY",
            compensation_decision="FLAG_AND_ESCALATE",
            outcome="ESCALATED_TO_HUMAN",
            # The field nobody reviewed.
            raw_payload={"homeAddress": "88 Marina Boulevard"},
        )


def test_the_surrogate_is_deterministic_and_one_way():
    """Z2 holds pseudonyms that join across records but do not resolve to a person."""
    assert surrogate("E7741903") == surrogate("E7741903")
    assert surrogate("E7741903") != surrogate("E7741904")
    assert "E7741903" not in surrogate("E7741903")
    assert surrogate(None) is None
