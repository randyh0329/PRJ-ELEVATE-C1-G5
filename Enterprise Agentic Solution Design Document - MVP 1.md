# **Enterprise Agentic Solution Design Document - MVP 1**

---

# **Document Control**

## **Document Metadata**

| Field | Value |
| :---- | :---- |
| **Project Name** | HR Agentic Solution (MVP 1) |
| **Document Owner** | Cloud Architecture & Modernization Specialist Team |
| **Status** | Approved Final Architecture / Evaluator Feedback Integrated |
| **Target Audience** | Enterprise Architects, Application Modernization Leads, AI Engineers, IT Director (Alex Rivera), Data Protection Officer (Maria Santos), HR Business Sponsors |
| **Target Cloud Platform**| Google Cloud Platform (Tiered Gemini 3.7 Flash & Gemini 3.1 Pro on Vertex AI, Cloud Run Multi-Region, Cloud Firestore, Cloud Tasks, Cloud DLP) |

## **Revision History**

| Version | Date | Author | Description of Change |
| :---- | :---- | :---- | :---- |
| **0.1** | 2026-08-25 | Elevate C1-G5 Architecture Team | Initial outline setup |
| **1.0** | 2026-08-25 | Elevate C1-G5 Architecture Team | Full comprehensive system design incorporating BRD requirements, multi-agent topology, security guardrails, Saga orchestration, and FinOps |
| **1.1** | 2026-08-25 | Elevate C1-G5 Architecture Team | Evaluator Feedback round 1: Concierge analogy, ROI matrix, RBAC table, Firestore schemas, pre-LLM DLP de-id, multi-region DR |
| **1.2** | 2026-08-25 | Elevate C1-G5 Architecture Team | Evaluator Feedback round 2: Standardized to Gemini 3.5 Flash; added explicit Cloud Tasks retry/throttling queue YAML configs; concrete Cloud DLP JSON template; PII element mapping matrix (Transcript vs LLM vs Transaction); Firestore max replication lag (<150ms); Eventarc-driven policy sync; and closed all open questions (OQ-01 to OQ-04) |
| **1.3** | 2026-08-25 | Elevate C1-G5 Architecture Team | Model Architecture Modernization: Upgraded to Google Cloud's latest GA generation models: Gemini 3.7 Flash (`gemini-3.7-flash`) as primary high-throughput agentic workhorse and Gemini 3.1 Pro (`gemini-3.1-pro`) for high-complexity Saga orchestration & LLM-as-a-Judge; integrated native agentic tool calling specifications (thought_signature); recalculated FinOps cost model with official Vertex AI token pricing. |

---

# **1. Executive Summary & Scope Boundaries**

## **1.1. Business Overview & Context**

### **The Enterprise Challenge**
Modern enterprises face immense operational drag within internal support organizations. Over 40% of all incoming HR and IT helpdesk tickets represent routine Tier 1 inquiries—such as leave policy clarifications, PTO accrual lookups, contact updates, and ticket status inquiries. Employees face severe friction navigating siloed, complex legacy UIs across disparate Human Capital Management (HCM - WorkWeek) and IT Service Management (ITSM - ServiceImmediately) systems, while human HR/IT specialists spend hundreds of hours per month on repetitive data entry.

### **The Business Metaphor: The Enterprise 5-Star Concierge (For Non-Technical Sponsors)**
To intuitively understand this architecture without getting lost in technical jargon, imagine the solution as a **World-Class Digital Concierge Desk** stationed at the entrance of our enterprise:

```mermaid
graph TD
    User(["Employee / Guest"]) --> Concierge["The Chief Concierge (Supervisor Router)<br>Greets you, verifies credentials, and understands your intent"]
    
    Concierge --> PolicyExpert["HR Policy Librarian (Policy Agent)<br>Instant access to certified corporate rulebooks; gives exact citations"]
    Concierge --> HCMClerk["HR Personnel Officer (WorkWeek Agent)<br>Checks personal PTO balances and submits vacation forms"]
    Concierge --> ITSupport["IT Desk Officer (ServiceImmediately Agent)<br>Tracks hardware/software tickets and submits incidents"]
    Concierge --> Coordinator["Chief Operations Coordinator (Saga Coordinator)<br>Coordinates multi-department requests like Relocation or Medical Leave"]
    
    Coordinator --> PolicyExpert
    Coordinator --> HCMClerk
    Coordinator --> ITSupport
```

1. **The Chief Concierge (Supervisor Router):** Welcomes the employee, validates who they are, verifies that their request adheres to house rules, and hands the request to the right specialist.
2. **The Policy Librarian (Policy Agent):** Instantly looks up official handbook pages and quotes company policy word-for-word, giving exact page citations with 0% guesswork.
3. **The HR Personnel Officer (WorkWeek Agent):** Securely opens the employee's personal personnel file to check remaining vacation days or log new time off.
4. **The IT Desk Officer (ServiceImmediately Agent):** Logs tickets for laptops or network issues and updates status.
5. **The Operations Coordinator (Saga Coordinator):** When a request spans across departments (e.g., Medical Leave requiring HR approval AND IT access routing), this coordinator ensures all steps happen in order. If IT systems are temporarily unavailable, the coordinator politely rolls back the HR filing so your records never end up out of sync.

### **Quantitative Business Value & Return on Investment (ROI)**
The HR Agentic Solution (MVP 1) directly translates generative AI into concrete, bottom-line business outcomes:

| Business Metric | Baseline (Manual Operations) | Target with HR Agent (MVP 1) | Tangible Enterprise Impact |
| :--- | :--- | :--- | :--- |
| **Tier 1 Ticket Volume** | 15,000 inquiries / month | <= 9,000 inquiries / month | **40% Inquiry Deflection** within 6 months |
| **Mean Time to Resolution (MTTR)** | 4.2 hours average turnaround | **< 45 seconds conversational turnaround** | **99% reduction in employee wait time** |
| **Operational Cost per Interaction** | ~$18.50 (Human agent labor) | **~$0.09 (GCP & Gemini 3.7 Flash / 3.1 Pro cost)** | **>$110,000 monthly operational savings** |
| **Policy Compliance & Citation** | Variable (Human memory errors) | **100% Grounded citations, 0% Hallucination** | Zero labor disputes from incorrect leave rules |
| **Employee Satisfaction (CSAT)** | 61% (Helpdesk ticketing friction) | **>= 88% Employee CSAT** | Increased productivity and seamless onboarding |

## **1.2. Scope Boundaries**

| Dimension | In-Scope (MVP 1) | Out of Scope (MVP 1 / Post-MVP) |
| :--- | :--- | :--- |
| **Conversational Interface** | Web-based responsive chat UI with streaming Server-Sent Events (SSE) and citation deep links | Native Slack / Teams / Workspace Chat integrations |
| **Knowledge Domain** | Curated static HR policy documents (PDF/Text) stored in Google Cloud Storage | Dynamic HR intranet wikis, unstructured SharePoint crawls, external search |
| **HCM Integration** | WorkWeek read (Profile, PTO balances) and write (Contact update, Leave request) | Payroll processing, Compensation, Benefits enrollment, Performance reviews |
| **ITSM Integration** | ServiceImmediately read (Ticket details/comments) and write (Create, comment, transition) | Change Management, Hardware Asset Tracking, CMDB updates |
| **Cross-System Workflows** | Equipment procurement (UC-2.1), Medical leave (UC-2.2), Relocation (UC-2.3) | Multi-tier human approval workflows involving manager sign-offs |
| **Identity & Access** | Single-tenant functional credentials with composite delegated token scoping | Enterprise IdP federation (Okta/Entra ID SSO) |
| **Languages** | English only | Multi-lingual support |
| **Modality** | Text-based conversation | Voice / IVR telephony integration |

## **1.3. Target Architecture Overview**

The target architecture is implemented using **Google Cloud Native** components, built for multi-region resilience, zero-trust security boundaries, and strict separation between cognitive reasoning and deterministic execution.

```mermaid
flowchart TB
    subgraph ClientAndIngress["Client and Ingress Layer"]
        UserBrowser["Employee Web Browser"] --> CloudArmor["Cloud Armor (WAF and DDoS Protection)"]
        CloudArmor --> GlobalLB["Global External Application Load Balancer"]
        GlobalLB --> ChatUI["Web Chat UI (Next.js on Cloud Run with SSE)"]
    end

    subgraph SecurityGateway["Security and Ingress Gateway (Cloud Run Multi-Region)"]
        ChatUI --> APIGateway["API Gateway and Interceptor"]
        APIGateway --> DLP["Cloud Sensitive Data Protection (DLP API)<br>(Pre-LLM PII De-identification)"]
        DLP --> ModelArmor["Vertex AI Model Armor<br>(Prompt Injection and Jailbreak Filter)"]
        ModelArmor --> Router["Supervisor and Intent Router (Gemini 3.7 Flash)"]
    end

    subgraph AgentCore["Agent Core Orchestration (Cloud Run Multi-Region)"]
        Router --> PolicyAgent["Policy Q&A Specialist Agent"]
        Router --> HCMAgent["WorkWeek HCM Specialist Agent"]
        Router --> ITSMAgent["ServiceImmediately Specialist Agent"]
        Router --> SagaCoordinator["Cross-System Saga Coordinator"]
        
        PolicyAgent --> LLMReasoning["Primary Agentic Engine (Gemini 3.7 Flash on Vertex AI)"]
        HCMAgent --> LLMReasoning
        ITSMAgent --> LLMReasoning
        SagaCoordinator --> SagaReasoning["High-Order Saga Reasoning (Gemini 3.1 Pro on Vertex AI)"]
    end

    subgraph IntegrationAndResilience["Enterprise Integration and Resilience Layer"]
        PolicyAgent --> VAISearch["Vertex AI Search (Grounding and Citations)"]
        VAISearch --> GCS["Cloud Storage (HR Policy PDFs)"]
        
        HCMAgent --> WWAdapter["WorkWeek Adapter and Validation Layer"]
        ITSMAgent --> SIAdapter["ServiceImmediately Adapter and Validation Layer"]
        
        WWAdapter --> CloudTasks["Cloud Tasks and Pub/Sub Buffer<br>(5xx and Throttling Resilience Queue)"]
        SIAdapter --> CloudTasks
        
        WWAdapter --> MockWW["WorkWeek HCM API (Mock Target)"]
        SIAdapter --> MockSI["ServiceImmediately ITSM API (Mock Target)"]
    end

    subgraph PersistenceAndGovernance["Persistence, Governance and Audit"]
        AgentCore <--> Firestore[("Cloud Firestore Multi-Region<br>(30-Day TTL Session and Saga State)")]
        APIGateway & AgentCore & WWAdapter & SIAdapter --> Logging["Cloud Logging and Cloud Trace"]
        Logging --> BigQuery[("BigQuery (1-Year Partitioned Audit Archive)")]
    end
```

## **1.4. Alternatives Considered**

| Architectural Decision | Chosen Selection | Alternatives Considered | Trade-offs & Rationale |
| :--- | :--- | :--- | :--- |
| **Agent Orchestration Framework** | **LangGraph / Python StateGraph on Cloud Run** | 1. Vertex AI Agent Builder (No-Code)<br/>2. Native Semantic Kernel / CrewAI | LangGraph provides explicit, auditable DAG-based state management, necessary for the Saga pattern (compensating transactions) and strict custom tool guardrails, which are difficult to strictly bound in purely declarative no-code builders. |
| **LLM Architecture & Model Selection** | **Tiered Gemini 3.7 Flash & Gemini 3.1 Pro on Vertex AI** | 1. Legacy Gemini 1.5 Pro / Flash & 2.0 / 2.5 series<br/>2. Intermediate Gemini 3.5 Series (3.5 Flash / Flash-Lite)<br/>3. Monolithic Gemini 3.1 Pro across all layers<br/>4. Open-source models on GKE (Gemma / Llama 3) | **Gemini 3.7 Flash (`gemini-3.7-flash`)** is Google Cloud's latest GA production workhorse (released August 2026), built explicitly for high-throughput agentic workflows, structured tool calling (with `thought_signature`), and sub-150ms TTFT latency. It serves as the primary engine for Supervisor Intent Routing, single-domain Specialist Agents, and streaming user responses.<br/><br/>**Gemini 3.1 Pro (`gemini-3.1-pro`)** is selectively invoked for complex multi-system Saga state arbitration (UC-2.x) and offline CI/CD LLM-as-a-Judge evaluation.<br/><br/>*Rationale against alternatives:* Legacy 1.5/2.x models lack modern agentic tool-calling optimization; monolithic Pro deployment incurs 4x higher token costs and risks P95 latency breaches (>3.5s); GKE OSS models lack managed Grounding deep links, Model Armor, and SLA guarantees. |
| **Knowledge Retrieval (RAG)** | **Vertex AI Search (Enterprise Search on GCS)** | 1. Custom RAG with pgvector on Cloud SQL / Spanner<br/>2. Vertex AI Vector Search | Vertex AI Search provides managed semantic chunking, automated re-ranking, and native Grounding & Citation attribution out of the box, directly fulfilling FR-5.2 and FR-5.3 with zero custom chunking overhead. |
| **Session & Distributed State** | **Cloud Firestore Multi-Region (`nam5`)** | 1. Memorystore (Redis)<br/>2. Cloud Spanner | Firestore offers serverless, multi-region transactional persistence with native TTL support for automatic 30-day session deletion, while persisting distributed Saga execution logs. Spanner is preserved as a future production upgrade. |
| **Resilience & Queueing** | **Cloud Tasks + Pub/Sub Dead Letter Queuing** | 1. Direct synchronous retries only<br/>2. External Celery/RabbitMQ cluster | Cloud Tasks provides fully managed, rate-limited HTTP dispatch with configurable backoff and zero infrastructure management, perfectly handling backend 429/5xx spikes. |

---

# **2. Production-Ready Future State Design & Disaster Recovery**

## **2.1. Enterprise Scalability Roadmap**
The MVP 1 architecture is engineered as a foundational stepping stone towards a global enterprise deployment:

1. **Identity Federation via Workload Identity Federation:** Replace mock user headers with corporate OIDC tokens issued by Okta or Microsoft Entra ID. The API Gateway validates JWT signatures and trades user tokens for short-lived downstream tokens.
2. **Enterprise API Hub (Apigee):** Route all WorkWeek and ServiceImmediately calls through Apigee for corporate API governance, centralized rate limiting, and mutual TLS (mTLS).
3. **Omnichannel Messaging:** Extend the Cloud Run API Gateway to accept webhooks from Slack Socket Mode, Microsoft Teams Bot Framework, and Google Chat API.

## **2.2. Disaster Recovery (DR) & Multi-Region High-Availability Architecture**
To fulfill enterprise business continuity expectations and address IT Director requirements, the architecture incorporates an active-active multi-region deployment with explicit replication lag parameters:

```mermaid
flowchart LR
    Users["Global Users"] --> AnycastIP["Cloud Anycast IP / Global HTTPS Load Balancer"]
    
    subgraph RegionPrimary["Primary Region: us-central1"]
        GLB1["Serverless NEG"] --> CR_Primary["Cloud Run (Primary)"]
    end
    
    subgraph RegionSecondary["Secondary Region: us-east4"]
        GLB2["Serverless NEG"] --> CR_Secondary["Cloud Run (Secondary)"]
    end
    
    AnycastIP --> GLB1
    AnycastIP --> GLB2
    
    CR_Primary & CR_Secondary <--> MultiRegionFS[("Cloud Firestore Multi-Region (nam5)<br>Synchronous Paxos Replication<br>Committed Lag = 0ms<br>Max Acceptable Metadata Lag under 150ms")]
    CR_Primary & CR_Secondary --> GlobalVault["Secret Manager and Vertex AI"]
```

| Metric | Target SLA | Implementation Strategy |
| :--- | :--- | :--- |
| **System Availability** | **99.9% (MVP 1) / 99.99% (Prod)** | Multi-Region Cloud Run compute with Cloud Load Balancing auto-failover |
| **Recovery Point Objective (RPO)** | **RPO = 0** | Cloud Firestore multi-region configuration (`nam5`) with synchronous Paxos-based replication across regions |
| **Recovery Time Objective (RTO)** | **RTO < 30 seconds** | Automatic health-check driven failover at the Cloud Load Balancer layer |
| **Committed Replication Lag** | **0 ms (Zero Lag)** | Write quorum requires synchronous acknowledgment across multi-region witnesses |
| **Max Acceptable Read Lag** | **< 150 milliseconds** | Bounded asynchronous follower read consistency for cross-region session checks |
| **Zonal Outage Resilience** | **Zero impact** | Cloud Run automatically distributes container instances across multiple availability zones within the region |

---

# **3. System Flows, Sequence Diagrams & Agent Design**

## **3.1. Hierarchical Multi-Agent Topology**
To enforce capability boundaries (FR-1.1), the system implements a strict **Supervisor-Worker Agent Topology**:

```mermaid
graph TD
    Input(["User Prompt"]) --> SafeIn["Input Guardrail & Pre-LLM PII Masker (Cloud DLP)"]
    SafeIn --> Sup["Supervisor Agent (Intent Router - Gemini 3.7 Flash)"]
    
    Sup -->|Policy Query| Worker1["Policy Specialist Agent (Gemini 3.7 Flash)"]
    Sup -->|WorkWeek Transaction| Worker2["HCM Specialist Agent (Gemini 3.7 Flash)"]
    Sup -->|ITSM Action| Worker3["ITSM Specialist Agent (Gemini 3.7 Flash)"]
    Sup -->|Cross-System Intent| Worker4["Saga Workflow Coordinator (Gemini 3.1 Pro)"]
    
    Worker1 --> Tool1["Vertex AI Search Datastore"]
    Worker2 --> Tool2["WorkWeek Gateway & Validator"]
    Worker3 --> Tool3["ServiceImmediately Gateway & Validator"]
    Worker4 --> Worker1
    Worker4 --> Worker2
    Worker4 --> Worker3
    
    Worker1 --> StateStore[("Firestore State (30-Day TTL)")]
    Worker2 --> StateStore
    Worker3 --> StateStore
    Worker4 --> StateStore
    
    Worker1 --> SafeOut["Output Guardrail & Re-identification Checker"]
    Worker2 --> SafeOut
    Worker3 --> SafeOut
    Worker4 --> SafeOut
    SafeOut --> Output(["Sanitized Grounded Response to User"])
```

## **3.2. End-to-End Sequence Diagrams**

### **Path 1: Single-Domain Policy Q&A with Streaming SSE & Grounding (UC-1.1)**
```mermaid
sequenceDiagram
    autonumber
    actor User as Employee
    participant UI as Chat Web UI
    participant GW as API Gateway (FastAPI)
    participant DLP as Cloud DLP (PII Redaction)
    participant Orch as Policy Agent (Gemini 3.7 Flash)
    participant Search as Vertex AI Search
    participant Audit as Cloud Logging and BigQuery

    User->>UI: What is the bereavement leave policy?
    UI->>GW: POST /v1/chat/stream (SSE Connection)
    GW->>DLP: Pre-LLM De-identify PII
    DLP-->>GW: Sanitized Prompt + Ephemeral Mapping
    GW->>Orch: Invoke Policy Specialist Agent
    Orch->>Search: Query Indexed Policy Documents
    Search-->>Orch: Return Chunks + DeepLink Metadata + Confidence Score
    
    alt Confidence at least 0.8 and Grounded
        Orch->>GW: Stream tokens via Server-Sent Events (SSE)
        GW->>UI: Stream response chunks (TTFT under 1.0s)
        GW->>Audit: Record Audit Log (Origin: AI-Policy-Agent, Allowed: true)
    else Confidence below 0.8 or No Match
        Orch-->>GW: Policy information not found in official documents
        GW->>UI: Return Fallback Grounding Rejection
        GW->>Audit: Record Log (Unanswered or Out of Scope)
    end
```

### **Path 2: Cross-System Orchestration (UC-2.2 Medical Leave) with Cloud Tasks Async Queueing**
```mermaid
sequenceDiagram
    autonumber
    actor User as Employee
    participant Orch as Saga Workflow Coordinator (Gemini 3.1 Pro)
    participant FS as Cloud Firestore (Saga Log)
    participant WW as WorkWeek API Adapter
    participant Tasks as Cloud Tasks Resilience Queue
    participant SI as ServiceImmediately API Adapter
    participant UI as Chat Web UI

    User->>UI: Request medical leave starting next week
    UI->>Orch: Start UC-2.2 Orchestration
    Orch->>FS: Init Saga (ID=saga-998, State=STARTED)
    
    Note over Orch, WW: Step 1: WorkWeek Leave Submission (Provisional)
    Orch->>WW: POST /leaves (Type: Medical, StartDate: 2026-09-01, Status: PENDING_APPROVAL)
    WW-->>Orch: HTTP 201 Created (LeaveID=LV-4012)
    Orch->>FS: Update Saga (State=STEP1_WW_COMPLETED, LeaveID=LV-4012)
    
    Note over Orch, SI: Step 2: ITSM Routing Ticket Creation
    Orch->>SI: POST /incidents (Category: Access, ShortDesc: Route email access to manager)
    
    alt ITSM Returns 429 Rate Limit or 5xx Server Error
        SI-->>Orch: HTTP 503 Service Unavailable / Rate Exceeded
        Orch->>Tasks: Enqueue Cloud Task (Payload, Backoff=Exponential, MaxRetries=5)
        Tasks-->>Orch: Task Accepted (TaskID=task-771)
        Orch->>FS: Update Saga (State=STEP2_ASYNC_QUEUED, TaskID=task-771)
        Orch-->>UI: "Your medical leave (LV-4012) is submitted for manager approval. IT email routing is queued due to peak load and will complete shortly."
    else Catastrophic Failure (Retries Exhausted on Cloud Tasks)
        Tasks->>FS: Trigger Compensation Webhook
        Note over Orch, WW: Compensating Transaction (Rollback)
        Orch->>WW: DELETE /leaves/LV-4012 (Compensate: Cancel pending leave)
        WW-->>Orch: HTTP 200 Cancelled
        Orch->>FS: Update Saga (State=COMPENSATED_CANCELLED)
        Orch-->>UI: "IT access routing failed. Your leave has been automatically rolled back to prevent inconsistent records. Please contact IT Helpdesk."
    end
```

### **Path 3: OAuth / OBO Token Revocation & Downstream Notification Sequence**
```mermaid
sequenceDiagram
    autonumber
    actor Admin as HR / Security Admin
    participant IdP as WorkWeek / Corporate IdP
    participant AuthGW as API Gateway (/api/v1/auth/revoke-webhook)
    participant FS as Cloud Firestore (Token Cache)
    participant WW_API as WorkWeek API Gateway
    participant SI_API as ServiceImmediately Gateway
    participant ActiveSession as Active Agent Container

    Admin->>IdP: Terminate Employee or Revoke Permissions
    IdP->>AuthGW: POST /api/v1/auth/revoke-webhook (HMAC Signature, EmployeeID, Timestamp)
    AuthGW->>AuthGW: Validate HMAC Signature
    
    par Invalidate Firestore and Downstream
        AuthGW->>FS: Delete token_cache where employeeId == payload.employeeId
        AuthGW->>FS: Update sessions set status = 'REVOKED' where employeeId == payload.employeeId
        AuthGW->>WW_API: POST /oauth/revoke (TokenID)
        AuthGW->>SI_API: POST /oauth/revoke (TokenID)
    end
    
    AuthGW-->>IdP: HTTP 200 OK (Revocation Confirmed)
    
    Note over ActiveSession: Next Conversation Turn by User
    User->>ActiveSession: Submit new leave request
    ActiveSession->>FS: Check token_cache and session status
    FS-->>ActiveSession: Status: REVOKED / Cache Miss
    ActiveSession-->>User: "Security credentials updated or revoked. Session terminated. Please re-authenticate."
```

---

# **4. Security, Governance & Identity**

## **4.1. Enterprise Role-Based Access Control (RBAC) Matrix**
To satisfy governance requirements (FR-1.5), the solution enforces a strict, tabular RBAC model across all system interfaces and agent tools:

| Enterprise User Role | Policy Q&A (RAG) | WorkWeek HCM Scope | ServiceImmediately ITSM Scope | Session & Audit Scope |
| :--- | :--- | :--- | :--- | :--- |
| **End User (Standard Employee)** | Full access to general static HR policies (Leave, Expense, Remote Work) | **Self-only:** Read profile, check own PTO balance; Submit own leave requests; Update own phone/address | **Self-only:** Query own incident tickets; Open incident; Add comments to own tickets | View own active conversational session only; No access to system audit logs |
| **People Partner (HR Specialist)** | Full access to HR policies and confidential HR operational guidelines | **Assigned Department:** Read department employee profiles; Verify team PTO balances | Query HR-related employee tickets; Post comments on behalf of HR Operations | View assigned department inquiry analytics; Redacted PII session logs |
| **IT Support Engineer** | Standard policy access | Read contact info only (for equipment dispatch) | **Full ITSM Queue:** Read, assign, update priority, post work notes, transition ticket lifecycle | Read technical execution logs and API diagnostic traces (PII redacted) |
| **Security & Compliance Admin** | Read-only policy access | No direct tool execution | No direct tool execution | **Full Audit Access:** Read BigQuery compliance audit logs, DLP de-identification telemetry |

## **4.2. PII Classification, Masking & Retention Mapping Table**
To satisfy DPO requirements, explicit data protection boundaries delineate between conversational transcripts, external LLM model payloads, and downstream transaction payloads:

| PII Data Element | Ingested User Input | LLM Payload (Vertex AI Gemini 3.7 Flash / 3.1 Pro) | Stored Transcript (Firestore / BigQuery) | Downstream API Payload (WorkWeek / ITSM) | Transformation Technique |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Social Security Number (SSN)** | Plaintext allowed | **BLOCKED / REDACTED (`[REDACTED_SSN]`)** | **REDACTED completely** | Strictly prohibited in conversational channel | Hard regex + DLP infoType filter |
| **Banking / Credit Card Info** | Plaintext blocked | **BLOCKED completely** | **REDACTED completely** | Out of Scope for MVP 1 | Automatic security block & log alert |
| **Employee Name** | Plaintext | **Pseudonymized (`[PERSON_1]`)** | Retained (Encrypted at rest) | Plaintext | Crypto-Deterministic FPE |
| **Personal Phone Number** | Plaintext | **Pseudonymized (`[PHONE_1]`)** | Masked (`[REDACTED_PHONE]`) | Plaintext (Contact Update API only) | Crypto-Deterministic FPE |
| **Home Address** | Plaintext | **Pseudonymized (`[ADDRESS_1]`)** | Masked (`[REDACTED_ADDRESS]`) | Plaintext (Contact Update API only) | Crypto-Deterministic FPE |
| **Employee ID** | Plaintext | **Pseudonymized (`[EMP_ID_1]`)** | Retained (Key identifier) | Plaintext in OBO Context Header | Crypto-Deterministic FPE |
| **Leave Balances / Dates** | Plaintext | Plaintext (Business necessity) | Retained for transaction trace | Plaintext | Standard validation |

## **4.3. Concrete Google Cloud DLP De-identification Configuration Template**
To guarantee DPO compliance sign-off, the automated de-identification pipeline uses the following Google Cloud Sensitive Data Protection (DLP) configuration template:

```json
{
  "deidentifyTemplate": {
    "displayName": "HR_Agent_Pre_LLM_Deidentification_Template",
    "description": "Pseudonymizes PII before sending context to Vertex AI Gemini 3.7 Flash / 3.1 Pro",
    "deidentifyConfig": {
      "infoTypeTransformations": {
        "transformations": [
          {
            "infoTypes": [
              { "name": "US_SOCIAL_SECURITY_NUMBER" },
              { "name": "CREDIT_CARD_NUMBER" },
              { "name": "BANK_ACCOUNT_NUMBER" }
            ],
            "primitiveTransformation": {
              "replaceWithInfoTypeConfig": {}
            }
          },
          {
            "infoTypes": [
              { "name": "PERSON_NAME" },
              { "name": "PHONE_NUMBER" },
              { "name": "EMAIL_ADDRESS" },
              { "name": "STREET_ADDRESS" }
            ],
            "primitiveTransformation": {
              "cryptoDeterministicConfig": {
                "cryptoKey": {
                  "kmsWrapped": {
                    "wrappedKey": "CiQA...",
                    "cryptoKeyName": "projects/prj-elevate-c1-g5/locations/global/keyRings/hr-agent-kr/cryptoKeys/dlp-fpe-key"
                  }
                },
                "surrogateInfoType": {
                  "name": "PSEUDONYM"
                }
              }
            }
          }
        ]
      }
    }
  }
}
```

## **4.4. Firestore Document Schemas, 30-Day Lifecycle & "Right to be Forgotten"**

### **Explicit Cloud Firestore Collections & Schemas**

#### **Collection: `sessions`**
```json
{
  "_id": "session-uuid-v4",
  "userId": "usr_99812",
  "employeeId": "EMP-44210",
  "role": "EMPLOYEE",
  "createdAt": "2026-08-25T10:00:00Z",
  "lastActivityAt": "2026-08-25T10:04:30Z",
  "status": "ACTIVE",
  "ttl_expiry": "2026-09-24T10:00:00Z"
}
```

#### **Subcollection: `sessions/{sessionId}/messages`**
```json
{
  "_id": "msg-001",
  "sender": "USER",
  "maskedContent": "How many hours of PTO do I have remaining?",
  "timestamp": "2026-08-25T10:00:05Z",
  "inputTokens": 14,
  "outputTokens": 0,
  "citations": []
}
```

#### **Collection: `sagas` (Distributed Workflow Log)**
```json
{
  "_id": "saga-998",
  "sessionId": "session-uuid-v4",
  "employeeId": "EMP-44210",
  "workflowType": "UC-2.2-MEDICAL-LEAVE",
  "currentState": "STEP1_WW_COMPLETED",
  "steps": [
    {
      "stepIndex": 1,
      "targetSystem": "WorkWeek",
      "action": "SUBMIT_LEAVE",
      "status": "SUCCESS",
      "externalReferenceId": "LV-4012",
      "timestamp": "2026-08-25T10:01:15Z"
    }
  ],
  "ttl_expiry": "2026-09-24T10:01:15Z"
}
```

#### **Collection: `token_cache`**
```json
{
  "_id": "EMP-44210_hash",
  "employeeId": "EMP-44210",
  "delegatedToken": "enc_token_blob",
  "cachedAt": "2026-08-25T10:00:00Z",
  "ttl_expiry": "2026-08-25T10:10:00Z"
}
```

### **Data Retention Lifecycle & Compliance Rules**
1. **Automated 30-Day Firestore TTL:** A Cloud Firestore TTL policy is configured on the `ttl_expiry` field across `sessions`, `messages`, and `sagas`. Documents reaching 30 days of age are permanently purged by Google Cloud's automated background TTL cleaner with zero manual maintenance.
2. **Audit Log Archiving in BigQuery:** Business metrics, tool execution origins, and safety scan decisions (with all PII stripped) are streamed into partitioned BigQuery tables retained for **365 days** to satisfy regulatory audit requirements, after which BigQuery partition expiration deletes them.
3. **Right to be Forgotten (GDPR Article 17) Purge Workflow:**
   - When an employee departs or submits an erasure request:
     1. An event is dispatched to `/api/v1/compliance/purge-employee-data`.
     2. Cloud Firestore immediately executes hard deletions across `sessions`, `messages`, and `sagas` matching the `employeeId`.
     3. For stale embeddings in Vertex AI Search, a Cloud Function triggers the **Vertex AI Search Datastore Sync API** with document deletion flags to purge vector embeddings within 15 minutes.
     4. Query-time metadata filtering instantly rejects any stale cached chunks associated with the user (< 100ms sync delay).
     5. A signed cryptographic confirmation token is returned to the Compliance Office.

---

# **5. Integration Details & Error Handling**

## **5.1. Tool Specifications & Agentic Execution (OpenAPI 3.0 Summary)**

### **Supported Downstream API Endpoints**
- **WorkWeek HCM API:**
  - `GET /api/v1/employees/me/profile` (Profile metadata)
  - `GET /api/v1/employees/me/balances` (Real-time PTO balances)
  - `POST /api/v1/employees/me/leaves` (Submit leave request)
  - `DELETE /api/v1/employees/me/leaves/{leaveId}` (Compensating action: Cancel leave)
- **ServiceImmediately ITSM API:**
  - `GET /api/v1/incidents/{ticketId}` (Ticket details & comments)
  - `POST /api/v1/incidents` (Create incident ticket)
  - `PATCH /api/v1/incidents/{ticketId}/status` (Update status e.g., Resolved)
  - `POST /api/v1/incidents/{ticketId}/comments` (Append work notes)

### **Agentic Tool Calling & Reasoning Signatures (Vertex AI Function Calling)**
To interface deterministically with WorkWeek and ServiceImmediately, the agents utilize native Vertex AI Function Calling on **Gemini 3.7 Flash** (`gemini-3.7-flash`):
- **Agentic Thought Signatures (`thought_signature`):** In accordance with the latest Gemini 3.7 Flash tool-calling specifications, function call parts emitted by the model include explicit reasoning trace signatures. This enables internal chain-of-thought verification of parameter boundaries (e.g., date formats, balance thresholds) prior to dispatching API calls.
- **Strict Parameter Schemas:** Tool definitions are strictly typed using OpenAPI 3.0 JSON Schema validation, preventing hallucinated arguments or malformed types from reaching backend service adapters.
- **Idempotency Keys:** Every state-modifying POST/PATCH request automatically injects an `X-Idempotency-Key` derived from the session ID and turn sequence number to prevent duplicate transactions under network retries.

## **5.2. API Throttling Limits & Concrete Cloud Tasks Queue Configurations**

```mermaid
flowchart TD
    Req["Specialist Agent Invokes Backend API"] --> RateCheck{"Is Backend Under Limit?<br>(WW: 50 rps, SI: 40 rps)"}
    
    RateCheck -->|Within Limit| DirectCall["Call Backend API (Direct HTTP)"]
    DirectCall --> Resp{"API Response"}
    
    Resp -->|HTTP 200/201| ReturnSuccess["Return Result to Agent"]
    
    RateCheck -->|Throttled 429| QueueBranch["Resilience Queueing Branch"]
    Resp -->|HTTP 500/503| QueueBranch
    
    QueueBranch --> Enqueue["Enqueue to Cloud Tasks (Rate-Limited Queue)<br>Payload + Execution Context"]
    Enqueue --> AckUser["Immediate User Feedback:<br>'Request queued due to high volume. Processing asynchronously.'"]
    
    Enqueue --> TaskWorker["Cloud Tasks Background Dispatcher<br>(Exponential Backoff: 1s, 2s, 4s, 8s, 16s)"]
    TaskWorker --> RetryCall["Retry Call to Backend"]
    
    RetryCall -->|Success| CompleteSaga["Update Saga Status to COMPLETED"]
    RetryCall -->|Exhausted 5 Retries| DLQ["Send to Pub/Sub Dead-Letter Queue (DLQ)"]
    DLQ --> Compensate["Trigger Saga Compensation & Alert Operations"]
```

### **Concrete API Throttling & Queue Parameters**

| Backend Target | Sustained Rate Limit | Burst Capacity | Max Concurrent Dispatches | Max Dispatch Rate | Max Retries | Backoff Multiplier | Min Backoff | Max Backoff |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **WorkWeek HCM API** | 50 req / sec | 100 req | 25 concurrent | 45.0 dispatches/sec | 5 attempts | 2.0 (Exponential) | 1.0 second | 60.0 seconds |
| **ServiceImmediately ITSM** | 40 req / sec | 80 req | 20 concurrent | 35.0 dispatches/sec | 5 attempts | 2.0 (Exponential) | 1.0 second | 60.0 seconds |

### **Cloud Tasks Production Queue Configuration (YAML Specification)**
```yaml
apiVersion: cloudtasks.googleapis.com/v2
kind: Queue
metadata:
  name: projects/prj-elevate-c1-g5/locations/us-central1/queues/backend-resilience-queue
rateLimits:
  maxDispatchesPerSecond: 40.0
  maxConcurrentDispatches: 20
  maxBurstSize: 50
retryConfig:
  maxAttempts: 5
  minBackoff: 1.000s
  maxBackoff: 60.000s
  maxDoublings: 4
```

## **5.3. Deterministic Business Rules Engine (Guardrails)**

```mermaid
flowchart TD
    Req["Tool Invocation Request"] --> CheckType{"Tool Target"}
    
    CheckType -->|WorkWeek Leave| C1["Check: StartDate <= EndDate and StartDate >= Today"]
    C1 -->|Pass| C2["Check: Requested Hours <= Accrued Balance"]
    C2 -->|Pass| ExecWW["Execute WorkWeek API Call"]
    C1 -->|Fail| Err1["Reject: Temporal Violation"]
    C2 -->|Fail| Err2["Reject: Insufficient Balance"]
    
    CheckType -->|ServiceImmediately Update| S1["Check: Current State is not Closed"]
    S1 -->|Pass| S2["Check: Valid State Transition (e.g. New to In Progress)"]
    S2 -->|Pass| S3["Check: No Duplicate Incident within 10 min"]
    S3 -->|Pass| ExecSI["Execute ServiceImmediately Call"]
    S1 -->|Fail| ErrSI["Reject: Invalid Lifecycle or Duplicate"]
    S2 -->|Fail| ErrSI
    S3 -->|Fail| ErrSI
```

## **5.4. Error Handling Matrix & Resilience Strategy**

| Failure Mode | Detection Indicator | System Fallback & Compensating Action | User-Facing Notification |
| :--- | :--- | :--- | :--- |
| **Vertex AI Search Outage** | 503 Service Unavailable / Timeout > 3s | Circuit breaker opens; bypass RAG retrieval; redirect to HR Helpdesk contacts. | *"Our policy knowledge system is temporarily unavailable. Please refer directly to the HR Portal at hr.corp.internal."* |
| **WorkWeek API Rate Limited (429)** | HTTP 429 Too Many Requests | Dispatch to Cloud Tasks rate-limited queue with exponential backoff. | *"WorkWeek is experiencing high traffic. Your request has been queued and will process within a few minutes."* |
| **Partial Cross-System Failure (Saga Step 2)** | HTTP 5xx on ServiceImmediately after WorkWeek success | Execute Compensating Action (Cancel leave in WorkWeek via DELETE /leaves/id). | *"We could not complete your IT request. Any pending leave changes have been rolled back to prevent inconsistent records."* |
| **Prompt Injection Detected** | Safety Score > 0.85 on Model Armor filter | Immediate turn termination; tool execution aborted; log security incident. | *"I am unable to process this request as it violates enterprise acceptable usage policies."* |
| **OBO Token Revoked / Expired** | HTTP 401 Unauthorized from backend | Invalidate local token cache; prompt user for re-authentication. | *"Your security credentials have expired or were updated. Please refresh your browser to re-authenticate."* |

---

# **6. Cost Estimation & FinOps**

## **6.1. Primary Cost Drivers & Monthly Estimate**

```mermaid
pie title Monthly Cost Breakdown by Component
    "Vertex AI Gemini 3.7 Flash & 3.1 Pro Tokens" : 55
    "Cloud Run Compute (Multi-Region)" : 21
    "Vertex AI Search Queries" : 14
    "Sensitive Data Protection and Armor" : 5
    "Cloud Firestore and BigQuery" : 5
```

| Component | Usage Assumptions (10,000 MAU / 100,000 Inquiries/Month) | Monthly Estimated Cost |
| :--- | :--- | :--- |
| **Gemini 3.7 Flash (Supervisor & Intent Router)** | 100,000 turns x 500 in / 100 out = 50M in ($37.50) + 10M out ($37.50) | ~$75.00 |
| **Gemini 3.7 Flash (Policy, HCM, ITSM Specialists)** | 75,000 turns x 1,800 in / 350 out = 135M in ($101.25) + 26.25M out ($98.44) | ~$199.69 |
| **Gemini 3.1 Pro (Cross-System Saga Orchestration)** | 5,000 complex turns x 2,500 in / 600 out = 12.5M in ($15.63) + 3M out ($15.00) | ~$30.63 |
| **Vertex AI Search (Datastores)** | 40,000 policy queries ($2.00 per 1,000 queries) | ~$80.00 |
| **Cloud Run Serverless Compute** | 200,000 vCPU-seconds + memory allocation (Multi-Region) | ~$115.00 |
| **Cloud Sensitive Data Protection** | ~15 GB text inspected for PII de-identification | ~$30.00 |
| **Cloud Firestore & BigQuery** | Session storage with 30-day TTL + 1-year audit logs | ~$25.00 |
| **Total Estimated Run Cost** | **Fully Managed Production-Ready Infrastructure** | **~$555.32 / month** |

*ROI Comparison: At ~$555.32/month infrastructure cost, deflecting 6,000 Tier 1 tickets saves an estimated $111,000 in monthly human helpdesk operational expense, yielding an outstanding ROI > 200x (~$0.09 per interaction).*

---

# **7. Deployment & Delivery Plan**

## **7.1. Infrastructure as Code (Terraform) Topology**

```mermaid
graph TD
    subgraph TF["Terraform Root Module"]
        M1["modules/networking: VPC, Cloud Armor, Serverless NEGs"]
        M2["modules/iam: Least-Privilege Service Accounts"]
        M3["modules/vertex_ai: Vertex AI Search and Model Armor"]
        M4["modules/cloud_run: Multi-Region API Gateway and Orchestrators"]
        M5["modules/storage: Multi-Region Firestore, GCS Policy Buckets"]
        M6["modules/resilience: Cloud Tasks Queues and Pub/Sub DLQ"]
        M7["modules/security: DLP De-identification Templates, Secret Manager"]
    end
```

## **7.2. Phased Delivery Roadmap**

```mermaid
gantt
    title MVP 1 Phased Delivery Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 1 Foundation
    Terraform IaC and Multi-Region GCP Setup :p1_1, 2026-09-01, 1w
    HR Policy Ingestion into Vertex Search   :p1_2, after p1_1, 1w
    section Phase 2 Agent Core
    Supervisor and LangGraph Engine Dev      :p2_1, after p1_2, 2w
    WorkWeek and ServiceImmediately Adapters :p2_2, 2026-09-15, 2w
    Deterministic Validation and Cloud Tasks :p2_3, after p2_2, 1w
    section Phase 3 Governance and Security
    Pre-LLM DLP De-id and Token Revocation   :p3_1, after p2_3, 1w
    Saga Compensating Flow Hardening         :p3_2, after p3_1, 1w
    section Phase 4 Verification and UAT
    Automated Benchmark Eval (>95% Acc)      :p4_1, after p3_2, 1w
    Stakeholder UAT and Executive Signoff    :p4_2, after p4_1, 1w
```

---

# **8. Assumptions, Constraints, Risk & Mitigations**

## **8.1. Risk & Mitigation Matrix**

| Risk ID | Description | Likelihood | Impact | Concrete Mitigation Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **RSK-01** | LLM Hallucinations in HR Policy Q&A violating compliance | Low | Critical | Enforce strict Grounding threshold (Vertex AI Grounding Check >= 0.8). Enforce citation-only responses; fall back to refusal if context is ambiguous. |
| **RSK-02** | Peak traffic triggers backend 429 throttling and sync timeouts | Medium | High | Integrate Cloud Tasks rate-limited queueing with exponential backoff and asynchronous user acknowledgement (Section 5.2). |
| **RSK-03** | Inconsistent state during cross-system execution failure | Medium | High | Implement Saga pattern with persistent Firestore step logging and automated rollback/compensating calls (NFR-4.3). |
| **RSK-04** | Prompt injection bypasses guardrails to leak sensitive employee data | Low | Critical | Deploy defense-in-depth: Model Armor pre-filter, Pre-LLM Cloud DLP de-identification, and strictly isolated tool execution scopes (RBAC). |
| **RSK-05** | Unauthorized access post employee status change | Low | Critical | Implement 10-minute OBO token cache with event-driven Webhook cache revocation (`/api/v1/auth/revoke-webhook`). |
| **RSK-06** | Data privacy compliance failure from indefinitely retained chat logs | Low | High | Implement native Cloud Firestore 30-day TTL automatic hard deletion + PII-scrubbed BigQuery audit archiving. |

---

# **9. Quality Evaluation & UAT Framework**

## **9.1. Evaluation Metrics & Success Thresholds**

| Dimension | Target Metric | Evaluation Method | Pass Threshold |
| :--- | :--- | :--- | :--- |
| **Policy Grounding** | Faithfulness & Citation Precision | Vertex AI Gen AI Evaluation SDK with **Gemini 3.1 Pro (`gemini-3.1-pro`) LLM-as-a-Judge** against Golden Dataset | **>= 95% Accuracy, 0% Hallucination** |
| **Guardrail Robustness**| Injection Block Rate | Automated adversarial red-teaming test suite (100 known jailbreak/prompt attack vectors) audited by Vertex AI Model Armor & Gemini 3.1 Pro | **100% Blocked, < 1% False Positives** |
| **Transaction Integrity**| Correctness of WorkWeek/ITSM calls | Automated integration test suite comparing mock DB states | **100% Correct Transactions** |
| **Response Latency** | Time-to-First-Token (TTFT) & Total Time | Cloud Trace APM distributed spans (Gemini 3.7 Flash SSE streaming) | **Average TTFT < 1.0s, Total < 3.5s (Max < 5.0s)** |
| **Safety Overhead** | Pre/Post Guardrail Latency | Custom telemetry metrics around Interceptor pipeline (Model Armor + Cloud DLP) | **< 300ms total latency overhead** |

## **9.2. Automated CI/CD Evaluation Pipeline**
Prior to deploying any update to the agent prompts, tools, or model configurations, the Cloud Build CI/CD pipeline triggers an automated evaluation harness powered by **Gemini 3.1 Pro (`gemini-3.1-pro`)** against a curated dataset of **150 golden HR prompts**:
1. **50 Single-Domain Policy Prompts (UC-1.1):** Evaluates semantic accuracy, citation integrity, and refusal accuracy on ambiguous/out-of-scope policies using Gemini 3.1 Pro as an impartial judge.
2. **50 Single-Action Tool Prompts (UC-1.2, UC-1.3):** Asserts deterministic parameter extraction, temporal rule adherence, and balance validation.
3. **50 Cross-System Saga Prompts (UC-2.1 to UC-2.3):** Injects simulated 429/5xx backend faults to verify Cloud Tasks queuing, backward rollback compensation, and message consistency.

---

# **10. Finalized Architectural Decisions (Closed Questions)**

All preliminary open questions have been formally resolved in consensus with Enterprise Architecture, IT Director, and DPO:

| Decision ID | Area | Finalized Technical Architecture & Business Rule | Approved By | Implementation Status |
| :--- | :--- | :--- | :--- | :--- |
| **DEC-01** (formerly OQ-01) | Knowledge Base (RAG) | **Eventarc-Driven Knowledge Ingestion:** GCS bucket `object.finalize` events trigger a Cloud Function that calls the Vertex AI Search Datastore Import API. Incremental sync latency is bounded under 15 minutes. | Data Lead | **Finalized & Documented** |
| **DEC-02** (formerly OQ-02) | Orchestration / HITL | **Provisional Submission with Asynchronous Manager Routing:** In UC-2.2 (Medical Leave), the agent submits the WorkWeek record with status `PENDING_APPROVAL` and opens an ITSM ticket routing the approval notice to the manager. This unblocks conversational UX while preserving managerial compliance. | HR Business Lead | **Finalized & Documented** |
| **DEC-03** (formerly OQ-03) | UI / Perceived Latency | **Mandatory Server-Sent Events (SSE) Streaming:** Web chat UI strictly implements SSE streaming. Perceived Time-to-First-Token (TTFT) is guaranteed under 1.0 seconds, delivering immediate conversational responsiveness. | Frontend Lead | **Finalized & Documented** |
| **DEC-04** (formerly OQ-04) | Security & Compliance | **Strict Three-Tier PII Partitioning:** Formally approved PII mapping table (Section 4.2) and concrete Cloud DLP JSON template (Section 4.3). Raw SPII is blocked from model prompts; transcripts are auto-purged after 30 days. | InfoSec & DPO | **Finalized & Documented** |

