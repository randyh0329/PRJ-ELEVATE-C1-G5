# References

External material, run instructions and code, per OKF §6.3. Nothing here is a policy
statement.

* [Source defect register](source-defects.md) - 23 catalogued defects in the handbook: contradictions, structural faults, corrupted text, LLM authoring artifacts, unresolved placeholders and gaps. Most concepts in this bundle link here.

# Computation code

* [`computations/vacation_entitlement.py`](computations/vacation_entitlement.py) - the executable for [vacation entitlement](/computations/vacation-entitlement.md). Standard library only; sourced rules and producer assumptions are marked inline.
* [`attesters/entitlement_binding.py`](attesters/entitlement_binding.py) - re-runs the published computation over a receipt's parameters and rejects any receipt whose source digest or result does not match.

# Run instructions

* [Running the vacation entitlement computation](skills/run-python-entitlement.md) - invocation, parameters, worked examples, receipt format and attestation.
