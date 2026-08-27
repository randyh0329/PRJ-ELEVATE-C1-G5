"""The saga ledger (§4.6) and the Cloud Tasks dispatcher (§5.2, §4.8).

Both have two backends and the tests run each one, because the pair is where
the bugs live: the in-memory store is what every other test exercises and the
Firestore path is what production uses, so a divergence between them is
invisible until deployment.

The dispatcher's two obligations are worth stating plainly. It must never
execute a task for a principal whose credentials were revoked mid-saga (§4.8) -
including a revocation that lands *between* retries, which is the case the
first check cannot catch. And it must shed load multiplicatively on failure and
recover additively (§5.2), so a backend having a bad minute does not become a
thundering herd.
"""

from __future__ import annotations

import asyncio
import datetime

import pytest

from src.core.state import (
    SagaCompensationClass,
    SagaStepRecord,
    SagaStepStatus,
    SagaWorkflowState,
)
from src.saga.dispatcher import CloudTasksDispatcher
from src.saga.ledger import SagaLedgerManager

# --- a Firestore stand-in ----------------------------------------------------


class FakeDocument:
    def __init__(self, store: dict, doc_id: str):
        self._store = store
        self._id = doc_id

    def set(self, doc: dict) -> None:
        self._store[self._id] = doc

    def get(self) -> FakeDocument:
        return self

    def to_dict(self) -> dict | None:
        return self._store.get(self._id)

    def update(self, patch: dict) -> None:
        self._store.setdefault(self._id, {}).update(patch)


class FakeCollection:
    def __init__(self, store: dict):
        self._store = store

    def document(self, doc_id: str) -> FakeDocument:
        return FakeDocument(self._store, doc_id)


class FakeFirestore:
    def __init__(self):
        self.collections: dict[str, dict] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self.collections.setdefault(name, {}))


def _step(index: int = 1, **overrides) -> SagaStepRecord:
    fields = {
        "step_index": index,
        "target_system": "WorkWeek",
        "action": "SUBMIT_LEAVE",
        "compensation_class": SagaCompensationClass.HUMAN_CONSEQUENTIAL,
    }
    fields.update(overrides)
    return SagaStepRecord(**fields)


@pytest.fixture(params=["memory", "firestore"])
def ledger(request) -> SagaLedgerManager:
    """The same suite against both backends - they must not diverge."""
    if request.param == "memory":
        return SagaLedgerManager(in_memory=True)
    return SagaLedgerManager(in_memory=False, firestore_client=FakeFirestore())


# --- ledger: lifecycle -------------------------------------------------------


def test_a_new_saga_starts_in_the_started_state(ledger):
    saga_id = ledger.init_saga("sess-1", "EMP-1", "UC-2.2-MEDICAL-LEAVE")

    doc = ledger.get_saga(saga_id)
    assert doc["currentState"] == SagaWorkflowState.STARTED.value
    assert doc["sessionId"] == "sess-1"
    assert doc["employeeId"] == "EMP-1"
    assert doc["steps"] == []


def test_a_caller_supplied_saga_id_is_honoured(ledger):
    assert ledger.init_saga("s", "e", "t", saga_id="saga-fixed") == "saga-fixed"


def test_a_generated_saga_id_is_unique(ledger):
    ids = {ledger.init_saga("s", "e", "t") for _ in range(20)}
    assert len(ids) == 20


def test_every_saga_carries_a_thirty_day_ttl(ledger):
    """NFR-1.3: the ledger is transactional state, not an archive."""
    doc = ledger.get_saga(ledger.init_saga("s", "e", "t"))

    created = datetime.date.fromisoformat(doc["createdAt"][:10])
    expiry = datetime.date.fromisoformat(doc["ttl_expiry"][:10])
    assert (expiry - created).days == 30


def test_the_workflow_state_machine_advances(ledger):
    saga_id = ledger.init_saga("s", "e", "t")

    ledger.update_saga_state(saga_id, SagaWorkflowState.COMPENSATED_ROLLED_BACK)

    assert (
        ledger.get_saga(saga_id)["currentState"]
        == SagaWorkflowState.COMPENSATED_ROLLED_BACK.value
    )


# --- ledger: steps -----------------------------------------------------------


def test_a_recorded_step_is_serialised_into_the_ledger(ledger):
    saga_id = ledger.init_saga("s", "e", "t")

    ledger.record_step(saga_id, _step(1, external_ref_id="LV-4012"))

    (row,) = ledger.get_saga(saga_id)["steps"]
    assert row["stepIndex"] == 1
    assert row["action"] == "SUBMIT_LEAVE"
    assert row["compensationClass"] == "HUMAN_CONSEQUENTIAL"
    assert row["status"] == SagaStepStatus.PENDING.value
    assert row["externalReferenceId"] == "LV-4012"


def test_recording_stamps_a_timestamp_when_the_caller_omits_one(ledger):
    saga_id = ledger.init_saga("s", "e", "t")
    step = _step()
    assert step.timestamp is None

    ledger.record_step(saga_id, step)

    assert step.timestamp is not None
    assert ledger.get_saga(saga_id)["steps"][0]["timestamp"] == step.timestamp


def test_a_caller_supplied_timestamp_is_preserved(ledger):
    saga_id = ledger.init_saga("s", "e", "t")

    ledger.record_step(saga_id, _step(timestamp="2026-01-01T00:00:00+00:00"))

    assert ledger.get_saga(saga_id)["steps"][0]["timestamp"] == "2026-01-01T00:00:00+00:00"


def test_recording_the_same_step_index_twice_replaces_it(ledger):
    """Idempotent by index on both backends.

    RPO=0 logging writes before it acts, so a retried step re-records itself. If
    that appended, the compensation walk would find two rows for one action and
    try to reverse it twice.
    """
    saga_id = ledger.init_saga("s", "e", "t")

    ledger.record_step(saga_id, _step(1, action="SUBMIT_LEAVE"))
    ledger.record_step(saga_id, _step(1, action="SUBMIT_LEAVE_RETRY"))
    ledger.record_step(saga_id, _step(2, action="DELEGATE_ACCESS"))

    steps = ledger.get_saga(saga_id)["steps"]
    assert [s["stepIndex"] for s in steps] == [1, 2]
    assert steps[0]["action"] == "SUBMIT_LEAVE_RETRY"


def test_updating_a_step_writes_every_supplied_field(ledger):
    saga_id = ledger.init_saga("s", "e", "t")
    ledger.record_step(saga_id, _step(1))

    ledger.update_step_status(
        saga_id,
        1,
        SagaStepStatus.FAILED_HANDED_TO_HUMAN,
        external_ref_id="LV-4012",
        compensation_payload={"priorStatus": "APPROVED"},
        follow_up_ref="OPS-2214",
        error_message="downstream 503",
    )

    (row,) = ledger.get_saga(saga_id)["steps"]
    assert row["status"] == "FAILED_HANDED_TO_HUMAN"
    assert row["externalReferenceId"] == "LV-4012"
    assert row["compensationPayload"] == {"priorStatus": "APPROVED"}
    assert row["followUpRef"] == "OPS-2214"
    assert row["errorMessage"] == "downstream 503"


def test_a_status_only_update_does_not_erase_the_external_reference(ledger):
    """The reference is the handle compensation reverses by (§5.4)."""
    saga_id = ledger.init_saga("s", "e", "t")
    ledger.record_step(saga_id, _step(1, external_ref_id="LV-4012"))

    ledger.update_step_status(saga_id, 1, SagaStepStatus.SUCCESS)

    (row,) = ledger.get_saga(saga_id)["steps"]
    assert row["status"] == "SUCCESS"
    assert row["externalReferenceId"] == "LV-4012"


def test_updating_a_step_index_that_does_not_exist_is_a_no_op(ledger):
    saga_id = ledger.init_saga("s", "e", "t")
    ledger.record_step(saga_id, _step(1))

    ledger.update_step_status(saga_id, 99, SagaStepStatus.FAILED)

    assert ledger.get_saga(saga_id)["steps"][0]["status"] == SagaStepStatus.PENDING.value


def test_only_the_named_step_is_touched(ledger):
    saga_id = ledger.init_saga("s", "e", "t")
    ledger.record_step(saga_id, _step(1))
    ledger.record_step(saga_id, _step(2))

    ledger.update_step_status(saga_id, 2, SagaStepStatus.ROLLED_BACK)

    statuses = [s["status"] for s in ledger.get_saga(saga_id)["steps"]]
    assert statuses == [SagaStepStatus.PENDING.value, SagaStepStatus.ROLLED_BACK.value]


# --- ledger: the unknown-saga contract ---------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda m: m.record_step("saga-missing", _step()),
        lambda m: m.update_step_status("saga-missing", 1, SagaStepStatus.SUCCESS),
        lambda m: m.update_saga_state("saga-missing", SagaWorkflowState.FAILED),
        lambda m: m.get_saga("saga-missing"),
    ],
)
def test_touching_an_unknown_saga_raises_rather_than_creating_one(call):
    """In-memory only: writing a step into a saga that was never opened is a bug
    in the caller, and silently creating the document would hide it."""
    with pytest.raises(KeyError, match="saga-missing"):
        call(SagaLedgerManager(in_memory=True))


def test_a_configured_client_is_ignored_while_in_memory_is_set():
    """`in_memory` wins, so a test can hold a real client without writing to it."""
    firestore = FakeFirestore()
    ledger = SagaLedgerManager(in_memory=True, firestore_client=firestore)

    ledger.record_step(ledger.init_saga("s", "e", "t"), _step())

    assert firestore.collections == {}


def test_firestore_is_bypassed_when_no_client_was_supplied():
    """`in_memory=False` with no client must not crash on None."""
    ledger = SagaLedgerManager(in_memory=False, firestore_client=None)
    saga_id = ledger.init_saga("s", "e", "t")

    ledger.record_step(saga_id, _step())

    assert len(ledger.get_saga(saga_id)["steps"]) == 1


def test_reading_a_saga_absent_from_firestore_yields_an_empty_document():
    ledger = SagaLedgerManager(in_memory=False, firestore_client=FakeFirestore())
    assert ledger.get_saga("saga-never-written") == {}


def test_a_step_written_into_an_empty_firestore_document_still_lands():
    """`record_step` may run before `init_saga` has been observed by the replica."""
    ledger = SagaLedgerManager(in_memory=False, firestore_client=FakeFirestore())

    ledger.record_step("saga-cold", _step())
    ledger.update_step_status("saga-cold", 1, SagaStepStatus.SUCCESS)

    assert ledger.get_saga("saga-cold")["steps"][0]["status"] == "SUCCESS"


# --- dispatcher: concurrency control (§5.2, NFR-4.2) -------------------------


def test_the_initial_limit_is_the_target_share_of_the_ceiling():
    assert CloudTasksDispatcher(max_concurrency_ceiling=20).current_concurrency_limit == 18
    assert (
        CloudTasksDispatcher(
            max_concurrency_ceiling=100, target_capacity_ratio=0.5
        ).current_concurrency_limit
        == 50
    )


def test_a_rate_limit_halves_the_concurrency():
    dispatcher = CloudTasksDispatcher(max_concurrency_ceiling=20)

    dispatcher.adapt_concurrency_on_rate_limit()

    assert dispatcher.current_concurrency_limit == 9


def test_backing_off_never_drops_below_the_floor():
    """Zero concurrency would stall the queue permanently rather than shed load."""
    dispatcher = CloudTasksDispatcher(max_concurrency_ceiling=20)

    for _ in range(10):
        dispatcher.adapt_concurrency_on_rate_limit()

    assert dispatcher.current_concurrency_limit == dispatcher.min_concurrency_limit == 2


def test_recovery_is_additive_not_a_jump_back_to_the_ceiling():
    dispatcher = CloudTasksDispatcher(max_concurrency_ceiling=20)
    dispatcher.current_concurrency_limit = 4

    dispatcher.adapt_concurrency_on_success()

    assert dispatcher.current_concurrency_limit == 5


def test_recovery_stops_at_the_ceiling():
    dispatcher = CloudTasksDispatcher(max_concurrency_ceiling=20)
    dispatcher.current_concurrency_limit = 20

    dispatcher.adapt_concurrency_on_success()

    assert dispatcher.current_concurrency_limit == 20


# --- dispatcher: execution ---------------------------------------------------


@pytest.fixture
def dispatcher() -> CloudTasksDispatcher:
    return CloudTasksDispatcher()


async def test_a_task_that_succeeds_first_time_reports_one_attempt(dispatcher):
    result = await dispatcher.enqueue_and_execute(
        "submit_leave", "EMP-1", lambda: {"ref": "LV-1"}, base_delay_seconds=0.0
    )

    assert result["status"] == "SUCCESS"
    assert result["attempts"] == 1
    assert result["result"] == {"ref": "LV-1"}
    assert dispatcher.in_flight_tasks[result["task_id"]]["status"] == "SUCCESS"


async def test_a_coroutine_action_is_awaited(dispatcher):
    async def action():
        await asyncio.sleep(0)
        return "async-ok"

    result = await dispatcher.enqueue_and_execute(
        "t", "EMP-1", action, base_delay_seconds=0.0
    )

    assert result["result"] == "async-ok"


async def test_success_widens_the_concurrency_window(dispatcher):
    dispatcher.current_concurrency_limit = 10

    await dispatcher.enqueue_and_execute("t", "EMP-1", lambda: None, base_delay_seconds=0.0)

    assert dispatcher.current_concurrency_limit == 11


async def test_a_transient_failure_is_retried_and_then_succeeds(dispatcher):
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("503 from backend")
        return "recovered"

    result = await dispatcher.enqueue_and_execute(
        "t", "EMP-1", flaky, base_delay_seconds=0.0
    )

    assert result["status"] == "SUCCESS"
    assert result["attempts"] == 3


async def test_each_failure_sheds_load_before_the_next_attempt(dispatcher):
    """Two failures then a success: halve, halve, then the additive increase."""
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("429")
        return "ok"

    dispatcher.current_concurrency_limit = 16
    await dispatcher.enqueue_and_execute("t", "EMP-1", flaky, base_delay_seconds=0.0)

    assert dispatcher.current_concurrency_limit == 5  # 16 -> 8 -> 4 -> +1


async def test_the_backoff_doubles_between_attempts(dispatcher, monkeypatch):
    delays: list[float] = []

    async def _sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    def always_fails():
        raise RuntimeError("down")

    await dispatcher.enqueue_and_execute(
        "t", "EMP-1", always_fails, max_retries=4, base_delay_seconds=0.05
    )

    # Three waits for four attempts: nothing is slept after the last one.
    assert delays == [0.05, 0.1, 0.2]


async def test_exhausted_retries_route_to_the_dead_letter_queue(dispatcher):
    def always_fails():
        raise RuntimeError("permanent backend outage")

    result = await dispatcher.enqueue_and_execute(
        "submit_leave", "EMP-1", always_fails, max_retries=3, base_delay_seconds=0.0
    )

    assert result["status"] == "FAILED_DLQ"
    assert result["attempts"] == 3
    assert "permanent backend outage" in result["error"]
    assert dispatcher.in_flight_tasks[result["task_id"]]["status"] == "DLQ_ROUTED"

    (entry,) = dispatcher.dlq_store
    assert entry["task_name"] == "submit_leave"
    assert entry["employee_id"] == "EMP-1"
    assert entry["retries_exhausted"] == 3
    assert entry["retention_days"] == 14


# --- dispatcher: mid-saga revocation (§4.8) ----------------------------------


async def test_a_revoked_principal_never_reaches_the_backend(dispatcher):
    ran = {"called": False}

    def action():
        ran["called"] = True

    dispatcher.mark_principal_revoked("EMP-9")
    result = await dispatcher.enqueue_and_execute("t", "EMP-9", action)

    assert result["status"] == "DISCARDED_PRINCIPAL_REVOKED"
    assert not ran["called"]
    assert dispatcher.in_flight_tasks[result["task_id"]]["status"] == (
        "DISCARDED_PRINCIPAL_REVOKED"
    )


async def test_a_revocation_that_lands_between_retries_stops_the_task(dispatcher):
    """The pre-flight check cannot catch this one, which is why it is re-checked.

    The window is real: a queued task can sit behind a backoff for seconds while
    an administrator disables the account.
    """
    calls = {"n": 0}

    def fails_then_would_succeed():
        calls["n"] += 1
        dispatcher.mark_principal_revoked("EMP-9")
        raise RuntimeError("transient")

    result = await dispatcher.enqueue_and_execute(
        "t", "EMP-9", fails_then_would_succeed, base_delay_seconds=0.0
    )

    assert result["status"] == "DISCARDED_PRINCIPAL_REVOKED"
    assert result["error"] == "Principal revoked before retry attempt"
    assert calls["n"] == 1
    assert dispatcher.dlq_store == []


async def test_revocation_is_scoped_to_the_principal(dispatcher):
    dispatcher.mark_principal_revoked("EMP-9")

    result = await dispatcher.enqueue_and_execute(
        "t", "EMP-1", lambda: "ok", base_delay_seconds=0.0
    )

    assert result["status"] == "SUCCESS"


async def test_every_task_is_registered_before_it_runs(dispatcher):
    """Including the discarded one - an audit needs the attempt, not just the outcome."""
    dispatcher.mark_principal_revoked("EMP-9")

    first = await dispatcher.enqueue_and_execute("a", "EMP-9", lambda: None)
    second = await dispatcher.enqueue_and_execute("b", "EMP-1", lambda: None)

    assert set(dispatcher.in_flight_tasks) == {first["task_id"], second["task_id"]}
    assert dispatcher.in_flight_tasks[first["task_id"]]["task_name"] == "a"
    assert "enqueued_at" in dispatcher.in_flight_tasks[second["task_id"]]
