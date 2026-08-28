# 🏛️ GCP Agent Registry Deployment Package (8-Agent Enterprise Fleet)

This self-contained directory contains the end-to-end **Architecture Plan**, **Terraform Infrastructure as Code (IaC)**, and **Automated Python Registration Scripts** to deploy and catalog all **8 enterprise agents** into **Google Cloud Vertex AI Agent Registry (Reasoning Engine)**.

---

## 📁 Package Directory Structure

```
agent_registry_deployment/
├── README.md                              # This quickstart & PR overview guide
├── 08_agent_registry_deployment_plan.md   # Master Architectural Deployment Plan
├── terraform/                             # GCP Infrastructure as Code
│   ├── main.tf                            # APIs, GCS Staging Bucket, IAM Service Account, PubSub Topics
│   ├── variables.tf                       # Configuration variables (Project, Region, Environment)
│   ├── outputs.tf                         # Resource outputs (Bucket URI, SA Email, Topics)
│   └── terraform.tfvars.example           # Example configuration values
└── scripts/                               # Python Deployment & Verification Engines
    ├── deploy_to_agent_registry.py        # Automated registration script for all 8 agents
    ├── verify_agent_registry.py           # Automated smoke test & health check harness
    ├── requirements.txt                   # Dependencies (vertexai, google-adk, pydantic, etc.)
    └── agent_registry_catalog.json        # Output catalog with generated resource IDs
```

---

## 📊 Catalog of the 8 Registered Agents (SDD v2.2 Aligned)

| # | Agent Name / Identifier | Registry Display Name | Architectural Tier | Model / Runtime | Bound Tools & Extensions |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **1** | `SupervisorAgentNode` (`sup-1.4.0`) | `hr-supervisor-orchestrator-v1` | Hierarchical Root Supervisor | `gemini-3.7-flash@2026-08` | Intent Routing, Keyword Escalation, Domain Containment (FR-5.4) |
| **2** | `PolicySpecialistNode` (`pol-1.4.0`) | `hr-policy-benefits-specialist-v1` | Policy Domain Specialist | `gemini-3.7-flash` | Grounded Policy Search ($\ge 0.85$ threshold), Deep Citations |
| **3** | `HCMSpecialistNode` (`hcm-1.4.0`) | `hr-lifecycle-operations-specialist-v1` | HCM Domain Specialist | `gemini-3.7-flash` | WorkWeek API (`get_balances`, `get_leave`, `request_time_off`) |
| **4** | `ITSMSpecialistNode` (`itsm-1.4.0`) | `hr-approval-gatekeeper-v1` | ITSM Domain Specialist | `gemini-3.7-flash` | ServiceImmediately (`get_incident`, `create_incident`, `update_status`) |
| **5** | `SagaCoordinatorNode` (`saga-1.4.0`) | `hr-saga-coordinator-v1` | Distributed Saga Orchestrator | `gemini-3.1-pro@2026-08` | Multi-System Orchestrator with Backward Compensation (UC-2.1 to UC-2.3) |
| **6** | `PolicyRAGService` (`policy-rag-v1`) | `hr-policy-rag-search-v1` | A2A Protocol Agent | `gemini-2.5-flash` / `text-embedding-005` | Agent Card, Chunking, Semantic Policy Retrieval |
| **7** | `DualGroundingEngine` | `hr-policy-dual-hybrid-v1` | Dual Hybrid Specialist | `gemini-3.7-flash` | OKF Concept Store + Agent Search over Altostrat Singapore Handbook |
| **8** | `RubricJudgeEngine` | `hr-eval-llm-judge-v1` | Evaluator & Judge | `gemini-3.1-pro` | 5-Dimensional Automated Rubric Scoring Engine |

---

## 🚀 Step-by-Step Deployment Instructions

### Step 1: Provision Cloud Infrastructure (Terraform)
```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your GCP project_id and region
terraform init
terraform apply -auto-approve
```

### Step 2: Register All 8 Agents to Vertex AI Agent Registry
```bash
cd ../scripts
pip install -r requirements.txt
export GOOGLE_CLOUD_PROJECT="YOUR_GCP_PROJECT_ID"
export GOOGLE_CLOUD_LOCATION="us-central1"

python deploy_to_agent_registry.py --project ${GOOGLE_CLOUD_PROJECT} --location ${GOOGLE_CLOUD_LOCATION}
```

### Step 3: Run Smoke Tests & Verification
```bash
python verify_agent_registry.py --project ${GOOGLE_CLOUD_PROJECT} --location ${GOOGLE_CLOUD_LOCATION}
```
