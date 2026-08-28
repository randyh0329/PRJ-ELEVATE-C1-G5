---
type: Attested Computation
title: Annual vacation entitlement (Singapore)
description: Computes annual vacation days from years of continuous service and FTE percentage under handbook Section 20.2, with first-year proration. Four rules are producer assumptions, not source facts.
tags: [computation, vacation, leave, entitlement, accrual, fte, proration, singapore]
status: draft
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
stale_after: 2027-07-01T00:00:00Z
runtime: python
computation: /references/computations/vacation_entitlement.py
parameters:
  - name: years_of_service
    type: integer
    required: true
    description: Completed years of continuous service at 1 January of the year in question. 0 means the employee's first, partial year.
  - name: fte_percent
    type: number
    required: true
    description: Working schedule as a percentage of full time, greater than 0 and at most 100.
  - name: calendar_days_remaining_in_first_year
    type: integer
    required: false
    description: Calendar days from start date to 31 December inclusive. Required when years_of_service is 0; rejected as insufficient input otherwise.
executor:
  resource: /references/skills/run-python-entitlement.md
  receipt:
    - run_id
    - executed_source
    - parameters
    - result
attester:
  resource: /references/attesters/entitlement_binding.py
sources:
  - id: hb-20-2
    resource: https://github.com/randyh0329/PRJ-ELEVATE-C1-G5/blob/main/ALTOSTRAT%20SINGAPORE%20EMPLOYEE%20POLICY%20HANDBOOK%20%26%20CONDUCT%20GUIDELINES.md
    title: "Handbook Section 20.2: Accrual Rates and Increments"
    last_modified: 2026-07-01T00:00:00Z
  - id: hb-20-1
    resource: https://github.com/randyh0329/PRJ-ELEVATE-C1-G5/blob/main/ALTOSTRAT%20SINGAPORE%20EMPLOYEE%20POLICY%20HANDBOOK%20%26%20CONDUCT%20GUIDELINES.md
    title: "Handbook Section 20.1: Eligibility"
    last_modified: 2026-07-01T00:00:00Z
---

`status: draft`. **This computation is not fully grounded.** Three of the tiers are quoted
from the handbook; the first-year proration formula, its denominator, the year-zero tier and
the rounding rule are **not in the source at all**. They are producer decisions, and any of
them could be wrong. Read [Assumptions](#assumptions-not-in-the-source) before using a
result.

# What it computes

The **annual vacation-day allotment** for one employee for one year - the number credited on
1 January, before any booking, carryover or payout.

It does **not** compute a current balance. Carryover, floating holidays, days already taken
and separation payout are all outside its scope; see [vacation](/leave/vacation.md).

# Sourced rules

**Service tiers.** Employees earn their full year's vacation on **1 January**; the amount
depends on length of continuous service:[^hb-20-2]

| Continuous service | Days |
|--------------------|------|
| 1 to 6 years | **20** |
| 7 to 10 years | **21** |
| 11 years and above | **22** |

**FTE proration.** Part-time and fixed-term employees accrue **prorated vacation hours based
on their individual working schedule or FTE percentage**.[^hb-20-2]

**Eligibility** (enforced by the caller, not the script): full-time, part-time and
fixed-term Singapore-based employees, **apprentices and interns**. **Temps, vendors and
contractors are not eligible** and must contact their direct employer.[^hb-20-1]

# Assumptions not in the source

| # | Assumption | What the handbook actually says | Risk if wrong |
|---|-----------|--------------------------------|---------------|
| 1 | **Year-zero tier is 20 days** | The tiers start at "1 to 6 years". A first-year employee has completed **0** years and falls in **no** tier. | Low. 20 is the lowest tier and the only sensible reading, but it is inferred. |
| 2 | **Straight-line proration by calendar day** | Only "you will earn a prorated number of vacation days **based on your start date**". No formula. | **High.** Proration by completed month, by pay period, or by working day would each give a different answer. |
| 3 | **365-day denominator** | Nothing. Leap years are not mentioned. | Low, but produces a small systematic under-credit in a leap year. |
| 4 | **Round half up to one decimal place** | Nothing. §20.2 separately says vacation is **booked** in half- or full-days. | **High.** See below. |

**Assumption 4 has a visible consequence.** Because rounding is to 0.1 day but booking is
restricted to 0.5-day increments, the computation can return an entitlement the employee
**cannot fully book** - a 33% FTE employee with 3 years' service earns `6.6` days, and the
trailing `0.1` is unbookable. The script flags this as
`bookable_in_handbook_increments: false` rather than silently rounding, because the handbook
does not say whether the remainder is lost, rounded up, or paid. **Escalate those cases to
People Ops.**

Rounding to 0.5 instead would make every result bookable, but would invent a rounding
direction the source does not authorise and would systematically over- or under-credit
part-time staff. Neither choice is grounded; the flagged one at least surfaces the problem.

# Running it

See [run-python-entitlement](/references/skills/run-python-entitlement.md) for invocation,
worked examples, receipt format and attestation. Summary:

```
python3 references/computations/vacation_entitlement.py '{"years_of_service": 8, "fte_percent": 100}'
→ {"vacation_days": 21.0, "bookable_in_handbook_increments": true}
```

The executor emits a receipt carrying `run_id`, `executed_source` (a SHA-256 of the script
actually run), `parameters` and `result`. The attester at
`/references/attesters/entitlement_binding.py` re-runs the published script over the
receipt's parameters and rejects any receipt whose digest or result does not match.

**Attestation establishes execution integrity only.** A bound receipt proves the published
arithmetic was performed faithfully. It says nothing about whether the four assumptions above
match Altostrat's actual practice.

# Errors, not defaults

The script raises rather than guessing:

* `years_of_service` of `0` **without** `calendar_days_remaining_in_first_year` → error. It
  will not assume a start date.
* `fte_percent` outside `0 < n ≤ 100` → error.
* `calendar_days_remaining_in_first_year` outside `1..365` → error.
* Negative `years_of_service` → error.

This is deliberate. An entitlement figure produced from a guessed input is worse than no
figure.

# Related

* [Vacation](/leave/vacation.md) - the full policy, including carryover, floating holidays
  and the 15-day booking notice.
* [Exit](/workplace/exit.md) - how the year's entitlement is prorated and paid out on
  separation.
* [Source defects](/references/source-defects.md) - the vacation gaps are entries in the
  register.

[^hb-20-2]: Handbook Section 20.2 - Accrual Rates and Increments
[^hb-20-1]: Handbook Section 20.1 - Eligibility
