# GCP Agent Registry Deployment Plan: 8-Agent Enterprise Fleet

---

## Document Control
| Field | Value |
| :--- | :--- |
| **Document Title** | GCP Agent Registry Deployment Plan: 8-Agent Enterprise Fleet |
| **Programme** | Global Enterprise Intelligent Workforce Automation |
| **Project** | HR Agentic Solution (MVP 1) & Policy Assistant Suite |
| **Author(s)** | Enterprise AI Solution Architecture Team (`choirul@`) |
| **Date** | August 28, 2026 |
| **Status** | Approved Deployment Architecture |
| **Target Platform** | Google Cloud Vertex AI Agent Registry / Reasoning Engine |

---

## 1. Executive Overview & Agent Registry Architecture

This document defines the deployment, registration, security hardening, and validation plan for all **8 agent entities** identified across the enterprise codebase into the **Google Cloud Vertex AI Agent Registry (Reasoning Engine / Agent Builder)**.

```mermaid
flowchart TD
    subgraph Codebase["📦 Local Agent Implementation Suites"]
        A1["Suite A: HRED Enterprise Mesh\n(4 Agents: Supervisor, Policy, Lifecycle, Approval)"]
        A2["Suite B: Standalone ADK Policy Agents\n(3 Agents: RAG, OKF, Hybrid)"]
        A3["Suite C: Automated Quality Judge\n(1 Agent: LLM-as-a-Judge)"]
    end

    subgraph IaC["⚙️ Terraform Infrastructure Provisioning"]
        T1["GCP APIs (aiplatform, discoveryengine, dlp, run, pubsub)"]
        T2["Service Account (hr-agent-runner) + Least-Privilege IAM"]
        T3["GCS Staging Bucket (gs://${PROJECT_ID}-agent-registry-staging)"]
        T4["Pub/Sub Event Topics (hr.lifecycle.transition, hr.approval.*)"]
    end

    subgraph DeploymentEngine["🚀 Python Vertex AI Deployment Engine"]
        D1["Artifact Packaging & Serialization (Cloudpickle/ADK Specs)"]
        D2["Vertex AI ReasoningEngine.create() API"]
        D3["Tool Extensions & Catalog Registration"]
    end

    subgraph Registry["🏛️ GCP Agent Registry (Vertex AI)"]
        R1["hr-supervisor-orchestrator-v1"]
        R2["hr-policy-benefits-specialist-v1"]
        R3["hr-lifecycle-operations-specialist-v1"]
        R4["hr-approval-gatekeeper-v1"]
        R5["hr-policy-rag-search-v1"]
        R6["hr-policy-okf-catalog-v1"]
        R7["hr-policy-dual-hybrid-v1"]
        R8["hr-eval-llm-judge-v1"]
    end

    subgraph Governance["🛡️ Zero-Trust Security & Verification"]
        S1["Inline Cloud DLP Streaming (<15ms SPII Redaction)"]
        S2["Vertex AI Model Armor Prompt Injection Filter"]
        S3["25-Case Golden Dataset Benchmark Verification"]
    end

    Codebase --> DeploymentEngine
    IaC --> DeploymentEngine
    DeploymentEngine --> Registry
    Registry --> Governance
```

---

## 2. Complete Inventory of the 8 Registered Agents

| # | Agent Identifier | GCP Registry Display Name | Architectural Tier | Model Configuration | Bound Tools & Extensions | Source Code Reference |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | `HRSupervisorAgent` | `hr-supervisor-orchestrator-v1` | Hierarchical Supervisor | `gemini-2.5-pro` / `flash` | Workday, ServiceNow, Specialist Mesh | [`enterprise_agents.py:L340`](file:///google/src/cloud/choirul/greeting_initialization/google3/experimental/users/choirul/hr_enterprise_design/agents/enterprise_agents.py#L340) |
| **2** | `PolicyBenefitsAgent` | `hr-policy-benefits-specialist-v1` | Domain Specialist | `gemini-2.5-flash` | Grounded Policy Catalog (Sec 19, 28, 12, 03) | [`enterprise_agents.py:L23`](file:///google/src/cloud/choirul/greeting_initialization/google3/experimental/users/choirul/hr_enterprise_design/agents/enterprise_agents.py#L23) |
| **3** | `LifecycleOperationsAgent` | `hr-lifecycle-operations-specialist-v1` | Domain Specialist | `gemini-2.5-flash` | ServiceNow Case, Pub/Sub Event Publisher | [`enterprise_agents.py:L159`](file:///google/src/cloud/choirul/greeting_initialization/google3/experimental/users/choirul/hr_enterprise_design/agents/enterprise_agents.py#L159) |
| **4** | `ManagerApprovalAgent` | `hr-approval-gatekeeper-v1` | HITL Gatekeeper | `gemini-2.5-flash` | Approval Store, Pub/Sub Approvals, Case Sync | [`enterprise_agents.py:L250`](file:///google/src/cloud/choirul/greeting_initialization/google3/experimental/users/choirul/hr_enterprise_design/agents/enterprise_agents.py#L250) |
| **5** | `hr_policy_agent_rag` | `hr-policy-rag-search-v1` | Standalone ADK Agent | `gemini-2.5-flash` | `search_policy_docs` (Vertex AI Search) | [`rag_scenario/agent/agent.py:L25`](file:///google/src/cloud/choirul/greeting_initialization/google3/experimental/users/choirul/hr_policy_agent/rag_scenario/agent/agent.py#L25) |
| **6** | `hr_policy_agent_okf` | `hr-policy-okf-catalog-v1` | Standalone ADK Agent | `gemini-2.5-flash` | `list_concepts`, `read_concept` (OKF Catalog) | [`okf_scenario/agent/agent.py:L25`](file:///google/src/cloud/choirul/greeting_initialization/google3/experimental/users/choirul/hr_policy_agent/okf_scenario/agent/agent.py#L25) |
| **7** | `hr_policy_agent_hybrid` | `hr-policy-dual-hybrid-v1` | Standalone ADK Agent | `gemini-2.5-flash` | Dual Grounding (OKF Tools + Vertex Search) | [`hybrid_scenario/agent/agent.py:L25`](file:///google/src/cloud/choirul/greeting_initialization/google3/experimental/users/choirul/hr_policy_agent/hybrid_scenario/agent/agent.py#L25) |
| **8** | `HREvalJudgeAgent` | `hr-eval-llm-judge-v1` | Evaluator / Judge | `gemini-3.6-flash` / `flash` | 5-Dimensional Rubric Scoring Engine | [`okf_scenario/evals/run_eval.py:L277`](file:///google/src/cloud/choirul/greeting_initialization/google3/experimental/users/choirul/hr_policy_agent/okf_scenario/evals/run_eval.py#L277) |

---

## 3. Terraform Infrastructure Architecture

The required cloud foundation is managed via Terraform under `terraform/agent_registry/`:
* **APIs Enabled**: `aiplatform`, `discoveryengine`, `dlp`, `run`, `pubsub`, `cloudbuild`, `storage`.
* **Identity & Access Management (IAM)**: Scoped service account `hr-agent-runner@` with `roles/aiplatform.user`, `roles/discoveryengine.editor`, and `roles/pubsub.publisher`.
* **Artifact Staging Bucket**: Encrypted Cloud Storage bucket with uniform bucket-level access.
* **Asynchronous Messaging**: Pub/Sub topics `hr.lifecycle.transition`, `hr.approval.requested`, and `hr.approval.completed`.

---

## 4. Phased Deployment & Execution Steps

### Phase 1: Infrastructure Provisioning
```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Specify project_id and region in terraform.tfvars
terraform init
terraform apply -auto-approve
```

### Phase 2: Agent Fleet Registration
```bash
cd ../scripts
pip install -r requirements.txt
export GOOGLE_CLOUD_PROJECT="YOUR_GCP_PROJECT_ID"
export GOOGLE_CLOUD_LOCATION="us-central1"

python deploy_to_agent_registry.py --project ${GOOGLE_CLOUD_PROJECT} --location ${GOOGLE_CLOUD_LOCATION}
```

### Phase 3: Smoke Testing & Verification
```bash
python verify_agent_registry.py --project ${GOOGLE_CLOUD_PROJECT} --location ${GOOGLE_CLOUD_LOCATION}
```

---

## 5. Security & Zero-Trust Policies
1. **Cloud DLP Streaming Integration**: All reasoning engine queries are processed through an inline Cloud DLP de-identification proxy to mask NRICs, SSNs, phone numbers, and home addresses before reaching LLM prompts.
2. **Model Armor Defense**: Rejects adversarial prompt injections, system prompt leak attempts, and toxic content.
3. **VPC Service Controls**: Registered Reasoning Engines are hosted inside a private GCP Service Perimeter.
