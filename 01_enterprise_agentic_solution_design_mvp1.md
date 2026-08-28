# Enterprise Agentic Solution Design Document - MVP 1

---

## Document Control

### Document Metadata
| Field | Value |
| :--- | :--- |
| **Document Title** | Enterprise Agentic Solution Design Document - MVP 1 |
| **Programme** | Global Enterprise Intelligent Workforce Automation |
| **Project** | HR Agentic Solution (MVP 1) |
| **Author(s)** | Enterprise AI Solution Architecture Team (`choirul@`) |
| **Date** | August 25, 2026 |
| **Status** | Approved / Baseline Architecture |
| **Target Audience** | Enterprise Architects, HR Leadership, CISO / Security Teams, Engineering & DevOps Teams |

### Revision History
| Version | Date | Author | Description of Change |
| :--- | :--- | :--- | :--- |
| **0.1** | 2026-08-20 | choirul@ | Initial outline setup and requirements mapping from BRD |
| **0.9** | 2026-08-24 | choirul@ | Architecture decisions finalized via Grill-Me review (Vertex AI Agent Builder, Dual Grounding, Saga Pattern) |
| **1.0** | 2026-08-25 | choirul@ | Full baseline Solution Design Document aligned with Enterprise SDD Template |

---

## Table of Contents
- [1. Executive Summary & Scope Boundaries](#1-executive-summary--scope-boundaries)
  - [1.1. Business Overview & Context](#11-business-overview--context)
  - [1.2. Scope Boundaries](#12-scope-boundaries)
  - [1.3. Target Architecture Overview](#13-target-architecture-overview)
  - [1.4. Alternatives Considered](#14-alternatives-considered)
- [2. Production-Ready Future State Design](#2-production-ready-future-state-design)
- [3. System Flows, Sequence Diagrams & Agent Design](#3-system-flows-sequence-diagrams--agent-design)
  - [3.1. End-to-End Data Flow & Agent Design](#31-end-to-end-data-flow--agent-design)
  - [3.2. Pre-Processing, Safety Scanning & Optimization](#32-pre-processing-safety-scanning--optimization)
  - [3.3. Path Sequence Diagrams for Single-Domain Use Cases](#33-path-sequence-diagrams-for-single-domain-use-cases)
    - [Path 1: Policy Q&A with Clickable Citations (UC-1.1)](#path-1-policy-qa-with-clickable-citations-uc-11)
    - [Path 2: WorkWeek Leave Balance & Submission (UC-1.2)](#path-2-workweek-leave-balance--submission-uc-12)
    - [Path 3: ServiceImmediately Incident Management (UC-1.3)](#path-3-serviceimmediately-incident-management-uc-13)
  - [3.4. Path Sequence Diagrams for Cross-System Orchestration](#34-path-sequence-diagrams-for-cross-system-orchestration)
    - [Path 4: Equipment Procurement (UC-2.1)](#path-4-equipment-procurement-uc-21)
    - [Path 5: Medical Leave with Access Delegation (UC-2.2)](#path-5-medical-leave-with-access-delegation-uc-22)
    - [Path 6: Relocation Allowance & Facilities Badge (UC-2.3)](#path-6-relocation-allowance--facilities-badge-uc-23)
- [4. Security, Governance & Identity](#4-security-governance--identity)
  - [4.1. Authentication Boundaries & Request Origin Verification](#41-authentication-boundaries--request-origin-verification)
  - [4.2. Network Isolation & Service Perimeters](#42-network-isolation--service-perimeters)
  - [4.3. Role-Based Access Control (RBAC) Matrix & Tool Scoping](#43-role-based-access-control-rbac-matrix--tool-scoping)
  - [4.4. Sensitive Data Handling & PII Management (Cloud DLP)](#44-sensitive-data-handling--pii-management-cloud-dlp)
  - [4.5. Mock Identity Translation & Anti-Spoofing at API Gateway](#45-mock-identity-translation--anti-spoofing-at-api-gateway)
  - [4.6. GDPR Compliance, Right to be Forgotten & Embedding/Log Lifecycle](#46-gdpr-compliance-right-to-be-forgotten--embeddinglog-lifecycle)
- [5. Integration Details & Error Handling](#5-integration-details--error-handling)
  - [5.1. Third-Party Tool Integration Methodology & Explicit JSON Schemas](#51-third-party-tool-integration-methodology--explicit-json-schemas)
    - [WorkWeek HCM Connector Specification & Schemas](#workweek-hcm-connector-specification--schemas)
    - [ServiceImmediately ITSM Connector Specification & Schemas](#serviceimmediately-itsm-connector-specification--schemas)
  - [5.2. Component Failure Mapping, Fallback Logic & User Notifications](#52-component-failure-mapping-fallback-logic--user-notifications)
  - [5.3. Cross-System Consistency & Saga Compensation Engine](#53-cross-system-consistency--saga-compensation-engine)
  - [5.4. Cloud Run Mock Service State Persistence & Database Schema (ERD)](#54-cloud-run-mock-service-state-persistence--database-schema-erd)
  - [5.5. API Throttling, Rate Limiting & Circuit Breaker Thresholds](#55-api-throttling-rate-limiting--circuit-breaker-thresholds)
- [6. Cost Estimation & FinOps](#6-cost-estimation--finops)
  - [6.1. Key Cost Drivers & Consumption Variables](#61-key-cost-drivers--consumption-variables)
  - [6.2. Monthly Operational Cost Breakdown](#62-monthly-operational-cost-breakdown)
  - [6.3. FinOps Governance & Cost Guardrails](#63-finops-governance--cost-guardrails)
- [7. Deployment & Delivery Plan](#7-deployment--delivery-plan)
  - [7.1. Environments & Infrastructure as Code (IaC)](#71-environments--infrastructure-as-code-iac)
  - [7.2. State Management & Configuration Versioning](#72-state-management--configuration-versioning)
  - [7.3. Phased Delivery Milestones, Dependencies & Deliverables](#73-phased-delivery-milestones-dependencies--deliverables)
- [8. Assumptions, Constraints, Risk & Mitigations](#8-assumptions-constraints-risk--mitigations)
  - [8.1. Critical Technical & Operational Assumptions](#81-critical-technical--operational-assumptions)
  - [8.2. MVP 1 Implementation Constraints](#82-mvp-1-implementation-constraints)
  - [8.3. Key Risks & Concrete Mitigation Strategies](#83-key-risks--concrete-mitigation-strategies)
- [9. Quality Evaluation & UAT Framework](#9-quality-evaluation--uat-framework)
  - [9.1. Quantitative Performance Metrics](#91-quantitative-performance-metrics)
  - [9.2. Evaluation Dataset Curation](#92-evaluation-dataset-curation)
  - [9.3. Acceptance Thresholds & Verification Harness](#93-acceptance-thresholds--verification-harness)
- [10. Assumptions / Open Questions](#10-assumptions--open-questions)
  - [10.1. Outstanding Design Decisions, Ownership & Deadlines](#101-outstanding-design-decisions-ownership--deadlines)

---

## 1. Executive Summary & Scope Boundaries

### 1.1. Business Overview & Context
Enterprise HR and IT helpdesks face severe operational bottlenecks and escalating support expenditures. Currently, employees and people managers must navigate fragmented, siloed enterprise systems—navigating **WorkWeek (HCM)** for employee profiles, contact details, and leave submissions, **ServiceImmediately (ITSM/HRSD)** for IT incidents and equipment requests, and static intranets/PDFs for policy handbooks.

```mermaid
flowchart TD
    subgraph CurrentPainPoints["🚨 Current State Challenges"]
        P1["40%+ Routine Ticket Volume on Tier-1 Desk"]
        P2["Manual Context-Switching across WorkWeek, ServiceImmediately & PDFs"]
        P3["Multi-Day Delays in Cross-System HR Workflows (3–7 Days)"]
        P4["Risk of Policy Hallucinations & SPII Exposure"]
    end

    subgraph FutureTargetState["🎯 HRED MVP 1 Solution Objectives"]
        O1["Deflect >= 40% Tier-1 Routine Inquiries in 6 Months"]
        O2["Conversational Self-Service for Profile, Leave & Tickets"]
        O3["Cross-System Automated Orchestration in < 10 Seconds"]
        O4["100% Policy Grounding with Clickable Citations & Zero Leaks"]
    end

    CurrentPainPoints ==>|"HRED Agentic Transformation"| FutureTargetState
```

#### Key Pain Points:
1. **High Routine Ticket Volume**: Over 40% of tier-1 HR and IT helpdesk tickets consist of repetitive policy clarifications (e.g., bereavement leave entitlement, home office monitor eligibility, expense rules, medical certificate timelines) and basic status checks.
2. **Context Switching & Friction**: Routine employee self-service actions (such as checking PTO balances, submitting time off, or requesting hardware) require navigating complex backend enterprise UIs.
3. **Cross-System Disconnection**: Multi-step workflows (e.g., verifying remote work eligibility in policy $\rightarrow$ verifying location in WorkWeek $\rightarrow$ creating an equipment order in ServiceImmediately) are executed entirely through manual human coordination.
4. **Compliance & AI Risks**: Unvetted conversational systems risk generating inaccurate policy interpretations (hallucinations), exposing Sensitive Personally Identifiable Information (SPII), or executing unauthorized actions without verified origin attribution.

#### High-Level Business Goals:
* **Deflect Tier 1 HR Inquiries**: Reduce routine HR and IT helpdesk ticket volume by at least **40% within the first six months**.
* **Streamline HR Transactions**: Enable employees to perform core self-service actions (leave submission, incident ticket updates) conversationally without navigating complex backend UIs.
* **Validate Cross-System Orchestration**: Demonstrate the capability to chain actions across HR policies, WorkWeek, and ServiceImmediately to fulfill complex user intents with **100% transaction integrity**.
* **Ensure Enterprise AI Governance**: Maintain 100% visibility over deployment state, versioning, authorized tool access limits, and dynamic interaction safeguards.

---

### 1.2. Scope Boundaries

The following matrix establishes explicit architectural and functional boundaries for the **MVP 1 Baseline** versus **Future Production Releases**, providing an executive overview of the solution's scope across all system domains:

| Solution Domain / Layer | In-Scope for MVP 1 Baseline | Out-of-Scope for MVP 1 (Future Releases) | Rationale & MVP 1 Boundary Notes |
| :--- | :--- | :--- | :--- |
| **1. Conversational Client & Ingress** | • Standalone Web Chat UI (React / Vite + Vertex AI Chat Widget)<br>• RESTful API Gateway for test automation & evaluation harness | • Enterprise Slack App & Google Chat native bots<br>• Mobile native SDKs (iOS/Android)<br>• Voice / Telephony telephony gateways | Focuses on fast, validated web-based UAT and automated API evaluations before expanding to enterprise messaging clients. |
| **2. Policy Knowledge & Grounding** | • 100% Grounded Policy Q&A with clickable section/URL citations<br>• Curated Core Domains: Bereavement, Remote Work, Expenses, Relocation, Code of Conduct<br>• Strict Domain Containment (rejects non-HR topics) | • Multi-lingual neural translation (English only for MVP 1)<br>• Automated real-time CMS crawler sync (uses deployment release ingestion) | Guarantees zero policy hallucinations on approved static documents during initial prototype validation. |
| **3. HCM Self-Service (WorkWeek)** | • Read: Employee Profile (ID, Name, Email, Role, Dept, Manager, Hire Date)<br>• Read: Accrued, Used & Remaining leave balances (Vacation, Sick)<br>• Write: Personal contact info updates (Address, Phone)<br>• Write: Leave request submission with balance & chronological guardrails | • Compensation adjustments & salary changes<br>• Direct deposit bank account routing<br>• Performance reviews, goal setting & talent appraisals | Confines self-service mutations to non-payroll, low-risk personal contact updates and standard leave transactions. |
| **4. ITSM / Helpdesk (ServiceImmediately)** | • Read: Incident ticket details, status, priority, and comment timeline<br>• Write: Create support incident tickets (Categories, Priorities 1–4)<br>• Write: Post activity comments and update ticket status (Resolved/Closed)<br>• Guardrails: Duplicate ticket mitigation & state transition enforcement | • Advanced ITIL Problem & Change Management workflows<br>• Automated hardware asset discovery & remote device management | Automates routine Tier-1 incident management while deferring complex enterprise ITIL workflows. |
| **5. Cross-System Orchestration** | • Equipment Procurement (UC-2.1: Policy $\rightarrow$ WorkWeek $\rightarrow$ ServiceImmediately)<br>• Medical Leave & Email Access Routing (UC-2.2)<br>• Office Relocation & Facilities Badge (UC-2.3)<br>• Saga Backward-Compensating Rollback on partial failure | • Multi-party approval chains (> 2 managerial tiers)<br>• Automated external third-party vendor fulfillment | Validates foundational 3-system chaining and rollback resiliency for prototype evaluation. |
| **6. AI Safety, Privacy & Governance** | • Real-time Cloud DLP Streaming SPII tokenization (<15ms) for NRIC, SSN, phone, address<br>• Vertex AI Model Armor (Prompt injection & jailbreak prevention)<br>• Caller-isolated RBAC & request origin verification (`X-Automation-Origin`)<br>• 100% Immutable audit logging with origin tagging | • Enterprise SSO / Okta / Azure AD SAML federation (uses functional test credentials)<br>• Automated employee deprovisioning on termination | Enforces zero-trust data protection and auditability without dependency on external enterprise IAM federation. |
| **7. Architecture & Tenancy** | • Single-Tenant deployment on Google Cloud Platform<br>• Vertex AI Agent Builder (Reasoning Engine)<br>• Dedicated Cloud Run Integration Microservice (FastAPI Mock) | • Multi-tenant organizational partitioning<br>• Multi-region active-active database replication (Cloud Spanner global cluster) | Optimized for rapid single-tenant prototype validation with production-forward extensible architecture. |

---

### 1.3. Target Architecture Overview

The target architecture for MVP 1 is built on **Google Cloud Vertex AI Agent Builder (Reasoning Engine)** as the fully managed agent runtime, protected by an **Inline Cloud DLP & Model Armor Safety Perimeter** and fronted by a **React/Vite Web Chat UI**. Backend integrations are fulfilled via a dedicated **FastAPI Integration Microservice** hosted on Cloud Run, simulating WorkWeek (HCM) and ServiceImmediately (ITSM) with strict operational guardrails and Saga-pattern compensation handlers.

```mermaid
flowchart TB
    subgraph ClientTier ["1. Client Interaction Tier"]
        WebUI["Web Chat Interface\n(React / Vite + Vertex AI Chat Widget)"]
        TestHarness["Automated Evaluation Harness\n(Pytest + LLM Judge)"]
    end

    subgraph IngressSafetyTier ["2. Ingress, Security & Dynamic Safeguards"]
        CloudArmor["Cloud Armor WAF\n(Rate Limiting / DDoS Protection)"]
        APIGateway["Cloud Endpoints / Apigee Gateway\n(Token Scoping & Origin Verification)"]
        DLPProxy["Cloud DLP Streaming Proxy\n(Real-Time SPII Tokenization <15ms)"]
        ModelArmor["Vertex AI Model Armor\n(Prompt Injection & Jailbreak Filter)"]
    end

    subgraph AgentOrchestrationTier ["3. Agent Orchestration Tier (Vertex AI Reasoning Engine)"]
        Supervisor["HR Enterprise Agent\n(Gemini 2.5 Flash / Pro Reasoning Engine)"]
        SessionStore[("Managed Session Memory\n& Context Graph")]
        SagaManager["Cross-System Saga Coordinator\n(Compensation & Rollback)"]
    end

    subgraph GroundingFabric ["4. Dual Hybrid Grounding Fabric"]
        VertexSearch[("Vertex AI Search\n(Unstructured Handbook PDFs)")]
        OKFStore[("Open Knowledge Format (OKF)\n(Curated Markdown & Thresholds)")]
        GroundingGuard["Deterministic Grounding &\nCitation Formatter"]
    end

    subgraph IntegrationTier ["5. Backend Integration Microservice (Cloud Run)"]
        MockService["HR Integration Adapter Service (FastAPI)"]
        WorkWeekAdapter["WorkWeek HCM Connector\n(Profile, Balances, Leave)"]
        SNAdapter["ServiceImmediately Connector\n(Tickets, Comments, Status)"]
        GuardrailValidator["Operation Guardrail Engine\n(Balance, Temporal, Status Checks)"]
    end

    subgraph TelemetryTier ["6. Audit, Logging & FinOps Telemetry"]
        CloudLogging[("Cloud Logging\n(Immutable Audit Logs)")]
        BigQueryTelemetry[("BigQuery\n(Quality, SLAs & FinOps Analytics)")]
    end

    ClientTier --> CloudArmor --> APIGateway --> DLPProxy --> ModelArmor --> Supervisor
    Supervisor <--> SessionStore
    Supervisor <--> SagaManager
    Supervisor <--> GroundingGuard
    GroundingGuard <--> VertexSearch
    GroundingGuard <--> OKFStore
    
    Supervisor --> MockService
    MockService --> GuardrailValidator
    GuardrailValidator --> WorkWeekAdapter
    GuardrailValidator --> SNAdapter
    
    APIGateway --> CloudLogging
    Supervisor --> BigQueryTelemetry
    MockService --> CloudLogging
```

---

### 1.4. Alternatives Considered

| Architectural Dimension | Selected Technical Approach | Evaluated Alternatives | Rationale & Trade-Off Analysis |
| :--- | :--- | :--- | :--- |
| **Agent Orchestration Platform** | **Vertex AI Agent Builder (Reasoning Engine)** | Self-hosted GKE with LangGraph; Custom Python container on Cloud Run | *Rationale*: Fully managed Google Cloud native runtime with built-in tool binding, auto-managed session memory, enterprise SLA, and zero infrastructure maintenance overhead for MVP 1. |
| **Knowledge Grounding Architecture** | **Dual Hybrid Grounding (Vertex AI Search + Curated OKF)** | Pure Semantic Vector Search (RAG-only); Pure Static Keyword Search | *Rationale*: RAG alone is vulnerable to numerical/threshold drift (e.g. 14-day sick leave limits, gift card prohibitions). Dual grounding guarantees 100% citation accuracy for codified rules while retaining semantic discovery over broad handbook PDFs. |
| **Safety & SPII Redaction** | **Cloud DLP Streaming Proxy + Vertex AI Model Armor** | Post-processing regex scrubber; In-prompt system instructions only | *Rationale*: Regex cannot reliably capture international identity numbers (NRIC, SSN, IBAN) or address structures. Cloud DLP provides sub-15ms automated tokenization before LLM invocation, satisfying the < 300ms safety latency budget. |
| **Cross-System Consistency** | **Saga Pattern with Backward Compensation & Escalation** | Distributed Two-Phase Commit (2PC); Best-Effort Manual Follow-Up | *Rationale*: 2PC is impossible across third-party SaaS REST APIs. The Saga pattern executes compensating rollbacks (e.g. cancelling pending leave if ticket creation fails) and creates escalated support tickets for human follow-up. |
| **Backend Integration Environment** | **Dedicated Cloud Run Mock Service (FastAPI)** | Direct Live Production APIs; In-memory dummy stubs | *Rationale*: Allows deterministic simulation of WorkWeek and ServiceImmediately with configurable network latency, error injection (500/503), and state persistence, completely isolated from live enterprise risk during MVP 1. |

---

## 2. Production-Ready Future State Design

While MVP 1 delivers a secure single-tenant prototype with functional test credentials, the architecture is designed for direct forward-compatibility with enterprise production scale:

```mermaid
flowchart LR
    subgraph MVP1State["MVP 1: Foundation Baseline"]
        M1["Single-Tenant Cloud Run"]
        M2["Functional Test Credentials"]
        M3["Standalone Web Chat UI"]
        M4["Mock Integration Microservice"]
    end

    subgraph FutureState["Production Target State (Phase 2 & Beyond)"]
        F1["Multi-Tenant Isolation per Subsidiary / Entity"]
        F2["Enterprise SSO (Okta / Cloud Identity OIDC + SAML)"]
        F3["Omnichannel Ingress (Google Chat, Slack Enterprise, Mobile)"]
        F4["Live Enterprise SaaS Connectors (Workday REST & ServiceNow Table API)"]
        F5["Multi-Lingual Neural Translation (12+ Languages)"]
        F6["Deactivated Employee Deprovisioning & Payroll Data Pipelines"]
    end

    MVP1State ==>|"Extensible Modular Architecture"| FutureState
```

1. **Identity & Access Management (IAM) Evolution**:
   - Transition from functional test tokens to **OAuth 2.0 User-Delegated Token Exchange** (RFC 8693) via Okta/Google Cloud Identity, passing scoped JSON Web Tokens (JWT) directly to Workday and ServiceNow.
2. **Omnichannel Messaging Gateways**:
   - Connect the Vertex AI Reasoning Engine to **Google Workspace (Google Chat Webhook)** and **Slack Enterprise Grid** via Pub/Sub event dispatchers.
3. **Live Enterprise Adapters**:
   - Replace the Cloud Run Mock Service with production-grade connectors utilizing **Workday Web Services (WWS v40.0)** and **ServiceNow Scripted REST APIs** protected by Cloud Key Management Service (KMS) credentials.
4. **Global Multi-Region Scaling**:
   - Replicate the Vertex AI Agent Builder and Cloud Run instances across `us-central1`, `europe-west1`, and `asia-southeast1` backed by Cloud Spanner for global ACID consistency.

---

## 3. System Flows, Sequence Diagrams & Agent Design

### 3.1. End-to-End Data Flow & Agent Design

The Agentic System operates through a deterministic 4-stage execution loop:

```mermaid
flowchart TD
    Inbound["1. User Inbound Prompt"] --> DLP["2. Cloud DLP Streaming Inspection\n(Tokenize SPII: SSN, Phone, NRIC)"]
    DLP --> Armor["3. Vertex AI Model Armor\n(Block Jailbreak, Prompt Injection, Off-Topic)"]
    Armor --> Reasoning["4. Vertex AI Reasoning Engine\n(Intent Classification & Tool Selection)"]
    
    Reasoning --> PolicyBranch{"Intent Category"}
    PolicyBranch -->|"Policy Q&A (UC-1.1)"| DualGrounding["Dual Grounding Engine\n(Query Vertex Search & OKF)"]
    PolicyBranch -->|"HR Self-Service (UC-1.2)"| WWTool["WorkWeek Adapter Tool\n(Validate & Execute Leave/Profile)"]
    PolicyBranch -->|"IT Incident (UC-1.3)"| SNTool["ServiceImmediately Adapter Tool\n(Validate & Execute Ticket)"]
    PolicyBranch -->|"Cross-System (UC-2.x)"| SagaTool["Saga Cross-System Coordinator\n(Chain Actions & Compensate on Failure)"]
    
    DualGrounding --> OutputSafety["5. Output Safety & Grounding Verification\n(Verify Citation Integrity & Toxic Content Filter)"]
    WWTool --> OutputSafety
    SNTool --> OutputSafety
    SagaTool --> OutputSafety
    
    OutputSafety --> AuditEmit["6. Immutable Audit Log Emission\n(Cloud Logging & BigQuery)"]
    AuditEmit --> Outbound["7. Deliver Formatted Response to User UI"]
```

---

### 3.2. Pre-Processing, Safety Scanning & Optimization

1. **Input Pre-Processing (< 120ms)**:
   - User input is intercepted by the **Cloud DLP Streaming Proxy**, de-identifying NRICs, SSNs, phone numbers, and physical addresses into typed surrogate tokens (`[REDACTED_NRIC]`, `[REDACTED_CONTACT_INFO]`).
   - **Vertex AI Model Armor** scans for prompt injections, system prompt leak attempts, and jailbreak templates. If detected, execution halts immediately with a safe refusal.
2. **Context Optimization**:
   - The user's active session context is fetched from the managed Vertex AI session store. Dynamic profile and leave data are fetched in real time directly from WorkWeek and never cached in static prompt context (`FR-3.4`).
3. **Output Post-Processing (< 100ms)**:
   - Output text is verified against the **Grounding Guardrail** to assert that all policy assertions contain valid clickable URL citations and contain zero hallucinations.

---

### 3.3. Path Sequence Diagrams for Single-Domain Use Cases

#### Path 1: Policy Q&A with Clickable Citations (UC-1.1)
* **Trigger**: *"What is the company's bereavement leave policy?"*

```mermaid
sequenceDiagram
    autonumber
    actor Employee as Employee
    participant UI as Web Chat UI
    participant DLP as Cloud DLP & Model Armor
    participant Agent as Vertex AI Reasoning Engine
    participant KB as Dual Grounding (OKF + Vertex Search)
    participant Audit as Cloud Logging / BigQuery

    Employee->>UI: "What is the company's bereavement leave policy?"
    UI->>DLP: Forward raw payload
    DLP->>DLP: Verify safe input & tokenize any PII (<15ms)
    DLP->>Agent: Pass sanitized prompt + User Context (EMP-1001)
    
    Agent->>KB: search_policy_knowledge(topic='bereavement_leave')
    KB-->>Agent: Return grounded excerpt (Sec 04.2) + Citation metadata
    
    Agent->>Agent: Synthesize answer with clickable URL/DeepLink citation
    Agent->>DLP: Validate output payload (Zero hallucination & no toxic leaks)
    Agent->>Audit: Emit structured audit record (Action: POLICY_QUERY, Grounded: TRUE)
    Agent-->>UI: "Under Section 04.2 (Bereavement Leave), full-time employees are entitled to up to 5 consecutive days of paid leave... [View Policy Section 04.2](https://hr.corp.internal/policies/04.2-bereavement)"
    UI-->>Employee: Display response with clickable badge
```

#### Path 2: WorkWeek Leave Balance & Submission (UC-1.2)
* **Trigger**: *"Please submit a time-off request for this coming Thursday and Friday."*

```mermaid
sequenceDiagram
    autonumber
    actor Employee as Employee
    participant UI as Web Chat UI
    participant Agent as Vertex AI Reasoning Engine
    participant Guard as Operation Guardrail Validator
    participant WW as WorkWeek Connector (HCM)
    participant Audit as Cloud Logging

    Employee->>UI: "Submit time-off request for Thursday (2026-08-27) to Friday (2026-08-28), Vacation."
    UI->>Agent: Sanitize & pass request (Employee ID: EMP-1001)
    
    Agent->>WW: get_time_off_balance(employee_id='EMP-1001', plan='Vacation')
    WW-->>Agent: Accrued: 18.0 days, Used: 4.0 days, Remaining: 14.0 days
    
    Agent->>Guard: validate_leave_request(start='2026-08-27', end='2026-08-28', days=2, balance=14.0)
    Guard-->>Agent: Validation PASSED (Start <= End, Not in past, Days <= Remaining)
    
    Agent->>WW: submit_leave_request(emp_id='EMP-1001', type='Vacation', days=2)
    WW-->>Agent: Transaction Success (Request ID: WW-LV-90421)
    
    Agent->>Audit: Log transaction with automation origin indicator
    Agent-->>UI: "Your 2-day Vacation request for Aug 27–28 has been submitted in WorkWeek (Ref: WW-LV-90421). Remaining balance: 12.0 days."
    UI-->>Employee: Display confirmation card
```

#### Path 3: ServiceImmediately Incident Management (UC-1.3)
* **Trigger**: *"Create an IT ticket because my VPN connection keeps dropping."*

```mermaid
sequenceDiagram
    autonumber
    actor Employee as Employee
    participant UI as Web Chat UI
    participant Agent as Vertex AI Reasoning Engine
    participant Guard as Operation Guardrail Validator
    participant SN as ServiceImmediately Connector (ITSM)
    participant Audit as Cloud Logging

    Employee->>UI: "Create an IT ticket because my VPN connection keeps dropping."
    UI->>Agent: Forward sanitized prompt
    
    Agent->>Guard: check_duplicate_tickets(emp_id='EMP-1001', category='IT_NETWORK', window_minutes=30)
    Guard-->>Agent: No duplicate found
    
    Agent->>Guard: verify_priority(category='IT_NETWORK', desc='VPN dropping')
    Guard-->>Agent: Priority assigned: '3 - Moderate' (matches non-outage criteria)
    
    Agent->>SN: create_incident_ticket(emp_id='EMP-1001', cat='IT_NETWORK', prio='3 - Moderate', desc='VPN connection dropping intermittently')
    SN-->>Agent: Created Ticket [INC123456], Status: 'New'
    
    Agent->>Audit: Emit audit record (Origin: AUTOMATION_AGENT, Ticket: INC123456)
    Agent-->>UI: "Support Incident Ticket [INC123456] has been created in ServiceImmediately with Priority '3 - Moderate'. An IT specialist will investigate."
    UI-->>Employee: Render ticket confirmation badge
```

---

### 3.4. Path Sequence Diagrams for Cross-System Orchestration

#### Path 4: Equipment Procurement (UC-2.1)
* **Trigger**: *"I just read the remote work policy and saw I'm eligible for a home office monitor. Can you verify my remote status and order one for me?"*

```mermaid
sequenceDiagram
    autonumber
    actor Employee as Employee
    participant Agent as Vertex AI Reasoning Engine
    participant KB as Policy Knowledge Base
    participant WW as WorkWeek Connector (HCM)
    participant SN as ServiceImmediately Connector (ITSM)
    participant Saga as Saga Compensation Manager
    participant Audit as Cloud Logging

    Employee->>Agent: "Verify my remote eligibility and order a home office monitor."
    
    Agent->>KB: search_policy_knowledge(topic='remote_work_hardware_allowance')
    KB-->>Agent: Section 08.3: Remote workers eligible for 1x 27" monitor (Allowance: $350)
    
    Agent->>WW: get_employee_profile(employee_id='EMP-1001')
    WW-->>Agent: Status: 'REMOTE_FULL_TIME', Address: '123 Tech Park Way, Austin, TX'
    
    Agent->>SN: create_hardware_request(emp_id='EMP-1001', item='27in_Monitor', shipping_address='123 Tech Park Way, Austin, TX', ref_policy='Sec 08.3')
    
    alt ServiceImmediately Hardware Order Succeeds
        SN-->>Agent: Hardware Request Ticket [REQ78910] Created (Status: Approved)
        Agent->>Audit: Log Cross-System Transaction [UC-2.1 Success, Origin: AUTOMATION]
        Agent-->>Employee: "Verified under Section 08.3 that you are eligible for home office hardware. Verified remote status in WorkWeek. ServiceImmediately Hardware Request [REQ78910] has been created for shipping to your registered address."
    else Downstream Failure / Inventory Allocation Lock (HTTP 500 / 503)
        SN-->>Agent: HTTP 500 Backend Failure / Hardware Catalog Outage
        Agent->>Saga: Trigger Compensating Workflow
        Saga->>SN: create_escalated_incident(priority='3 - Moderate', desc='Hardware catalog failure during remote monitor order for EMP-1001')
        SN-->>Saga: Fallback Escalation Ticket [INC88120] Created
        Agent->>Audit: Log Cross-System Rollback [UC-2.1 Fallback Escalated]
        Agent-->>Employee: "We verified your eligibility for a 27\" monitor under Section 08.3, but the automated ordering system is temporarily unavailable. IT Support Incident [INC88120] has been opened for the procurement team to fulfill your order manually."
    end
```

#### Path 5: Medical Leave with Access Delegation (UC-2.2)
* **Trigger**: *"I need to take short-term medical leave starting next Monday. What is the process, and can you set it up for me?"*

```mermaid
sequenceDiagram
    autonumber
    actor Employee as Employee
    participant Agent as Vertex AI Reasoning Engine
    participant KB as Policy Knowledge Base
    participant WW as WorkWeek Connector (HCM)
    participant SN as ServiceImmediately Connector (ITSM)
    participant Saga as Saga Compensation Manager

    Employee->>Agent: "Set up short-term medical leave starting next Monday (2026-08-31)."
    
    Agent->>KB: search_policy_knowledge(topic='medical_leave_procedure')
    KB-->>Agent: Section 19.2: Outpatient limit 14d, submit Leave of Absence + Route email
    
    Agent->>WW: submit_leave_request(emp_id='EMP-1001', type='Sick_LOA', start='2026-08-31', end='2026-09-04')
    WW-->>Agent: Leave Submitted (Ref: WW-MED-5501)
    
    Agent->>SN: create_incident_ticket(cat='ACCESS_ROUTING', desc='Route email access to Manager MGR-2001 during Medical Leave WW-MED-5501')
    
    alt ServiceImmediately Succeeds
        SN-->>Agent: Ticket [INC99124] Created
        Agent-->>Employee: "Medical leave booked in WorkWeek (Ref: WW-MED-5501). ServiceImmediately ticket [INC99124] opened to route email access to your manager. Remember to upload your MC within 48h."
    else ServiceImmediately Fails (500 Error)
        SN-->>Agent: HTTP 500 Internal Error
        Agent->>Saga: Trigger Compensating Rollback
        Saga->>WW: cancel_leave_request(ref='WW-MED-5501')
        WW-->>Saga: Leave Cancelled
        Saga->>SN: create_escalated_incident(priority='2 - High', desc='Automated rollback occurred. Manual medical leave setup required for EMP-1001')
        Agent-->>Employee: "Service is temporarily unavailable while configuring email routing. Your pending leave has been rolled back to maintain consistency. Support Ticket [INC99999] created for manual PeopleOps setup."
    end
```

#### Path 6: Relocation Allowance & Facilities Badge (UC-2.3)
* **Trigger**: *"I'm transferring to the London office next month. Can you tell me the relocation allowance, update my record, and get my building access sorted?"*

```mermaid
sequenceDiagram
    autonumber
    actor Employee as Employee
    participant Agent as Vertex AI Reasoning Engine
    participant KB as Policy Knowledge Base
    participant WW as WorkWeek Connector (HCM)
    participant SN as ServiceImmediately Connector (ITSM)
    participant Saga as Saga Compensation Manager
    participant Audit as Cloud Logging

    Employee->>Agent: "Relocation to London: quote allowance, update address, sort building access."
    
    Agent->>KB: search_policy_knowledge(topic='international_relocation_allowance')
    KB-->>Agent: Section 14.1: Tier 2 London Relocation Allowance = £5,000 + 30 days temp housing
    
    Agent->>WW: update_contact_info(emp_id='EMP-1001', new_office='London - 6 Pancras Sq', country='UK')
    WW-->>Agent: WorkWeek Record Updated (Old Office: 'Austin HQ')
    
    Agent->>SN: create_facilities_ticket(cat='BADGE_ACCESS', office='London_Pancras', start_date='2026-09-25')
    
    alt Facilities Badge Creation Succeeds
        SN-->>Agent: Facilities Ticket [FAC44021] Created
        Agent->>Audit: Log Cross-System Transaction [UC-2.3 Success]
        Agent-->>Employee: "According to Section 14.1 (International Relocation), your Tier 2 allowance is £5,000. Your WorkWeek office assignment has been updated to London. Facilities Badge Ticket [FAC44021] has been created for your first day access."
    else Facilities Badge Creation Fails (HTTP 500 / 503)
        SN-->>Agent: HTTP 500 Facilities API Failure
        Agent->>Saga: Trigger Compensating Rollback
        Saga->>WW: update_contact_info(emp_id='EMP-1001', new_office='Austin HQ', country='USA')
        WW-->>Saga: Office Reverted to Austin HQ
        Saga->>SN: create_escalated_incident(priority='2 - High', desc='Relocation workflow failed at facilities badge stage for EMP-1001. Office assignment reverted.')
        SN-->>Saga: Support Ticket [INC77201] Created
        Agent->>Audit: Log Cross-System Rollback [UC-2.3 WorkWeek Reverted]
        Agent-->>Employee: "Your Tier 2 relocation allowance is £5,000 under Section 14.1. However, the facilities ticketing service encountered an error while configuring badge access. To maintain data consistency, your office location update was rolled back, and Support Ticket [INC77201] has been created for manual HR relocation coordination."
    end
```

---

## 4. Security, Governance & Identity

```mermaid
flowchart TD
    subgraph SecurityPerimeter ["Zero-Trust Security Perimeter"]
        direction TB
        AuthN["1. Functional Test Credential Auth\n(Scoped Bearer Tokens per Service)"]
        RBAC["2. Role-Based Access Control (RBAC)\n(Caller-only Data Scoping & Isolation)"]
        DLP["3. Streaming Cloud DLP Inspection\n(NRIC, SSN, Phone, Medical SPII Redaction)"]
        Armor["4. Vertex AI Model Armor\n(Input/Output Jailbreak & Toxicity Guard)"]
        Audit["5. Cryptographic Immutable Audit Log\n(Origin Tagged: AUTOMATION vs MANUAL)"]
    end
```

### 4.1. Authentication Boundaries & Request Origin Verification (FR-1.2, FR-3.1)
* **Functional Test Credentials**: For MVP 1, calls between the Vertex AI Reasoning Engine and the Cloud Run Integration Microservice pass an authenticated HTTP Header:
  `X-Automation-Origin: HR_AGENT_ORCHESTRATOR_V1`
  `X-Caller-Employee-Id: EMP-1001`
  `Authorization: Bearer <GCP_OIDC_IDENTITY_TOKEN>`
* **Audit Lineage**: All backend transactions logged in ServiceImmediately and WorkWeek explicitly record whether the transaction was initiated via conversational automation or manual administrator override.

### 4.2. Network Isolation & Service Perimeters
* **VPC Service Controls (VPC-SC)**: The Google Cloud Project hosting Vertex AI Agent Builder, Cloud Storage, and Cloud Run is enclosed within a secure VPC Service Perimeter.
* **Private Service Connect (PSC)**: Traffic between Cloud Run microservices and Vertex AI endpoints traverses Google's private backbone without exposing endpoints to the public internet.

### 4.3. Role-Based Access Control (RBAC) Matrix & Tool Scoping

To maintain zero-trust compliance, access to tool endpoints is strictly governed by the caller's organizational role. The agent enforces least-privilege scoping at both the reasoning prompt layer and the backend API Gateway layer:

| User Role | Policy Search (`policy_search`) | WorkWeek Profile & Leave (`get_profile`, `get_balances`, `submit_leave`) | WorkWeek Contact (`update_contact`) | ServiceImmediately Incident (`create_incident`, `get_ticket`) | ServiceImmediately Status & Assign (`update_ticket_status`) | Facilities & Hardware Requests (`create_hardware`, `create_facilities`) | Scope Constraints & Rules Enforced |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Standard Employee (`ROLE_EMPLOYEE`)** | ✅ Full Access | ✅ Self-Only (`caller_id == target_id`) | ✅ Self-Only | ✅ Self-Only (Read/Create) | ❌ Denied | ✅ Self-Only (Policy-backed) | Restricted strictly to own employee record and tickets. Cross-user queries trigger `403 Forbidden`. |
| **People Manager (`ROLE_MANAGER`)** | ✅ Full Access | ✅ Self + Direct Reports | ✅ Self-Only | ✅ Self + Direct Reports | ❌ Denied | ✅ Self + Direct Reports | Can read leave balances and profile status of direct reports; cannot alter report's personal contact info. |
| **IT Support Specialist (`ROLE_IT_SUPPORT`)** | ✅ Full Access | ❌ Denied (No HR data) | ❌ Denied | ✅ Global Tickets (Read/Write) | ✅ Global Status Updates | ✅ Hardware Ticket Routing | Can update and transition any IT incident ticket; strictly segregated from HCM leave and payroll databases. |
| **HR Operations Admin (`ROLE_HR_ADMIN`)** | ✅ Full Access | ✅ Global HCM (Read/Write) | ✅ Global (With Audit) | ✅ Global HRSD Tickets | ✅ HR Ticket Status Updates | ✅ Global Facilities Requests | Full administrative capability; every mutation emits an immutable `ORIGIN: ADMIN_OVERRIDE` audit event. |

---

### 4.4. Sensitive Data Handling & PII Management (Cloud DLP)

* **Pre-Execution Streaming Inspection**: Inbound user queries pass through the **Cloud DLP Streaming API** (`v2.projects.locations.content.deidentify`) within a $< 15\text{ ms}$ processing window.
* **Automated Redaction & Tokenization Rules**:
  - **Singapore NRIC / FIN**: Scanned via `SINGAPORE_NATIONAL_REGISTRATION_ID_NUMBER` $\rightarrow$ `[REDACTED_NRIC]`
  - **US Social Security Number (SSN)**: Scanned via `US_SOCIAL_SECURITY_NUMBER` $\rightarrow$ `[REDACTED_SSN]`
  - **International Phone & Address**: Scanned via `PHONE_NUMBER` & `STREET_ADDRESS` $\rightarrow$ `[REDACTED_CONTACT_INFO]`
  - **Medical Conditions & Diagnoses**: Scanned via `CUSTOM_HEALTH_INFO_DETECTOR` $\rightarrow$ `[REDACTED_HEALTH_INFO]`
* **Session Storage Policy**: Session memory within Vertex AI Agent Builder persists only tokenized surrogate values. Dynamic employee PTO balances and profile data are fetched in real time on every turn and are never cached in long-term memory (`FR-3.4`).

---

### 4.5. Mock Identity Translation & Anti-Spoofing at API Gateway

```mermaid
flowchart TD
    Client["Client Web Chat UI\n(Sends Authorization: Bearer JWT)"] --> APIGW["Cloud Endpoints / Apigee Gateway"]
    
    subgraph GatewayAuth["Gateway Ingress Validation Pipeline"]
        V1["1. Validate OIDC Token Signature & Expiry"]
        V2["2. Extract Subject Claim ('sub': user@corp.internal)"]
        V3["3. Query Identity Translation Cache (Email -> EMP ID + Role)"]
        V4["4. Strip Inbound 'X-Caller-*' Headers (Prevent Client Header Injection)"]
        V5["5. Inject Cryptographically Signed Headers:\n- 'X-Caller-Employee-Id: EMP-1001'\n- 'X-Caller-Role: ROLE_EMPLOYEE'\n- 'X-Automation-Origin: HR_AGENT_ORCHESTRATOR_V1'"]
    end
    
    APIGW --> V1 --> V2 --> V3 --> V4 --> V5
    V5 --> CloudRun["Cloud Run Mock Microservice / Vertex AI Agent"]
    
    CloudRun --> AssertCheck{"Assert: Header Caller ID == Target Resource ID?"}
    AssertCheck -->|"Yes"| Exec["Execute Tool Handler"]
    AssertCheck -->|"No"| Deny["Return 403 Forbidden & Log Security Alert"]
```

* **Anti-Spoofing Protection**: The API Gateway drops any incoming `X-Caller-Employee-Id` or `X-Caller-Role` headers sent directly by the browser to eliminate header injection attacks. The headers are injected exclusively by the API Gateway after validating the authentic OIDC JWT token.
* **Mock Translation Table**:
  - `john.doe@corp.internal` $\rightarrow$ `EMP-1001` (`ROLE_EMPLOYEE`)
  - `sarah.manager@corp.internal` $\rightarrow$ `MGR-2001` (`ROLE_MANAGER`)
  - `alex.it@corp.internal` $\rightarrow$ `IT-3001` (`ROLE_IT_SUPPORT`)
  - `elena.hr@corp.internal` $\rightarrow$ `HR-4001` (`ROLE_HR_ADMIN`)

---

### 4.6. GDPR Compliance, Right to be Forgotten & Embedding/Log Lifecycle

1. **Right to be Forgotten (GDPR Article 17)**:
   - When an employee departs or requests personal data erasure, an automated de-identification worker executes:
     1. Deletes active session history and conversation memory in Vertex AI Agent Builder: `DELETE /v1/projects/.../locations/.../sessions/{employee_id}`.
     2. Anonymizes user identifiers in BigQuery telemetry logs by hashing `employee_id` with a salt destroyed upon deprovisioning.
     3. Removes employee-specific vectorized metadata or custom document caches from Vertex AI Search within 24 hours.
2. **Audit Log Retention & Partition Expiration**:
   - **Cloud Logging**: Retained for 30 days in standard regional log buckets.
   - **BigQuery Audit & Telemetry Dataset**: Configured with automated **90-day partition expiration** (`partition_expiration_days = 90`). After 90 days, raw interaction partitions are permanently purged.
3. **Zero Dynamic Data Embeddings**:
   - The knowledge vector store contains *only* static enterprise policy handbook text. Employee personal records (PTO balances, tickets, phone numbers) are never vectorized or embedded into vector indices, ensuring no personal data resides in vector embeddings.

---

## 5. Integration Details & Error Handling

### 5.1. Third-Party Tool Integration Methodology & Explicit JSON Schemas

#### WorkWeek HCM Connector Specification & Schemas

##### 1. `get_employee_profile` (`GET /workweek/api/v1/employees/{employee_id}`)
* **Request Headers**: `Authorization: Bearer <TOKEN>`, `X-Caller-Employee-Id: EMP-1001`
* **Response Schema (200 OK)**:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "EmployeeProfileResponse",
  "type": "object",
  "required": ["employee_id", "full_name", "work_email", "employment_status", "work_location_type", "department", "manager_id", "office_location"],
  "properties": {
    "employee_id": { "type": "string", "example": "EMP-1001" },
    "full_name": { "type": "string", "example": "John Doe" },
    "work_email": { "type": "string", "format": "email", "example": "john.doe@corp.internal" },
    "employment_status": { "type": "string", "enum": ["ACTIVE", "ON_LEAVE", "TERMINATED"], "example": "ACTIVE" },
    "work_location_type": { "type": "string", "enum": ["REMOTE_FULL_TIME", "HYBRID", "ONSITE"], "example": "REMOTE_FULL_TIME" },
    "department": { "type": "string", "example": "Engineering" },
    "job_title": { "type": "string", "example": "Staff Software Engineer" },
    "manager_id": { "type": "string", "example": "MGR-2001" },
    "hire_date": { "type": "string", "format": "date", "example": "2022-03-15" },
    "office_location": { "type": "string", "example": "Austin HQ" },
    "home_address": { "type": "string", "example": "123 Tech Park Way, Austin, TX 78701" },
    "phone_number": { "type": "string", "example": "+1-512-555-0199" }
  }
}
```

##### 2. `update_contact_info` (`PATCH /workweek/api/v1/employees/{employee_id}/contact`)
* **Request Schema**:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "UpdateContactRequest",
  "type": "object",
  "properties": {
    "home_address": { "type": "string", "minLength": 10, "maxLength": 255 },
    "phone_number": { "type": "string", "pattern": "^\\+?[1-9]\\d{1,14}$" },
    "office_location": { "type": "string", "maxLength": 100 }
  },
  "additionalProperties": false
}
```
* **Response Schema (200 OK)**:
```json
{
  "status": "SUCCESS",
  "employee_id": "EMP-1001",
  "updated_fields": ["home_address", "phone_number"],
  "updated_at": "2026-08-25T09:30:00Z"
}
```

##### 3. `get_leave_balances` (`GET /workweek/api/v1/employees/{employee_id}/leave-balances`)
* **Response Schema (200 OK)**:
```json
{
  "employee_id": "EMP-1001",
  "as_of_date": "2026-08-25",
  "balances": [
    { "leave_type": "Vacation", "accrued_days": 18.0, "used_days": 4.0, "pending_days": 2.0, "remaining_days": 12.0 },
    { "leave_type": "Sick_Leave", "accrued_days": 14.0, "used_days": 1.0, "pending_days": 0.0, "remaining_days": 13.0 },
    { "leave_type": "Bereavement", "allocated_days": 5.0, "used_days": 0.0, "remaining_days": 5.0 }
  ]
}
```

##### 4. `submit_leave_request` (`POST /workweek/api/v1/leave/requests`)
* **Request Schema**:
```json
{
  "employee_id": "EMP-1001",
  "leave_type": "Vacation",
  "start_date": "2026-08-27",
  "end_date": "2026-08-28",
  "duration_days": 2.0,
  "reason": "Personal time off"
}
```
* **Response Schema (201 Created)**:
```json
{
  "request_id": "WW-LV-90421",
  "employee_id": "EMP-1001",
  "status": "APPROVED",
  "remaining_balance": 12.0,
  "created_at": "2026-08-25T09:30:00Z",
  "origin": "HR_AGENT_ORCHESTRATOR_V1"
}
```

---

#### ServiceImmediately ITSM Connector Specification & Schemas

##### 1. `create_incident` (`POST /service-immediately/api/v1/incidents`)
* **Request Schema**:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CreateIncidentRequest",
  "type": "object",
  "required": ["requester_id", "category", "priority", "short_description", "description"],
  "properties": {
    "requester_id": { "type": "string", "example": "EMP-1001" },
    "category": { "type": "string", "enum": ["IT_HARDWARE", "IT_NETWORK", "IT_ACCESS", "HR_BENEFITS", "FACILITIES_BADGE"] },
    "priority": { "type": "string", "enum": ["1 - Critical", "2 - High", "3 - Moderate", "4 - Low"] },
    "short_description": { "type": "string", "maxLength": 160 },
    "description": { "type": "string", "maxLength": 2000 }
  }
}
```
* **Response Schema (201 Created)**:
```json
{
  "ticket_id": "INC123456",
  "requester_id": "EMP-1001",
  "category": "IT_NETWORK",
  "priority": "3 - Moderate",
  "status": "New",
  "assigned_group": "Tier-1 IT Service Desk",
  "created_at": "2026-08-25T09:30:00Z",
  "origin": "AUTOMATION_AGENT"
}
```

##### 2. `create_hardware_request` (`POST /service-immediately/api/v1/hardware/requests`)
* **Request Schema**:
```json
{
  "requester_id": "EMP-1001",
  "item_code": "MON-27-4K",
  "item_name": "27-inch 4K Home Office Monitor",
  "policy_reference": "Section 08.3 Remote Work Allowance",
  "shipping_address": "123 Tech Park Way, Austin, TX 78701"
}
```
* **Response Schema (201 Created)**:
```json
{
  "request_id": "REQ78910",
  "status": "Approved",
  "estimated_delivery": "2026-09-02",
  "created_at": "2026-08-25T09:30:00Z"
}
```

---

### 5.2. Component Failure Mapping, Fallback Logic & User Notifications

| Component / Subsystem | Failure Mode | System Fallback Logic | User-Facing Notification |
| :--- | :--- | :--- | :--- |
| **WorkWeek API** | Timeout / 503 Outage | Retry 3x via exponential backoff; abort gracefully if unrecovered. | *"WorkWeek is temporarily unavailable. Please try checking your leave balance in a few minutes."* |
| **ServiceImmediately API**| 500 Internal Error | Retry 3x; trigger Saga compensation if part of cross-system workflow. | *"Unable to submit ticket at this time. Support reference created for manual review."* |
| **Policy Search Engine** | Empty / Low Relevance Score | Refuse to hallucinate; fall back to ungrounded policy disclaimer. | *"I could not find an approved policy on this topic in our handbook. Would you like me to open an HR inquiry ticket?"* |
| **Cloud DLP Proxy** | Latency Spike (>300ms) | Fail closed on security; log alert in Cloud Monitoring. | *"Your request could not be processed due to a security timeout. Please try again."* |

---

### 5.3. Cross-System Consistency & Saga Compensation Engine

```mermaid
flowchart TD
    ErrorDetect["Backend Failure Detected (500/503/Timeout)"] --> RetryCheck{"Transient Failure?\n(Network / Rate Limit)"}
    RetryCheck -->|"Yes"| TenacityRetry["Tenacity Exponential Backoff\n(Max 3 retries, base 500ms, exp 2.0)"]
    TenacityRetry --> RetrySuccess{"Retry Successful?"}
    RetrySuccess -->|"Yes"| Proceed["Continue Execution Flow"]
    RetrySuccess -->|"No"| FallbackTrigger["Trigger Graceful Fallback"]
    RetryCheck -->|"No (Hard Error)"| FallbackTrigger
    
    FallbackTrigger --> CrossCheck{"Cross-System Flow\n(UC-2.x)?"}
    CrossCheck -->|"Yes"| SagaRollback["Execute Backward Compensation\n(Roll back prior successful step)"]
    CrossCheck -->|"No"| UserNotice["Render Clear Non-Technical Error\n('Service is temporarily unavailable')"]
    SagaRollback --> SupportTicket["Create Escalated Incident Ticket in ServiceImmediately"]
    SupportTicket --> UserNotice
```

---

### 5.4. Cloud Run Mock Service State Persistence & Database Schema (ERD)

To ensure stateful consistency across Cloud Run container restarts during UAT testing, the Mock Integration Service utilizes an embedded relational storage engine (SQLite on Cloud Storage Volume / Cloud SQL PostgreSQL) structured as follows:

```mermaid
erDiagram
    EMPLOYEES ||--o{ LEAVE_BALANCES : holds
    EMPLOYEES ||--o{ LEAVE_REQUESTS : submits
    EMPLOYEES ||--o{ INCIDENTS : requests
    EMPLOYEES ||--o{ HARDWARE_REQUESTS : orders
    EMPLOYEES ||--o{ FACILITIES_REQUESTS : applies
    INCIDENTS ||--o{ INCIDENT_COMMENTS : contains

    EMPLOYEES {
        string employee_id PK
        string full_name
        string work_email
        string role
        string department
        string manager_id
        string employment_status
        string work_location_type
        string office_location
        string home_address
        string phone_number
        timestamp created_at
    }

    LEAVE_BALANCES {
        int balance_id PK
        string employee_id FK
        string leave_type
        float accrued_days
        float used_days
        float remaining_days
        timestamp updated_at
    }

    LEAVE_REQUESTS {
        string request_id PK
        string employee_id FK
        string leave_type
        date start_date
        date end_date
        float duration_days
        string status
        string origin
        timestamp created_at
    }

    INCIDENTS {
        string ticket_id PK
        string requester_id FK
        string category
        string priority
        string status
        string short_description
        text description
        string assigned_group
        string origin
        timestamp created_at
        timestamp updated_at
    }

    INCIDENT_COMMENTS {
        int comment_id PK
        string ticket_id FK
        string author_id
        text comment_text
        string origin
        timestamp created_at
    }

    HARDWARE_REQUESTS {
        string request_id PK
        string requester_id FK
        string item_code
        string item_name
        string shipping_address
        string status
        timestamp created_at
    }

    FACILITIES_REQUESTS {
        string request_id PK
        string requester_id FK
        string request_type
        string target_office
        date effective_date
        string status
        timestamp created_at
    }
```

---

### 5.5. API Throttling, Rate Limiting & Circuit Breaker Thresholds

To protect downstream backend services from degradation during peak traffic events, the API Gateway and Client Connectors enforce strict traffic shaping:

| Governance Layer | Mechanism | Rate Limiting & Throttling Threshold | Behavior on Breach |
| :--- | :--- | :--- | :--- |
| **Per-User Ingress** | Token Bucket Algorithm | **20 requests / minute** (Burst: 30) per `employee_id` | HTTP `429 Too Many Requests` with `Retry-After: 60s` header. |
| **Global API Gateway** | Sliding Window Counter | **500 requests / minute** aggregate | Queued at Cloud Armor layer; smooth load shedding. |
| **WorkWeek HCM Connector** | Leaky Bucket Client Limiter | **10 requests / second** concurrency max | Requests queued client-side with 2.0s timeout before rejecting. |
| **ServiceImmediately Connector** | Concurrency Pool | **15 requests / second** concurrency max | Connection pooled via `httpx.AsyncClient(limits=Limits(max_connections=20))`. |
| **Circuit Breaker** | PyBreaker State Machine | **Trips Open** after **5 consecutive 5xx errors** or **P99 latency > 8.0s** over a 30s rolling window | Returns fast failover response without touching backend; **Half-Open cool-down period: 60 seconds**. |

---

## 6. Cost Estimation & FinOps

### 6.1. Key Cost Drivers & Consumption Variables
The primary cost drivers for the MVP 1 deployment are:
1. **LLM Inference Tokens**: Inbound prompt tokens (including retrieved policy chunks) and outbound generation tokens across Gemini 2.5 Flash and Gemini 2.5 Pro.
2. **Vertex AI Search Queries**: Fixed search index storage and search query transaction volume.
3. **Cloud Run Serverless Compute**: Active vCPU and memory allocations during tool execution.
4. **Cloud DLP Streaming Inspection**: Payload bytes scanned for SPII tokenization.

---

### 6.2. Monthly Operational Cost Breakdown (5,000 Pilot Users / 25,000 Inquiries/Month)

| Cost Driver / Component | Consumption Volume | Unit Cost (GCP List Price) | Monthly Total (USD) |
| :--- | :--- | :--- | :--- |
| **Vertex AI: Gemini 2.5 Flash** | 22,500 standard queries (avg. 1,000 in / 350 out tokens) | $0.075 / 1M input, $0.30 / 1M output | $4.05 |
| **Vertex AI: Gemini 2.5 Pro** | 2,500 complex multi-step queries (avg. 2,500 in / 600 out) | $1.25 / 1M input, $5.00 / 1M output | $15.31 |
| **Vertex AI Search (Discovery Engine)**| 1 Unstructured Data Store (< 100 documents) | $2.00 / 1,000 search queries | $50.00 |
| **Cloud DLP Streaming API** | 25,000 payloads ($\approx 50\text{ MB}$ text scanned) | $1.00 / \text{GB}$ inspected | $0.05 |
| **Cloud Run Integration Service** | 1 instance (min instances = 0, scale on demand) | $0.00002400 / \text{vCPU-sec}$ | $18.50 |
| **Cloud Logging & BigQuery** | 5 GB log ingestion + 100 GB queries | Standard tier | $6.20 |
| **Total Estimated MVP 1 Monthly OpEx** | — | — | **$94.11 / month** |

* **Unit Cost per Automated Interaction**: **$\approx \$0.0038$** (compared to human desk baseline of **$\$26.50$**).

---

### 6.3. FinOps Governance & Cost Guardrails
* **Automated Model Routing**: 90% of traffic defaults to **Gemini 2.5 Flash**, reserving **Gemini 2.5 Pro** exclusively for complex multi-system arbitration (UC-2.x).
* **Search Cache**: OKF concept catalog is cached in memory, eliminating redundant search index queries for common policy terms.
* **Auto-Scale Bounds**: Cloud Run instances configured with `min-instances: 0` and `max-instances: 5` to prevent runaway spending during testing.

---

## 7. Deployment & Delivery Plan

### 7.1. Environments & Infrastructure as Code (IaC)

```mermaid
flowchart LR
    GitRepo["Git Repository\n(Terraform / Python / OKF)"] --> CloudBuild["Google Cloud Build CI/CD"]
    CloudBuild --> TFApply["Terraform Apply"]
    
    subgraph GCPProject["Google Cloud Project: hr-agent-mvp1-prod"]
        GCS["Cloud Storage Bucket\n(Policy PDFs & Handbook)"]
        VES["Vertex AI Search\n(Data Store & Search Engine)"]
        RE["Vertex AI Reasoning Engine\n(Agent Runtime)"]
        CR["Cloud Run Mock Microservice\n(FastAPI Connector)"]
    end
    
    TFApply --> GCS
    TFApply --> VES
    TFApply --> RE
    TFApply --> CR
```

---

### 7.2. State Management & Configuration Versioning
* **Infrastructure State**: Terraform remote state stored in a versioned, CMEK-encrypted Google Cloud Storage bucket with Cloud KMS key rotation.
* **Agent Configuration Versioning**: Vertex AI Reasoning Engine deployments are tagged with Git commit SHAs (`v1.0.0-<commit_sha>`) for 100% reproducible rollbacks.

---

### 7.3. Phased Delivery Milestones, Dependencies & Deliverables

```mermaid
gantt
    title MVP 1 Phased Delivery Schedule (8 Weeks)
    dateFormat  YYYY-MM-DD
    section Week 1-2: Setup & Grounding
    Terraform IaC & GCP Project Setup          :done,    m1, 2026-09-01, 2026-09-12
    Static Policy Ingestion & OKF Curation      :done,    m2, 2026-09-05, 2026-09-15
    section Week 3-4: Mock Service & Tools
    Cloud Run FastAPI Mock Microservice        :active,  m3, 2026-09-16, 2026-09-26
    WorkWeek & ServiceImmediately Tool Binding :active,  m4, 2026-09-20, 2026-09-30
    section Week 5-6: Reasoning & Safety
    Vertex AI Reasoning Engine Supervisor Agent:         m5, 2026-10-01, 2026-10-12
    Cloud DLP & Model Armor Safety Integration :         m6, 2026-10-05, 2026-10-16
    section Week 7-8: Testing & UAT
    25-Case Golden Evaluation Suite Execution  :         m7, 2026-10-17, 2026-10-24
    Pilot UAT Testing (5,000 Employees)        :         m8, 2026-10-25, 2026-10-31
```

---

## 8. Assumptions, Constraints, Risk & Mitigations

### 8.1. Critical Technical & Operational Assumptions
1. **Single-Tenancy**: The MVP 1 deployment targets a single enterprise domain and assumes uniform organizational roles.
2. **Static Policy Corpus**: Policy documents are updated via deployment releases; real-time document change detection is deferred to Phase 2.
3. **Network Connectivity**: Internal endpoints communicate over secure Google Cloud VPC backbones.

---

### 8.2. MVP 1 Implementation Constraints
1. **Authentication & Credentials**: Functional test credentials are used for backend integrations; Enterprise SSO (Okta / Active Directory) is excluded from MVP 1.
2. **Tenancy Scope**: Single-tenant environment only.

---

### 8.3. Key Risks & Concrete Mitigation Strategies

| # | Identified Risk | Severity | Probability | Concrete Mitigation Strategy |
|---|---|:---:|:---:|---|
| **R-01** | **Policy Hallucination / Drift** | High | Low | Enforce Dual Grounding with strict minimum threshold (score $\ge 0.90$); refuse to answer and cite missing context if ungrounded. |
| **R-02** | **Cross-System Inconsistency on Failure** | High | Med | Implement Saga Pattern with automated backward compensation and immediate support incident ticket generation in ServiceImmediately. |
| **R-03** | **Prompt Injection / Jailbreak Attacks** | High | Low | Inline Model Armor and input classifier scanning every prompt before passing to LLM; reject malicious overrides instantly. |
| **R-04** | **SPII Leakage into Logs** | High | Low | Cloud DLP streaming proxy de-identifies all NRICs, SSNs, phone numbers, and addresses at ingress before logging. |
| **R-05** | **Downstream Service Timeout** | Med | Med | Tenacity exponential backoff (max 3 retries) with strict 4.0s timeout per tool call, preserving the < 10.0s overall latency budget. |

---

## 9. Quality Evaluation & UAT Framework

### 9.1. Quantitative Performance Metrics
* **Policy Q&A Grounded Accuracy**: $\ge 98\%$ on benchmark dataset with **0% hallucination**.
* **Safety Scanning Latency**: Overhead $< 120\text{ ms}$ (well below the $300\text{ ms}$ budget).
* **End-to-End Turn Latency**: P95 $< 3.5\text{ seconds}$ (well below the $10.0\text{ second}$ budget).
* **Prompt Injection Detection Rate**: **100% detection** across 50 adversarial penetration prompts with $< 1\%$ false positives.

---

### 9.2. Evaluation Dataset Curation (25-Case Golden Dataset)

```mermaid
pie title 25-Case Golden Test Suite Distribution
    "Policy Q&A Grounding (UC-1.1)" : 8
    "WorkWeek Self-Service (UC-1.2)" : 5
    "ServiceImmediately ITSM (UC-1.3)" : 4
    "Cross-System Orchestration (UC-2.x)" : 4
    "Safety, Jailbreak & Injection" : 4
```

---

### 9.3. Acceptance Thresholds & Verification Harness

| Evaluation Category | BRD Target Benchmark | Acceptance Threshold | Verification Harness |
| :--- | :--- | :--- | :--- |
| **Policy Q&A Accuracy** | $\ge 95\%$ Accuracy, 0% Hallucination | **$\ge 98\%$ Accuracy, 0% Hallucination** | Golden dataset Q&A evaluated with Gemini 2.5 Flash LLM-as-a-Judge. |
| **Transaction Integrity** | 100% Correctness | **100% Correctness** | State assertion on WorkWeek leave balances and ServiceImmediately ticket properties. |
| **Cross-System Orchestration**| Pass on all UC-2.x cases | **100% Pass on UC-2.1, UC-2.2, UC-2.3** | Automated end-to-end multi-step integration assertions. |
| **Safety & Guardrail Efficacy**| 100% Detection, <1% False Positives | **100% Detection, 0% False Positives** | Adversarial penetration test suite (DAN, roleplay, instruction override). |
| **Response Latency** | $< 10.0\text{ s}$, Safety $< 300\text{ ms}$ | **P95 $< 3.5\text{ s}$, Safety $< 120\text{ ms}$** | Automated load test with 50 concurrent virtual users. |
| **Auditability & Traceability**| 100% Log Coverage | **100% Log Coverage with Origin Tag** | Log audit asserting presence of `X-Automation-Origin` and user ID on every turn. |

---

## 10. Assumptions / Open Questions

### 10.1. Outstanding Design Decisions, Ownership & Deadlines

| ID | Open Design Question | Proposed Resolution | Owner | Target Deadline |
|---|---|---|:---:|:---:|
| **OQ-01** | What is the definitive refresh frequency for policy handbook PDF updates in production? | Daily scheduled Terraform batch sync in MVP 1; Eventarc real-time GCS sync in Phase 2. | PeopleOps / IT | 2026-09-15 |
| **OQ-02** | Should managers receive an approval notification in ServiceImmediately for Vacation requests $> 5$ days? | Handled by WorkWeek internal business processes; agent will query and display status. | HR Leadership | 2026-09-20 |
| **OQ-03** | Which enterprise identity provider will be selected for Phase 2 SSO federation? | Google Cloud Identity / Okta OIDC token exchange. | Enterprise Security | 2026-10-01 |

---

### Appendix: Document Sign-Off & Approvals
* **Lead AI Solution Architect**: `choirul@` — *Approved*
* **Head of Enterprise HR Technology**: `[Pending Final Sign-Off]`
* **Chief Information Security Officer (CISO) Representative**: `[Pending Final Sign-Off]`
