# ADK & Vertex AI Agent Runtime Step-by-Step Migration Plan (TODO)

## Phase 1: Dependencies & Environment Setup (Foundation)
- [x] 1.1 Add `google-adk` and required SDKs to `pyproject.toml` and install in `.venv`
- [x] 1.2 Create ADK import verification and FastMCP connectivity smoke test (`tests/test_adk_smoke.py`)

## Phase 2: ADK Multi-Agent Architecture & McpToolset (ADK Core)
- [ ] 2.1 Define WorkWeek `McpToolset` (`StreamableHTTPConnectionParams` with `X-MCP-Token`)
- [ ] 2.2 Define ServiceImmediately `McpToolset`
- [ ] 2.3 Construct ADK `Agent` instances (Supervisor, WorkWeek Specialist, ITSM Specialist, Policy Specialist)
- [ ] 2.4 Integrate enterprise guardrails (DLP / Model Armor / OIDC Token Minter) as ADK Hooks / Middleware

## Phase 3: Vertex AI Agent Engine (Agent Runtime) Session & Memory Integration (Runtime Core)
- [ ] 3.1 Refactor `src/core/session.py` from in-memory dict to Agent Runtime Managed Session Adapter
- [ ] 3.2 Implement multi-turn state preservation and Memory Bank recall using native `session_id`
- [ ] 3.3 Switch FastAPI `/chat` endpoint in `src/main.py` to route through ADK Agent Runtime execution path

## Phase 4: Full Test Suite & ADK Evaluation Harness Verification (Check & Verification)
- [ ] 4.1 Ensure 100% pass across all unit and integration tests (399 tests)
- [ ] 4.2 Validate ADK 4-Tier Evaluation Suite (`eval/run_eval_suite.py`, 20 golden cases) at 100% pass rate
- [ ] 4.3 Verify Policy RAG evaluation harness against benchmark thresholds

## Phase 5: Provisioning & Deployment to Agent Runtime (Deployment)
- [ ] 5.1 Align `agents-cli-manifest.yaml` with the ADK multi-agent configuration
- [ ] 5.2 Deploy agent orchestrator to Vertex AI Agent Engine (Agent Runtime) via `agents-cli` / SDK
- [ ] 5.3 Verify managed session persistence and live SaaS FastMCP execution in Cloudtop / GCP environment
