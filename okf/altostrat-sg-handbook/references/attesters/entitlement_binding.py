"""Attester for /computations/vacation-entitlement.md.

Checks that a claimed result is consistent with the computation as published: it re-runs
the computation over the receipt's parameters and compares. It does NOT check that the
computation is a correct reading of the handbook - only that the executor ran the
published source and reported what it actually produced.

Run:  python3 entitlement_binding.py receipt.json
Exit 0 if the receipt binds, 1 if it does not, 2 on a malformed receipt.
"""

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "computations"))

from vacation_entitlement import annual_vacation_days

COMPUTATION_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, "computations", "vacation_entitlement.py",
)

REQUIRED_RECEIPT_KEYS = ("run_id", "executed_source", "parameters", "result")


def source_digest(path=COMPUTATION_PATH):
    with open(path, "rb") as handle:
        return "sha256:" + hashlib.sha256(handle.read()).hexdigest()


def attest(receipt):
    """Return (ok, list_of_findings)."""
    findings = []

    missing = [key for key in REQUIRED_RECEIPT_KEYS if key not in receipt]
    if missing:
        return False, ["receipt is missing required keys: %s" % ", ".join(missing)]

    published = source_digest()
    if receipt["executed_source"] != published:
        findings.append(
            "executed_source %s does not match the published computation %s"
            % (receipt["executed_source"], published)
        )

    params = receipt["parameters"]
    try:
        recomputed = annual_vacation_days(
            years_of_service=params["years_of_service"],
            fte_percent=params["fte_percent"],
            calendar_days_remaining_in_first_year=params.get(
                "calendar_days_remaining_in_first_year"
            ),
        )
    except (ValueError, KeyError, TypeError) as exc:
        return False, ["recomputation failed: %s: %s" % (type(exc).__name__, exc)]

    if recomputed != receipt["result"]:
        findings.append(
            "result %r does not match recomputation %r" % (receipt["result"], recomputed)
        )

    return not findings, findings


def main(argv):
    if len(argv) != 2:
        print("usage: entitlement_binding.py <receipt.json>", file=sys.stderr)
        return 2
    try:
        with open(argv[1]) as handle:
            receipt = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print("could not read receipt: %s" % exc, file=sys.stderr)
        return 2

    ok, findings = attest(receipt)
    print(json.dumps({"bound": ok, "findings": findings}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
