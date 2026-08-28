"""Turning an extracted leave request into a bookable span, or into a question.

A leave request reaches us as three loosely-related arguments pulled out of free
text by a model: a start date, an end date, and a number of days. Any of them
may be absent, unparseable, or inconsistent with the others - "999 days off from
tomorrow" arrived here with no duration at all.

The rule this module exists to enforce is that a missing argument is a question,
never a default. The previous behaviour defaulted `days` to 1.0, `start_date` to
tomorrow and `end_date` to the start, which between them could manufacture a
complete leave request out of an empty dict and write it to the HR system of
record - and then report it back as confirmed, with a duration and dates the
employee had never given.

It lives on its own rather than inside the WorkWeek specialist because there are
two agent runtimes in this repository (`src.core.agents.hcm` and
`src.adk.supervisor`) and both book leave. They had separate copies of the
defaults, so fixing one left the other quietly booking 2026-09-01 to 2026-09-02
for anybody whose dates could not be read.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any

from src.core.clock import add_working_days, working_days_between

logger = logging.getLogger("core.leave_request")


@dataclass(frozen=True)
class LeaveSpan:
    """A request complete enough to submit: when it runs and what it costs."""
    start_date: datetime.date
    end_date: datetime.date
    days: float


@dataclass(frozen=True)
class Clarification:
    """A request that cannot be read, and the question to put back to the employee."""
    question: str


def parse_leave_date(value: Any) -> datetime.date | None:
    """An ISO date, or `None` when the model supplied something unusable.

    The model populates these arguments, so a malformed value ("next Monday") is
    an expected input rather than an exceptional one - hence a `None` return
    instead of a raise every caller would have to wrap.
    """
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        logger.warning("Unparseable leave date %r; the caller must ask rather than derive one", value)
        return None


def parse_leave_days(value: Any) -> float | None:
    """A positive duration, or `None` when there isn't a readable one."""
    if value is None:
        return None
    try:
        days = float(value)
    except (TypeError, ValueError):
        logger.warning("Unparseable leave duration %r; the caller must ask rather than assume one", value)
        return None
    if days <= 0:
        logger.warning("Non-positive leave duration %r; treating as absent", value)
        return None
    return days


def resolve_leave_span(
    start_date: Any,
    end_date: Any,
    days: Any,
    today: datetime.date,
) -> LeaveSpan | Clarification:
    """Complete the request from what was actually extracted, or ask for the rest.

    Durations are counted in working days, matching the handbook: `okf/…/leave/
    vacation.md` line 94 - "Vacation is *not* extended by public holidays falling
    inside it" - so a span is worth its weekdays and nothing is added back.
    """
    start = parse_leave_date(start_date)
    end = parse_leave_date(end_date)
    duration = parse_leave_days(days)

    if start is None:
        return Clarification(
            "I could not tell which date your leave should start. "
            "Which date would you like to start from?"
        )
    if duration is None and end is None:
        return Clarification(
            f"I could not tell how much leave you are requesting from "
            f"{start.isoformat()}. How many days would you like to take?"
        )

    # Exactly one of the two is missing at this point, so the other determines it.
    if end is None:
        # A half-day is the one duration shorter than its span; it occupies a
        # single working day rather than none.
        end = start if duration < 1 else add_working_days(start, int(duration))
    elif duration is None:
        if end < start:
            return Clarification(
                f"I read your leave as running from {start.isoformat()} back to "
                f"{end.isoformat()}, which cannot be right. Which dates did you mean?"
            )
        duration = float(working_days_between(start, end))
        if duration == 0:
            return Clarification(
                f"{start.isoformat()} to {end.isoformat()} contains no working days. "
                "Which dates did you mean?"
            )

    # A backwards span is a misread, not something to silently straighten out:
    # correcting it books dates nobody asked for and reports them as confirmed.
    if end < start:
        return Clarification(
            f"I read your leave as running from {start.isoformat()} back to "
            f"{end.isoformat()}, which cannot be right. Which dates did you mean?"
        )
    if start < today:
        return Clarification(
            f"{start.isoformat()} is in the past. Which date would you like to start from?"
        )

    return LeaveSpan(start_date=start, end_date=end, days=duration)
