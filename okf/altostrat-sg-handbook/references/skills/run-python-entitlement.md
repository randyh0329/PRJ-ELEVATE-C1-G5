---
type: Skill
title: Running the vacation entitlement computation
description: Executor instructions for /computations/vacation-entitlement.md - how to invoke the script, what receipt to emit, and how to have the receipt attested.
tags: [reference, skill, executor, computation, python, vacation]
status: stable
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
---

This is the executor procedure for
[vacation entitlement](/computations/vacation-entitlement.md). It is a `references/`
document under OKF §6.3, not a policy statement.

# Prerequisites

* Python 3.7 or later. The script uses only the standard library - `json`, `sys`,
  `decimal`.
* No network access, no filesystem writes, no arguments other than the parameter object.

# Invoke

```
python3 references/computations/vacation_entitlement.py '<parameters-as-json>'
```

Paths are relative to the bundle root.

# Parameters

| Name | Type | Required | Meaning |
|------|------|----------|---------|
| `years_of_service` | integer ≥ 0 | yes | Completed years of continuous service at 1 January of the year in question. `0` means the employee's first, partial year. |
| `fte_percent` | number, `0 < n ≤ 100` | yes | Working schedule as a percentage of full time. |
| `calendar_days_remaining_in_first_year` | integer, `1..365` | only when `years_of_service` is `0` | Calendar days from the start date to 31 December inclusive. |

# Output

On success, one JSON object on stdout, exit status `0`:

```json
{"vacation_days": 21.0, "bookable_in_handbook_increments": true}
```

`bookable_in_handbook_increments` is `false` when the result is not a whole or half day.
Handbook §20.2 permits booking **only in half- or full-days**, so a `false` here means the
entitlement cannot be fully consumed as booked leave. The handbook does not say what happens
to the remainder. **Escalate rather than round it away.**

On failure, one JSON object with an `error` key, exit status `1` (or `2` for a missing
argument). Errors are raised, never silently defaulted:

```json
{"error": "ValueError: first-year requests must supply calendar_days_remaining_in_first_year"}
```

# Worked examples

Verified by execution on 2026-08-27:

| Parameters | Result |
|------------|--------|
| `{"years_of_service": 3, "fte_percent": 100}` | `20.0`, bookable |
| `{"years_of_service": 8, "fte_percent": 100}` | `21.0`, bookable |
| `{"years_of_service": 15, "fte_percent": 100}` | `22.0`, bookable |
| `{"years_of_service": 3, "fte_percent": 60}` | `12.0`, bookable |
| `{"years_of_service": 0, "fte_percent": 100, "calendar_days_remaining_in_first_year": 183}` | `10.0`, bookable |
| `{"years_of_service": 3, "fte_percent": 33}` | `6.6`, **not** bookable |
| `{"years_of_service": 0, "fte_percent": 80, "calendar_days_remaining_in_first_year": 200}` | `8.8`, **not** bookable |
| `{"years_of_service": 0, "fte_percent": 100}` | error - first-year requires the day count |
| `{"years_of_service": 2, "fte_percent": 0}` | error - `fte_percent` out of range |

# Emit a receipt

Write a JSON object with exactly these four keys:

```json
{
  "run_id": "<unique identifier for this execution>",
  "executed_source": "sha256:<digest of the script you actually ran>",
  "parameters": { "years_of_service": 8, "fte_percent": 100 },
  "result": 21.0
}
```

Compute `executed_source` **at run time from the file you executed**:

```
python3 -c "import hashlib,sys;print('sha256:'+hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" \
  references/computations/vacation_entitlement.py
```

As of 2026-08-27 that digest is
`sha256:40238f434e11f37ea03985b112f03c225b4d82c1ab6bf9843e8666e6ce1a396d`. **Do not copy
this value into a receipt** - recompute it, or the receipt attests nothing.

# Attest the receipt

```
python3 references/attesters/entitlement_binding.py <receipt.json>
```

Exit `0` and `{"bound": true, "findings": []}` mean the receipt binds: the published script
was the one run, and the reported result is what it produces for those parameters. Exit `1`
lists what failed. Exit `2` means the receipt was unreadable or malformed.

Verified on 2026-08-27: a correct receipt binds; a receipt with `result` altered to `25.0`
is rejected with `result 25.0 does not match recomputation 21.0`.

# What attestation does not establish

The attester re-runs the published script. It confirms **execution integrity only**. It does
**not** confirm that the script is a correct reading of the handbook, and it cannot - four of
the script's rules are producer assumptions with no basis in the source. Those are
enumerated in [vacation entitlement](/computations/vacation-entitlement.md#assumptions-not-in-the-source).

A bound receipt is therefore evidence that *this arithmetic* was performed faithfully, not
that the number is the employee's true entitlement.
