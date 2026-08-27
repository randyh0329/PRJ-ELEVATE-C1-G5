# Enterprise HR Multi-Agent Orchestration Solution (MVP 1)

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg)](https://fastapi.tiangolo.com)
[![Google ADK](https://img.shields.io/badge/Google%20ADK-1.4.0-4285F4.svg)](https://cloud.google.com/vertex-ai)
[![License: Internal](https://img.shields.io/badge/License-Internal%20Google-red.svg)]()

Production-grade, multi-agent AI architecture implementing cross-system enterprise workflows across **WorkWeek HCM** and **ServiceImmediately ITSM**, policy grounding with zero-hallucination citations, two-layer composite credential authorization, Cloud DLP/Model Armor security perimeters, and consequence-aware distributed transaction (Saga) compensation.

---

## 1. Project Folder Structure

```
/usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/
├── config/                                 # Centralized configuration & environment settings
│   ├── __init__.py
│   └── settings.py                         # Pydantic BaseSettings (MCP, endpoints, guardrails)
├── src/                                    # Core application source code
│   ├── __init__.py
│   ├── main.py                             # FastAPI REST API server + interactive console CLI
│   ├── core/                               # StateGraph engine & specialized agent nodes
│   │   ├── __init__.py
│   │   ├── state.py                        # TypedDict AgentState & SagaStepRecord definitions
│   │   ├── graph.py                        # AgentOrchestrationGraph multi-agent execution pipeline
│   │   ├── agent.py                        # HREnterpriseAgent facade for unified turn processing
│   │   ├── session.py                      # Short-term session memory store (no static balance caching)
│   │   ├── safety.py                       # Ingress/egress DLP and Model Armor security filters
│   │   └── agents/                         # Tiered specialized agent nodes
│   │       ├── __init__.py
│   │       ├── supervisor.py               # Gemini 3.7 Flash: Intent routing & domain containment
│   │       ├── policy.py                   # Gemini 3.7 Flash: Grounded policy RAG specialist
│   │       ├── hcm.py                      # Gemini 3.7 Flash: WorkWeek HCM self-service specialist
│   │       ├── itsm.py                     # Gemini 3.7 Flash: ServiceImmediately ITSM specialist
│   │       └── saga.py                     # Gemini 3.1 Pro: Distributed Saga workflow coordinator
│   ├── saga/                               # Distributed transaction ledger & compensation logic
│   │   ├── __init__.py
│   │   ├── ledger.py                       # Firestore Multi-Region nam5 Saga step ledger
│   │   ├── compensation.py                 # Consequence-Aware Compensation Decision Matrix (§5.4)
│   │   └── dispatcher.py                   # Cloud Tasks AIMD rate-limited async task dispatcher
│   ├── security/                           # Identity, auth minting & perimeter inspection
│   │   ├── __init__.py
│   │   ├── token_minter.py                 # Two-Layer Composite Token Minter (IAM signJwt Layer 2)
│   │   ├── dlp.py                          # Cloud DLP SPII/PII de-identification & re-identification
│   │   └── model_armor.py                  # Vertex AI Model Armor prompt injection & jailbreak filter
│   ├── guardrails/                         # Business rules & operational constraints
│   │   ├── __init__.py
│   │   └── operation_guardrails.py         # 30-min deduplication, positive leave days, temporal checks
│   ├── grounding/                          # OKF catalog & deterministic policy grounding
│   │   ├── __init__.py
│   │   ├── okf_store.py                    # Open Knowledge Format (OKF) curated policy catalog
│   │   ├── policy_engine.py                # Dual Grounding Engine with deep-link clickable citations
│   │   └── rag_boilerplate.py              # Vertex AI Agent Search datastore integration stubs
│   ├── integrations/                       # SaaS adapters, FastMCP clients, and mock microservices
│   │   ├── __init__.py
│   │   ├── workweek/                       # WorkWeek HCM adapter client, mock service, and models
│   │   ├── service_immediately/            # ServiceImmediately ITSM client, mock service, models
│   │   ├── mcp/                            # Live SaaS FastMCP JSON-RPC client (X-MCP-Token header)
│   │   └── saas_boilerplate/               # A2A protocol & live Workday / ServiceNow adapters
│   └── telemetry/                          # Immutable auditing & observability
│       ├── __init__.py
│       └── audit_logger.py                 # Structured JSON compliance audit logger
├── app/                                    # Backward-compatibility bridge for Google ADK tooling
├── eval/                                   # Google ADK 4-Tier Golden Evaluation Suite
│   ├── __init__.py
│   ├── eval_config.json                    # ADK evaluation configuration
│   ├── trajectory_runner.py                # Automated multi-turn trajectory harness
│   ├── run_eval_suite.py                   # 4-Tier evalset runner & report generator
│   └── golden/
│       ├── golden_mas_eval.evalset.json    # 20-case 4-tier stratified ADK evaluation dataset
│       └── v1.jsonl                        # Versioned JSONL golden benchmark cases
├── tests/                                  # Comprehensive pytest test suite (40 test cases)
│   ├── __init__.py
│   ├── conftest.py                         # Pytest test fixtures & state isolation
│   ├── test_api_server.py                  # FastAPI REST endpoints & HTTP assertions
│   ├── test_cross_system_orchestration.py  # UC-2.1 Equipment & UC-2.3 Relocation workflows
│   ├── test_guardrails.py                  # Deduplication, balance limits & state machine checks
│   ├── test_policy_qa.py                   # UC-1.1 Grounded Policy Q&A & zero-hallucination refusals
│   ├── test_saas_mcp_integration.py        # Live SaaS FastMCP client integration tests
│   ├── test_safety.py                      # DLP SPII masking & Model Armor jailbreak prevention
│   ├── test_saga_compensation.py           # UC-2.2 Medical leave backward compensation
│   ├── test_service_immediately_flow.py    # UC-1.3 IT incident creation & priority assignment
│   ├── test_state_and_security.py          # Two-layer token minting & DLP cryptographic assertions
│   ├── test_trajectory_harness.py          # Synthetic fault injection across UC-2.1/2.2/2.3
│   └── test_workweek_flow.py               # UC-1.2 Leave balance inquiry & submission
├── artifacts/
│   └── docs/
│       └── eval_report.md                  # Auto-generated execution report & diagnostics
├── agents-cli-manifest.yaml                # Google Agents CLI deployment manifest
├── pyproject.toml                          # Package configuration & dependencies
├── requirements.txt                        # Pinned dependencies
└── .env.example                            # Sample environment variables
```

---

## 2. Key Features & Architecture Capabilities

### 2.1 Multi-Agent StateGraph Orchestration
* **Supervisor Agent Node (Gemini 3.7 Flash):** Routes user turns with sub-second latency, enforcing capability allowlists (FR-1.1) and domain containment (FR-5.4) against out-of-domain prompts.
* **Specialist Nodes:**
  * **Policy Specialist (Gemini 3.7 Flash):** Zero-hallucination RAG over OKF curated handbook with clickable markdown citations (e.g., `[View Policy Section 04.2](https://hr.corp.internal/policies/04.2-bereavement)`).
  * **WorkWeek HCM Specialist (Gemini 3.7 Flash):** Real-time balance queries, leave submissions, and contact updates.
  * **ServiceImmediately ITSM Specialist (Gemini 3.7 Flash):** Support ticket creation, status queries, hardware orders, and facilities badge requests.
* **Saga Coordinator Node (Gemini 3.1 Pro):** Coordinates multi-step, cross-system distributed transactions across WorkWeek and ServiceImmediately.

### 2.2 SDD §5.4 Consequence-Aware Saga Compensation Matrix
Protects enterprise data integrity during partial system outages and network failures:
* **`HUMAN_CONSEQUENTIAL` (e.g., Medical Leave Filings):** Never automatically reversed on downstream failures; primary leave stands and automated follow-ups route to a human operations queue (`FAILED_HANDED_TO_HUMAN`, `OPS-...`).
* **`REVERSIBLE_SAFE` (e.g., Contact / Office Updates):** Prior state is captured before mutation and automatically restored upon downstream failure (`ROLLED_BACK`, `COMPENSATED_ROLLED_BACK`).
* **`ANCILLARY` (e.g., IT Notification Tickets):** Failures raise operations tickets without invalidating the core transaction.

### 2.3 Two-Layer Composite Credentials & Security Perimeter
* **Layer 1 (Workload Identity):** Google-signed OIDC token authenticating Cloud Run orchestrator (`Authorization: Bearer <oidc>`).
* **Layer 2 (Subject Assertion):** RS256/asymmetric JWT minted via IAM `signJwt` carrying immutable server-side bound employee identity (`X-Subject-Assertion: <jwt>`), 120-second TTL, and JTI nonce replay defense.
* **Cloud DLP Ingress/Egress Interceptor:** Sub-15ms real-time surrogate masking of Singapore NRIC/FIN, US SSN, phone numbers, and email addresses before LLM invocation, with trust-boundary re-identification.
* **Vertex AI Model Armor:** Fail-closed inspection blocking prompt injection, DAN jailbreaks, and system prompt override attempts.

### 2.4 Operational Guardrails & Business Constraints
* **30-Minute Ticket Deduplication:** Prevents duplicate IT incident creation for the same user and category within a rolling 30-minute window.
* **Leave Constraints:** Rejects negative leave durations, requests exceeding current available balances, past dates, and invalid temporal ranges ($start\_date > end\_date$).
* **Anti-Inflation Priority Engine:** Downgrades inflated incident priorities unless outage context keywords are present.

---

## 3. Getting Started & Installation

### Prerequisites
* Python 3.10+
* Google Cloud SDK (`gcloud`) authenticated (for live Cloud deployment)
* `uv` or standard Python `venv`

### Setup Environment
```bash
# Clone repository and enter project directory
cd /usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

---

## 4. Running the Application

### 4.1 Launch FastAPI REST API Server
```bash
# Start server on port 8000
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

#### API Endpoints
* `POST /chat` — Process turn through safety filters and multi-agent StateGraph:
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -d '{"employee_id": "EMP-1001", "message": "What is the bereavement leave policy?"}'
  ```
* `GET /health` — Service health check.
* `GET /audit-logs?caller_employee_id=EMP-1001` — Query immutable audit events.
* `GET /workweek/profile/{employee_id}` — Inspect WorkWeek profile.
* `GET /workweek/balances/{employee_id}` — Fetch real-time leave balances.

### 4.2 Launch Interactive Terminal CLI
```bash
# Run interactive CLI session (defaulting to live FastMCP employee EMP-509)
python src/main.py --cli --employee-id EMP-509

# Run as specific employee persona
python src/main.py --cli --employee-id EMP-1001
```

* CLI Commands:
  * `switch <EMP_ID>` — Switch active authenticated employee persona.
  * `reset` — Reload backend mock databases to baseline state.
  * `exit` or `quit` — Terminate CLI session.

---

## 5. Running Tests & Evaluation

### 5.1 Run Full Pytest Suite (40/40 Unit, Integration & Trajectory Tests)
```bash
# Run all tests with verbose output
PYTHONPATH=. pytest tests/ -v
```

#### Test Suite Breakdown
| Test Module | Coverage Area | Cases |
| :--- | :--- | :---: |
| [`tests/test_api_server.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_api_server.py) | FastAPI `/health`, `/chat`, `/audit-logs` REST endpoints | 6 |
| [`tests/test_state_and_security.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_state_and_security.py) | Two-layer composite token minting, DLP masking, Model Armor | 3 |
| [`tests/test_trajectory_harness.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_trajectory_harness.py) | Synthetic fault injection & consequence-aware Saga verification | 7 |
| [`tests/test_cross_system_orchestration.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_cross_system_orchestration.py) | UC-2.1 Equipment procurement & UC-2.3 Relocation allowance | 3 |
| [`tests/test_saga_compensation.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_saga_compensation.py) | UC-2.2 Medical leave happy path and backward rollback | 2 |
| [`tests/test_guardrails.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_guardrails.py) | Deduplication window, balance limits, temporal ordering | 4 |
| [`tests/test_policy_qa.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_policy_qa.py) | Policy grounding citations & ungrounded inquiry refusals | 2 |
| [`tests/test_saas_mcp_integration.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_saas_mcp_integration.py) | FastMCP communication via `X-MCP-Token` header | 3 |
| [`tests/test_safety.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_safety.py) | Singapore NRIC / US SSN / phone / email DLP redaction | 5 |
| [`tests/test_workweek_flow.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_workweek_flow.py) | WorkWeek balance inquiries & caller isolation security | 3 |
| [`tests/test_service_immediately_flow.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_service_immediately_flow.py) | ServiceImmediately incident creation & deduplication | 2 |
| **Total** | | **40** |

---

### 5.2 Run Google ADK 4-Tier Golden Evaluation Suite
The ADK evaluation suite runs the 20-case 4-tier stratified golden dataset ([`eval/golden/golden_mas_eval.evalset.json`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/eval/golden/golden_mas_eval.evalset.json)) through [`eval/run_eval_suite.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/eval/run_eval_suite.py).

```bash
# Execute evaluation suite and generate diagnostics report
PYTHONPATH=. python eval/run_eval_suite.py
```

#### Evaluation Report Output ([`artifacts/docs/eval_report.md`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/artifacts/docs/eval_report.md))
```
🚀 Starting ADK Evaluation Suite: hr_agent_mas_eval (20 cases)
✅ Evaluation complete. Generated report at: artifacts/docs/eval_report.md
📊 Overall Pass Rate: 100.0% (20/20)
```

#### 4-Tier Stratified Evaluation Matrix
| Tier | Description | Target Ratio | Cases | Passed | Pass Rate | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Tier 1** | Happy Path / Direct Lookups | 40% | 8 | 8 | 100.0% | ✅ PASS |
| **Tier 2** | MAS Gotchas & Routing Traps | 30% | 6 | 6 | 100.0% | ✅ PASS |
| **Tier 3** | Hallucination Baits / Absent Policies | 15% | 3 | 3 | 100.0% | ✅ PASS |
| **Tier 4** | Out-of-Scope / Boundary Probes | 15% | 3 | 3 | 100.0% | ✅ PASS |
| **Total** | | **100%** | **20** | **20** | **100.0%** | **✅ PASS** |

### 5.3 Run Evaluation via Google Agents CLI (`agents-cli`)
```bash
# Evaluate using Google Agents CLI manifest
uvx google-agents-cli eval run \
  --evalset eval/golden/golden_mas_eval.evalset.json \
  --config eval/eval_config.json
```

---

## 6. Architecture & Design Documentation
* [Enterprise Agentic Solution Design Document - MVP 1.md](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/Enterprise%20Agentic%20Solution%20Design%20Document%20-%20MVP%201.md)
* [HR Agentic Solution BRD.md](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/HR%20Agentic%20Solution%20BRD.md)
* [ALTOSTRAT SINGAPORE EMPLOYEE POLICY HANDBOOK & CONDUCT GUIDELINES.md](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/ALTOSTRAT%20SINGAPORE%20EMPLOYEE%20POLICY%20HANDBOOK%20%26%20CONDUCT%20GUIDELINES.md)
* [Evaluation Execution Report](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/artifacts/docs/eval_report.md)
