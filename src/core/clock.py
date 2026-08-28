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
