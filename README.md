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
│   ├── settings.py                         # Pydantic BaseSettings (MCP, endpoints, guardrails)
│   └── corpus.yaml                         # Policy RAG corpora, ACL map, chunking & calibration
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
│   │   ├── model_armor.py                  # Dual-Engine Model Armor prompt injection & jailbreak filter
│   │   └── mcp_token_manager.py            # FastMCP token resolution via Secret Manager (mcp-user-tokens)
│   ├── guardrails/                         # Business rules & operational constraints
│   │   ├── __init__.py
│   │   └── operation_guardrails.py         # 30-min deduplication, positive leave days, temporal checks
│   ├── grounding/                          # OKF catalog & deterministic policy grounding
│   │   ├── __init__.py
│   │   ├── okf_store.py                    # Four curated policy rules; the fallback when no index is built
│   │   ├── policy_engine.py                # Dual Grounding Engine: FAISS corpus first, curated rules as backstop
│   │   ├── rag_boilerplate.py              # BaseRAGPipeline interface + Vertex AI Search stubs
│   │   ├── faiss_pipeline.py               # FaissPolicyRAG: BaseRAGPipeline over the local FAISS index
│   │   └── policy_rag/                     # FAISS semantic retrieval + A2A server (see its README.md)
│   │       ├── config.py                   # corpus.yaml loader: corpora, ACL, chunking, calibration
│   │       ├── loaders.py                  # OKF frontmatter & raw-handbook section loaders
│   │       ├── documents.py                # Document / Chunk / SourceRef corpus types
│   │       ├── chunking.py                 # Heading-boundary chunker with size-overflow split
│   │       ├── embeddings.py               # Providers: local (BGE-small) | vertex | hash (CI)
│   │       ├── index.py                    # FAISS IndexFlatIP in IndexIDMap2 + build manifest
│   │       ├── retriever.py                # Hybrid dense+lexical scoring, query-time ACL filter
│   │       ├── guards.py                   # 5 corpus-datasheet refuse/escalate rules
│   │       ├── answer.py                   # Extractive | Gemini composer + groundedness gate
│   │       ├── service.py                  # PolicyRagService: retrieve → guard → compose
│   │       ├── ingest.py                   # Index build with canary probes & drift detection
│   │       ├── cli.py                      # ingest | query | search | stats | drift | serve
│   │       └── a2a_app/                    # A2A agent card, executor, JSON-RPC server, client demo
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
│   ├── run_policy_rag_eval.py              # Policy RAG recall/MRR, refusal & guard harness
│   └── golden/
│       ├── golden_mas_eval.evalset.json    # 20-case 4-tier stratified ADK evaluation dataset
│       ├── redteam_model_armor.json        # 100-vector red-team safety evaluation dataset (SM-02)
│       ├── policy_rag_golden.json          # 45 policy questions with expected disposition
│       └── v1.jsonl                        # Versioned JSONL golden benchmark cases
├── scripts/                                # Automation & deployment scripts
│   ├── deploy-cloud-run.sh                 # Multi-region Cloud Run container deployment
│   ├── eval_retrieval.py                   # Policy retrieval benchmark script
│   └── setup_model_armor_templates.py      # GCP Model Armor ingress/egress template automation
├── tests/                                  # Pytest suite: 1,192 unit/integration cases (100% pass)
│   ├── __init__.py
│   ├── conftest.py                         # Pytest test fixtures & state isolation
│   ├── test_api_server.py                  # FastAPI REST endpoints & HTTP assertions
│   ├── test_auth.py                        # Google OIDC & session authentication
│   ├── test_cross_system_orchestration.py  # UC-2.1 Equipment & UC-2.3 Relocation workflows
│   ├── test_guardrails.py                  # Deduplication, balance limits & state machine checks
│   ├── test_itsm_tool_selection.py         # Read vs mutation intent tool selection
│   ├── test_mcp_client.py                  # FastMCP JSON-RPC client tests
│   ├── test_mcp_token_manager.py           # Secret Manager user token auto-resolution
│   ├── test_model_armor.py                 # Model Armor dual-engine, circuit breaker & 100-vector red-team
│   ├── test_policy_graph_node.py           # PolicySpecialistNode grounding gate, escalation & fallback
│   ├── test_policy_qa.py                   # UC-1.1 Grounded Policy Q&A & zero-hallucination refusals
│   ├── test_saas_mcp_integration.py        # Live SaaS FastMCP client integration tests
│   ├── test_safety.py                      # DLP SPII masking & Model Armor jailbreak prevention
│   ├── test_saga_compensation.py           # UC-2.2 Medical leave backward compensation
│   ├── test_service_immediately_flow.py    # UC-1.3 IT incident creation & priority assignment
│   ├── test_state_and_security.py          # Two-layer token minting & DLP cryptographic assertions
│   ├── test_trajectory_harness.py          # Synthetic fault injection across UC-2.1/2.2/2.3
│   ├── test_vertex_client.py               # Vertex AI Gemini client & token management
│   ├── test_workweek_flow.py               # UC-1.2 Leave balance inquiry & submission
│   └── policy_rag/                         # FAISS policy RAG suite (hash embeddings)
│       ├── conftest.py                     # Hermetic corpus, index & service fixtures
│       ├── test_config.py                  # corpus.yaml, ACL overrides & environment overrides
│       ├── test_loaders.py                 # OKF frontmatter & handbook section parsing
│       ├── test_chunking.py                # Heading boundaries, overflow split, determinism
│       ├── test_embeddings.py              # local / vertex / hash providers behind one interface
│       ├── test_index.py                   # FAISS store, deterministic ids, eviction, persistence
│       ├── test_ingest.py                  # load → chunk → embed → verify → publish, and drift
│       ├── test_retriever.py               # Fusion, calibration, ACL / corpus / doc-type filters
│       ├── test_guards.py                  # Refuse & escalate rules and advisory notices
│       ├── test_answer.py                  # Extractive & Gemini composition, groundedness gate
│       ├── test_service.py                 # End-to-end retrieve → guard → compose + citations
│       ├── test_cli.py                     # `policy-rag` ingest / search / ask / serve surface
│       ├── test_eval_harness.py            # Recall/MRR arithmetic, CI exit codes, tuning sweep
│       ├── test_faiss_pipeline.py          # BaseRAGPipeline adapter contract & ACL pass-through
│       ├── test_a2a.py                     # Live JSON-RPC round trips over ASGI transport
│       ├── test_a2a_executor.py            # Request parsing & the entitlement trust boundary
│       └── test_a2a_client_demo.py         # The reference consumer, driven against the real app
├── var/                                    # Build artefacts (git-ignored): FAISS index & manifest
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
* **Dual-Engine Vertex AI Model Armor Service (`src/security/model_armor.py`):**
  * **Live GCP Model Armor Client (`LiveModelArmorClient`):** Interacts with regional REST endpoints (`https://modelarmor.{location}.rep.googleapis.com/v1/...`) via in-process ADC token resolution and pre-warmed connection pooling, evaluating `hr-ingress-template` (PI/jailbreak & RAI filters: `SEXUALLY_EXPLICIT`, `HATE_SPEECH`, `HARASSMENT`, `DANGEROUS`) and `hr-egress-template`.
  * **Local Stand-in (`LocalModelArmorStandin`):** Sub-millisecond deterministic offline surrogate and immediate failover engine (DEP-09) covering 50+ adversarial jailbreaks, prompt injection, and credential leak patterns.
  * **Fail-Closed Circuit Breaker (`SafetyCircuitBreaker`):** Trips if error or timeout rate exceeds 2% over a 5-minute sliding window (`ALRT-08`), failing closed to guarantee security.
  * **100-Vector Red-Team Golden Dataset (`eval/golden/redteam_model_armor.json`):** 50 Inbound Attacks, 25 Outbound Threats, 25 Benign Controls (100% defense, 0.0% false positives).
* **FastMCP Secret Manager Token Resolution (`src/security/mcp_token_manager.py`):** Dynamic resolution of caller employee tokens via Google Cloud Secret Manager (`mcp-user-tokens`), ensuring least-privilege tenant access.

### 2.4 FAISS Semantic Retrieval over the Handbook Corpus
A second, working `BaseRAGPipeline` backend alongside the deferred Vertex AI
Search adapter — 480 chunks from 81 documents, indexed from the OKF v0.2 bundle
and the raw Altostrat Singapore handbook:
* **Exact cosine search:** FAISS `IndexFlatIP` over L2-normalised vectors in an `IndexIDMap2`. At this corpus size an ANN structure buys nothing, and `remove_ids` is what the SLA-04 stale-embedding eviction path needs.
* **Hybrid scoring:** dense bi-encoder similarity plus a bounded IDF-weighted lexical corroboration bonus, so a passage is never *penalised* for stating a rule in words the question did not use.
* **Dual gate (SDD §3.3 Path 1):** retrieval relevance ≥ 0.80 **and** groundedness ≥ 0.85. The extractive composer quotes verbatim and is grounded by construction; the Gemini composer has its output measured against the retrieved content and discarded below the threshold.
* **Five refuse/escalate guards:** absent handbook sections, extended-workforce leave questions, known source conflicts, no hits above the gate, and groundedness failures — each traceable to the corpus datasheet's *"what must not be answered"*.
* **Query-time ACL (SDD §4.7):** `references/` material requires `hr_operational`; entitlements bind from the verified caller, never the payload.
* **A2A surface:** three skills served over JSON-RPC with a discoverable agent card, so other teams' agents consume the knowledge base without importing this package.
* **Wired into both entry points:** free-text policy questions retrieve from this index whether they arrive through the REST path (`DualGroundingEngine`) or the StateGraph path (`PolicySpecialistNode`). The index is a git-ignored build artefact, so when it is absent both fall back to their pre-corpus fixtures and say so — every answer carries a `grounding_source` of `faiss` or `curated`. **The two disagree:** the fixture puts bereavement leave at 5 days, the handbook at 20 work days. Run the ingest below before trusting an answer.

### 2.5 Operational Guardrails & Business Constraints
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

### Build the Policy RAG Index
The FAISS index is a build artefact, not a committed file. It has to be built
once before the policy retrieval CLI, the A2A server or the retrieval evaluation
will run — everything else in this repo works without it.

```bash
# Downloads BAAI/bge-small-en-v1.5 on first run; writes var/index/
PYTHONPATH=. python -m src.grounding.policy_rag.cli ingest
```

Rebuild whenever the handbook, the OKF bundle or `config/corpus.yaml` changes;
`... cli drift` reports sources whose digest no longer matches the build.

---

## 4. Running the Application

### 4.1 Launch FastAPI REST API Server
```bash
# Start server on port 8000
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

#### API Endpoints
* `GET /` — Interactive Web Chat UI (responsive modern dark theme UI with persona switching and quick action buttons).
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

### 4.3 Launch the Policy RAG A2A Server
Exposes the grounded handbook retriever to *other teams' agents* over the A2A
protocol, so a consuming agent discovers the skills from the card rather than
being coded against this repo. Requires the index from §3.

```bash
PYTHONPATH=. python -m src.grounding.policy_rag.cli serve --port 8080
```

| Endpoint | |
| :--- | :--- |
| `GET /.well-known/agent-card.json` | Discovery: skills, input/output modes, interfaces |
| `POST /` | A2A JSON-RPC (`message/send`, `tasks/get`, and the gRPC-style aliases) |
| `GET /healthz` | Index-aware liveness |

Three skills, selected via `skill` in the message metadata: `policy_answer`
(composed answer + citations + notices), `policy_search` (ranked chunks, no
prose) and `corpus_status` (chunk counts, embedder fingerprint, drift).

```bash
PYTHONPATH=. python -m src.grounding.policy_rag.a2a_app.client_demo \
  --url http://127.0.0.1:8080 --skill policy_answer \
  "How many vacation days after 8 years of service?"
```

Entitlements are read from the `X-Altostrat-Entitlements` header set by the
authenticating gateway, **never** from the message payload — in an agent-to-agent
chain the body may have been composed by an LLM acting on employee-supplied text,
so it cannot carry an authorization decision (SDD §4.1 / §4.7).

See [`src/grounding/policy_rag/README.md`](src/grounding/policy_rag/README.md)
for the retrieval design, the two gates, the guard rules and the calibration
methodology.

---

## 5. Running Tests & Evaluation

### 5.1 Run Full Pytest Suite (1,192 Unit, Integration & Trajectory Tests)
```bash
# Run all tests with verbose output
PYTHONPATH=. pytest tests/ -v

# Policy RAG subsystem only
PYTHONPATH=. pytest tests/policy_rag -v

# With coverage (100% statement and branch, enforced across src/, app/, eval/ and scripts/)
PYTHONPATH=. pytest --cov
```

The suite is hermetic: the policy RAG tests run on the deterministic `hash`
embedding provider, so there is no model download and no network call. The
optional cloud and ML SDKs (`google-genai`, `sentence-transformers`, `vertexai`)
are driven against stub modules for the same reason. The two
`test_saas_mcp_integration.py` cases that need a live FastMCP token skip when it
is absent or expired.

#### Test Suite Breakdown
| Test Module | Coverage Area | Cases |
| :--- | :--- | :---: |
| [`tests/test_orchestration_graph.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_orchestration_graph.py) | Graph runtime: guardrail gate, supervisor routing, node dispatch | 41 |
| [`tests/test_agent_orchestrator.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_agent_orchestrator.py) | The four-stage `HREnterpriseAgent` loop, every collaborator faked | 47 |
| [`tests/test_supervisor_routing.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_supervisor_routing.py) | Supervisor intent routing & domain containment | 3 |
| [`tests/test_routing_models.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_routing_models.py) | Routing schemas and the argument consolidation they perform | 21 |
| [`tests/test_cross_system_orchestration.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_cross_system_orchestration.py) | UC-2.1 equipment procurement & UC-2.3 relocation allowance | 6 |
| [`tests/test_runtime_primitives.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_runtime_primitives.py) | Session, audit log and surrogate helpers every path leans on | 33 |
| [`tests/test_compat_and_boilerplate.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_compat_and_boilerplate.py) | Compatibility shims & deferred-integration placeholders | 23 |
| [`tests/test_saga_ledger_and_dispatcher.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_saga_ledger_and_dispatcher.py) | Saga ledger (§4.6) and the Cloud Tasks dispatcher (§5.2, §4.8) | 50 |
| [`tests/test_saga_coordinator_node.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_saga_coordinator_node.py) | Graph-path saga coordinator & the §5.4 compensation matrix | 33 |
| [`tests/test_saga_compensation.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_saga_compensation.py) | UC-2.2 medical leave happy path and backward rollback | 2 |
| [`tests/test_trajectory_harness.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_trajectory_harness.py) | Synthetic fault injection & consequence-aware saga verification | 8 |
| [`tests/test_hcm_specialist.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_hcm_specialist.py) | WorkWeek HCM specialist: tool execution & response formatting | 82 |
| [`tests/test_workweek_client_adapter.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_workweek_client_adapter.py) | WorkWeek adapter: caller isolation, live/mock split, audit trail | 51 |
| [`tests/test_workweek_mock_service.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_workweek_mock_service.py) | The in-memory WorkWeek backend standing in for the HCM tenant | 22 |
| [`tests/test_workweek_flow.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_workweek_flow.py) | UC-1.2 leave balance inquiries & caller isolation | 3 |
| [`tests/test_service_immediately_client_adapter.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_service_immediately_client_adapter.py) | ServiceImmediately adapter: the four FR-4.2 operations end to end | 50 |
| [`tests/test_service_immediately_flow.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_service_immediately_flow.py) | UC-1.3 incident creation & deduplication | 2 |
| [`tests/test_itsm_tool_selection.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_itsm_tool_selection.py) | Read vs mutation intent tool selection & question parsing | 42 |
| [`tests/test_mcp_client.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_mcp_client.py) | The SaaS FastMCP client, offline | 56 |
| [`tests/test_mcp_token_manager.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_mcp_token_manager.py) | Secret Manager dynamic FastMCP token resolution | 4 |
| [`tests/test_model_armor.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_model_armor.py) | Model Armor dual-engine, circuit breaker & 100-vector red-team | 9 |
| [`tests/test_saas_mcp_integration.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_saas_mcp_integration.py) | FastMCP communication via `X-MCP-Token` (skips without a token) | 3 |
| [`tests/test_vertex_client.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_vertex_client.py) | Vertex AI Gemini client: credentials, model fallback, schema shaping | 25 |
| [`tests/test_security_auth.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_security_auth.py) | Identity federation and the session token (§4.1) | 29 |
| [`tests/test_auth.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_auth.py) | Google OIDC, identity federation & session authentication | 11 |
| [`tests/test_api_auth_endpoints.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_api_auth_endpoints.py) | Login, session and caller-binding endpoints (§4.1) | 40 |
| [`tests/test_api_server.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_api_server.py) | FastAPI `/health`, `/chat`, `/audit-logs` REST endpoints | 6 |
| [`tests/test_guardrails.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_guardrails.py) | Deduplication window, balance limits, temporal ordering | 27 |
| [`tests/test_privacy_gates.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_privacy_gates.py) | §4.10 E6 de-identification bypass & §4.11 audit allow-list | 17 |
| [`tests/test_safety.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_safety.py) | Singapore NRIC / US SSN / phone / email DLP redaction | 5 |
| [`tests/test_state_and_security.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_state_and_security.py) | Two-layer composite token minting, DLP masking, Model Armor | 4 |
| [`tests/test_okf_register.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_okf_register.py) | OKF curated handbook concept store & keyword search | 29 |
| [`tests/test_policy_graph_node.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_policy_graph_node.py) | `PolicySpecialistNode` grounding gate, escalation & fallback | 11 |
| [`tests/test_policy_qa.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_policy_qa.py) | UC-1.1 policy grounding, deep-link citations & refusals | 8 |
| [`tests/test_eval_suite_runner.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/test_eval_suite_runner.py) | The ADK golden-evalset runner | 32 |
| [`tests/policy_rag/test_config.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_config.py) | `corpus.yaml`, ACL overrides and environment overrides | 12 |
| [`tests/policy_rag/test_loaders.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_loaders.py) | OKF frontmatter & raw-handbook section parsing | 25 |
| [`tests/policy_rag/test_chunking.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_chunking.py) | Heading-boundary chunking, overflow split, determinism | 17 |
| [`tests/policy_rag/test_embeddings.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_embeddings.py) | `local` / `vertex` / `hash` providers behind one interface | 31 |
| [`tests/policy_rag/test_language.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_language.py) | Language detection & multi-lingual query routing | 33 |
| [`tests/policy_rag/test_index.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_index.py) | FAISS store, deterministic ids, eviction, disk round trip | 19 |
| [`tests/policy_rag/test_ingest.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_ingest.py) | load → chunk → embed → verify → publish, and drift detection | 20 |
| [`tests/policy_rag/test_retriever.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_retriever.py) | Score fusion, calibration, ACL / corpus / doc-type filters | 32 |
| [`tests/policy_rag/test_guards.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_guards.py) | Refuse & escalate rules and advisory notices | 30 |
| [`tests/policy_rag/test_answer.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_answer.py) | Extractive & Gemini composition, the groundedness gate | 22 |
| [`tests/policy_rag/test_service.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_service.py) | Retrieve → guard → compose, citation resolution, corpus stats | 8 |
| [`tests/policy_rag/test_cli.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_cli.py) | The `policy-rag` ingest / search / ask / serve surface | 15 |
| [`tests/policy_rag/test_eval_harness.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_eval_harness.py) | Recall/MRR arithmetic, CI exit codes, the tuning sweep | 29 |
| [`tests/policy_rag/test_faiss_pipeline.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_faiss_pipeline.py) | `BaseRAGPipeline` adapter contract & ACL pass-through | 15 |
| [`tests/policy_rag/test_a2a.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_a2a.py) | A2A card discovery, JSON-RPC round trips, header entitlements | 14 |
| [`tests/policy_rag/test_a2a_executor.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_a2a_executor.py) | Request parsing & the entitlement trust boundary (§4.1) | 23 |
| [`tests/policy_rag/test_a2a_client_demo.py`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/tests/policy_rag/test_a2a_client_demo.py) | The reference consumer, driven against the real app | 11 |
| **Total** | | **1,192** |

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

### 5.4 Run the Policy RAG Retrieval Evaluation
Scores the FAISS retriever against 45 golden questions in
[`eval/golden/policy_rag_golden.json`](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/eval/golden/policy_rag_golden.json).
Each question declares its expected *disposition* — `answer` (with the paths that
must be retrieved), `escalate` or `refuse` — not just an expected string, which is
the only way the harness can tell "correctly declined" from "failed to retrieve".
Requires the index from §3.

```bash
PYTHONPATH=. python eval/run_policy_rag_eval.py                       # score at the configured gate
PYTHONPATH=. python eval/run_policy_rag_eval.py --show-failures       # per-question detail
PYTHONPATH=. python eval/run_policy_rag_eval.py --sweep               # gate 0.40 → 0.95
PYTHONPATH=. python eval/run_policy_rag_eval.py --min-pass-rate 0.85  # CI mode, non-zero exit
```

Current, with `BAAI/bge-small-en-v1.5` at the SDD §3.3 relevance gate of 0.80:

| Metric | Result |
| :--- | :---: |
| Overall | 41/45 |
| Recall@1 | 78.79% |
| Recall@k | 87.88% |
| MRR | 0.828 |
| Answer accuracy | 87.88% |
| Escalate accuracy | 100.00% |
| Refusal accuracy | 100.00% |

All four failures are over-conservative refusals — the corpus contains the answer
and retrieval did not clear the gate. There are no wrong answers and no missed
escalations, which is the direction the failures should point under NFR-3.1.

`--sweep` derives the `calibration` block in `config/corpus.yaml` and **must be
re-run whenever `embedding.model` changes**: the gate stays pinned at the SDD's
0.80 and the calibration moves to fit the model, not the other way round.

---

## 6. Architecture & Design Documentation
* [Enterprise Agentic Solution Design Document - MVP 1.md](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/Enterprise%20Agentic%20Solution%20Design%20Document%20-%20MVP%201.md)
* [HR Agentic Solution BRD.md](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/HR%20Agentic%20Solution%20BRD.md)
* [ALTOSTRAT SINGAPORE EMPLOYEE POLICY HANDBOOK & CONDUCT GUIDELINES.md](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/ALTOSTRAT%20SINGAPORE%20EMPLOYEE%20POLICY%20HANDBOOK%20%26%20CONDUCT%20GUIDELINES.md)
* [Evaluation Execution Report](file:///usr/local/google/home/robertkj/PRJ-ELEVATE-C1-G5/artifacts/docs/eval_report.md)
