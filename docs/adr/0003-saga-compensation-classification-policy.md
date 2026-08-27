# ADR 0003: Saga Compensation Classification Policy

## Status
Accepted

## Context
In multi-system workflows (e.g. UC-2.2 Medical Leave Setup, UC-2.3 Office Relocation), operations span WorkWeek HCM and ServiceImmediately ITSM. If an ancillary step fails (such as provisioning an email delegation ticket in ITSM), a naive distributed transaction rollback would retract the employee's Medical Leave filing in WorkWeek. In an enterprise HR context, automatically cancelling a statutory medical leave filing causes severe legal, compliance, and employee distress.

## Decision
Categorize all saga workflow operations into 4 explicit compensation classes (SDD §5.4):
1. `READ_ONLY`: No compensation action needed.
2. `REVERSIBLE_SAFE`: Low-risk operations (e.g., updating residential address) where an inverse operation safely restores prior state on subsequent failure.
3. `ANCILLARY`: Operational support tasks (e.g., IT routing tickets, Facilities badge permits).
4. `HUMAN_CONSEQUENTIAL`: High-impact enterprise actions (e.g., Medical Leave filings, Short-Term Disability, Grievances).
   - **Crucial Rule**: On failure of subsequent ANCILLARY steps, HUMAN_CONSEQUENTIAL actions **MUST NOT BE AUTOMATICALLY ROLLED BACK**.
   - Instead, the workflow transitions to `PARTIALLY_COMPLETED_MANUAL_FOLLOWUP`, queues an escalation ticket in ServiceImmediately, and informs the employee that their leave is preserved while IT routing will be handled manually.
   - Structured `saga_compensation_event` telemetry is emitted adhering strictly to zero raw-PII logging standards.

## Consequences
- Protects employee welfare and statutory compliance during cross-system partial failures.
- Provides complete transparency regarding partially completed workflows.
