# ADR 0001: Hierarchical Multi-Agent Topology

## Status
Accepted

## Context
The enterprise HR and IT assistant must handle diverse domains: static policy retrieval, sensitive transactional HCM self-service, operational IT ticketing, and multi-step cross-system workflows. A single monolithic agent with flat tool calling suffers from tool hallucination, prompt injection vulnerability, and lack of domain containment.

## Decision
Adopt a strictly segregated, hierarchical multi-agent state graph consisting of:
1. **Supervisor Router (`sup-1.4.0`)**: Evaluates domain containment and delegates strictly to specialist agents. Prohibited from executing external tools directly.
2. **Policy Specialist (`pol-1.4.0`)**: Answers policy queries using Agent Search over curated Markdown knowledge bases with citations.
3. **WorkWeek HCM Specialist (`hcm-1.4.0`)**: Handles employee profile queries, contact information updates, and leave transactions under bound delegated identity.
4. **ServiceImmediately Specialist (`itsm-1.4.0`)**: Manages IT service desk incident querying, creation, commenting, and lifecycle transitions.
5. **Saga Coordinator (`saga-1.4.0`)**: Coordinates multi-step cross-system operations with deterministic compensation policies.

## Consequences
- Prevents cross-domain tool leakage.
- Enforces strict least-privilege tool allowlists per node.
- Provides modular observability and independent evaluation gates per agent.
