# ADK & Vertex AI Agent Runtime Step-by-Step Migration Plan (TODO)

## Phase 1: Dependencies & Environment Setup (Foundation)
- [x] 1.1 Add `google-adk` and required SDKs to `pyproject.toml` and install in `.venv`
- [x] 1.2 Create ADK import verification and FastMCP connectivity smoke test (`tests/test_adk_smoke.py`)

## Phase 2: ADK Multi-Agent Architecture & McpToolset (ADK Core)
- [x] 2.1 Define WorkWeek `McpToolset` (`StreamableHTTPConnectionParams` with `X-MCP-Token`)
- [x] 2.2 Define ServiceImmediately `McpToolset`
- [x] 2.3 Construct ADK `Agent` instances (Supervisor, WorkWeek Specialist, ITSM Specialist, Policy Specialist)
- [x] 2.4 Integrate enterprise guardrails (DLP / Model Armor / OIDC Token Minter) as ADK Ingress/Egress Pipeline

## Phase 3: Vertex AI Agent Engine (Agent Runtime) Session & Memory Integration (Runtime Core)
- [x] 3.1 Implement Agent Runtime Managed Session & Memory Bank adapter (`src/adk/session.py`)
- [x] 3.2 Implement multi-turn state preservation and Memory Bank recall using native `session_id`
- [x] 3.3 Switch agent orchestration core in `src/core/agent.py` to route through ADK Agent Runtime execution path

## Phase 4: Full Test Suite & ADK Evaluation Harness Verification (Check & Verification)
- [x] 4.1 Ensure 100% pass across all unit and integration tests (414 tests passing)
- [x] 4.2 Validate ADK Multi-Agent integration test suite (`tests/adk/test_adk_multi_agent.py`) at 100% pass rate
- [x] 4.3 Verify ADK evaluation suite harness (`tests/test_eval_suite_runner.py`) at 100% pass rate

## Phase 5: Verification & Production Readiness
- [x] 5.1 Verify FastAPI `/chat`, `/health`, and REST API endpoints over ADK Agent Runtime
- [x] 5.2 Validate live WorkWeek & ServiceImmediately intent dispatching and policy grounding citations
- [x] 5.3 Validate Model Armor threat scanning and DLP PII redaction on ADK pipeline
