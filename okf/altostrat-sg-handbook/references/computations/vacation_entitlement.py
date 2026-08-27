"""Annual vacation-day entitlement under Altostrat Singapore handbook Section 20.2.

SOURCED  - the three service tiers and the FTE-proration rule are stated in the handbook.
ASSUMED  - the year-zero tier, the first-year proration formula, the 365-day denominator
           and the rounding rule are NOT in the handbook. They are producer decisions.
           See /computations/vacation-entitlement.md for why each was chosen and what
           would change if People Ops resolves them differently.

Run:  python3 vacation_entitlement.py '{"years_of_service": 8, "fte_percent": 100}'
Reads one JSON object argument, writes one JSON object to stdout.
"""

import json
import sys
from decimal import ROUND_HALF_UP, Decimal

# SOURCED: Handbook Section 20.2, "Accrual Rates and Increments".
# Read as (minimum years of continuous service, annual days).
SERVICE_TIERS = (
    (11, 22),   # "11 years and above of service: 22 days"
    (7, 21),    # "7 to 10 years of service: 21 days"
    (1, 20),    # "1 to 6 years of service: 20 days"
)

# ASSUMED: the handbook's tiers begin at 1 year. It states that first-year employees are
# prorated but never names the tier being prorated. We use the lowest tier.
YEAR_ZERO_BASE_DAYS = 20

# ASSUMED: fixed 365-day year. The handbook gives no denominator and does not address
# leap years.
DAYS_IN_YEAR = 365


def base_days(years_of_service):
    """Full-year, full-time entitlement before any proration."""
    if years_of_service < 0:
        raise ValueError("years_of_service must not be negative")
    if years_of_service == 0:
        return YEAR_ZERO_BASE_DAYS
    for minimum, days in SERVICE_TIERS:
        if years_of_service >= minimum:
            return days
    raise AssertionError("unreachable: tiers cover all years >= 1")


def annual_vacation_days(years_of_service, fte_percent,
                         calendar_days_remaining_in_first_year=None):
    """Return the vacation days earned for the year, rounded to one decimal place.

    years_of_service
        Completed years of continuous service at 1 January of the year in question.
        0 means this is the employee's first (partial) year.
    fte_percent
        Working schedule as a percentage of full time. 100 for full-time.
        SOURCED: Section 20.2 prorates part-time and fixed-term employees "based on their
        individual working schedule or FTE percentage".
    calendar_days_remaining_in_first_year
        Required only when years_of_service is 0. Calendar days from the start date to
        31 December inclusive.
    """
    if not 0 < fte_percent <= 100:
        raise ValueError("fte_percent must be greater than 0 and at most 100")

    days = Decimal(base_days(years_of_service))

    if years_of_service == 0:
        if calendar_days_remaining_in_first_year is None:
            raise ValueError(
                "first-year requests must supply calendar_days_remaining_in_first_year"
            )
        remaining = int(calendar_days_remaining_in_first_year)
        if not 0 < remaining <= DAYS_IN_YEAR:
            raise ValueError(
                "calendar_days_remaining_in_first_year must be in 1..%d" % DAYS_IN_YEAR
            )
        # ASSUMED: straight-line proration by calendar day. The handbook says only
        # "prorated ... based on your start date".
        days = days * Decimal(remaining) / Decimal(DAYS_IN_YEAR)

    days = days * Decimal(fte_percent) / Decimal(100)

    # ASSUMED: round half up to one decimal place. The handbook states no rounding rule.
    return float(days.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def main(argv):
    if len(argv) != 2:
        print(json.dumps({"error": "expected exactly one JSON argument"}))
        return 2
    try:
        params = json.loads(argv[1])
        result = annual_vacation_days(
            years_of_service=params["years_of_service"],
            fte_percent=params["fte_percent"],
            calendar_days_remaining_in_first_year=params.get(
                "calendar_days_remaining_in_first_year"
            ),
        )
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": "%s: %s" % (type(exc).__name__, exc)}))
        return 1

    bookable = (Decimal(str(result)) * 2) % 1 == 0
    print(json.dumps({
        "vacation_days": result,
        "bookable_in_handbook_increments": bookable,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
