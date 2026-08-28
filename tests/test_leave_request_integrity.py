"""Nothing about a leave request may be invented.

The bug this file exists for: asked to "take 999 days off from tomorrow", the
agent answered

    Your vacation request for 1.0 days from 2026-08-29 to 2026-08-29 has been
    submitted in WorkWeek. Transaction Reference: [WW-LV-MCP].
    Remaining balance: 18.0 days.

Every number in that sentence was manufactured. The extractor returned no
duration, so `days` defaulted to 1.0; `start_date` defaulted to tomorrow and
`end_date` to the start; the reference was a hardcoded constant identical for
every request ever made; and the balance was `previous - days`, arithmetic on a
read taken before the write. The 999 the employee actually asked for never
reached the balance guardrail, which would have refused it outright.

Five separate defaults had to line up to produce it, so the tests are grouped by
the one they pin:

  * argument resolution - a missing argument becomes a question, not a value
  * the working-day calendar the durations are counted in
  * the guardrail that makes `days` and the span describe each other
  * the reference and balance reported back after a successful write
  * both agent runtimes, end to end, on the original prompt shape
"""

from __future__ import annotations

import datetime

import pytest

from src.adk.supervisor import adk_runner
from src.core.agents.hcm import workweek_autonomous_specialist
from src.core.clock import add_working_days, working_days_between
from src.core.leave_request import (
    Clarification,
    LeaveSpan,
    parse_leave_days,
    resolve_leave_span,
)
from src.guardrails.operation_guardrails import OperationGuardrailEngine
from src.integrations.vertex.client import VertexGeminiClient
from src.models.routing import WorkWeekToolSelection

#: A Friday, matching the day the reported conversation happened on.
TODAY = datetime.date(2026, 8, 28)
MON = datetime.date(2026, 9, 7)
FRI = datetime.date(2026, 9, 11)
SAT = datetime.date(2026, 9, 5)
SUN = datetime.date(2026, 9, 6)


def _resolve(**kwargs):
    args = {"start_date": None, "end_date": None, "days": None, "today": TODAY}
    args.update(kwargs)
    return resolve_leave_span(**args)


# --- the working-day calendar -------------------------------------------------
#
# Weekends are excluded and public holidays are deliberately not, because the
# handbook says a holiday inside leave does not extend it
# (okf/altostrat-sg-handbook/leave/vacation.md, line 94). There is no holiday
# table anywhere in this repository, and inventing one would be fabricating
# policy - the failure mode this whole file is about.


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (MON, MON, 1),                                # one weekday
        (MON, FRI, 5),                                # a full working week
        (SAT, SUN, 0),                                # a weekend is no leave at all
        (datetime.date(2026, 9, 4), MON, 2),          # Fri..Mon skips the weekend
        (datetime.date(2026, 9, 7), datetime.date(2026, 9, 18), 10),  # two weeks
        (FRI, MON, 0),                                # backwards spans count nothing
    ],
)
def test_working_days_between_counts_weekdays_inclusively(start, end, expected):
    assert working_days_between(start, end) == expected


@pytest.mark.parametrize(
    ("start", "days", "expected"),
    [
        (MON, 1, MON),
        (MON, 5, FRI),
        (datetime.date(2026, 9, 4), 2, MON),          # Friday + 2 lands on Monday
        (SAT, 1, MON),                                # a span starting on a weekend
        (MON, 0, MON),                                # nothing to add
        (MON, 10, datetime.date(2026, 9, 18)),
    ],
)
def test_add_working_days_lands_on_a_weekday(start, days, expected):
    assert add_working_days(start, days) == expected


def test_the_two_calendar_helpers_agree_with_each_other():
    """Whatever `add_working_days` produces must cost the days it was asked for."""
    for days in range(1, 25):
        end = add_working_days(MON, days)
        assert working_days_between(MON, end) == days


# --- a missing argument is a question -----------------------------------------


def test_an_empty_request_asks_for_a_start_date():
    """The whole request used to be manufactured from exactly this input."""
    result = _resolve()

    assert isinstance(result, Clarification)
    assert "which date" in result.question.lower()


def test_a_start_date_with_no_duration_asks_for_one():
    """"999 days off from tomorrow": the 999 was not extracted, and the missing
    duration silently became 1.0 rather than a question."""
    result = _resolve(start_date="2026-09-07")

    assert isinstance(result, Clarification)
    assert "how many days" in result.question.lower()


@pytest.mark.parametrize("value", ["next Monday", "tomorrow", "2026-13-01", "01/09/2026", ""])
def test_a_start_date_the_extractor_could_not_write_asks_rather_than_defaults(value):
    result = _resolve(start_date=value, days=3)

    assert isinstance(result, Clarification)


@pytest.mark.parametrize("value", ["a few", None, "", 0, -3])
def test_a_duration_that_is_not_a_positive_number_is_absent_not_zero(value):
    """`float("a few")` used to raise and `days=0` used to submit. Both are
    "we did not get a duration", which is a question."""
    assert parse_leave_days(value) is None

    result = _resolve(start_date="2026-09-07", days=value)
    assert isinstance(result, Clarification)
    assert "how many days" in result.question.lower()


def test_a_span_running_backwards_is_queried_not_reversed():
    result = _resolve(start_date="2026-09-11", end_date="2026-09-07")

    assert isinstance(result, Clarification)
    assert "cannot be right" in result.question


def test_a_backwards_span_with_a_duration_is_queried_too():
    """With `days` present the end date used to be recomputed from it, booking a
    span the employee never named and calling it submitted."""
    result = _resolve(start_date="2026-09-11", end_date="2026-09-07", days=2)

    assert isinstance(result, Clarification)


def test_a_span_of_pure_weekend_is_queried():
    result = _resolve(start_date="2026-09-05", end_date="2026-09-06")

    assert isinstance(result, Clarification)
    assert "no working days" in result.question


def test_a_start_date_in_the_past_is_queried_not_pulled_forward():
    """Silently moving January's leave to today books dates nobody asked for."""
    result = _resolve(start_date="2026-01-05", end_date="2026-01-07")

    assert isinstance(result, Clarification)
    assert "past" in result.question


def test_today_itself_is_not_in_the_past():
    result = _resolve(start_date=TODAY.isoformat(), days=1)

    assert result == LeaveSpan(start_date=TODAY, end_date=TODAY, days=1.0)


# --- deriving the argument that was not given ---------------------------------


def test_a_duration_alone_derives_the_end_date_in_working_days():
    assert _resolve(start_date="2026-09-07", days=5) == LeaveSpan(MON, FRI, 5.0)


def test_a_derived_end_date_steps_over_the_weekend():
    """Friday plus two days is Monday, not Saturday - a leave request cannot end
    on a day the employee was never working."""
    assert _resolve(start_date="2026-09-04", days=2) == LeaveSpan(
        datetime.date(2026, 9, 4), MON, 2.0
    )


def test_a_half_day_occupies_a_single_working_day():
    assert _resolve(start_date="2026-09-07", days=0.5) == LeaveSpan(MON, MON, 0.5)


def test_a_span_alone_derives_the_duration_in_working_days():
    """Mon..Fri the following week is ten working days, not the fourteen
    calendar days between them."""
    assert _resolve(start_date="2026-09-07", end_date="2026-09-18") == LeaveSpan(
        MON, datetime.date(2026, 9, 18), 10.0
    )


def test_a_span_alone_does_not_charge_for_its_weekend():
    assert _resolve(start_date="2026-09-04", end_date="2026-09-07") == LeaveSpan(
        datetime.date(2026, 9, 4), MON, 2.0
    )


def test_both_arguments_given_are_both_kept():
    """Neither is recomputed: the guardrail decides whether they agree."""
    assert _resolve(start_date="2026-09-07", end_date="2026-09-11", days=5) == LeaveSpan(
        MON, FRI, 5.0
    )


# --- the duration and the span must describe each other -----------------------


@pytest.fixture
def engine():
    return OperationGuardrailEngine()


def test_a_duration_longer_than_its_span_is_refused(engine):
    """Ten days of balance charged against one day away."""
    res = engine.validate_leave_request(
        days_requested=10.0, remaining_balance=20.0,
        start_date=MON, end_date=MON, reference_date=TODAY,
    )

    assert not res.is_valid
    assert res.rule_name == "LEAVE_DURATION_SPAN_CONSTRAINT"
    assert "1 working day." in res.error_message


def test_a_duration_shorter_than_its_span_is_refused(engine):
    """The expensive direction: away for a working week, charged one day. The
    discrepancy surfaces at year end or on separation, when the balance is
    settled in cash."""
    res = engine.validate_leave_request(
        days_requested=1.0, remaining_balance=20.0,
        start_date=MON, end_date=FRI, reference_date=TODAY,
    )

    assert not res.is_valid
    assert res.rule_name == "LEAVE_DURATION_SPAN_CONSTRAINT"
    assert "5 working days" in res.error_message


def test_a_span_with_no_working_days_in_it_is_refused(engine):
    res = engine.validate_leave_request(
        days_requested=2.0, remaining_balance=20.0,
        start_date=SAT, end_date=SUN, reference_date=TODAY,
    )

    assert not res.is_valid
    assert res.rule_name == "LEAVE_EMPTY_SPAN_CONSTRAINT"


def test_a_half_day_against_a_single_working_day_is_accepted(engine):
    """The one legitimate way to consume less balance than the span is worth."""
    res = engine.validate_leave_request(
        days_requested=0.5, remaining_balance=20.0,
        start_date=MON, end_date=MON, reference_date=TODAY,
    )

    assert res.is_valid


def test_a_half_day_stretched_over_a_working_week_is_not(engine):
    res = engine.validate_leave_request(
        days_requested=0.5, remaining_balance=20.0,
        start_date=MON, end_date=FRI, reference_date=TODAY,
    )

    assert not res.is_valid
    assert res.rule_name == "LEAVE_DURATION_SPAN_CONSTRAINT"


def test_a_matching_duration_and_span_passes(engine):
    res = engine.validate_leave_request(
        days_requested=5.0, remaining_balance=20.0,
        start_date=MON, end_date=FRI, reference_date=TODAY,
    )

    assert res.is_valid


def test_the_balance_limit_still_bites_when_the_span_agrees(engine):
    """999 days is refusable only once a duration that large can reach here at
    all - previously it was replaced by 1.0 several layers earlier."""
    res = engine.validate_leave_request(
        days_requested=999.0, remaining_balance=14.0,
        start_date=MON, end_date=add_working_days(MON, 999), reference_date=TODAY,
    )

    assert not res.is_valid
    assert res.rule_name == "LEAVE_BALANCE_LIMIT_CONSTRAINT"


# --- the offline extractor ----------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        "take 999 days off from tomorrow",
        "cancel my leave",
        "show my leave requests",
        "update my phone number",
        "who is my manager",
        "how much vacation do I have",
    ],
)
def test_the_offline_tool_selector_returns_instead_of_raising(prompt):
    """Every branch omitted the schema's required `reasoning` field, so each one
    raised `ValidationError` out of the very `except` clause that called it: the
    offline path had no offline path. The suite never saw it because `conftest`
    replaces `select_workweek_tool` wholesale, so this only ever ran in
    production, during exactly the Vertex outage it exists for."""
    selection = VertexGeminiClient._fallback_select_workweek_tool(
        VertexGeminiClient.__new__(VertexGeminiClient), prompt, TODAY
    )

    assert selection.tool_name
    assert selection.reasoning


def test_the_offline_selector_extracts_no_leave_dates_it_cannot_read():
    """Keyword matching can pick the tool. It cannot read a date or a duration,
    and it used to answer "2.0 days starting next Monday" anyway."""
    selection = VertexGeminiClient._fallback_select_workweek_tool(
        VertexGeminiClient.__new__(VertexGeminiClient), "take 999 days off from tomorrow", TODAY
    )
    args = selection.get_effective_arguments()

    assert selection.tool_name == "request_time_off"
    assert "start_date" not in args
    assert "end_date" not in args
    assert "days" not in args


def test_the_offline_selector_invents_no_contact_details():
    """It filled in "Updated Address" and "+65-6123-4567" - a placeholder and
    someone else's phone number, saved over the employee's real details."""
    selection = VertexGeminiClient._fallback_select_workweek_tool(
        VertexGeminiClient.__new__(VertexGeminiClient), "update my address please", TODAY
    )

    assert selection.tool_name == "update_personal_info"
    assert selection.get_effective_arguments() == {}


def test_the_offline_selector_cancels_nothing_it_was_not_given():
    """This defaulted to request 101 - a real id belonging to whoever owned it."""
    selection = VertexGeminiClient._fallback_select_workweek_tool(
        VertexGeminiClient.__new__(VertexGeminiClient), "cancel my leave", TODAY
    )

    assert selection.tool_name == "cancel_leave_request"
    assert "request_id" not in selection.get_effective_arguments()


# --- the reported conversation, end to end ------------------------------------


def test_the_reported_prompt_shape_asks_instead_of_confirming_a_booking():
    """The regression proper. With no duration extracted, the employee used to
    read "your vacation request for 1.0 days ... has been submitted"."""
    result = workweek_autonomous_specialist.execute_fast_path(
        tool_name="request_time_off",
        arguments={"start_date": "2026-08-29", "leave_type": "Vacation"},
        caller_id="EMP-1001",
        reference_date=TODAY,
    )

    assert result["action_performed"] == "CLARIFY_LEAVE"
    assert result["transaction_reference"] is None
    assert "submitted" not in result["response_text"].lower()
    assert "1.0 days" not in result["response_text"]


def test_a_duration_beyond_the_balance_now_reaches_the_balance_guardrail():
    """EMP-1001 holds 14 vacation days. 999 must be refused for that reason and
    named as such, not quietly replaced by a number that fits."""
    result = workweek_autonomous_specialist.execute_fast_path(
        tool_name="request_time_off",
        arguments={"start_date": "2026-08-31", "days": 999.0},
        caller_id="EMP-1001",
        reference_date=TODAY,
    )

    assert "999.0 days" in result["response_text"]
    assert "Insufficient leave balance" in result["response_text"]
    assert result["transaction_reference"] is None


def test_a_confirmed_booking_still_reads_back_cleanly():
    """The fix must not make the working case unusable: a complete request is
    still submitted, and still reports its dates, duration and reference."""
    result = workweek_autonomous_specialist.execute_fast_path(
        tool_name="request_time_off",
        arguments={"start_date": "2026-08-31", "days": 1.0},
        caller_id="EMP-1001",
        reference_date=TODAY,
    )

    assert result["action_performed"] == "SUBMIT_LEAVE"
    assert "2026-08-31" in result["response_text"]
    assert result["transaction_reference"]
    assert "WW-LV-MCP" not in result["response_text"]


def test_no_reported_reference_is_never_replaced_by_a_constant():
    """"WW-LV-MCP" was handed to every employee as their transaction reference.
    It matched no record in WorkWeek and `cancel_leave_request` could do nothing
    with it - a reference we invented is worse than admitting we have none."""
    composed = workweek_autonomous_specialist._format_tool_response(
        "request_time_off",
        {},
        {
            "status": "SUCCESS",
            "request_id": None,
            "remaining_balance": None,
            "start_date": "2026-09-07",
            "end_date": "2026-09-07",
            "days": 1.0,
            "leave_type": "Vacation",
        },
    )

    assert "WW-LV-MCP" not in composed["response_text"]
    assert composed["transaction_reference"] is None
    assert "did not return a reference" in composed["response_text"]
    assert "Remaining balance" not in composed["response_text"]


def _extract_nothing_but_the_tool(monkeypatch):
    """Make the tool selector answer the way the offline fallback now does:
    naming `request_time_off` with no dates and no duration."""
    monkeypatch.setattr(
        VertexGeminiClient,
        "select_workweek_tool",
        lambda self, prompt, **kwargs: WorkWeekToolSelection(
            tool_name="request_time_off",
            arguments={"leave_type": "Vacation"},
            reasoning="Test: nothing extractable beyond the tool.",
        ),
    )


def test_the_adk_runtime_asks_rather_than_booking_its_own_default_fortnight(monkeypatch):
    """The second runtime had its own copy of the defaults - 2026-09-01 to
    2026-09-02 for 2.0 days - so fixing one left the other still booking."""
    _extract_nothing_but_the_tool(monkeypatch)

    response = adk_runner.process_message(
        "submit a vacation request", caller_employee_id="EMP-1001"
    )

    assert response.action_performed == "CLARIFY_LEAVE_REQUEST"
    assert response.transaction_reference is None
    assert "2026-09-01" not in response.response_text
    assert "successfully submitted" not in response.response_text


def test_the_adk_runtime_cancels_nothing_it_was_not_given(monkeypatch):
    """Its cancellation branch ended in `req_id = req_id or "101"`, so "cancel
    my leave" with nothing to match cancelled request 101."""
    monkeypatch.setattr(
        VertexGeminiClient,
        "select_workweek_tool",
        lambda self, prompt, **kwargs: WorkWeekToolSelection(
            tool_name="cancel_leave_request",
            arguments={},
            reasoning="Test: cancellation with no reference.",
        ),
    )

    response = adk_runner.process_message(
        "please cancel my leave", caller_employee_id="EMP-1001"
    )

    assert response.action_performed == "CLARIFY_CANCELLATION"
    assert "101" not in response.response_text
