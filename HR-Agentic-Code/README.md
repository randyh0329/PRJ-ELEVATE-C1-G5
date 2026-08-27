# Enterprise HR Agentic Solution (MVP 1)

This repository contains the baseline code for the **Enterprise HR Agentic Solution (MVP 1)**, designed according to the approved Solution Design Document (SDD).

## Architectural Highlights
- **Dynamic Safety Perimeter**: Real-time Cloud DLP SPII redaction (Singapore NRIC, US SSN, phone/address tokenization) and Model Armor prompt injection / jailbreak protection.
- **Agent Orchestration**: HREnterpriseAgent reasoning loop with intent classification, parameter extraction, and execution routing.
- **Deterministic Dual Grounding**: Curated Open Knowledge Format (OKF) store providing grounded policy Q&A with 100% verified clickable deep links (e.g. `[View Policy Section 04.2](https://hr.corp.internal/policies/04.2-bereavement)`).
- **HCM & ITSM Mock Connectors**: WorkWeek HCM and ServiceImmediately ITSM adapters with operational guardrails (leave balance limits, temporal constraints, 30-minute ticket deduplication, state transitions).
- **Saga Cross-System Coordinator**: Distributed transaction management with backward compensation (e.g., auto-canceling WorkWeek leave if downstream ServiceImmediately ticket creation fails) and escalation ticketing.
- **Structured Audit Logging**: Cryptographic-grade audit logging tagging origin (`X-Automation-Origin`) and caller (`X-Caller-Employee-Id`).
- **Modular Boilerplates**: Structured stubs for live Workday REST, ServiceNow Table API, Vertex AI Search RAG pipelines, and Agent-to-Agent (A2A) event protocols.

---

## Directory Layout
```
HR-Gentic_code/
├── config/
│   └── settings.py               # Application & environment configuration
├── src/
│   ├── main.py                   # FastAPI REST API & Interactive CLI Entrypoint
│   ├── core/                     # Agent Orchestrator, DLP/Safety, Saga Coordinator, Session
│   │   ├── agent.py
│   │   ├── safety.py
│   │   ├── saga.py
│   │   └── session.py
│   ├── grounding/                # Policy Grounding Engine, OKF Store, RAG Boilerplate
│   │   ├── okf_store.py
│   │   ├── policy_engine.py
│   │   └── rag_boilerplate.py
│   ├── guardrails/               # Operational Guardrails (Balance, Temporal, Deduplication)
│   │   └── operation_guardrails.py
│   ├── integrations/             # Connectors & Mock Services
│   │   ├── workweek/             # WorkWeek HCM connector & mock backend
│   │   ├── service_immediately/  # ServiceImmediately ITSM connector & mock backend
│   │   └── saas_boilerplate/     # Boilerplates for Live Workday, ServiceNow, A2A
│   └── telemetry/                # Structured Audit Logger
│       └── audit_logger.py
└── tests/                        # 25-Case Golden Evaluation & Verification Suite
```

---

## Getting Started

### 1. Installation & Environment Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Running Unit & Integration Tests
```bash
pytest tests/ -v
```

### 3. Running the FastAPI Server
```bash
python3 -m uvicorn src.main:app --reload --port 8000
```

### 4. Running the Interactive Agent CLI
```bash
python3 src/main.py --cli
```
