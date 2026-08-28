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

## 📊 Catalog of the 8 Registered Agents

| # | Agent Name / Identifier | Registry Display Name | Architectural Tier | Model / Runtime | Bound Tools & Extensions |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **1** | `HRSupervisorAgent` | `hr-supervisor-orchestrator-v1` | Hierarchical Root Supervisor | Gemini 2.5 Pro / Flash | Workday, ServiceNow, Sub-Agent Mesh Dispatcher |
| **2** | `PolicyBenefitsAgent` | `hr-policy-benefits-specialist-v1` | Domain Specialist | Gemini 2.5 Flash | Grounded Policy Catalog (Sec 19, 28, 12, 03) |
| **3** | `LifecycleOperationsAgent` | `hr-lifecycle-operations-specialist-v1` | Domain Specialist | Gemini 2.5 Flash | `ServiceNowClient.create_case`, Pub/Sub Topics |
| **4** | `ManagerApprovalAgent` | `hr-approval-gatekeeper-v1` | HITL Governance | Gemini 2.5 Flash | Approval Store, Pub/Sub Events, Case Sync |
| **5** | `hr_policy_agent_rag` | `hr-policy-rag-search-v1` | ADK Autonomous Agent | `gemini-2.5-flash` | `search_policy_docs` (Vertex AI Search) |
| **6** | `hr_policy_agent_okf` | `hr-policy-okf-catalog-v1` | ADK Autonomous Agent | `gemini-2.5-flash` | `list_concepts`, `read_concept` (OKF Catalog) |
| **7** | `hr_policy_agent_hybrid` | `hr-policy-dual-hybrid-v1` | ADK Autonomous Agent | `gemini-2.5-flash` | Dual Grounding (OKF Tools + Vertex Search) |
| **8** | `HREvalJudgeAgent` | `hr-eval-llm-judge-v1` | Evaluator & Judge | `gemini-3.6-flash` | 5-Dimensional Rubric Scoring Engine |

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
