"""The business clock.

Every date this system reasons about - leave start dates, the "is this in the
past?" guardrail, the reference date handed to the supervisor model - is a date
in the *employee's* working calendar, not on the server's wall clock.

`datetime.date.today()` returns the date in the container's local zone. Under
SDD §2.2 the service is active-active across `us-central1` and `us-east4` while
the MVP-1 workforce is in Singapore, so that call has three different answers
depending on which region served the turn and what hour it is. An employee
booking leave for "tomorrow" at 22:00 SGT is on the *previous* calendar day in
both US regions, and §5.3's `start_date >= today` check would be comparing
against the wrong day.

Reading the date through one configured business timezone makes the answer the
same everywhere and testable in one place.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from config.settings import get_settings


def business_timezone() -> ZoneInfo:
    """The workforce timezone from settings (`BUSINESS_TIMEZONE`)."""
    return ZoneInfo(get_settings().BUSINESS_TIMEZONE)


def business_now() -> datetime.datetime:
    """Timezone-aware current instant in the business timezone."""
    return datetime.datetime.now(business_timezone())


def business_today() -> datetime.date:
    """Today's date as the workforce experiences it.

    Use this anywhere a `reference_date` argument falls back to "now". Callers
    that already accept an injected `reference_date` keep doing so - that is what
    makes the date-sensitive tests deterministic.
    """
    return business_now().date()


def working_days_between(start: datetime.date, end: datetime.date) -> int:
    """Working days in the inclusive span `start`..`end`.

    Weekends are excluded; **public holidays are deliberately not**. That is not
    an omission to fix later - it is what the handbook says. `okf/…/leave/
    vacation.md` line 94: "Vacation is *not* extended by public holidays falling
    inside it." A holiday inside a vacation does not give the day back, so it
    counts like any other weekday and no calendar is needed to count it.

    The alternative - shipping a Singapore holiday table - would mean inventing
    policy the corpus does not state, in the same system whose whole design
    premise is that it only answers from the approved handbook. A table that
    drifts from the real calendar would silently miscount leave, which is worse
    than not having one.

    Returns 0 for a span containing no weekdays; callers must decide what that
    means rather than treating it as a valid one-day request.
    """
    if end < start:
        return 0
    span = (end - start).days + 1
    return sum(
        1
        for offset in range(span)
        if (start + datetime.timedelta(days=offset)).weekday() < 5  # Mon-Fri
    )


def add_working_days(start: datetime.date, days: int) -> datetime.date:
    """The end date of a leave span of `days` working days beginning at `start`.

    Inverse of `working_days_between`, so `working_days_between(start,
    add_working_days(start, n)) == n` for `n >= 1`. The start date itself counts
    as the first working day when it is a weekday; a span asked to begin on a
    weekend starts counting from the following Monday.
    """
    if days < 1:
        return start
    current = start
    while current.weekday() >= 5:
        current += datetime.timedelta(days=1)
    counted = 1
    while counted < days:
        current += datetime.timedelta(days=1)
        if current.weekday() < 5:
            counted += 1
    return current
