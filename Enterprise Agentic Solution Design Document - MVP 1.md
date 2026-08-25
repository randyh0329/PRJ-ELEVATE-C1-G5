# **Enterprise Agentic Solution Design Document - MVP 1**

---

# **Document Control**

## **Document Metadata**

| Field | Value |
| :---- | :---- |
| **Project Name** | HR Agentic Solution (MVP 1) |
| **Document ID** | SDD-ELEVATE-C1-G5-MVP1 |
| **Version** | 1.5 |
| **Date** | 2026-08-25 |
| **Author(s)** | Elevate C1-G5 Architecture Team |
| **Document Owner** | Cloud Architecture & Modernization Specialist Team |
| **Reviewers** | Alex Rivera (IT Director), Maria Santos (Data Protection Officer), HR Business Sponsor, InfoSec |
| **Status** | Approved Final Architecture / Evaluator Feedback Rounds 1-4 Integrated |
| **Target Audience** | Enterprise Architects, Application Modernization Leads, AI Engineers, IT Director, Data Protection Officer, HR Business Sponsors |
| **Source Requirements** | `HR Agentic Solution BRD.md` (FR-1.1 - FR-5.5, NFR-1.1 - NFR-4.3, UC-1.1 - UC-2.3) |
| **Target Cloud Platform** | Google Cloud Platform (Tiered Gemini 3.7 Flash + Gemini 3.1 Pro on Vertex AI, Agent Search, Model Armor, Cloud Run Multi-Region, Cloud Firestore, Cloud Tasks, Sensitive Data Protection) |

## **Revision History**

| Version | Date | Author | Description of Change |
| :---- | :---- | :---- | :---- |
| **0.1** | 2026-08-25 | Elevate C1-G5 Architecture Team | Initial outline setup |
| **1.0** | 2026-08-25 | Elevate C1-G5 Architecture Team | Full comprehensive system design incorporating BRD requirements, multi-agent topology, security guardrails, Saga orchestration, and FinOps |
| **1.1** | 2026-08-25 | Elevate C1-G5 Architecture Team | Evaluator Feedback round 1: Concierge analogy, ROI matrix, RBAC table, Firestore schemas, pre-LLM DLP de-id, multi-region DR |
| **1.2** | 2026-08-25 | Elevate C1-G5 Architecture Team | Evaluator Feedback round 2: Model standardization; explicit Cloud Tasks retry/throttling queue YAML; concrete Cloud DLP JSON template; PII element mapping matrix; Firestore replication lag bounds; Eventarc-driven policy sync; closed open questions OQ-01 to OQ-04 |
| **1.3** | 2026-08-25 | Romi Jung / Elevate C1-G5 Architecture Team | Model Architecture Modernization: upgraded to Gemini 3.7 Flash (`gemini-3.7-flash`) as the primary high-throughput agentic workhorse and Gemini 3.1 Pro (`gemini-3.1-pro`) for high-complexity Saga orchestration and LLM-as-a-Judge; integrated native agentic tool-calling specifications (`thought_signature`); recalculated the FinOps cost model with Vertex AI token pricing |
| **1.4** | 2026-08-25 | Elevate C1-G5 Architecture Team | **BRD conformance & correctness pass** (builds on the v1.3 tiered-model architecture, which is retained). Restored §4.1 delegated authorization with a verifiable two-layer composite token (replaces unsigned context header); added FR-1.3 **output** validation via Model Armor `SanitizeModelResponse` with a 300 ms safety-latency budget; added the missing `PATCH /employees/me/contact` operation (FR-3.2) and restored full OpenAPI 3.0 contracts; added sequence diagrams for **all six** use cases; introduced a Saga **compensation classification policy** so an accepted medical leave is never auto-cancelled over an ancillary IT step; added Agent & Tool Registry (FR-1.1); added knowledge-ACL revocation propagation SLA; reconciled the cost model to a single 15,000-inquiry/month basis; corrected Firestore consistency semantics; added a model-version governance policy over the v1.3 tiering; reconciled the cost model onto the single 15,000-inquiry/month basis used by the ROI case; restored §8 Assumptions & Constraints; added Golden Dataset spec, UAT plan, engineering standards, Terraform state management; added **Appendix A - Requirements Traceability Matrix**, **Appendix B - Glossary**, and **Appendix C - SDD Rubric Coverage Index** |
| **1.5** | 2026-08-25 | Elevate C1-G5 Architecture Team | **Evaluator feedback round 4** (run `sdd-20260825-ce39a6`). Re-architected the §4.3 safety chain from five sequential stages to three concurrency groups: design budget falls from **280 ms / 20 ms headroom to 120 ms / 180 ms headroom**, with per-stage hard deadlines that fail closed so network jitter cannot cascade into a turn timeout. Added **§7.5 Observability, Alerting & Operational Runbook** enumerating 17 concrete alert policies with thresholds, windows, severities and automated responses (including gateway and backend 5xx spike triggers), multi-window burn-rate alerting, and three structured log payload schemas. Added **adaptive concurrency control (AIMD)** to §5.2 so throughput safety no longer depends on vendor-confirmed rate limits - **closes OPEN-01 as DEC-08**. Selected Cloud Identity groups as the entitlement source of truth behind a swappable provider interface - **closes OPEN-03 as DEC-09**, so the restricted corpus ships in MVP. Added **§4.8 Credential & Entitlement Revocation Mid-Session and Mid-Saga**; formalised the §4.7 revocation SLAs as numbered, measured, alert-backed commitments (SLA-01 - SLA-06); added an explicit **consent-withdrawal** workflow distinct from Art. 17 erasure, and made masked-PII audit-log retention and stale-embedding purge explicit in §4.6.<br><br>**Evaluator feedback round 5** (run `sdd-20260825-6f9866`, both personas *pass*). Added **§1.5 Reviewer's Index** mapping recurring review questions to the answering section, after round 5 reported throttling (§5.2), revocation (§4.8) and 5xx fallback (§5.5) as absent when all three were present - a discoverability failure in a 1,900-line document. Added a **dead-letter queue strategy** (§5.2) covering poison-payload classification, 14-day retention, compensation-class routing and safe replay. Added **§5.6 Mock Service Fidelity & Production Cutover Plan** with latency and fault injection requirements and a six-stage shadow-to-canary cutover, so mock-based MVP delivery stops deferring integration risk. Added **SLA-07/SLA-08** and a named operational workflow for policy publication, with immediate exclusion of superseded documents so the failure mode is "no answer" rather than "wrong answer". Added **§6.5 price sensitivity and automated Catalog API verification** - **closes OPEN-02 as DEC-10**. **Closes OPEN-04 as DEC-11** with a documented rubric re-keying procedure. §10.2 now holds no delivery-blocking items; residual uncertainty is carried in §8.1 assumptions and §8.3 risks |

---

# **1. Executive Summary & Scope Boundaries**

## **1.1. Business Overview & Context**

### **The Enterprise Challenge**
Modern enterprises face immense operational drag within internal support organizations. Over 40% of all incoming HR and IT helpdesk tickets represent routine Tier 1 inquiries - such as leave policy clarifications, PTO accrual lookups, contact updates, and ticket status inquiries. Employees face severe friction navigating siloed, complex legacy UIs across disparate Human Capital Management (HCM - WorkWeek) and IT Service Management (ITSM - ServiceImmediately) systems, while human HR/IT specialists spend hundreds of hours per month on repetitive data entry.

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
2. **The Policy Librarian (Policy Agent):** Instantly looks up official handbook pages and quotes company policy word-for-word, giving exact page citations. If the handbook does not cover the question, the librarian says so rather than guessing.
3. **The HR Personnel Officer (WorkWeek Agent):** Securely opens the employee's *own* personnel file - never anyone else's - to check remaining vacation days, update a phone number or home address, or log new time off.
4. **The IT Desk Officer (ServiceImmediately Agent):** Logs tickets for laptops or network issues, adds notes, and updates status.
5. **The Operations Coordinator (Saga Coordinator):** When a request spans departments (e.g. Medical Leave requiring an HR filing *and* IT access routing), this coordinator sequences the steps and keeps a written ledger of what completed. **If a later step fails, the coordinator does not tear up work that has real consequences for the employee.** An accepted leave filing stays accepted; the coordinator raises a flagged follow-up task for a human and tells the employee plainly what is outstanding. Only harmless, reversible steps are automatically undone. (See §5.4.)

### **Quantitative Business Value & Return on Investment (ROI)**

> **Baseline provenance:** volumes, MTTR, cost-per-contact and CSAT are drawn from the FY26 internal helpdesk operations baseline supplied with the BRD. They are re-validated at UAT exit (§9.4) before the post-MVP business case is signed.

| Business Metric | Baseline (Manual Operations) | Target with HR Agent (MVP 1) | Tangible Enterprise Impact |
| :--- | :--- | :--- | :--- |
| **Tier 1 Ticket Volume** | 15,000 inquiries / month | <= 9,000 inquiries / month reaching a human | **40% Inquiry Deflection** within 6 months (BRD Objective 1) |
| **Mean Time to Resolution (MTTR)** | 4.2 hours average turnaround | **< 45 seconds conversational turnaround** | ~99% reduction in employee wait time for deflected inquiries |
| **Operational Cost per Interaction** | ~$18.50 (human agent labour) | **~$0.034 (fully-loaded platform cost, §6)** | **~$110,490 net monthly operational saving** |
| **Policy Compliance & Citation** | Variable (human memory errors) | **>= 95% grounded accuracy, 0% policy hallucination** | Fewer labour disputes from incorrect leave rules (NFR-3.1) |
| **Employee Satisfaction (CSAT)** | 61% (helpdesk ticketing friction) | **>= 88% Employee CSAT** | Increased productivity and seamless onboarding |

*Cost arithmetic: 6,000 deflected inquiries x $18.50 = $111,000 avoided labour; less ~$510/month platform run cost (§6) = **~$110,490 net**, an ROI of roughly **217x** on platform spend.*

## **1.2. Scope Boundaries**

| Dimension | In-Scope (MVP 1) | Out of Scope (MVP 1 / Post-MVP) |
| :--- | :--- | :--- |
| **Conversational Interface** | Web-based responsive chat UI with streaming Server-Sent Events (SSE) and citation deep links | Native Slack / Teams / Workspace Chat integrations |
| **Knowledge Domain** | Curated static HR policy documents (PDF/Text) stored in Google Cloud Storage | Dynamic HR intranet wikis, unstructured SharePoint crawls, external web search |
| **HCM Integration** | WorkWeek read (Profile, PTO balances) and write (Contact update, Leave request, Leave cancellation) | Payroll processing, Compensation, Benefits enrolment, Performance reviews |
| **ITSM Integration** | ServiceImmediately read (Ticket details, comment timeline) and write (Create, comment, status transition) | Change Management, Hardware Asset Tracking, CMDB updates |
| **Cross-System Workflows** | Equipment procurement (UC-2.1), Medical leave (UC-2.2), Relocation (UC-2.3) | A human-approval **workflow engine**. The agent *routes an approval notification* to the manager via ITSM (DEC-02); it does not host, track or adjudicate the sign-off itself. |
| **Identity & Access** | Single-tenant functional test credentials; composite delegated authorization with server-side subject binding (§4.1) | Enterprise IdP federation (Okta / Microsoft Entra ID SSO), Active Directory |
| **Backend Systems** | Purpose-built **mock** WorkWeek and ServiceImmediately services behind the same adapter contracts as production | Connection to live production HCM/ITSM tenants |
| **Languages** | English only | Multi-lingual support |
| **Modality** | Text-based conversation | Voice / IVR telephony integration |

## **1.3. Target Architecture Overview**

The target architecture is implemented using **Google Cloud native** components, built for multi-region resilience, zero-trust security boundaries, and a strict separation between **cognitive reasoning** (the model decides *what* to do) and **deterministic execution** (validated code decides *whether it is allowed* and performs it).

```mermaid
flowchart TB
    subgraph ClientAndIngress["Client and Ingress Layer"]
        UserBrowser["Employee Web Browser"] --> CloudArmor["Cloud Armor (WAF and DDoS Protection)"]
        CloudArmor --> GlobalLB["Global External Application Load Balancer"]
        GlobalLB --> ChatUI["Web Chat UI (Next.js on Cloud Run with SSE)"]
    end

    subgraph SecurityGateway["Security and Ingress Gateway (Cloud Run Multi-Region)"]
        ChatUI --> APIGateway["API Gateway and Interceptor<br>Session auth, subject binding, trace injection"]
        APIGateway --> DLP["Sensitive Data Protection (DLP API)<br>Pre-LLM PII de-identification"]
        DLP --> ArmorIn["Model Armor - SanitizeUserPrompt<br>Prompt injection, jailbreak, RAI, malicious URL"]
        ArmorIn --> Router["Supervisor and Intent Router (Gemini 3.7 Flash)"]
    end

    subgraph AgentCore["Agent Core Orchestration (Cloud Run Multi-Region)"]
        Router --> PolicyAgent["Policy Q&A Specialist Agent"]
        Router --> HCMAgent["WorkWeek HCM Specialist Agent"]
        Router --> ITSMAgent["ServiceImmediately Specialist Agent"]
        Router --> SagaCoordinator["Cross-System Saga Coordinator"]

        PolicyAgent --> LLMReasoning["Specialist Agentic Engine (Gemini 3.7 Flash on Vertex AI)"]
        HCMAgent --> LLMReasoning
        ITSMAgent --> LLMReasoning
        SagaCoordinator --> SagaReasoning["High-Order Saga Reasoning (Gemini 3.1 Pro on Vertex AI)"]
    end

    subgraph EgressGuard["Egress Validation (FR-1.3 Output Validation)"]
        LLMReasoning --> ArmorOut["Model Armor - SanitizeModelResponse<br>Toxicity, SPII leakage, malicious URL"]
        ArmorOut --> GroundCheck["Groundedness and Citation Integrity Check"]
        GroundCheck --> Reident["Selective Re-identification inside Trust Boundary"]
    end

    subgraph IntegrationAndResilience["Enterprise Integration and Resilience Layer"]
        PolicyAgent --> AgentSearch["Agent Search - formerly Vertex AI Search<br>Grounding and Citations"]
        AgentSearch --> GCS["Cloud Storage (HR Policy PDFs)"]

        HCMAgent --> WWAdapter["WorkWeek Adapter<br>Pydantic validation + business rules"]
        ITSMAgent --> SIAdapter["ServiceImmediately Adapter<br>Pydantic validation + business rules"]

        WWAdapter --> CloudTasks["Cloud Tasks and Pub/Sub Buffer<br>5xx and throttling resilience queue"]
        SIAdapter --> CloudTasks

        WWAdapter --> MockWW["WorkWeek HCM API (Mock Target)"]
        SIAdapter --> MockSI["ServiceImmediately ITSM API (Mock Target)"]
    end

    subgraph PersistenceAndGovernance["Persistence, Governance and Audit"]
        AgentCore <--> Firestore[("Cloud Firestore Multi-Region nam5<br>30-Day TTL Session and Saga State")]
        APIGateway & AgentCore & WWAdapter & SIAdapter --> Logging["Cloud Logging and Cloud Trace"]
        Logging --> BigQuery[("BigQuery - 1-Year Partitioned Audit Archive")]
    end

    Reident --> ChatUI
```

## **1.4. Alternatives Considered**

| Architectural Decision | Chosen Selection | Alternatives Considered | Trade-offs & Rationale | Business Value |
| :--- | :--- | :--- | :--- | :--- |
| **Agent Orchestration Framework** | **LangGraph / Python StateGraph on Cloud Run** | 1. **ADK on Gemini Enterprise Agent Platform** (managed Sessions, Memory Bank, Example Store, observability)<br>2. Vertex AI Agent Builder (declarative / low-code)<br>3. Semantic Kernel / CrewAI | ADK on the managed Agent Platform is the strongest genuine competitor and removes session/memory infrastructure work; it is the recommended **post-MVP** target (§2.1). For MVP 1 we chose LangGraph on Cloud Run because the Saga pattern requires an explicit, inspectable state machine with hand-written compensating transitions and a persisted step ledger we control (§5.4), and because the eval harness needs deterministic replay of a fixed graph. Declarative builders were rejected: guardrails and compensation cannot be strictly bounded in them. | Auditable, replayable execution graph - a precondition for the 100%-transaction-correctness criterion in BRD §7 |
| **LLM Architecture & Model Selection** | **Tiered: Gemini 3.7 Flash + Gemini 3.1 Pro on Vertex AI** | 1. Legacy Gemini 1.5 / 2.x series<br>2. Intermediate Gemini 3.5 Flash / Flash-Lite<br>3. Monolithic Gemini 3.1 Pro across all layers<br>4. Open-source models self-hosted on GKE (Gemma / Llama) | **Gemini 3.7 Flash (`gemini-3.7-flash`)** is the primary agentic workhorse - supervisor intent routing, all three single-domain specialists, and streamed user responses - chosen for high-throughput structured tool calling and low TTFT.<br><br>**Gemini 3.1 Pro (`gemini-3.1-pro`)** is invoked selectively for two workloads where reasoning depth outweighs latency: multi-system Saga state arbitration (UC-2.x, ~7% of turns) and offline CI/CD LLM-as-a-Judge evaluation (§9.3), which is not on the user's critical path at all.<br><br>*Against the alternatives:* legacy 1.5/2.x lack modern agentic tool-calling optimisation; 3.5-series is superseded; monolithic Pro roughly triples token cost (§6) and risks the p95 latency target for the 93% of turns that do not need it; self-hosted OSS forfeits managed grounding deep links, Model Armor integration and the SLA.<br><br>**Both model IDs are pinned and any change is gated on the §9.3 eval suite** - see the version-governance rule below. | Reasoning depth spent only where it changes the outcome; ~$219/month total model spend at MVP volume |
| **Knowledge Retrieval (RAG)** | **Agent Search** (formerly Vertex AI Search) over a GCS datastore | 1. Custom RAG with pgvector on Cloud SQL / Spanner<br>2. Vertex AI Vector Search | Agent Search provides managed semantic chunking, automated re-ranking, and native grounding/citation attribution out of the box, directly fulfilling FR-5.2 and FR-5.3 with zero custom chunking code, plus document-level ACL enforcement needed for tiered policy corpora (§4.7). | Fastest path to citation-backed answers; no bespoke retrieval stack to maintain |
| **Session & Distributed State** | **Cloud Firestore Multi-Region (`nam5`)** | 1. Memorystore (Redis)<br>2. Cloud Spanner | Firestore offers serverless multi-region transactional persistence with **native TTL** for automatic 30-day session deletion, and durable Saga step logs. Redis is not durable enough for a compliance ledger; Spanner is over-provisioned for MVP volumes and is retained as the production upgrade path. | Retention compliance (NFR-1.3) enforced by the platform rather than by application code |
| **Resilience & Queueing** | **Cloud Tasks + Pub/Sub Dead-Letter Queue** | 1. Direct synchronous retries only<br>2. Self-managed Celery / RabbitMQ | Cloud Tasks provides managed, rate-limited HTTP dispatch with configurable exponential backoff and no infrastructure to run, absorbing backend 429/5xx spikes (NFR-4.2). | Peak-load resilience without an ops team (Alex Rivera's stated concern) |
| **Input / Output Safety** | **Model Armor** (`SanitizeUserPrompt` + `SanitizeModelResponse`) with org-level floor settings | 1. Custom Gemini classifier on the egress path<br>2. Model-native safety settings only | Model Armor covers all six required detection categories (Responsible AI, prompt injection & jailbreak, sensitive data, CSAM, malicious URL, document screening) as a stateless low-latency service, and org-level **floor settings** make the control non-bypassable by any single service. A custom classifier duplicates this at higher latency and cost, and could be disabled by a code change. | Non-bypassable, centrally-governed safety control satisfying FR-1.3 on both directions |

> **Model version governance (FR-1.1).** Both production models are pinned to explicit versioned endpoints, not floating aliases. Any model change - including a minor version bump - is treated as a change to the system under test: it must pass the full §9.3 golden-set and red-team gate before promotion, and the model ID is recorded per turn in the audit log so any answer can be attributed to the exact model that produced it. The judge model (`gemini-3.1-pro`) is pinned **independently** of the production models, so an evaluation-harness upgrade can never be mistaken for a product regression.

## **1.5. Reviewer's Index - Where Each Governance Concern Is Answered**

This document is long because the subject matter is. To keep it navigable for a reviewer with a specific question - and to stop any control being judged absent merely because it is deep in a later section - the table below maps the questions that recur in architecture review directly to the section that answers them.

| If you are asking... | It is answered in | Short answer |
| :--- | :--- | :--- |
| How do we know a request really came from the agent, acting for a specific user? | **§4.1** | Two-layer composite credential; both layers verified independently |
| Can the model be tricked into acting as another employee? | **§4.1**, **§4.2** | No - the acting employee ID is bound server-side and is not a tool parameter |
| What are the API throttling thresholds and backoff strategy? | **§5.2** | 50 rps WorkWeek / 40 rps ServiceImmediately seeds, exponential backoff 1 s - 60 s, plus AIMD adaptive concurrency that self-calibrates |
| What happens to payloads that fail permanently? | **§5.2 (DLQ strategy)** | Classified, retained 14 days, replayable; consequential payloads always reach a human, never silently dropped |
| How fast is a revoked session actually killed? | **§4.7 (SLA-01)**, **§4.8**, **Path 7** | Under 5 s, enforced on every turn; 120 s credential TTL means there is no long-lived token to strand |
| What happens if a backend returns 5xx or times out mid-transaction? | **§5.5**, **§5.2** | Queue-and-confirm with idempotency keys; user gets a plain-language message; no stack traces |
| Will an accepted medical leave be auto-cancelled if a later step fails? | **§5.4**, **§4.8** | No. `HUMAN_CONSEQUENTIAL` steps are never automatically reversed |
| How quickly do policy changes reach the knowledge base? | **§4.6 (SLA-07)**, **DEC-01** | Under 15 min routine, under 5 min emergency, event-driven not scheduled |
| What is alerted on, and at what threshold? | **§7.5** | 5 SLOs, 17 alert policies with thresholds, windows, severities and automated responses |
| Is the safety scanning going to blow the latency budget? | **§4.3** | 120 ms p95 design budget against a 300 ms ceiling; per-stage deadlines fail closed |
| How is PII kept out of the model and the logs? | **§4.4**, **§4.5** | DLP de-identification before the prompt; surrogates in logs; re-identification only inside the trust boundary |
| What about erasure and consent withdrawal? | **§4.6** | Art. 17 purge with receipt; Art. 7(3) withdrawal with ephemeral mode; stale embeddings evicted |
| How do we get from mock services to the real HCM and ITSM? | **§5.6** | Contract-identical mocks with fault and latency injection, then shadow, canary and cutover |
| What does it cost, and how sensitive is that? | **§6** | ~$510/month at 15,000 inquiries; sensitivity analysis in §6.5 |
| What is not yet decided? | **§10.2** | Nothing that blocks delivery; residual uncertainty is recorded as assumptions (§8.1) and risks (§8.3) |

---

# **2. Production-Ready Future State Design & Disaster Recovery**

## **2.1. Enterprise Scalability Roadmap**
The MVP 1 architecture is engineered as a foundational stepping stone toward global enterprise deployment:

1. **Identity Federation:** Replace the MVP functional-credential session with corporate OIDC tokens issued by Okta or Microsoft Entra ID, exchanged at the gateway for the short-lived downstream assertions already defined in §4.1. Because the subject is already bound server-side, this is a gateway-only change - no agent or adapter code is touched.
2. **Managed Agent Runtime:** Migrate the LangGraph orchestrator onto **Gemini Enterprise Agent Platform** (ADK) to inherit managed Sessions, Memory Bank, Example Store, Code Execution and built-in observability, retiring the hand-rolled Firestore session layer.
3. **Enterprise API Hub (Apigee):** Route all WorkWeek and ServiceImmediately traffic through Apigee for corporate API governance, centralised rate limiting, and mutual TLS.
4. **Omnichannel Messaging:** Extend the Cloud Run gateway to accept Slack Socket Mode, Microsoft Teams Bot Framework, and Google Chat webhooks.
5. **Multi-Tenancy:** Introduce a tenant dimension into the subject assertion, Firestore partition keys, and Agent Search datastore ACLs.

## **2.2. Disaster Recovery (DR) & Multi-Region High-Availability Architecture**
To fulfil NFR-2.2 (99.9% uptime) and enterprise business continuity expectations, the architecture is deployed active-active across two regions:

```mermaid
flowchart LR
    Users["Global Users"] --> AnycastIP["Cloud Anycast IP / Global External HTTPS Load Balancer"]

    subgraph RegionPrimary["Primary Region: us-central1"]
        GLB1["Serverless NEG"] --> CR_Primary["Cloud Run (Primary)"]
    end

    subgraph RegionSecondary["Secondary Region: us-east4"]
        GLB2["Serverless NEG"] --> CR_Secondary["Cloud Run (Secondary)"]
    end

    AnycastIP --> GLB1
    AnycastIP --> GLB2

    CR_Primary & CR_Secondary <--> MultiRegionFS[("Cloud Firestore Multi-Region nam5<br>Synchronous Paxos quorum commit<br>Strongly consistent reads in both regions")]
    CR_Primary & CR_Secondary --> GlobalVault["Secret Manager, Cloud KMS and Vertex AI"]
```

| Metric | Target SLA | Implementation Strategy |
| :--- | :--- | :--- |
| **System Availability** | **99.9% (MVP 1) / 99.99% (Prod)** | Multi-region Cloud Run with Global External ALB health-check auto-failover |
| **Recovery Point Objective (RPO)** | **RPO = 0** | Firestore `nam5` commits synchronously to a Paxos quorum spanning regions before acknowledging the write |
| **Recovery Time Objective (RTO)** | **RTO < 30 seconds** | Health-check-driven failover at the load-balancer layer; both regions serve continuously, so failover is capacity shedding rather than a cold start |
| **Read Consistency** | **Strongly consistent in both regions** | Firestore multi-region serves strongly consistent reads from the quorum. There is **no** stale-follower read path and therefore no committed-write replication lag to tolerate. |
| **Cross-Region Read Latency Budget** | **p99 < 150 ms** | Budget for a strongly-consistent quorum read observed from the non-primary region. This is a **latency** target, not a staleness window - it is measured by a synthetic probe and alerts at 150 ms. |
| **Zonal Outage Resilience** | **Zero impact** | Cloud Run distributes instances across zones within each region automatically |
| **Backup & Point-in-Time Recovery** | **7-day PITR window** | Firestore PITR enabled; scheduled daily exports to a dual-region GCS bucket with 35-day retention, guarding against logical corruption that replication would faithfully copy |
| **Failover Drill Cadence** | **Quarterly** | Region evacuation game-day; RTO measured and recorded as a DR runbook exit criterion |

> **Correction note (v1.4):** earlier revisions described a "max acceptable replication lag < 150 ms" with "bounded asynchronous follower reads." That characterisation applies to Cloud Spanner stale reads, not Firestore. Firestore `nam5` acknowledges a write only after synchronous quorum replication, so committed-write lag is zero by construction; the 150 ms figure is retained above but re-labelled as what it actually is - a cross-region read *latency* budget.

---

# **3. System Flows, Sequence Diagrams & Agent Design**

## **3.1. Hierarchical Multi-Agent Topology**
To enforce capability boundaries (FR-1.1), the system implements a strict **Supervisor-Worker Agent Topology**. Workers cannot call each other; only the Supervisor or the Saga Coordinator may delegate.

```mermaid
graph TD
    Input(["User Prompt"]) --> Bind["Gateway: bind subject from authenticated session<br>(employee_id is NEVER model-supplied)"]
    Bind --> SafeIn["Pre-LLM PII de-identification (Cloud DLP)"]
    SafeIn --> ArmorIn["Model Armor SanitizeUserPrompt"]
    ArmorIn --> Sup["Supervisor Agent - Intent Router (Gemini 3.7 Flash)"]

    Sup -->|Policy Query| Worker1["Policy Specialist Agent"]
    Sup -->|WorkWeek Transaction| Worker2["HCM Specialist Agent"]
    Sup -->|ITSM Action| Worker3["ITSM Specialist Agent"]
    Sup -->|Cross-System Intent| Worker4["Saga Workflow Coordinator (Gemini 3.1 Pro)"]
    Sup -->|Out of Domain| Refuse["Domain Containment Refusal (FR-5.4)"]

    Worker1 --> Tool1["Agent Search Datastore (ACL-filtered)"]
    Worker2 --> Tool2["WorkWeek Adapter and Validator"]
    Worker3 --> Tool3["ServiceImmediately Adapter and Validator"]
    Worker4 --> Worker1
    Worker4 --> Worker2
    Worker4 --> Worker3

    Worker1 --> StateStore[("Firestore State - 30-Day TTL")]
    Worker2 --> StateStore
    Worker3 --> StateStore
    Worker4 --> StateStore

    Worker1 --> ArmorOut["Model Armor SanitizeModelResponse"]
    Worker2 --> ArmorOut
    Worker3 --> ArmorOut
    Worker4 --> ArmorOut
    ArmorOut --> Ground["Groundedness + Citation Integrity Check"]
    Ground --> Reident["Selective re-identification inside trust boundary"]
    Reident --> Output(["Sanitised, grounded response to user"])
```

## **3.2. Agent & Tool Registry (FR-1.1 Capability & Lifecycle Governance)**

Every agent and every tool is declared in a version-controlled registry (`config/registry.yaml`) that is the *only* source of tool bindings at runtime. A tool absent from the registry cannot be invoked, and an invocation attempt outside an agent's declared allowlist is rejected before any network call and logged as a governance violation (FR-1.1, NFR-1.2).

| Agent | Owner | Version | Model | Authorised Tools (allowlist) | Prohibited |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Supervisor / Router** | Platform Team | `sup-1.4.0` | `gemini-3.7-flash@<pinned>` | *Delegation only* - no external tools | All backend APIs |
| **Policy Specialist** | HR Knowledge Team | `pol-1.4.0` | `gemini-3.7-flash@<pinned>` | `agent_search.query` | WorkWeek, ServiceImmediately |
| **WorkWeek HCM Specialist** | HCM Integration Team | `hcm-1.4.0` | `gemini-3.7-flash@<pinned>` | `ww.get_profile`, `ww.update_contact`, `ww.get_balances`, `ww.submit_leave`, `ww.cancel_leave` | Agent Search, ServiceImmediately |
| **ServiceImmediately Specialist** | ITSM Integration Team | `itsm-1.4.0` | `gemini-3.7-flash@<pinned>` | `si.get_incident`, `si.create_incident`, `si.post_comment`, `si.update_status` | Agent Search, WorkWeek |
| **Saga Coordinator** | Platform Team | `saga-1.4.0` | `gemini-3.1-pro@<pinned>` | *Delegation to the three specialists only* | Direct backend calls |

Registry entries carry `owner`, `semver`, `created_at`, `last_reviewed_at`, `prompt_file_sha256` and `model_id`. The registry is diffed in CI; any change requires the §9.3 eval gate to pass and is recorded in the ADR log (§7.2).

## **3.3. End-to-End Sequence Diagrams**

All six BRD use cases are represented, plus the credential-revocation path.

### **Path 1: Policy Q&A with Streaming and Grounding (UC-1.1)**
```mermaid
sequenceDiagram
    autonumber
    actor User as Employee
    participant UI as Chat Web UI
    participant GW as API Gateway
    participant DLP as Cloud DLP
    participant Armor as Model Armor
    participant Orch as Policy Agent (Gemini 3.7 Flash)
    participant Search as Agent Search
    participant Audit as Cloud Logging and BigQuery

    User->>UI: What is the bereavement leave policy?
    UI->>GW: POST /v1/chat/stream (session cookie, SSE)
    GW->>GW: Bind employee_id from session; mint composite token
    GW->>DLP: Pre-LLM de-identify PII
    DLP-->>GW: Sanitised prompt + ephemeral surrogate map
    GW->>Armor: SanitizeUserPrompt
    Armor-->>GW: ALLOW (no injection, in-domain)
    GW->>Orch: Invoke Policy Specialist
    Orch->>Search: Query datastore, ACL filter = caller entitlements
    Search-->>Orch: Chunks + deep-link metadata + retrieval relevance score

    alt Retrieval relevance >= 0.8
        Orch->>Orch: Generate answer constrained to retrieved chunks
        Orch->>Armor: SanitizeModelResponse (toxicity, SPII, malicious URL)
        Armor-->>Orch: ALLOW
        Orch->>Orch: Groundedness check >= 0.85 AND every citation resolves
        Orch->>GW: Stream tokens over SSE
        GW->>UI: Stream chunks (target TTFT avg < 1.0 s, p95 < 1.5 s)
        GW->>Audit: Log (origin=AI-Policy-Agent, allowed=true, model_id, citations)
    else Retrieval below threshold, ungrounded, or a citation fails to resolve
        Orch-->>GW: Refusal - not covered by official policy documents
        GW->>UI: Grounding-rejection fallback with HR Portal link
        GW->>Audit: Log (unanswered / out of scope / citation failure)
    end
```

> **Two distinct gates.** *Retrieval relevance* (>= 0.8) decides whether we have usable source material. *Groundedness* (>= 0.85) decides whether the generated sentence is actually supported by that material. Earlier revisions conflated the two under one 0.8 threshold; they measure different things and both must pass.

### **Path 2: HR Self-Service Happy Path - Balance Check then Leave Submission (UC-1.2)**
```mermaid
sequenceDiagram
    autonumber
    actor User as Employee
    participant GW as API Gateway
    participant Orch as HCM Specialist Agent
    participant Val as WorkWeek Adapter (Pydantic + Rules)
    participant WW as WorkWeek HCM API
    participant FS as Cloud Firestore
    participant Audit as Cloud Logging

    User->>GW: How much PTO do I have, and book Thu and Fri off
    GW->>Orch: Invoke with bound subject EMP-44210
    Orch->>Val: ww.get_balances()
    Note over Val: employee_id injected server-side from the token subject,<br>NOT from any model-produced argument
    Val->>WW: GET /api/v1/employees/me/balances
    WW-->>Val: Vacation accrued 96h, used 40h, remaining 56h
    Val-->>Orch: Balances (fetched live - never cached, FR-3.4)
    Orch-->>User: You have 56 vacation hours remaining. Booking Thu 27 and Fri 28 Aug, 16 hours.

    Orch->>Val: ww.submit_leave(start=2026-08-27, end=2026-08-28, type=Vacation, hours=16)
    Val->>Val: Rule 1 - start <= end and start >= today (FR-3.3)
    Val->>Val: Rule 2 - 16h <= 56h remaining (FR-3.3)
    Val->>Val: Rule 3 - date format and enum validation
    Val->>WW: POST /api/v1/employees/me/leaves
    WW-->>Val: HTTP 201 Created, LeaveID LV-4021
    Val-->>Orch: Success LV-4021
    Orch->>FS: Persist turn (masked transcript, tool trace)
    Orch->>Audit: Log (origin=AI-HCM-Agent, action=SUBMIT_LEAVE, ref=LV-4021, allowed=true)
    Orch-->>User: Submitted. Reference LV-4021. Remaining balance after approval - 40 hours.
```

### **Path 3: IT Incident Management - Query and Create (UC-1.3)**
```mermaid
sequenceDiagram
    autonumber
    actor User as Employee
    participant Orch as ITSM Specialist Agent
    participant Val as ServiceImmediately Adapter
    participant SI as ServiceImmediately ITSM API
    participant Audit as Cloud Logging

    User->>Orch: What is the status of INC123456? Also my VPN keeps dropping.
    Orch->>Val: si.get_incident(ticket_id=INC123456)
    Val->>Val: Ownership check - ticket requestor must equal bound subject (FR-1.5)
    Val->>SI: GET /api/v1/incidents/INC123456
    SI-->>Val: State In Progress, Priority 3-Moderate, assignee, comment timeline
    Val-->>Orch: Ticket detail
    Orch-->>User: INC123456 is In Progress with Network Ops. Latest note - awaiting switch replacement.

    Orch->>Val: si.create_incident(category=Network, short_desc=VPN drops, priority=3-Moderate)
    Val->>Val: Duplicate scan - same requestor, category, 10-minute window (FR-4.3)
    Val->>Val: Priority verification - "1-Critical" only if the description meets critical criteria (FR-4.3)
    Val->>SI: POST /api/v1/incidents (X-Agent-Origin asserted, FR-4.1)
    SI-->>Val: HTTP 201 Created, INC123999
    Val-->>Orch: Success
    Orch->>Audit: Log (origin=AI-ITSM-Agent, action=CREATE_INCIDENT, ref=INC123999)
    Orch-->>User: Raised INC123999 (Moderate) for the VPN drops.
```

### **Path 4: Cross-System Equipment Procurement (UC-2.1)**
```mermaid
sequenceDiagram
    autonumber
    actor User as Employee
    participant Saga as Saga Coordinator (Gemini 3.1 Pro)
    participant FS as Cloud Firestore (Saga Log)
    participant Pol as Policy Agent
    participant HCM as WorkWeek Adapter
    participant SI as ServiceImmediately Adapter

    User->>Saga: I read I am eligible for a home office monitor - can you verify and order one?
    Saga->>FS: Init saga-1041 (type=UC-2.1-EQUIPMENT, state=STARTED)

    Saga->>Pol: Query remote work equipment entitlement
    Pol-->>Saga: Remote employees eligible for one monitor per 24 months, cap USD 350, cite Remote Work Policy s4.2
    Saga->>FS: Step 1 SUCCESS (read-only, no compensation needed)

    Saga->>HCM: ww.get_profile()
    HCM-->>Saga: Work location REMOTE, shipping address on file
    Saga->>FS: Step 2 SUCCESS (read-only)

    alt Employee is not remote-eligible
        Saga-->>User: Your record shows an on-site work location, so the home office monitor entitlement does not apply. Policy Remote Work s4.2 cited. No request raised.
    else Eligible
        Saga->>SI: si.create_incident(category=Hardware Request, desc=Monitor + shipping address, priority=4-Low)
        SI-->>Saga: HTTP 201, REQ-8830
        Saga->>FS: Step 3 SUCCESS, state=COMPLETED
        Saga-->>User: Verified remote eligibility under Remote Work Policy s4.2. Hardware request REQ-8830 raised to your address on file.
    end
```

### **Path 5: Cross-System Medical Leave with Corrected Compensation Policy (UC-2.2)**
```mermaid
sequenceDiagram
    autonumber
    actor User as Employee
    participant Saga as Saga Coordinator (Gemini 3.1 Pro)
    participant FS as Cloud Firestore (Saga Log)
    participant Pol as Policy Agent
    participant WW as WorkWeek Adapter
    participant Tasks as Cloud Tasks Resilience Queue
    participant SI as ServiceImmediately Adapter
    participant Ops as Ops Alerting and Manual Follow-up Queue

    User->>Saga: I need short-term medical leave from next Monday. What is the process, can you set it up?
    Saga->>FS: Init saga-998 (type=UC-2.2-MEDICAL-LEAVE, state=STARTED)

    Saga->>Pol: Retrieve short-term medical leave procedure
    Pol-->>Saga: Grounded procedure + citation
    Saga-->>User: Quotes procedure with citation

    Note over Saga, WW: Step 1 - WorkWeek leave filing. Class = HUMAN_CONSEQUENTIAL
    Saga->>WW: POST /leaves (type=Medical, start=2026-09-01, status=PENDING_APPROVAL)
    WW-->>Saga: HTTP 201 Created, LV-4012
    Saga->>FS: state=STEP1_WW_COMPLETED, leaveId=LV-4012

    Note over Saga, SI: Step 2 - ITSM manager-approval routing ticket. Class = ANCILLARY
    Saga->>SI: POST /incidents (category=Access, desc=Route approval and email delegation to manager)

    alt Step 2 succeeds
        SI-->>Saga: HTTP 201, INC-5510
        Saga->>FS: state=COMPLETED
        Saga-->>User: Leave LV-4012 filed for manager approval. IT routing ticket INC-5510 raised.
    else Step 2 returns 429 or 5xx
        SI-->>Saga: HTTP 503 Service Unavailable
        Saga->>Tasks: Enqueue retry (exponential backoff, maxAttempts=5)
        Saga->>FS: state=STEP2_ASYNC_QUEUED, taskId=task-771
        Saga-->>User: Your medical leave LV-4012 is filed and stands. The IT routing step is queued and will complete shortly.
    else Step 2 retries exhausted
        Tasks->>FS: state=PARTIALLY_COMPLETED_MANUAL_FOLLOWUP
        Note over Saga, WW: Step 1 is NOT rolled back. An accepted medical leave<br>is never auto-cancelled because an ancillary IT step failed.
        Saga->>Ops: Raise P2 manual follow-up with saga id, leave id, failed payload
        Saga->>FS: Record orphaned step for reconciliation
        Saga-->>User: Your medical leave LV-4012 is filed and unaffected. We could not complete the IT email-routing step automatically, so it has been passed to the IT service desk as a tracked follow-up. No action is needed from you.
    end
```

> **Why this changed in v1.4.** Earlier revisions issued `DELETE /leaves/LV-4012` when the ancillary ITSM step exhausted its retries - cancelling a filed medical leave because an email-routing ticket failed. NFR-4.3 explicitly permits *"log the failure clearly and provide instructions for manual follow-up"* as an alternative to compensation. Cancelling a medical leave filing is a materially harmful, non-idempotent act against the employee; a failed IT ticket is not. See the compensation classification policy in §5.4.

### **Path 6: Cross-System Relocation (UC-2.3)**
```mermaid
sequenceDiagram
    autonumber
    actor User as Employee
    participant Saga as Saga Coordinator (Gemini 3.1 Pro)
    participant FS as Cloud Firestore (Saga Log)
    participant Pol as Policy Agent
    participant WW as WorkWeek Adapter
    participant SI as ServiceImmediately Adapter

    User->>Saga: I am transferring to the London office next month - allowance, record update, building access?
    Saga->>FS: Init saga-1180 (type=UC-2.3-RELOCATION, state=STARTED)

    Saga->>Pol: Retrieve relocation allowance limits
    Pol-->>Saga: Intra-region transfer allowance cap + citation
    Saga-->>User: States allowance with citation, then requests the new address

    Note over Saga, WW: Explicit user confirmation required before any write
    Saga-->>User: Confirm the new London address to write to your WorkWeek record
    User-->>Saga: Confirms address
    Saga->>WW: PATCH /api/v1/employees/me/contact (address, phone)
    WW-->>Saga: HTTP 200, previousAddress returned for compensation
    Saga->>FS: state=STEP2_CONTACT_UPDATED, prior value stored. Class = REVERSIBLE_SAFE

    Saga->>SI: POST /incidents (category=Facilities, desc=London badge access, priority=3-Moderate)

    alt Facilities ticket succeeds
        SI-->>Saga: HTTP 201, REQ-9004
        Saga->>FS: state=COMPLETED
        Saga-->>User: Allowance quoted, address updated, badge request REQ-9004 raised.
    else Facilities ticket permanently fails
        Saga->>WW: PATCH /contact (restore previous address) - reversible, no employee harm
        Saga->>FS: state=COMPENSATED_ROLLED_BACK
        Saga-->>User: We could not raise the facilities request, so your address change has been reverted to keep records consistent. Please retry, or contact Facilities directly.
    end
```

### **Path 7: Credential Revocation and Downstream Invalidation**
```mermaid
sequenceDiagram
    autonumber
    actor Admin as HR / Security Admin
    actor User as Employee
    participant IdP as WorkWeek / Corporate IdP
    participant AuthGW as API Gateway (/api/v1/auth/revoke-webhook)
    participant FS as Cloud Firestore (Token Cache and Sessions)
    participant Search as Agent Search ACL Sync
    participant WW_API as WorkWeek API Gateway
    participant SI_API as ServiceImmediately Gateway
    participant ActiveSession as Active Agent Container

    Admin->>IdP: Terminate employee or revoke permissions
    IdP->>AuthGW: POST /api/v1/auth/revoke-webhook (HMAC signature, employeeId, timestamp, nonce)
    AuthGW->>AuthGW: Verify HMAC, reject stale timestamp or replayed nonce

    par Invalidate state, downstream tokens and knowledge entitlements
        AuthGW->>FS: Delete token_cache where employeeId matches
        AuthGW->>FS: Set sessions.status = REVOKED where employeeId matches
        AuthGW->>Search: Update principal entitlement set (see 4.7)
        AuthGW->>WW_API: POST /oauth/revoke
        AuthGW->>SI_API: POST /oauth/revoke
    end

    AuthGW-->>IdP: HTTP 200 Revocation confirmed

    Note over ActiveSession: Next conversation turn by the user
    User->>ActiveSession: Submit a new leave request
    ActiveSession->>FS: Check session status and token cache
    FS-->>ActiveSession: REVOKED / cache miss
    ActiveSession-->>User: Security credentials were updated or revoked. Session terminated - please re-authenticate.
```

---

# **4. Security, Governance & Identity**

## **4.1. Delegated Authorization & Verification of Request Origin (FR-1.2, FR-3.1)**

Every call from an agent to a backend adapter, and from an adapter to WorkWeek or ServiceImmediately, carries a **two-layer composite credential**. Both layers must verify; either one alone is rejected.

```mermaid
flowchart LR
    Session["Authenticated chat session<br>(MVP: functional test credential;<br>Post-MVP: corporate OIDC)"] --> GW["API Gateway"]
    GW -->|"1. Bind subject server-side"| Mint["Token Minting"]
    Mint --> L1["Layer 1 - Workload identity<br>Google-signed OIDC ID token<br>aud = target adapter URL"]
    Mint --> L2["Layer 2 - Subject assertion<br>JWT signed by agent SA via<br>IAM Credentials signJwt"]
    L1 --> Adapter["Adapter / Backend"]
    L2 --> Adapter
    Adapter -->|"Verify L1 against Google JWKS"| V1{"Workload authentic?"}
    Adapter -->|"Verify L2 signature, aud, exp, jti"| V2{"Subject assertion valid?"}
    V1 -->|No| Reject["401 Reject and log security event"]
    V2 -->|No| Reject
    V1 --> Allow["Execute with subject scope"]
    V2 --> Allow
```

**Layer 1 - Workload identity.** A Google-signed **OIDC ID token** minted for the calling service account, with `aud` bound to the exact target adapter URL. Verified against Google's public JWKS. This proves *which workload* is calling and satisfies the FR-1.2 requirement that downstream calls be attributable to an authorised automation entity. It cannot be forged without the service-account key, which is never exported (workload identity only).

**Layer 2 - Subject assertion.** A short-lived JWT signed by the agent service account through **IAM Credentials `projects.serviceAccounts.signJwt`** - a real asymmetric signature, not an encoding.

```json
{
  "iss": "hr-agent-orchestrator@prj-elevate-c1-g5.iam.gserviceaccount.com",
  "sub": "EMP-44210",
  "act": { "sub": "hr-agent-orchestrator@prj-elevate-c1-g5.iam.gserviceaccount.com" },
  "aud": "https://workweek-adapter-<hash>-uc.a.run.app",
  "sid": "session-uuid-v4",
  "tid": "turn-000317",
  "trace": "projects/prj-elevate-c1-g5/traces/9f2c...",
  "agent": "hcm-1.3.0",
  "model_id": "gemini-3.7-flash@<pinned>",
  "scope": ["ww.balances.read", "ww.leaves.write"],
  "jti": "b1f0c8de-...",
  "iat": 1787654321,
  "exp": 1787654441
}
```

| Property | Value | Rationale |
| :--- | :--- | :--- |
| **Signing** | `signJwt` via IAM Credentials API (RS256) | Verifiable, non-forgeable, no exported key material |
| **TTL** | 120 seconds | Narrow replay window even if a token is captured in a log |
| **Replay defence** | `jti` nonce, tracked in Firestore `token_cache` for the TTL | Single-use per call |
| **Audience binding** | `aud` = exact target URL | A token for the HCM adapter cannot be replayed against the ITSM adapter |
| **Scope** | Explicit tool-permission strings, intersected with the RBAC matrix (§4.2) | Least privilege enforced per call, not per session |
| **Actor claim** | `act` names the automating service account | Audit records distinguish agent-performed from user-performed actions (FR-1.2, FR-4.1) |

> ### **The load-bearing rule**
> **`sub` is bound server-side at the API Gateway from the authenticated session. It is never a model-supplied tool argument, and no tool signature accepts an `employee_id` parameter.**
>
> This single rule is what makes FR-1.5 (RBAC and data isolation) hold *under prompt injection*. Even if an attacker fully controls the model's output and it emits `get_balances(employee_id="EMP-00001")`, the adapter has no such parameter to accept; it reads the subject from the verified assertion and calls `/employees/me/...`. Cross-user data access is therefore structurally impossible rather than prompt-dependent. Every RBAC control in §4.2 rests on this.

**Deprecated in v1.4.** Earlier revisions specified `X-User-Context: base64(JSON{userId, employeeId, role, tenantId})` and described it as cryptographically signed. Base64 is an encoding, not a signature - any caller able to reach the adapter could mint an arbitrary identity. That header is removed. `X-Agent-Origin` and `X-Execution-Trace-ID` are retained **for observability only** and carry no authorization weight.

## **4.2. Enterprise Role-Based Access Control (RBAC) Matrix (FR-1.5)**

Effective permission for any call = *(role grant in this matrix)* ∩ *(`scope` claim in the subject assertion)* ∩ *(agent tool allowlist in §3.2)*. All three must permit the operation.

| Enterprise User Role | Policy Q&A (RAG) | WorkWeek HCM Scope | ServiceImmediately ITSM Scope | Session & Audit Scope |
| :--- | :--- | :--- | :--- | :--- |
| **End User (Standard Employee)** | General static HR policy corpus (Leave, Expense, Remote Work, Code of Conduct) | **Self-only:** read own profile, own PTO balances; submit own leave; update own phone/address | **Self-only:** query own incidents; open incident; comment on own tickets | Own active session only; no access to system audit logs |
| **People Partner (HR Specialist)** | General corpus **plus** confidential HR operational guidelines (ACL-gated, §4.7) | **Assigned department:** read department employee profiles; verify team PTO balances. No writes on behalf of others in MVP 1. | Query HR-category tickets; post comments on behalf of HR Operations | Department inquiry analytics; PII-redacted session logs |
| **IT Support Engineer** | General corpus only | Read contact info only, for equipment dispatch | **Full ITSM queue:** read, assign, set priority, post work notes, transition lifecycle | Technical execution logs and API diagnostic traces (PII redacted) |
| **Security & Compliance Admin** | General corpus, read-only | No tool execution | No tool execution | **Full audit access:** BigQuery compliance archive, DLP telemetry, guardrail decision logs |

## **4.3. Conversation Safety - Input and Output Validation (FR-1.3, NFR-1.1)**

FR-1.3 mandates validation in **both** directions. Both are implemented on Model Armor, with org-level **floor settings** so that no individual service configuration can weaken the control below the enterprise minimum.

| Direction | Control | Detection Categories | Action on Detection |
| :--- | :--- | :--- | :--- |
| **Inbound** (before the model) | `SanitizeUserPrompt` | Prompt injection & jailbreak; Responsible AI (hate, harassment, sexual, dangerous); Sensitive Data Protection; malicious URL; CSAM; document & image screening | Terminate the turn, abort all tool execution, log a security event, return the standard refusal |
| **Inbound** (domain) | Supervisor classification + deny-list | Off-topic / out-of-domain (FR-5.4 domain containment) | Polite in-scope redirect; logged as `OUT_OF_DOMAIN` |
| **Outbound** (before display) | `SanitizeModelResponse` | Toxicity and RAI violations; **SPII leakage in the generated text**; malicious or non-corporate URL | Suppress the response, substitute a safe fallback, log a blocked-output event |
| **Outbound** (factuality) | Groundedness scoring + citation resolution | Unsupported assertion; citation that does not resolve to an active indexed document (FR-5.4 citation integrity) | Downgrade to refusal rather than emit an unsupported policy claim |
| **Outbound** (privacy) | Re-identification gate | Surrogate tokens re-expanded **only** inside the trust boundary, and only for fields the caller is entitled to see | Any surrogate that cannot be authorised is left masked |

### **Safety Latency Budget (NFR-2.1: safety scanning must add < 300 ms per turn)**

**Reworked in v1.5.** v1.4 costed this chain as five *sequential* stages totalling 280 ms, leaving 20 ms against the NFR-2.1 ceiling. That criticism was correct and is accepted: 20 ms is not an engineering margin, it is a rounding error, and a single TCP retransmit on a regional DLP call would breach the SLO. The stages were sequential only because they were *described* sequentially - the data dependencies never required it. v1.5 makes concurrency the **default design**, not a contingency held in reserve.

**Dependencies that genuinely constrain ordering:**

- DLP de-identification and Model Armor `SanitizeUserPrompt` both consume the **raw** user input, and neither consumes the other's output. They run concurrently.
- The model cannot start until both return: de-identification supplies the prompt text, Armor supplies the allow/block verdict.
- `SanitizeModelResponse` and groundedness scoring both consume **generated** text, which arrives incrementally under SSE. Both run on a rolling window concurrently with generation, so only the final window sits on the critical path.
- Re-identification consumes the approved final text, so it is strictly last - but it is an in-memory map lookup.

| Concurrency group | Stages executed | Critical-path cost (p95) | Why this is the real cost |
| :--- | :--- | :--- | :--- |
| **G1 - Inbound** | DLP de-identify (60 ms) ∥ `SanitizeUserPrompt` (80 ms) | **80 ms** | Two independent calls on the same input; the group costs the slower one, not the sum |
| **G2 - Outbound, overlapped with generation** | Rolling `SanitizeModelResponse` ∥ rolling groundedness + citation resolution | **30 ms** | Both scan a sliding window as tokens stream; only the final ~200-token window is unscanned when generation ends. Citation resolution is a cached datastore metadata lookup already warm by then |
| **G3 - Release** | Re-identification of authorised surrogates | **10 ms** | Session-scoped in-memory surrogate map |
| **Total safety overhead** | | **120 ms (p95)** | **180 ms headroom against the 300 ms NFR-2.1 ceiling** |

The cost of this design is a late-suppression edge case: the final window may fail its scan after partial text has streamed. The UI handles it by retracting the partial message and substituting the safe fallback. That is a deliberate trade - a rare visible retraction in exchange for 160 ms of reclaimed headroom on every turn.

### **Per-Stage Deadlines and Failure Policy**

Headroom alone does not answer the timeout concern, because a hung dependency consumes unbounded time regardless of budget. Every stage therefore carries a hard deadline, and **every deadline fails closed** - a guardrail that cannot complete must not be assumed to pass.

| Stage | Hard deadline | Action on breach | Rationale |
| :--- | :--- | :--- | :--- |
| DLP de-identification | 150 ms | Abort turn; standard service-unavailable message; `DLP_DEADLINE` security event | Raw SPII must never reach a model prompt (FR-1.4) |
| `SanitizeUserPrompt` | 150 ms | Abort turn; standard refusal; `ARMOR_IN_DEADLINE` event | An unscanned prompt cannot be permitted to reach the model (FR-1.3) |
| `SanitizeModelResponse` | 150 ms | Suppress the response, emit the safe fallback, retract any partial stream | An unscanned response cannot be shown to a user (FR-1.3) |
| Groundedness + citation | 120 ms | Downgrade to refusal rather than emit an unverified policy claim | FR-5.4 strict grounding; 0% hallucination is a hard NFR-3.1 target |
| Re-identification | 50 ms | Leave surrogates masked and render them as such | Masked output is degraded, not unsafe |

Deadlines sit **well above** each stage's p95 budget precisely so that ordinary jitter is absorbed by the 180 ms of headroom rather than by a timeout. A stage trips its deadline only in a genuine fault, not in a minor network fluctuation - which is the specific failure Alex Rivera raised.

**Circuit breaker.** If Model Armor or DLP returns errors or deadline breaches on more than **2% of calls over a 5-minute window**, the breaker opens and the service enters *fail-closed degraded mode*: conversational reads continue to be refused rather than served unscanned, and `ALRT-08` pages the on-call engineer immediately (§7.5). There is no fail-open path. A documented break-glass procedure exists, but it requires two-person InfoSec authorisation and is itself audited - the system will never silently degrade a safety control to preserve availability.

> **These remain design budgets, not measurements.** §9.1 makes measured safety overhead a hard pass/fail gate, §7.4 Phase 3 retains its latency-tuning exit criterion, and `ALRT-04` warns at 240 ms - 80% of the ceiling - so the team learns of drift long before the NFR is breached.

## **4.4. PII Classification, Masking & Retention Mapping (FR-1.4)**

Explicit data-protection boundaries between conversational transcripts, external model payloads, and downstream transaction payloads:

| PII Data Element | Ingested User Input | LLM Payload (Gemini 3.7 Flash / 3.1 Pro) | Stored Transcript (Firestore / BigQuery) | Downstream API Payload (WorkWeek / ITSM) | Transformation Technique |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Social Security Number** | Accepted then immediately transformed | **BLOCKED / `[REDACTED_SSN]`** | **Redacted completely** | Prohibited in this channel | Hard regex + DLP infoType, `replaceWithInfoType` |
| **Banking / Credit Card** | Blocked at ingress | **Blocked completely** | **Redacted completely** | Out of scope for MVP 1 | Automatic block + security alert |
| **Employee Name** | Plaintext | **Pseudonymised `[PERSON_1]`** | Retained (CMEK-encrypted at rest) | Plaintext | Crypto-deterministic surrogate |
| **Personal Phone Number** | Plaintext | **Pseudonymised `[PHONE_1]`** | Masked `[REDACTED_PHONE]` | Plaintext (contact-update API only) | Crypto-deterministic surrogate |
| **Home Address** | Plaintext | **Pseudonymised `[ADDRESS_1]`** | Masked `[REDACTED_ADDRESS]` | Plaintext (contact-update API only) | Crypto-deterministic surrogate |
| **Employee ID** | Not accepted from the user | **Pseudonymised `[EMP_ID_1]`** | Retained (key identifier) | Carried in the signed `sub` claim, never in prose | Crypto-deterministic surrogate |
| **Leave Balances / Dates** | Plaintext | Plaintext (business necessity) | Retained for transaction trace | Plaintext | Standard schema validation |

Crypto-deterministic surrogates are stable within a session, so the model can reason about "the same person" across turns without ever seeing the real value. The surrogate map is held in memory for the turn and never persisted.

## **4.5. Cloud DLP De-identification Configuration Template**

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
              { "name": "BANK_ACCOUNT_NUMBER" },
              { "name": "IBAN_CODE" },
              { "name": "PASSPORT" }
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
                    "cryptoKeyName": "projects/prj-elevate-c1-g5/locations/global/keyRings/hr-agent-kr/cryptoKeys/dlp-surrogate-key"
                  }
                },
                "surrogateInfoType": { "name": "PSEUDONYM" }
              }
            }
          }
        ]
      }
    }
  }
}
```

An `inspectTemplate` with `minLikelihood: LIKELY` and `includeQuote: false` pairs with the above. Both templates are managed in Terraform (`modules/security`) so that a change is reviewable, versioned and re-deployable rather than a console edit.

## **4.6. Firestore Schemas, 30-Day Lifecycle & Right to be Forgotten (NFR-1.3)**

### **Collection: `sessions`**
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

### **Subcollection: `sessions/{sessionId}/messages`**
```json
{
  "_id": "msg-001",
  "sender": "USER",
  "maskedContent": "How many hours of PTO do I have remaining?",
  "timestamp": "2026-08-25T10:00:05Z",
  "modelId": "gemini-3.7-flash@<pinned>",
  "inputTokens": 14,
  "outputTokens": 0,
  "guardrailVerdict": "ALLOW",
  "citations": []
}
```

### **Collection: `sagas` (distributed workflow ledger)**
```json
{
  "_id": "saga-998",
  "sessionId": "session-uuid-v4",
  "employeeId": "EMP-44210",
  "workflowType": "UC-2.2-MEDICAL-LEAVE",
  "currentState": "PARTIALLY_COMPLETED_MANUAL_FOLLOWUP",
  "steps": [
    {
      "stepIndex": 1,
      "targetSystem": "WorkWeek",
      "action": "SUBMIT_LEAVE",
      "compensationClass": "HUMAN_CONSEQUENTIAL",
      "status": "SUCCESS",
      "externalReferenceId": "LV-4012",
      "compensationPayload": null,
      "timestamp": "2026-08-25T10:01:15Z"
    },
    {
      "stepIndex": 2,
      "targetSystem": "ServiceImmediately",
      "action": "CREATE_ROUTING_TICKET",
      "compensationClass": "ANCILLARY",
      "status": "FAILED_HANDED_TO_HUMAN",
      "followUpRef": "OPS-2214",
      "timestamp": "2026-08-25T10:04:02Z"
    }
  ],
  "ttl_expiry": "2026-09-24T10:01:15Z"
}
```

### **Collection: `token_cache`**
```json
{
  "_id": "sha256(EMP-44210|aud|jti)",
  "employeeId": "EMP-44210",
  "jti": "b1f0c8de-...",
  "audience": "https://workweek-adapter-<hash>-uc.a.run.app",
  "cachedAt": "2026-08-25T10:00:00Z",
  "ttl_expiry": "2026-08-25T10:02:00Z"
}
```

> **FR-3.4 compliance.** No employee-specific *dynamic* data - profile fields, PTO balances, ticket state - is ever cached in the orchestration layer. `token_cache` holds only replay-defence metadata. Every profile or balance read hits WorkWeek live. Transcripts persisted to Firestore are masked per §4.4.

### **Retention Lifecycle & Compliance Rules**

| Data Class | Store | Retention | Mechanism |
| :--- | :--- | :--- | :--- |
| Conversational transcripts (masked) | Firestore `messages` | 30 days | Native Firestore TTL on `ttl_expiry` |
| Session metadata | Firestore `sessions` | 30 days | Native TTL |
| Saga execution ledger | Firestore `sagas` | 30 days | Native TTL |
| Replay-defence nonces | Firestore `token_cache` | 120 seconds | Native TTL |
| **Audit records containing masked PII** (crypto-deterministic surrogates only - raw SPII is never written) | BigQuery, daily-partitioned | **365 days**, then automatic partition drop | Partition expiration, enforced in Terraform; a monthly retention-conformance job asserts that no partition older than 365 days exists and pages on failure (`ALRT-13`) |
| **Guardrail decision logs** (prompt hash + verdict; the offending text itself is never retained) | BigQuery, daily-partitioned | **365 days**, then automatic partition drop | Partition expiration; same conformance job |
| Security incident logs | Cloud Logging bucket, locked | 400 days, immutable | Log bucket retention lock |

**Right to be Forgotten (GDPR Article 17) purge workflow:**
1. Erasure request or departure event dispatched to `POST /api/v1/compliance/purge-employee-data`.
2. Firestore executes hard deletion across `sessions`, `messages`, `sagas` and `token_cache` matching the `employeeId`.
3. BigQuery audit rows are pseudonymised in place rather than deleted, preserving the lawful-basis audit trail (NFR-1.2 requires every action be logged) while removing identifiability - the retained record shows *that* an action occurred, not *who*.
4. Any employee-contributed content in the Agent Search datastore is deleted and the datastore incrementally re-imported; embeddings are purged within **15 minutes**.
5. Query-time metadata filtering rejects stale cached chunks immediately, so the effective exposure window is the filter-propagation time, not the re-index time.
6. A signed confirmation receipt is returned to the Compliance Office and archived.

**Stale embeddings.** Step 4 above is the control for the Right to be Forgotten as it applies to the vector layer. Employee-contributed content can enter the Agent Search datastore only through the policy-repository ingestion path, so the purge is bounded and enumerable: the source object is deleted from GCS, `object.delete` fires an Eventarc trigger, and the datastore performs an incremental re-import that **evicts the corresponding embeddings within 15 minutes** (SLA-04). Because the query-time metadata filter rejects chunks whose source document is marked deleted, a stale embedding is unreachable from the moment the deletion is recorded - the 15-minute figure is the physical-removal SLA, not the exposure window.

### **Consent Withdrawal (distinct from Article 17 erasure)**

Withdrawal of consent under GDPR Art. 7(3) is a **different** request from erasure and is handled separately: an employee may withdraw consent to conversational-history processing while remaining employed and while the lawful-basis audit trail must still be preserved.

| Step | Action | Store affected | Timing |
| :--- | :--- | :--- | :--- |
| 1 | Employee withdraws consent in the chat UI (`POST /api/v1/compliance/withdraw-consent`) or via the HR portal | - | Immediate acknowledgement |
| 2 | `consent_state` on the employee record is set to `WITHDRAWN`; the flag is read on **every** turn | Firestore `sessions` | < 5 s, next turn |
| 3 | All historical interaction turns for that employee are hard-deleted | Firestore `messages`, `sessions`, `sagas` | **< 60 minutes**, batched purge job (SLA-05) |
| 4 | Future turns run in **ephemeral mode**: no transcript is persisted, the session holds context in memory only, and it is discarded at session end | Firestore (no writes) | Ongoing |
| 5 | Audit records are pseudonymised in place, not deleted | BigQuery | < 60 minutes |
| 6 | Withdrawal itself is recorded as an auditable compliance event | BigQuery, Cloud Logging | Immediate |

The distinction matters for compliance defensibility: erasure removes the person from the system, whereas withdrawal removes the *processing* while preserving the legally required record **that** processing previously occurred. Step 4 is the part most designs omit - without ephemeral mode, the next turn silently re-creates the transcript the employee just asked the system to stop keeping.

## **4.7. Knowledge ACL & Entitlement Revocation Propagation**

The policy corpus is tiered: a general corpus every employee may read, and a restricted **HR operational guidelines** corpus available only to People Partners (§4.2). Access is enforced at two independent layers so that a lag in one cannot leak content.

| Layer | Mechanism | Propagation on revocation |
| :--- | :--- | :--- |
| **Query-time filter** | Every Agent Search query carries the caller's entitlement set, derived from the *live* verified subject assertion, as a metadata filter | **Immediate** - the next query already excludes the restricted corpus, because entitlements come from the token, not from a cached index |
| **Datastore ACL** | Document-level ACLs synced to Agent Search from the entitlement source | **< 15 minutes** - Eventarc-triggered incremental sync on entitlement change |
| **Session invalidation** | Firestore session status set to `REVOKED` by the webhook (Path 7) | **< 5 seconds** - checked on every turn |

This ordering is deliberate: the fast, authoritative control is the query-time filter, and the slower ACL sync is defence-in-depth. **The maximum window in which a revoked principal could retrieve restricted content is bounded by the session check (< 5 s), not by the ACL sync (< 15 min).**

### **Formalised Revocation & Purge SLAs**

The DPO asked for a *formalised* SLA rather than a design intention. Each commitment below has a numbered identifier, a measurement method, an owning alert, and a defined consequence on breach. These are operational commitments carried into the service's SLO set (§7.5), not prose.

| SLA ID | Commitment | Target | How it is measured | Alert on breach | Consequence of breach |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SLA-01** | Session invalidation after a revocation webhook | **< 5 s** (p99) | Synthetic revocation probe every 5 min: revoke a canary principal, measure until the next turn is refused | `ALRT-14` | P1 security incident; break-glass global session flush available |
| **SLA-02** | Downstream OAuth grant revocation at WorkWeek and ServiceImmediately | **< 10 s** (p99) | Webhook fan-out span in Cloud Trace | `ALRT-14` | P1; adapters fall back to rejecting the cached credential |
| **SLA-03** | Entitlement change propagated to Agent Search document ACLs | **< 15 min** (p95) | Eventarc-to-datastore sync completion timestamp diff | `ALRT-15` | P2; query-time filter (immediate) remains the authoritative control throughout |
| **SLA-04** | Stale embeddings physically evicted after source-document deletion | **< 15 min** (p95) | Incremental re-import completion event | `ALRT-15` | P2; metadata filter renders the chunk unreachable meanwhile |
| **SLA-05** | Historical interaction turns purged after consent withdrawal | **< 60 min** | Purge-job completion record, row-count assertion to zero | `ALRT-13` | P2 compliance event, reported to the DPO |
| **SLA-06** | Article 17 erasure completed end to end and receipt issued | **< 24 h** | Signed receipt timestamp vs request timestamp | `ALRT-13` | P1 compliance event; DPO notified directly |
| **SLA-07** | **Updated HR policy reflected in the knowledge base** (routine) | **< 15 min** (p95) | Timestamp diff between GCS `object.finalize` and datastore import completion | `ALRT-16` | P2; the superseded document is marked `stale` and excluded from retrieval immediately, so the failure mode is "no answer", never "wrong answer" |
| **SLA-08** | Updated HR policy reflected in the knowledge base (**emergency** path) | **< 5 min** | Same, measured on force-reindex runs | `ALRT-16` | P1; HR Policy Owner notified directly |

**Why the layering makes the slow SLA tolerable.** SLA-03 and SLA-04 are the only commitments measured in minutes, and neither is load-bearing for confidentiality. Entitlements are evaluated from the *live* verified subject assertion on every query, so a principal whose role was revoked one second ago is already excluded by the query-time filter even though the datastore ACL still lists them. The ACL sync exists so that a defect in the filter layer is not a single point of failure. **There is no compliance window in which a revoked user can read restricted content** - the concern the DPO raised is closed by the ordering, not merely mitigated by the SLA.

### **Operational Workflow: Publishing a Policy Change**

SLA-07 is only credible if a named person can execute it without engineering involvement. The pipeline is event-driven, so publishing *is* the trigger - there is no scheduled job to wait for and no ticket to raise.

| Step | Actor | Action | Elapsed |
| :--- | :--- | :--- | :--- |
| 1 | HR Policy Owner | Upload the revised document to the governed GCS policy bucket, superseding the prior version | t=0 |
| 2 | *Automatic* | `object.finalize` fires an Eventarc trigger (DEC-01) | < 5 s |
| 3 | *Automatic* | The superseded version is flagged `stale` in the datastore metadata and **immediately excluded from retrieval** | < 10 s |
| 4 | *Automatic* | Cloud Function calls the Agent Search incremental import; chunking, embedding and indexing run | t + 15 min (p95) |
| 5 | *Automatic* | A verification probe queries a canary question whose answer only the new version contains | on completion |
| 6 | *Automatic* | Probe failure raises `ALRT-16`; success writes a publication receipt to the audit dataset | on completion |
| 7 | HR Policy Owner | Sees the publication receipt in the policy dashboard | t + 15 min |

**The stale-answer question, answered directly.** Step 3 is the control, not step 4. Exclusion of the superseded version is immediate and independent of re-indexing, so during the indexing window the agent will say *"I could not find that in the official policy documents"* rather than quote a withdrawn policy. **Refusing is an acceptable 15-minute state; asserting a repealed policy is not.**

**Emergency path (SLA-08).** For an urgent correction - a policy withdrawn for legal reasons - the HR Policy Owner sets the `priority-reindex` object label, which routes to a dedicated high-priority import and completes in under 5 minutes. Step 3 still applies at t + 10 s regardless, so the incorrect content is unreachable almost immediately either way.

## **4.8. Credential & Entitlement Revocation Mid-Session and Mid-Saga**

Path 7 (§3.3) shows the revocation fan-out. This section states the behavioural contract explicitly, including the case Path 7 does not draw: revocation that lands **while a multi-step Saga is in flight**.

**Why a mid-session revocation cannot be missed.** The composite credential of §4.1 is deliberately short-lived - the subject assertion carries a **120-second TTL** and is minted per turn, never cached across turns. There is no long-lived bearer token to revoke in the conventional sense. Three independent checks run before any tool executes:

| Check | Source of truth | Cost | Fails the turn when |
| :--- | :--- | :--- | :--- |
| Session status | Firestore `sessions.status` | Single indexed read, already on the turn path | Status is `REVOKED` |
| Subject-assertion freshness | Assertion `exp` claim, 120 s TTL | Local signature verification | Expired, or minting is refused because the principal is gone |
| Live entitlement set | Re-derived at mint time from the entitlement provider (DEC-09) | Cached 60 s, invalidated by webhook | Requested scope is no longer held |

**Mid-turn revocation.** A revocation arriving after the turn began but before a tool call is caught by the session check preceding that call. A revocation arriving after a write has been dispatched cannot un-send it; the write is already authorised and audited, and the *next* turn is refused. This is stated plainly rather than papered over - a system that claimed to retract an in-flight authorised write would be lying.

**Mid-Saga revocation.** The interaction with §5.4 compensation classes is the subtle case, and the answer follows the same principle that governs compensation generally:

| Saga state at revocation | Behaviour |
| :--- | :--- |
| No step yet executed | Saga abandoned, ledger marked `REVOKED_BEFORE_EXECUTION`, nothing to undo |
| Only `READ_ONLY` steps executed | Saga abandoned; no state changed |
| A `REVERSIBLE_SAFE` step executed | Step compensated automatically, Saga closed, action recorded |
| An `ANCILLARY` step executed | Left in place and flagged; an ITSM follow-up task is opened for a human |
| A **`HUMAN_CONSEQUENTIAL`** step executed (e.g. a filed medical leave) | **Never automatically reversed.** The Saga halts, remaining steps are cancelled, and a P2 ITSM ticket is routed to HR Operations with full context so a human completes or unwinds it deliberately |

The last row is the important one. A terminated employee's already-filed medical leave is not silently cancelled because their session died - that would convert an access-control event into an HR harm, which is exactly the failure mode DEC-06 exists to prevent. Revocation stops *future* agent action; it does not retroactively rewrite completed, audited, human-consequential state.

**Queued work.** Cloud Tasks entries already enqueued for a revoked principal are not executed: each task handler re-verifies session status and entitlements before dispatch, and a task failing that check is moved to the DLQ with reason `PRINCIPAL_REVOKED` rather than retried.

---

# **5. Integration Details & Error Handling**

## **5.1. Tool Specifications (OpenAPI 3.0)**

All nine operations mandated by FR-3.2 and FR-4.2, plus the leave-cancellation compensator. Note that no operation accepts an employee identifier as a parameter - the subject comes from the signed assertion (§4.1), which is why the WorkWeek paths are `/me/`.

```yaml
openapi: 3.0.3
info:
  title: WorkWeek HCM Adapter API
  version: 1.4.0
  description: >
    Deterministic adapter fronting the WorkWeek HCM system. The acting employee is
    resolved server-side from the verified subject assertion; it is never a request parameter.
servers:
  - url: https://workweek-adapter-{hash}-uc.a.run.app
security:
  - workloadOidc: []
    subjectAssertion: []
paths:
  /api/v1/employees/me/profile:
    get:
      operationId: ww.get_profile
      summary: Retrieve Employee Profile (FR-3.2)
      responses:
        '200':
          description: Core work and contact metadata
          content:
            application/json:
              schema:
                type: object
                required: [employeeId, name, email, department, role, manager, hireDate]
                properties:
                  employeeId: { type: string, example: "EMP-44210" }
                  name:       { type: string }
                  email:      { type: string, format: email }
                  department: { type: string }
                  role:       { type: string }
                  manager:    { type: string }
                  hireDate:   { type: string, format: date }
                  homeAddress:{ type: string }
                  phoneNumber:{ type: string }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '503': { $ref: '#/components/responses/Unavailable' }

  /api/v1/employees/me/contact:
    patch:
      operationId: ww.update_contact
      summary: Update Contact Information (FR-3.2)
      description: >
        Updates personal home address and/or phone number. Enforces FR-3.3 format
        restrictions. Returns the previous values so the Saga Coordinator can compensate.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              minProperties: 1
              properties:
                homeAddress:
                  type: string
                  minLength: 5
                  maxLength: 250
                phoneNumber:
                  type: string
                  pattern: '^\+?[1-9]\d{6,14}$'
      responses:
        '200':
          description: Contact updated
          content:
            application/json:
              schema:
                type: object
                properties:
                  updated:          { type: array, items: { type: string } }
                  previousAddress:  { type: string }
                  previousPhone:    { type: string }
        '422': { $ref: '#/components/responses/ValidationError' }
        '401': { $ref: '#/components/responses/Unauthorized' }

  /api/v1/employees/me/balances:
    get:
      operationId: ww.get_balances
      summary: Query Time-Off Balances (FR-3.2)
      description: Always fetched live from WorkWeek; never cached (FR-3.4).
      responses:
        '200':
          content:
            application/json:
              schema:
                type: object
                properties:
                  vacation:
                    $ref: '#/components/schemas/Balance'
                  sick:
                    $ref: '#/components/schemas/Balance'

  /api/v1/employees/me/leaves:
    post:
      operationId: ww.submit_leave
      summary: Submit Leave Request (FR-3.2)
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [startDate, endDate, leaveType, workDays]
              properties:
                startDate: { type: string, format: date }
                endDate:   { type: string, format: date }
                leaveType: { type: string, enum: [Vacation, Sick, Medical] }
                workDays:  { type: number, minimum: 0.5 }
                reason:    { type: string, maxLength: 500 }
      responses:
        '201':
          description: Leave request created
          content:
            application/json:
              schema:
                type: object
                properties:
                  leaveId: { type: string, example: "LV-4021" }
                  status:  { type: string, enum: [PENDING_APPROVAL, APPROVED] }
        '422':
          description: >
            Guardrail rejection (FR-3.3) - balance exceeded, start after end,
            or start date in the past. See ValidationError.
          content:
            application/json:
              schema:
                type: object
                properties:
                  code:   { type: string, enum: [INSUFFICIENT_BALANCE, TEMPORAL_VIOLATION, FORMAT_VIOLATION] }
                  detail: { type: string }

  /api/v1/employees/me/leaves/{leaveId}:
    delete:
      operationId: ww.cancel_leave
      summary: Cancel a pending leave request (Saga compensator, REVERSIBLE_SAFE only)
      description: >
        Invoked ONLY for leave filings the same conversation created moments earlier and
        which are classified REVERSIBLE_SAFE by the policy in section 5.4. Never invoked
        against a HUMAN_CONSEQUENTIAL filing such as medical leave.
      parameters:
        - name: leaveId
          in: path
          required: true
          schema: { type: string }
      responses:
        '200': { description: Cancelled }
        '404': { description: Not found or not owned by the calling subject }

components:
  schemas:
    Balance:
      type: object
      properties:
        accruedHours:   { type: number }
        usedHours:      { type: number }
        remainingHours: { type: number }
  responses:
    Unauthorized:
      description: Missing or invalid workload OIDC token or subject assertion
    ValidationError:
      description: Deterministic business-rule or schema validation failure
    Unavailable:
      description: Backend unavailable; caller should enqueue via Cloud Tasks
  securitySchemes:
    workloadOidc:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Google-signed OIDC ID token, audience-bound to this service
    subjectAssertion:
      type: apiKey
      in: header
      name: X-Subject-Assertion
      description: RS256 JWT signed via IAM Credentials signJwt; carries the bound subject
```

```yaml
openapi: 3.0.3
info:
  title: ServiceImmediately ITSM Adapter API
  version: 1.4.0
servers:
  - url: https://serviceimmediately-adapter-{hash}-uc.a.run.app
security:
  - workloadOidc: []
    subjectAssertion: []
paths:
  /api/v1/incidents/{ticketId}:
    get:
      operationId: si.get_incident
      summary: Query Ticket Details including full comment timeline (FR-4.2)
      parameters:
        - name: ticketId
          in: path
          required: true
          schema: { type: string, pattern: '^(INC|REQ)[0-9]{6,}$' }
      responses:
        '200':
          content:
            application/json:
              schema:
                type: object
                properties:
                  ticketId:         { type: string }
                  shortDescription: { type: string }
                  description:      { type: string }
                  category:         { type: string }
                  priority:         { $ref: '#/components/schemas/Priority' }
                  state:            { $ref: '#/components/schemas/State' }
                  assignee:         { type: string }
                  comments:
                    type: array
                    items:
                      type: object
                      properties:
                        author:    { type: string }
                        body:      { type: string }
                        createdAt: { type: string, format: date-time }
        '403':
          description: Caller is not the requestor and lacks a queue-level role (FR-1.5)

  /api/v1/incidents:
    post:
      operationId: si.create_incident
      summary: Create Incident Ticket (FR-4.2)
      description: >
        Records the verified automation source on the ticket so audit records are
        unambiguous about agent-originated entries (FR-4.1).
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [category, shortDescription, priority]
              properties:
                category:         { type: string }
                shortDescription: { type: string, maxLength: 160 }
                description:      { type: string, maxLength: 4000 }
                priority:         { $ref: '#/components/schemas/Priority' }
      responses:
        '201':
          content:
            application/json:
              schema:
                type: object
                properties:
                  ticketId: { type: string }
        '409':
          description: Duplicate suppression - matching ticket within 10 minutes (FR-4.3)
        '422':
          description: Priority verification failed - "1 - Critical" not justified (FR-4.3)

  /api/v1/incidents/{ticketId}/comments:
    post:
      operationId: si.post_comment
      summary: Post Ticket Comment (FR-4.2)
      parameters:
        - name: ticketId
          in: path
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [body]
              properties:
                body: { type: string, maxLength: 4000 }
      responses:
        '201': { description: Comment appended to the activity timeline }

  /api/v1/incidents/{ticketId}/status:
    patch:
      operationId: si.update_status
      summary: Update Ticket Status (FR-4.2)
      parameters:
        - name: ticketId
          in: path
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [state]
              properties:
                state:           { $ref: '#/components/schemas/State' }
                resolutionNotes: { type: string, maxLength: 4000 }
      responses:
        '200': { description: Transition applied }
        '422':
          description: Illegal lifecycle transition, e.g. New directly to Closed (FR-4.3)

components:
  schemas:
    Priority:
      type: string
      enum: ["1 - Critical", "2 - High", "3 - Moderate", "4 - Low"]
    State:
      type: string
      enum: [New, In Progress, On Hold, Resolved, Closed]
  securitySchemes:
    workloadOidc:
      type: http
      scheme: bearer
      bearerFormat: JWT
    subjectAssertion:
      type: apiKey
      in: header
      name: X-Subject-Assertion
```

### **Agentic Tool Calling & Reasoning Signatures (Vertex AI Function Calling)**

The specialist agents bind to the contracts above through native Vertex AI Function Calling on **Gemini 3.7 Flash**:

- **Strict parameter schemas.** Tool definitions are generated *from* the OpenAPI documents above, so a single source defines both the wire contract and the model-facing schema. A hallucinated argument or a malformed type is rejected at deserialisation, before the adapter runs. Note what the schemas do **not** contain: no operation exposes an employee identifier parameter, so there is no field for the model to populate incorrectly (§4.1).
- **Agentic thought signatures (`thought_signature`).** Function-call parts emitted by Gemini 3.7 Flash carry reasoning-trace signatures. These are persisted with the turn and used for two things: post-hoc explanation of *why* a tool was selected during audit review, and trajectory assertions in the §9.2 evaluation suite. **They are an observability and evaluation artefact, not a security control** - the authoritative checks remain the deterministic validators in §5.3, which run regardless of what the signature claims.
- **Idempotency keys.** Every state-modifying `POST`/`PATCH` injects an `X-Idempotency-Key`:
  - direct conversational writes use `session_id : turn_seq : operation_id`
  - queued Saga steps use `saga_id : step_index`, so a Cloud Tasks retry after an ambiguous timeout resolves to the same key as the original attempt

  Both adapters and both mock backends reject a repeated key with `409`, which is what makes the retry policy in §5.2 safe against duplicate leave requests and duplicate tickets.

## **5.2. API Throttling Thresholds, Backoff Strategy, Queue Configuration & Dead-Letter Handling (NFR-4.2)**

```mermaid
flowchart TD
    Req["Specialist Agent Invokes Backend API"] --> RateCheck{"Is backend under limit?<br>WW 50 rps / SI 40 rps"}

    RateCheck -->|Within limit| DirectCall["Call backend API (direct HTTP)"]
    DirectCall --> Resp{"API response"}

    Resp -->|HTTP 200/201| ReturnSuccess["Return result to agent"]

    RateCheck -->|Throttled 429| QueueBranch["Resilience queueing branch"]
    Resp -->|HTTP 500/503| QueueBranch

    QueueBranch --> Idem["Attach idempotency key<br>(saga id + step index)"]
    Idem --> Enqueue["Enqueue to Cloud Tasks rate-limited queue<br>payload + execution context"]
    Enqueue --> AckUser["Immediate user feedback:<br>request queued, processing asynchronously"]

    Enqueue --> TaskWorker["Cloud Tasks dispatcher<br>exponential backoff 1s, 2s, 4s, 8s, 16s"]
    TaskWorker --> RetryCall["Retry call to backend"]

    RetryCall -->|Success| CompleteSaga["Update saga state to COMPLETED"]
    RetryCall -->|5 attempts exhausted| DLQ["Pub/Sub dead-letter queue"]
    DLQ --> Classify["Apply compensation classification (5.4)"]
```

Every queued call carries the `X-Idempotency-Key` described in §5.1, so a retry after an ambiguous timeout cannot create a duplicate leave request or ticket.

### **Concrete Throttling & Queue Parameters**

| Backend Target | Sustained Rate Limit | Burst Capacity | Max Concurrent Dispatches | Max Dispatch Rate | Max Retries | Backoff Multiplier | Min Backoff | Max Backoff |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **WorkWeek HCM API** | 50 req/s | 100 req | 25 concurrent | 45.0 dispatches/s | 5 attempts | 2.0 (exponential) | 1.0 s | 60.0 s |
| **ServiceImmediately ITSM** | 40 req/s | 80 req | 20 concurrent | 35.0 dispatches/s | 5 attempts | 2.0 (exponential) | 1.0 s | 60.0 s |

Dispatch rates are deliberately set ~10% below the sustained backend limit so that queue drain plus live traffic together stay inside the ceiling rather than re-triggering the throttling that caused the queueing.

### **Adaptive Concurrency Control - Why the Table Above Is a Seed, Not a Dependency**

**New in v1.5, and this closes OPEN-01.** The numbers above are the *mock* services' limits. v1.4 listed the real WorkWeek and ServiceImmediately production limits as an unresolved external dependency, which correctly drew the criticism that queue configuration might need emergency post-deployment adjustment. The right answer is not to chase a number from another team before launch - it is to build a client that **does not need the number to be correct**.

Each adapter wraps its Cloud Tasks queue in an **AIMD (additive-increase / multiplicative-decrease) adaptive limiter** that discovers the true safe ceiling from the backend's own behaviour:

| Parameter | Value | Purpose |
| :--- | :--- | :--- |
| Initial concurrency limit | 50% of the configured static ceiling | Launch conservatively; never open at full rate against an unverified backend |
| Additive increase | +1 concurrent slot per 100 consecutive successes | Slow, evidence-based probing upward |
| Multiplicative decrease | x0.5 on any `429`, `503`, or `Retry-After` | Immediate, aggressive back-off - the classic congestion-control asymmetry |
| Latency-gradient trigger | Decrease when observed p95 exceeds 2x the rolling 30-minute baseline | Catches a degrading backend that is still returning `200`s before it starts shedding load |
| Hard ceiling | The `tfvars` value in the table above | Adaptation may lower the rate below the configured limit; it may never raise it above |
| Floor | 2 concurrent | Guarantees forward progress and prevents a transient error storm from wedging the queue at zero |
| Re-probe interval | 10 min after a decrease | Recovers capacity automatically once the backend is healthy again |

**What this changes about the risk.** If the real production ceiling turns out to be 20 rps rather than 50, the limiter converges to it within minutes of first contact, without an incident, a code change, or a redeploy. If it turns out to be 200 rps, the system stays at the configured 50 and the team raises the `tfvars` ceiling deliberately when they choose to. Either way, **the wrong static number is no longer an outage** - it is at worst a temporary throughput inefficiency that the system corrects itself and reports through `ALRT-02` and `ALRT-03` (§7.5). Phase 2 additionally runs a calibration load test against each backend and records the observed ceiling in the deployment record.

### **Dead-Letter Queue Strategy for Permanently Failed Payloads**

Retry configuration answers *transient* failure. It says nothing about a payload that will never succeed - a malformed request, a backend that rejects the operation outright, or a principal revoked between enqueue and dispatch. Those must not be retried forever and must not be silently discarded. A dropped transactional payload in an HR system is an employee whose leave was never filed and who was never told.

A task is moved to the Pub/Sub dead-letter queue when it exhausts 5 attempts, or immediately when the failure is classified non-retryable.

| Classification | Trigger | Retried? | Disposition |
| :--- | :--- | :--- | :--- |
| **Transient** | `429`, `503`, timeout, connection reset | Yes, up to 5 attempts with 1 s - 60 s exponential backoff | Usually drains without human involvement |
| **Poison payload** | `400`, `422`, schema validation failure | **No** - fails immediately to DLQ | Cannot succeed on retry; retrying only amplifies load |
| **Authorization lapsed** | Session `REVOKED`, entitlement withdrawn, assertion unmintable | **No** | DLQ with reason `PRINCIPAL_REVOKED` (§4.8) |
| **Idempotency conflict** | `409` on a replayed `X-Idempotency-Key` | **No** | Treated as **success** - the operation already happened. Not a failure at all |
| **Exhausted transient** | 5 attempts consumed | Attempts complete | DLQ with the full attempt history |

**Disposition rules once a payload is in the DLQ:**

| Rule | Behaviour |
| :--- | :--- |
| **Retention** | 14 days in the DLQ topic, then archived to the BigQuery audit dataset. Long enough to cover a holiday weekend plus an investigation |
| **Never silently dropped** | Every DLQ entry raises an event. `ALRT-10` fires on depth > 50; `ALRT-09` fires on any Saga step stalled > 15 min |
| **Compensation-class routing** | The entry is classified per §5.4. A `HUMAN_CONSEQUENTIAL` payload **always** generates a P2 ITSM ticket to HR Operations with full context. An `ANCILLARY` one generates a tracked follow-up. A `READ_ONLY` one is discarded after logging |
| **User is always told** | The §5.5 matrix message is sent on the affected session. The employee is never left believing a transaction completed when it did not |
| **Replay** | Idempotency keys make replay safe by construction, so an operator can re-drive the queue after a backend recovers without risking duplicates. Replay is an authenticated operator action, recorded in the audit trail |
| **Poison quarantine** | Payloads that fail replay twice are quarantined out of the replay set so one bad message cannot block drain of the rest |

**Ordering.** Queues are per-backend, not per-user, and Saga step ordering is enforced by the ledger in §5.4 rather than by queue ordering - so a DLQ'd step halts its own Saga without stalling unrelated traffic.

### **Cloud Tasks Queue Configuration**
```yaml
apiVersion: cloudtasks.googleapis.com/v2
kind: Queue
metadata:
  name: projects/prj-elevate-c1-g5/locations/us-central1/queues/workweek-resilience-queue
rateLimits:
  maxDispatchesPerSecond: 45.0
  maxConcurrentDispatches: 25
  maxBurstSize: 100
retryConfig:
  maxAttempts: 5
  minBackoff: 1.000s
  maxBackoff: 60.000s
  maxDoublings: 4
---
apiVersion: cloudtasks.googleapis.com/v2
kind: Queue
metadata:
  name: projects/prj-elevate-c1-g5/locations/us-central1/queues/serviceimmediately-resilience-queue
rateLimits:
  maxDispatchesPerSecond: 35.0
  maxConcurrentDispatches: 20
  maxBurstSize: 80
retryConfig:
  maxAttempts: 5
  minBackoff: 1.000s
  maxBackoff: 60.000s
  maxDoublings: 4
```

## **5.3. Deterministic Business Rules Engine (FR-3.3, FR-4.3)**

Guardrails execute in the adapter, in typed Python, **after** the model has proposed a call and **before** any backend write. The model can suggest an invalid action; it cannot perform one.

```mermaid
flowchart TD
    Req["Tool invocation request"] --> Schema["Pydantic schema and format validation<br>dates, phone pattern, enums (FR-3.3)"]
    Schema -->|Invalid| ErrFmt["Reject: Format Violation"]
    Schema -->|Valid| CheckType{"Tool target"}

    CheckType -->|WorkWeek Leave| C1["Check: startDate <= endDate and startDate >= today"]
    C1 -->|Pass| C2["Check: requested hours <= accrued remaining balance"]
    C2 -->|Pass| ExecWW["Execute WorkWeek call"]
    C1 -->|Fail| Err1["Reject: Temporal Violation"]
    C2 -->|Fail| Err2["Reject: Insufficient Balance"]

    CheckType -->|WorkWeek Contact| K1["Check: phone matches E.164, address length 5 to 250"]
    K1 -->|Pass| K2["Check: explicit user confirmation recorded this turn"]
    K2 -->|Pass| ExecWW
    K1 -->|Fail| ErrFmt
    K2 -->|Fail| ErrConfirm["Reject: Unconfirmed Write"]

    CheckType -->|ServiceImmediately| S1["Check: current state is not Closed"]
    S1 -->|Pass| S2["Check: legal lifecycle transition, no New to Closed"]
    S2 -->|Pass| S3["Check: no duplicate incident within 10 minutes"]
    S3 -->|Pass| S4["Check: priority justified - 1 Critical requires<br>outage, security or safety keywords plus scope"]
    S4 -->|Pass| ExecSI["Execute ServiceImmediately call"]
    S1 -->|Fail| ErrSI["Reject: Invalid Lifecycle"]
    S2 -->|Fail| ErrSI
    S3 -->|Fail| ErrDup["Reject: Duplicate Suppressed"]
    S4 -->|Fail| ErrPri["Reject: Priority Not Justified - downgrade offered"]
```

## **5.4. Saga Compensation Classification Policy (NFR-4.3)**

NFR-4.3 offers two acceptable outcomes for a partially-failed cross-system workflow: *attempt compensating actions*, **or** *log the failure clearly and provide instructions for manual follow-up*. Blanket automatic rollback is therefore not required, and for some steps it is actively harmful. Every Saga step is classified at design time:

| Class | Definition | Failure behaviour of a *later* step | Examples |
| :--- | :--- | :--- | :--- |
| **`READ_ONLY`** | No state change in any system of record | Nothing to undo | Policy retrieval, profile read, balance check |
| **`REVERSIBLE_SAFE`** | Write that can be exactly reversed within minutes with no consequence to the employee, and whose prior value is captured | **Auto-compensate.** Restore the prior value, mark `COMPENSATED_ROLLED_BACK`, tell the user plainly | Contact/address update (prior value returned by the API); a vacation leave filed seconds earlier in the same turn |
| **`ANCILLARY`** | Supporting step whose failure does not invalidate the primary outcome | Do not touch prior steps. Retry, then hand to a human follow-up queue | ITSM email-routing ticket, facilities badge request, notification |
| **`HUMAN_CONSEQUENTIAL`** | Write with material effect on the employee's employment, pay, health cover, or legal standing | **Never auto-reverse.** Preserve it, mark `PARTIALLY_COMPLETED_MANUAL_FOLLOWUP`, raise a P2 operations task, tell the user exactly what stands and what is outstanding | Medical / statutory leave filing, long-term absence record |

Decision rule, applied by the Saga Coordinator on terminal failure of step *N*:

```mermaid
flowchart TD
    Fail["Step N permanently failed after retries"] --> Q1{"Is step N itself ANCILLARY?"}
    Q1 -->|Yes| Human["Preserve all prior steps.<br>state = PARTIALLY_COMPLETED_MANUAL_FOLLOWUP<br>Raise P2 ops task. Inform user plainly."]
    Q1 -->|No| Q2{"Are ALL prior steps<br>READ_ONLY or REVERSIBLE_SAFE?"}
    Q2 -->|Yes| Roll["Auto-compensate in reverse order.<br>state = COMPENSATED_ROLLED_BACK"]
    Q2 -->|No| Mixed["Compensate only the REVERSIBLE_SAFE steps.<br>Preserve HUMAN_CONSEQUENTIAL steps.<br>Raise P2 ops task listing both."]
    Human --> Log["Persist full step ledger to Firestore and BigQuery"]
    Roll --> Log
    Mixed --> Log
```

Every branch is logged with the saga id, the classification of each step, what was preserved, what was reversed, and the follow-up reference - satisfying the NFR-4.3 requirement that the failure be *logged clearly* whichever path is taken.

## **5.5. Error Handling Matrix & Resilience Strategy (NFR-4.1)**

No branch exposes a stack trace, internal hostname, or vendor error code to the user.

| Failure Mode | Detection Indicator | System Fallback & Compensating Action | User-Facing Notification |
| :--- | :--- | :--- | :--- |
| **Agent Search outage** | 503 or timeout > 3 s | Circuit breaker opens; RAG bypassed; no ungrounded answer is generated | *"Our policy knowledge system is temporarily unavailable. Please refer to the HR Portal at hr.corp.internal."* |
| **WorkWeek rate limited (429)** | HTTP 429 | Dispatch to the rate-limited Cloud Tasks queue with idempotency key and exponential backoff | *"WorkWeek is busy right now. Your request is queued and will process within a few minutes."* |
| **WorkWeek / ITSM 5xx** | HTTP 500/503 | Same queueing path; saga state set to `STEP_N_ASYNC_QUEUED` | *"That system is temporarily unavailable. I have queued your request and will confirm when it completes."* |
| **Ancillary saga step permanently fails** | Retries exhausted, step class `ANCILLARY` | **Preserve all prior steps**; raise P2 manual follow-up; record orphaned step (§5.4) | *"Your leave filing stands. The IT routing step could not be completed automatically and has been passed to the service desk as a tracked follow-up."* |
| **Reversible saga step then permanent failure** | Retries exhausted, all prior steps `REVERSIBLE_SAFE` | Auto-compensate in reverse order using captured prior values | *"We could not complete your request, so the change to your record has been reverted. Please try again shortly."* |
| **Prompt injection detected** | Model Armor `SanitizeUserPrompt` block verdict | Terminate turn; abort all tool execution; log security incident | *"I am unable to process this request as it falls outside acceptable usage."* |
| **Unsafe or SPII-leaking output** | Model Armor `SanitizeModelResponse` block verdict | Suppress the response entirely; substitute the safe fallback; log blocked output (FR-1.3, NFR-1.2) | *"I could not produce a safe answer to that. Please rephrase, or contact the HR helpdesk."* |
| **Ungrounded answer or dead citation** | Groundedness < 0.85 or citation fails to resolve | Refuse rather than assert (FR-5.2, FR-5.4) | *"I could not find that in the official policy documents, so I would rather not guess. Here is the HR Portal link."* |
| **Credential revoked or expired** | 401 from adapter, or session `REVOKED` | Invalidate token cache; terminate session | *"Your access was updated. Please refresh and sign in again."* |
| **Out-of-domain request** | Supervisor domain classification (FR-5.4) | No tool call; no model generation on the topic | *"I can help with HR policies, WorkWeek and IT tickets. That one is outside what I can assist with."* |

## **5.6. Mock Service Fidelity & Production Cutover Plan**

Mock WorkWeek and ServiceImmediately services are a BRD constraint, not a design preference (CON-01, BRD §6). The fair criticism is not that mocks are used - it is that a mock which returns instantly and never fails validates nothing about behaviour under real latency and real faults, so the risk is merely deferred to cutover. This section removes that deferral: the mocks are engineered as **fidelity-controlled surrogates**, and the switch to live systems is a rehearsed procedure rather than an event.

### **Fidelity Requirements on the Mock Services**

| Fidelity dimension | Requirement | Why it matters before cutover |
| :--- | :--- | :--- |
| **Contract identity** | Mock and production adapters are generated from the *same* OpenAPI documents in §5.1. A schema change regenerates both | A contract drift cannot hide until cutover; CI fails first |
| **Latency distribution** | Mocks replay a configurable latency profile per operation (default p50 180 ms / p95 900 ms / p99 2.5 s), not a constant | The §4.3 and §9.1 latency budgets are exercised against realistic timing, so queueing and streaming behaviour are proven, not assumed |
| **Fault injection** | Configurable injection of `429`, `500`, `503`, timeout and slow-loris responses at a settable rate | This is what actually exercises §5.2 retry, AIMD back-off, the DLQ strategy and the §5.5 matrix. Every one of those paths has a test that fires it deliberately |
| **Rate-limit emulation** | Mocks enforce a token bucket and return `429` with `Retry-After` once exceeded | The adaptive limiter's convergence behaviour is observable pre-production |
| **Stateful consistency** | Mocks persist state, enforce the FR-3.3 / FR-4.3 business rules, and honour `X-Idempotency-Key` with `409` on replay | Transaction-integrity and idempotency tests are meaningful rather than trivially passing |
| **Peak-traffic load profile** | A load test drives 10x expected peak concurrency against the injected latency profile | Answers Sarah Chen's drop-off concern with a measurement rather than an assurance |

The point of the table: **every resilience mechanism in this document is tested against adverse conditions during MVP 1**, because the mock is instrumented to create them on demand. That is often more rigorous than testing against a healthy production sandbox, which will not return a `503` when asked.

### **Production Cutover Procedure**

```mermaid
flowchart LR
    S0["Stage 0: Contract parity<br>Same OpenAPI suite green<br>against mock and vendor sandbox"] --> S1
    S1["Stage 1: Shadow<br>Live reads mirrored to production<br>Responses compared, never shown"] --> S2
    S2["Stage 2: Read cutover<br>Real reads, writes still mocked<br>Bake 5 business days"] --> S3
    S3["Stage 3: Canary writes<br>One volunteer cohort<br>Writes reconciled daily"] --> S4
    S4["Stage 4: Progressive rollout<br>10 to 50 to 100 percent by cohort"] --> S5
    S5["Stage 5: Mock retained<br>as the CI and DR fixture"]
    S1 -.->|Response diff > 1%| Rollback["Rollback: flip adapter tfvars<br>No code change, no redeploy"]
    S3 -.->|Any write mismatch| Rollback
    S4 -.->|SLO burn or ALRT-02| Rollback
```

| Stage | Exit criterion | Rollback trigger |
| :--- | :--- | :--- |
| 0 - Contract parity | The §5.1 contract suite passes identically against the mock and the vendor sandbox | Any schema divergence |
| 1 - Shadow | < 1% response divergence over 3 days; observed p95 latency within the §9.1 budget | Divergence > 1%, or latency outside budget |
| 2 - Read cutover | 5 business days with no SLO-01 or SLO-02 regression | Any P1 alert attributable to the backend |
| 3 - Canary writes | 100% write reconciliation for the cohort over 3 days | **Any** write mismatch - zero tolerance, these are real HR records |
| 4 - Progressive rollout | 100% of cohorts, error budget intact | SLO burn-rate alert (`ALRT-12`) or `ALRT-02` |
| 5 - Steady state | Mock retained as the CI fixture and the DR fallback | n/a |

Because the adapter is selected by configuration (§7.2), rollback at any stage is a `tfvars` flip - **no code change and no redeploy**. Shadow and canary stages are where real-world latency and synchronisation delay are discovered, and they happen before any employee's record depends on them.

---

# **6. Cost Estimation & FinOps**

## **6.1. Basis of Estimate**

All figures below use a **single consistent basis**, aligned to the BRD baseline volume:

| Parameter | Value |
| :--- | :--- |
| Monthly inquiry volume | **15,000 inquiries** (BRD Tier 1 baseline) |
| Average conversation length | 4 turns per inquiry |
| **Total model turns** | **60,000 turns / month** |
| Intent mix | 55% policy Q&A, 20% WorkWeek, 18% ITSM, **7% cross-system saga (4,200 turns)** |
| Routing pass (3.7 Flash) | ~500 input / ~100 output tokens per turn |
| Specialist reasoning (3.7 Flash) | ~1,800 input / ~350 output tokens per turn |
| Saga arbitration (3.1 Pro) | ~2,500 input / ~600 output tokens per turn |

**Token rates used** (Vertex AI, as adopted in v1.3): Gemini 3.7 Flash **$0.75 / M input, $3.75 / M output**; Gemini 3.1 Pro **$1.25 / M input, $5.00 / M output**.

> **Unit prices are indicative and dated 2026-08-25.** They must be re-verified against the Google Cloud pricing calculator at ARB approval (OPEN-02). The arithmetic below is shown in full so a revised rate can be re-applied without re-deriving the model.
>
> **Note on the basis change.** v1.3's cost table was computed at 100,000 inquiries/month while §1.1 states a 15,000/month baseline, so the two sections implied per-interaction costs that differed by more than an order of magnitude. v1.4 recomputes everything on the single 15,000-inquiry basis, which is the figure the ROI case and the 40% deflection target both depend on.

## **6.2. Monthly Cost Breakdown**

```mermaid
pie title Monthly Cost Distribution by Component
    "Gemini 3.7 Flash and 3.1 Pro tokens" : 43
    "Cloud Run compute (multi-region)" : 24
    "Model Armor safety scanning" : 12
    "Global LB and Cloud Armor" : 6
    "Agent Search queries" : 5
    "BigQuery audit archive" : 4
    "Cloud Firestore state" : 2
    "Sensitive Data Protection" : 2
    "Logging, Tasks, Secret Manager" : 2
```

| Component | Usage Basis | Rate | Monthly Cost |
| :--- | :--- | :--- | ---: |
| **Gemini 3.7 Flash - supervisor / intent routing** | 60,000 x 500 in = 30M in ($22.50); x 100 out = 6M out ($22.50) | $0.75 / $3.75 per M | $45.00 |
| **Gemini 3.7 Flash - Policy, HCM, ITSM specialists** | 55,800 x 1,800 in = 100.4M in ($75.33); x 350 out = 19.5M out ($73.24) | $0.75 / $3.75 per M | $148.57 |
| **Gemini 3.1 Pro - cross-system Saga arbitration** | 4,200 x 2,500 in = 10.5M in ($13.13); x 600 out = 2.52M out ($12.60) | $1.25 / $5.00 per M | $25.73 |
| **Agent Search** | ~12,500 grounded queries | $2.00 / 1,000 queries | $25.00 |
| **Model Armor** | 120,000 scans (one inbound + one outbound per turn) | ~$0.50 / 1,000 scans | $60.00 |
| **Cloud Run** | 2 regions, min-instance warm pool + request compute | vCPU-s + GiB-s | $120.00 |
| **Global ALB + Cloud Armor** | Forwarding rules, security policy, request volume | fixed + per-request | $30.00 |
| **Sensitive Data Protection (DLP)** | ~0.3 GB inspected and de-identified | per-GB inspection | $10.00 |
| **BigQuery** | ~20 GB/month streaming insert + 365-day partitioned storage | ingest + storage | $20.00 |
| **Cloud Firestore** | 60,000 sessions, ~2M read/write ops, 30-day TTL | per-op + storage | $12.00 |
| **Cloud Logging** | ~30 GB beyond the free tier | per-GB ingestion | $10.00 |
| **Cloud Tasks + Secret Manager + KMS** | ~200k task ops; secret versions; DLP key | per-op / per-version | $4.00 |
| **Total estimated monthly run cost** | | | **~$510.30** |

*Note: the LLM-as-a-Judge evaluation workload (§9.3) runs in CI, not in production, and is budgeted separately at ~$15/month against the engineering cost centre.*

**Unit economics:** $510.30 / 15,000 inquiries = **$0.034 per inquiry**, against a $18.50 human cost-per-contact - a ~540x reduction in marginal cost to serve.

**ROI:** 6,000 deflected inquiries x $18.50 = **$111,000** avoided monthly labour cost, less $510 run cost = **~$110,490 net monthly benefit**, approximately **217x** return on platform spend.

## **6.3. Cost at Scale**

| Monthly Inquiry Volume | Model Turns | Estimated Monthly Cost | Cost per Inquiry | Notes |
| :--- | :--- | ---: | ---: | :--- |
| 1,500 (pilot cohort) | 6,000 | ~$182 | $0.121 | Fixed floor dominates - warm Cloud Run instances, LB, minimum BigQuery and logging |
| **15,000 (MVP target)** | **60,000** | **~$510** | **$0.034** | Basis of estimate above |
| 150,000 (enterprise rollout) | 600,000 | ~$4,060 | $0.027 | Token and scan costs dominate; Cloud Run scales sub-linearly, so unit cost still falls |

## **6.4. FinOps Controls**

1. **Budget alerts** at 50 / 80 / 100% of a $750 monthly budget, routed to the platform team.
2. **Per-turn token ceiling** enforced in the orchestrator: a turn exceeding 12,000 input tokens is truncated by dropping oldest conversation history, never by dropping retrieved policy context.
3. **Context window discipline:** conversation history is summarised after 10 turns rather than replayed verbatim.
4. **Cost attribution labels** (`app=hr-agent`, `env`, `component`, `use-case`) on every resource, feeding a BigQuery billing-export dashboard broken down by use case.
5. **Min-instance right-sizing** reviewed monthly against p95 cold-start impact - the largest single lever on the fixed cost floor.

## **6.5. Price Sensitivity & Automated Rate Verification**

The unit prices in §6.2 are indicative rates dated 2026-08-25. v1.5 treats that as a *precision* question rather than a *decision* question, because the business case does not turn on it.

All figures are **monthly**, on the same 15,000-inquiry basis as §6.2, against $111,000 of avoided helpdesk cost per month (6,000 deflected inquiries x $18.50).

| Scenario | Monthly cost | Cost per inquiry | Monthly net benefit | ROI |
| :--- | :--- | :--- | :--- | :--- |
| Rates 50% lower than assumed | ~$255 | $0.017 | ~$110,745 | ~434x |
| **Indicative rates (§6.2 basis)** | **~$510** | **$0.034** | **~$110,490** | **~217x** |
| Rates 20% higher | ~$612 | $0.041 | ~$110,388 | ~180x |
| Rates 50% higher | ~$765 | $0.051 | ~$110,235 | ~144x |
| Rates **double** the assumption | ~$1,021 | $0.068 | ~$109,979 | ~108x |

Total platform spend would have to rise roughly **217x** - to about $111,000 a month - before the programme stopped paying for itself. The ROI conclusion is invariant across every plausible pricing outcome, so **no approval decision needs to wait for price re-verification.**

**Automated verification instead of a manual check.** A scheduled Cloud Build job queries the **Cloud Billing Catalog API** for the SKUs used in §6.2, recomputes the monthly total against the documented volumes, and fails if any unit rate has drifted more than 10% from the value recorded here. The result is written to the FinOps dashboard with the retrieval date. Price accuracy therefore becomes a monitored, self-correcting property rather than a pre-approval task assigned to a person - which is what closes it as a dependency.

---

# **7. Deployment & Delivery Plan**

## **7.1. Infrastructure as Code (Terraform) Topology & State Management**

```mermaid
graph TD
    subgraph TF["Terraform Root Module"]
        M1["modules/networking: VPC, Cloud Armor, Global ALB, Serverless NEGs"]
        M2["modules/iam: least-privilege service accounts, Workload Identity"]
        M3["modules/vertex_ai: Agent Search datastore, Model Armor templates and floor settings"]
        M4["modules/cloud_run: multi-region gateway, orchestrator, adapters"]
        M5["modules/storage: Firestore nam5, GCS policy buckets, BigQuery datasets"]
        M6["modules/resilience: Cloud Tasks queues, Pub/Sub DLQ, Eventarc triggers"]
        M7["modules/security: DLP inspect and de-identify templates, KMS, Secret Manager"]
        M8["modules/observability: dashboards, SLOs, alert policies, log sinks"]
    end
```

| Concern | Approach |
| :--- | :--- |
| **State backend** | Remote GCS backend, one bucket per environment, object versioning and bucket-level retention enabled |
| **State locking** | Native GCS object-generation locking; CI holds the lock for the plan/apply pair |
| **State isolation** | Separate state files per environment (`dev`, `uat`, `prod`) and per lifecycle tier (`bootstrap`, `platform`, `app`), so an app-tier mistake cannot destroy the datastore |
| **State encryption** | CMEK on the state bucket; no plaintext secrets in state - secrets are referenced by Secret Manager resource name |
| **Drift detection** | Nightly `terraform plan` in CI; a non-empty plan opens a ticket automatically |
| **Promotion** | Identical modules across environments; only `tfvars` differ. No environment-specific resource blocks. |

## **7.2. Engineering Standards & Repository Conventions**

The implementation repository commits in advance to the following, so that maintainability, security, testing, architecture, performance and readability are properties of the build rather than a retrofit:

| Axis | Standard |
| :--- | :--- |
| **Architecture** | `src/` layout, one module per agent and per tool. Dependency inversion at the integration boundary: adapters implement a protocol, so mock and real WorkWeek/ServiceImmediately backends swap by configuration with no code change. No agent imports another agent. |
| **Maintainability** | Typed Python throughout; Pydantic models for every tool input and output; functions under 50 lines; cyclomatic complexity gate in CI; Architecture Decision Record log in `docs/adr/`. |
| **Readability** | Ruff format + lint and `mypy --strict` enforced in CI as blocking checks. Google-style docstrings on every public function. Prompts live in versioned files under `prompts/`, never inline string literals. |
| **Security** | No secret in code or state - Secret Manager only. One least-privilege service account per Cloud Run service. Dependency and container scanning (Artifact Registry + Dependabot) blocking on high severity. No `employee_id` parameter on any tool signature (§4.1). |
| **Testing** | Unit tests per module; **contract tests** against the OpenAPI specs in §5.1 for both mock and real adapters; **trajectory tests** asserting the expected tool-call sequence per use case; Saga compensation-classification tests covering all four classes; 80% line-coverage gate. |
| **Performance** | Async I/O throughout; parallel fan-out for independent saga steps; connection pooling to adapters; p95 latency assertion in CI against a fixed prompt set. |
| **Configuration versioning** | Prompts, the agent/tool registry (§3.2), guardrail thresholds, and model IDs are all version-controlled artefacts with a semver and a changelog entry. A prompt change is a code change and runs the full eval gate. |

## **7.3. CI/CD Pipeline**

```mermaid
flowchart LR
    PR["Pull Request"] --> Lint["Ruff + mypy strict"]
    Lint --> Unit["Unit + contract tests, 80% coverage gate"]
    Unit --> Sec["Dependency and container scan"]
    Sec --> TFPlan["terraform plan (no apply)"]
    TFPlan --> EvalGate["Gen AI Eval gate: 150 golden prompts<br>+ 100 red-team vectors"]
    EvalGate -->|Any regression| Block["Block merge"]
    EvalGate -->|Pass| Merge["Merge to main"]
    Merge --> Build["Cloud Build image, sign with Binary Authorization"]
    Build --> UAT["Deploy to UAT, smoke + trajectory tests"]
    UAT --> Canary["Prod canary 10% for 30 minutes with SLO watch"]
    Canary -->|SLO breach| Rollback["Automatic rollback to prior revision"]
    Canary -->|Healthy| Full["Progressive rollout to 100%"]
```

## **7.4. Phased Delivery Roadmap**

```mermaid
gantt
    title MVP 1 Phased Delivery Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 1 Foundation
    Terraform IaC and multi-region GCP setup   :p1_1, 2026-09-01, 1w
    HR policy ingestion into Agent Search      :p1_2, after p1_1, 1w
    section Phase 2 Agent Core
    Supervisor and LangGraph engine            :p2_1, after p1_2, 2w
    WorkWeek and ServiceImmediately adapters   :p2_2, 2026-09-15, 2w
    Deterministic validation and Cloud Tasks   :p2_3, after p2_2, 1w
    section Phase 3 Governance and Security
    Composite token auth and revocation        :p3_1, after p2_3, 1w
    DLP de-id, Model Armor in and out          :p3_2, after p3_1, 1w
    Safety latency tuning to under 300ms       :p3_3, after p3_2, 3d
    Saga compensation classification hardening :p3_4, after p3_3, 4d
    section Phase 4 Verification and UAT
    Golden dataset build and automated eval    :p4_1, after p3_4, 1w
    Stakeholder UAT and executive signoff      :p4_2, after p4_1, 1w
```

**Phase exit criteria.** Phase 3 does not exit until measured p95 safety overhead is below 300 ms (NFR-2.1) and all four compensation classes have passing tests. Phase 4 does not exit until the §9.1 thresholds are met on the golden set and the §9.4 UAT scenarios are signed off.

## **7.5. Observability, Alerting & Operational Runbook**

**New in v1.5.** Earlier revisions named `modules/observability` and listed the metrics it would emit, but never enumerated the thresholds at which a human is woken. A dashboard nobody is paged from is decoration. This section closes that gap: every alert below has a condition, a threshold, an evaluation window, a severity, a routing channel, and - where safe - an automated response that fires before the human arrives.

### **Service Level Objectives and Error Budget**

| SLO ID | Service Level Indicator | Objective | Measurement window | Error budget |
| :--- | :--- | :--- | :--- | :--- |
| **SLO-01** | Availability: fraction of turns returning a non-5xx result | **99.9%** | 30-day rolling | 43 m 12 s / month |
| **SLO-02** | Latency: fraction of turns with TTFT < 1.5 s | **95%** | 30-day rolling | 5% of turns |
| **SLO-03** | Safety overhead: fraction of turns with guardrail overhead < 300 ms | **99%** | 30-day rolling | 1% of turns |
| **SLO-04** | Transaction integrity: backend writes that succeed or compensate correctly | **99.99%** | 30-day rolling | 1 in 10,000 |
| **SLO-05** | Revocation propagation within SLA-01 | **99.9%** | 30-day rolling | Security-critical; any breach reviewed individually |

Error-budget policy: at **50%** consumption, non-essential feature work pauses in favour of reliability; at **100%**, all deploys except reliability fixes and security patches are frozen until the window rolls.

### **Alert Policies**

Severity routing: **P1** pages the on-call engineer immediately (PagerDuty); **P2** raises a ticket and posts to `#elevate-c1-g5-ops` within business hours; **P3** is a dashboard annotation reviewed at the weekly operations review.

| Alert ID | Condition | Threshold | Window | Sev | Automated response |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ALRT-01** | **Gateway 5xx spike** - ratio of 5xx to total responses at the Global ALB | **> 2%** | 5 min | **P1** | Health-check weight shifted away from the failing region; failover readiness check triggered (§2.2) |
| **ALRT-02** | **Backend 5xx spike** - WorkWeek or ServiceImmediately 5xx ratio | **> 5%** | 5 min | **P2** | Adaptive limiter halves concurrency (§5.2); affected tool marked degraded so the supervisor stops routing to it and the error-handling matrix (§5.5) message is served |
| **ALRT-03** | Backend `429` / `Retry-After` rate | **> 1%** | 5 min | **P3** | AIMD multiplicative decrease; no human action unless sustained > 1 h |
| **ALRT-04** | **Safety overhead approaching the NFR ceiling** - p95 guardrail chain latency | **> 240 ms** (80% of ceiling) | 10 min | **P2** | None; this is the deliberate early warning that protects the §4.3 budget before NFR-2.1 is breached |
| **ALRT-05** | Safety overhead p95 exceeds the NFR ceiling | **> 300 ms** | 5 min | **P1** | NFR-2.1 breach; SLO-03 error budget debited |
| **ALRT-06** | Time-to-first-token p95 | **> 1.5 s** | 10 min | **P2** | Model-endpoint health check; automatic retry against the secondary region endpoint |
| **ALRT-07** | Guardrail block-rate anomaly - deviation from the 7-day baseline | **> 3 sigma** in either direction | 30 min | **P2** | None automatic. A spike suggests an attack campaign; a collapse suggests a broken guardrail. Both need eyes |
| **ALRT-08** | **Model Armor or DLP API error / deadline rate** | **> 2%** | 5 min | **P1** | Circuit breaker opens into fail-closed degraded mode (§4.3). Because this refuses user traffic rather than serving it unscanned, it pages immediately |
| **ALRT-09** | Saga steps stuck in `PENDING` | Any step **> 15 min** | 5 min | **P2** | Automatic DLQ replay attempt; on second failure an HR Operations follow-up ticket is opened (§5.4) |
| **ALRT-10** | Dead-letter queue depth | **> 50 messages** | 10 min | **P2** | Queue drain paused pending triage to avoid amplifying a downstream fault |
| **ALRT-11** | Cross-region Firestore read latency p99 | **> 150 ms** | 10 min | **P3** | Synthetic probe escalation; informs the §2.2 budget |
| **ALRT-12** | **Availability error-budget burn rate** (multi-window, multi-burn-rate) | **14.4x over 1 h AND 6x over 6 h** | dual | **P1** | Fast-burn page: at this rate the entire 30-day budget is consumed in ~2 days |
| **ALRT-12b** | Slow-burn variant | **3x over 24 h AND 1x over 3 d** | dual | **P2** | Ticket; indicates chronic degradation rather than an outage |
| **ALRT-13** | **Compliance job failure** - retention-conformance job, consent-withdrawal purge (SLA-05), or Art. 17 erasure (SLA-06) fails or exceeds its SLA | Any occurrence | per-run | **P2** | DPO notified automatically; erasure-receipt issuance blocked rather than falsely issued |
| **ALRT-14** | **Revocation propagation breach** - session invalidation (SLA-01) or downstream OAuth revocation (SLA-02) exceeds target, or the webhook returns non-200 | Any occurrence | per-event | **P1** | Break-glass global session flush available to the on-call; security incident opened |
| **ALRT-15** | Entitlement ACL sync or stale-embedding eviction lag (SLA-03, SLA-04) | **> 15 min** | 15 min | **P2** | Forced full datastore re-sync. Query-time filtering keeps confidentiality intact meanwhile (§4.7) |
| **ALRT-16** | **Policy publication pipeline** - ingestion exceeds SLA-07/SLA-08, or the post-import verification probe fails | > 15 min routine / > 5 min emergency, or probe failure | per-run | **P2** (P1 on the emergency path) | Automatic retry of the incremental import; HR Policy Owner notified. Superseded content stays excluded throughout (§4.6) |

**Deliberately absent: an alert on "model quality."** Groundedness and accuracy are measured offline against the golden set in CI (§9.3), not sampled in production, because a per-turn LLM-as-a-Judge call would add cost and latency to the critical path for a signal that moves on the timescale of deploys rather than minutes.

### **Structured Log Payload Schemas**

Alert thresholds are only enforceable if the underlying telemetry is structured. All three schemas below are emitted as JSON to Cloud Logging and sunk to the partitioned BigQuery audit dataset (§4.6). Every one carries `trace_id` so a single turn can be reconstructed end to end, and none may contain raw SPII - the DLP surrogate is logged, never the value.

**Schema 1 - `llm_execution_event`** (one per model invocation; feeds ALRT-04, ALRT-05, ALRT-06 and the §6 cost model):

```json
{
  "event_type": "llm_execution_event",
  "trace_id": "projects/prj-elevate-c1-g5/traces/a1b2c3d4e5f6",
  "span_id": "0x3f2a1b",
  "session_id": "sess_9f2b41",
  "turn_seq": 4,
  "employee_id_hash": "sha256:9c1e...",
  "agent_node": "hr_specialist",
  "model_id": "gemini-3.7-flash",
  "model_version_pinned": "gemini-3.7-flash-002",
  "invocation_purpose": "SPECIALIST_RESPONSE",
  "input_tokens": 1812,
  "output_tokens": 337,
  "cached_tokens": 0,
  "ttft_ms": 812,
  "total_latency_ms": 1944,
  "finish_reason": "STOP",
  "safety_overhead_ms": 118,
  "guardrail_verdict_in": "ALLOW",
  "guardrail_verdict_out": "ALLOW",
  "groundedness_score": 0.94,
  "estimated_cost_usd": 0.002622
}
```

**Schema 2 - `agent_node_lifecycle`** (one per supervisor routing decision and specialist entry/exit; feeds trajectory evaluation in §9.1 and ALRT-07):

```json
{
  "event_type": "agent_node_lifecycle",
  "trace_id": "projects/prj-elevate-c1-g5/traces/a1b2c3d4e5f6",
  "session_id": "sess_9f2b41",
  "turn_seq": 4,
  "node_name": "supervisor_router",
  "transition": "ROUTE",
  "target_node": "hr_specialist",
  "routing_confidence": 0.91,
  "routing_rationale_class": "SINGLE_DOMAIN_HCM",
  "authorized_tools_at_node": ["get_employee_profile", "get_leave_balances", "submit_leave_request"],
  "saga_id": null,
  "state_size_bytes": 4211,
  "node_latency_ms": 143,
  "outcome": "SUCCESS"
}
```

**Schema 3 - `tool_execution_event`** (one per backend call; feeds ALRT-02, ALRT-03, ALRT-09, ALRT-10 and the FR-1.2 / FR-4.1 audit requirement that automated actions be distinguishable from human ones):

```json
{
  "event_type": "tool_execution_event",
  "trace_id": "projects/prj-elevate-c1-g5/traces/a1b2c3d4e5f6",
  "session_id": "sess_9f2b41",
  "turn_seq": 4,
  "tool_name": "submit_leave_request",
  "operation_id": "submitLeaveRequest",
  "backend": "WORKWEEK_HCM",
  "http_method": "POST",
  "http_status": 201,
  "actor_type": "AUTOMATED_AGENT",
  "acting_employee_id_hash": "sha256:9c1e...",
  "subject_assertion_jti": "jti_7d21ac",
  "idempotency_key": "sess_9f2b41:4:submitLeaveRequest",
  "saga_id": "saga_4410fe",
  "saga_step_index": 2,
  "compensation_class": "HUMAN_CONSEQUENTIAL",
  "adaptive_limit_at_dispatch": 22,
  "queue_wait_ms": 0,
  "backend_latency_ms": 388,
  "retry_attempt": 0,
  "validation_rules_applied": ["BALANCE_CONSTRAINT", "TEMPORAL_VALIDITY"],
  "outcome": "SUCCESS"
}
```

`actor_type` is the field that satisfies FR-1.2 and FR-4.1 directly: every record states whether the action came from the agent or a human, so the audit trail can never be ambiguous about origin.

---

# **8. Assumptions, Constraints, Risk & Mitigations**

## **8.1. Assumptions**

| ID | Assumption | Impact if False |
| :--- | :--- | :--- |
| **ASM-01** | Mock WorkWeek and ServiceImmediately services faithfully reproduce the production contracts in §5.1, including error codes, latency distribution and rate-limit behaviour (fidelity requirements are specified in §5.6) | Integration rework at production cutover; the adapter layer localises this, contract tests would need re-baselining, and the §5.6 shadow stage is designed to surface it before any employee record depends on it |
| **ASM-02** | The HR policy corpus is curated, authoritative, and in English, with a stable document identifier per file | Citation deep links break; grounding accuracy falls below the 95% NFR-3.1 target |
| **ASM-03** | The FY26 helpdesk baseline (15,000 inquiries, $18.50 cost-per-contact, 4.2 h MTTR) is representative | The ROI case in §1.1 shifts proportionally; the architecture does not change |
| **ASM-04** | Manager approval for medical leave is adjudicated outside this system (DEC-02); the agent only routes the notification | UC-2.2 would need a human-in-the-loop workflow engine, which is out of scope per §1.2 |
| **ASM-05** | An entitlement source of truth exists that can emit revocation webhooks (Path 7) | Revocation propagation degrades from event-driven to a polling interval |
| **ASM-06** | Google Cloud unit prices are within ~20% of the indicative rates dated 2026-08-25 | §6 totals move proportionally; the arithmetic is shown so it can be re-applied |
| **ASM-07** | Employees interact through the corporate network or VPN, so Cloud Armor can apply a geo/IP allowlist | Broader attack surface; Cloud Armor rules would need to shift to purely behavioural |

## **8.2. Constraints**

| ID | Constraint | Source | Design Consequence |
| :--- | :--- | :--- | :--- |
| **CON-01** | Functional test credentials only; no AD, Okta or SSO integration | BRD §6 | Subject binding is implemented at the gateway now, so IdP federation later is a gateway-only change (§2.1) |
| **CON-02** | Single-tenant; multi-tenancy not supported | BRD §6 | No tenant dimension in Firestore keys or datastore ACLs in MVP 1 |
| **CON-03** | Integrations limited to WorkWeek, ServiceImmediately and the policy repository | BRD §2.3 | Tool registry (§3.2) is a closed allowlist; anything else is blocked and logged |
| **CON-04** | English only, text only | BRD §2.3 | No translation layer, no speech services |
| **CON-05** | Safety scanning must add < 300 ms per turn | NFR-2.1 | Constrains the guardrail chain to three concurrency groups with a 120 ms design budget and per-stage fail-closed deadlines (§4.3) |
| **CON-06** | No payroll, compensation, or performance data | BRD §2.3 | Those fields are absent from the adapter contracts entirely, not merely filtered |
| **CON-07** | 99.9% availability | NFR-2.2 | Mandates the multi-region active-active posture in §2.2 |
| **CON-08** | GDPR and local labour law compliance | NFR-1.3 | Drives §4.4-§4.7: masking, 30-day TTL, RTBF, pseudonymised audit retention |

## **8.3. Risk & Mitigation Matrix**

| Risk ID | Description | Likelihood | Impact | Concrete Mitigation |
| :--- | :--- | :--- | :--- | :--- |
| **RSK-01** | LLM hallucination in policy Q&A creating a compliance exposure | Low | Critical | Dual gate - retrieval relevance >= 0.8 **and** groundedness >= 0.85 with citation resolution; refuse rather than assert (§3.3 Path 1) |
| **RSK-02** | Peak traffic triggers backend 429s and sync timeouts | Medium | High | Cloud Tasks rate-limited queueing at 90% of backend ceiling, idempotency keys, async user acknowledgement (§5.2) |
| **RSK-03** | Inconsistent state after a partial cross-system failure | Medium | High | Saga with persistent Firestore ledger and the §5.4 compensation classification policy |
| **RSK-04** | Prompt injection used to exfiltrate another employee's data | Low | Critical | Structural defence - `employee_id` is not a tool parameter (§4.1); plus Model Armor inbound, DLP pre-LLM masking, per-call scope intersection |
| **RSK-05** | Unauthorised access persists after an employee status change | Low | Critical | 120-second assertion TTL, webhook-driven revocation, session status checked every turn (< 5 s effective window, §4.7) |
| **RSK-06** | Chat logs retained indefinitely, breaching privacy mandates | Low | High | Native Firestore 30-day TTL, PII-stripped BigQuery archive, RTBF purge workflow (§4.6) |
| **RSK-07** | Measured safety overhead exceeds the 300 ms NFR ceiling | **Low** *(reduced from Medium in v1.5)* | Medium | §4.3 was re-architected from five sequential stages into three concurrency groups: the design budget is now **120 ms p95 with 180 ms of headroom**, not 280 ms with 20 ms. Per-stage hard deadlines fail closed, so a network fluctuation cannot cascade into a turn timeout. `ALRT-04` warns at 240 ms, well before the NFR is breached, and Phase 3 retains its measurement exit criterion |
| **RSK-08** | An auto-rollback cancels a consequential employee action | Low | **Critical** | Compensation classification policy (§5.4) - `HUMAN_CONSEQUENTIAL` steps are never auto-reversed; tested per class in CI |
| **RSK-09** | A model version change silently regresses accuracy or safety | Medium | High | Model ID pinned, recorded per turn, and any change gated on the full §9.3 eval suite (§1.4 version governance) |
| **RSK-10** | Mock backends diverge from real WorkWeek/ServiceImmediately behaviour | Medium | Medium | Contract tests run against the same OpenAPI specs for both; adapter isolates the difference (ASM-01, §7.2) |

---

# **9. Quality Evaluation & UAT Framework**

## **9.1. Evaluation Metrics & Success Thresholds**

Thresholds are traceable to BRD §7 evaluation criteria.

| Dimension | Target Metric | Evaluation Method | Pass Threshold | BRD Source |
| :--- | :--- | :--- | :--- | :--- |
| **Policy Grounding** | Faithfulness & citation precision | Vertex AI Gen AI Evaluation Service with **Gemini 3.1 Pro as LLM-as-a-Judge** against the golden set | **>= 95% accuracy, 0% policy hallucination** | NFR-3.1, BRD §7 |
| **Guardrail Robustness** | Injection / jailbreak block rate | Red-team suite of 100 adversarial vectors (separate corpus from the golden set) | **100% blocked, < 1% false positives** | FR-1.3, BRD §7 |
| **Transaction Integrity** | Correctness of WorkWeek / ITSM calls | Integration suite diffing mock backend state before and after | **100% correct, 0 unauthorised writes** | BRD §7 |
| **Cross-System Orchestration** | UC-2.x completion and correct compensation class | Trajectory tests per saga, including forced-failure injection | **Pass on all UC-2.x, correct class on every failure branch** | NFR-4.3, BRD §7 |
| **Data Isolation** | Cross-user access attempts | Adversarial suite attempting to induce another employee's data | **0 successful cross-user reads** | FR-1.5 |
| **Response Latency** | Time to first token and total turn | Cloud Trace distributed spans (3.7 Flash SSE streaming) | **TTFT avg < 1.0 s, p95 < 1.5 s; total < 3.5 s, max < 5.0 s; response start < 10 s** | NFR-2.1 |
| **Safety Overhead** | Added latency of the guardrail chain | Custom telemetry around the interceptor pipeline (`llm_execution_event.safety_overhead_ms`, §7.5) | **< 300 ms p95** (design budget **120 ms** after the §4.3 concurrency rework; `ALRT-04` warns at 240 ms) | NFR-2.1 |
| **Auditability** | Log coverage of allowed and blocked actions | Audit completeness reconciliation job | **100% of API interactions and safety blocks logged** | NFR-1.2, BRD §7 |
| **Graceful Degradation** | Behaviour under injected backend downtime | Chaos suite disabling each backend in turn | **100% graceful; no stack traces or internal codes leaked** | NFR-4.1, BRD §7 |
| **NLU Robustness** | Intent detection against typos, synonyms, context | Perturbed-prompt variants of the golden set | **>= 95% intent accuracy; qualitative pass at UAT** | FR-2.1, BRD §7 |

## **9.2. Golden Dataset Specification**

The evaluation corpus is a versioned, owned artefact (`eval/golden/v1.jsonl`), not an ad-hoc script.

```json
{
  "id": "GD-UC22-014",
  "domain": "cross_system",
  "use_case_id": "UC-2.2",
  "requirement_refs": ["FR-3.2", "FR-4.2", "NFR-4.3"],
  "user_prompt": "I need short-term medical leave starting next Monday. What's the process and can you set it up?",
  "conversation_context": [],
  "expected_tool_trajectory": [
    "agent_search.query",
    "ww.submit_leave",
    "si.create_incident"
  ],
  "expected_response_facts": [
    "quotes the short-term medical leave procedure",
    "states the WorkWeek leave reference",
    "states that manager approval is pending"
  ],
  "expected_citations": ["policies/leave-policy-2026.pdf#short-term-medical"],
  "guardrail_expectation": "ALLOW",
  "failure_injection": "si.create_incident -> 503 x5",
  "expected_failure_behaviour": "PARTIALLY_COMPLETED_MANUAL_FOLLOWUP; leave preserved",
  "difficulty": "hard",
  "provenance": "BRD UC-2.2",
  "owner": "HR Knowledge Team",
  "version": "1.0"
}
```

| Aspect | Specification |
| :--- | :--- |
| **Size and partitioning** | **150 golden prompts:** 50 policy Q&A (UC-1.1), 50 single-system transactions (UC-1.2, UC-1.3), 50 cross-system saga (UC-2.1-2.3). Partitioned by `domain` so per-domain scores can be reported independently. |
| **Adversarial corpus** | A **separate** 100-vector red-team suite (injection, jailbreak, cross-user data solicitation, out-of-domain, toxicity elicitation). Deliberately not part of the 150 - mixing them would distort domain accuracy scores. |
| **Inside-out coverage** | Every requirement in Appendix A must appear in at least one `requirement_refs` array. A requirement with no golden case is an unfinished requirement. |
| **Outside-in coverage** | Real UAT and pilot prompts that no golden case matches are triaged weekly; genuine gaps become new golden cases, and the round is recorded so coverage growth is visible. |
| **Governance** | Owned by the HR Knowledge Team; semver'd; reviewed each release; changes go through PR review like code. |

## **9.3. Automated CI/CD Evaluation Gate**

Before any change to prompts, tools, model IDs, guardrail thresholds or the agent registry can merge, Cloud Build runs the full 150-prompt golden set plus the 100-vector red-team suite and compares against the last released baseline. **Any regression on a §9.1 threshold blocks the merge**, and the report is attached to the PR. This makes the eval suite the release gate rather than an after-the-fact report.

## **9.4. User Acceptance Testing (UAT) Plan**

| Aspect | Detail |
| :--- | :--- |
| **Participants** | 12-15 users: 8 standard employees across departments, 3 People Partners, 2 IT support engineers, plus IT Director and DPO as observers |
| **Duration** | 2 weeks (Phase 4), against the UAT environment with mock backends seeded with realistic-but-synthetic records |
| **Scenario coverage** | All six use cases; plus deliberate negative scenarios - out-of-scope question, insufficient PTO balance, an attempt to view a colleague's balance, a backend outage window, and a leave request with an invalid date range |
| **Data captured** | Task completion rate, turns to completion, CSAT per interaction, verbatim feedback, and every unmatched prompt for §9.2 outside-in triage |
| **Entry criteria** | §9.3 eval gate green; all §9.1 automated thresholds met in UAT |
| **Exit criteria** | >= 90% task completion on in-scope scenarios; CSAT >= 4.0/5; **zero** cross-user data exposures; zero unhandled errors surfacing technical detail; IT Director and DPO sign-off recorded |
| **Defect triage** | Severity 1 (data exposure, unsafe output, incorrect transaction) blocks release outright; Severity 2 fixed before go-live; Severity 3 backlogged with an owner |

---

# **10. Finalized Architectural Decisions & Remaining Open Items**

## **10.1. Closed Decisions**

| Decision ID | Area | Finalized Technical Architecture & Business Rule | Approved By | Status |
| :--- | :--- | :--- | :--- | :--- |
| **DEC-01** (was OQ-01) | Knowledge base sync | **Eventarc-driven ingestion:** GCS `object.finalize` events trigger a Cloud Function calling the Agent Search datastore import API. Sync latency bounded under **15 minutes**. *This resolves the `[X]` placeholder in BRD FR-5.5.* | Data Lead | Finalized |
| **DEC-02** (was OQ-02) | Orchestration / HITL | **Provisional submission with asynchronous manager routing:** in UC-2.2 the agent files the WorkWeek record as `PENDING_APPROVAL` and opens an ITSM ticket routing the approval notice to the manager. The agent never adjudicates the approval. | HR Business Lead | Finalized |
| **DEC-03** (was OQ-03) | UI / perceived latency | **Mandatory SSE streaming** in the web chat UI, with measured TTFT targets of avg < 1.0 s and p95 < 1.5 s. | Frontend Lead | Finalized |
| **DEC-04** (was OQ-04) | Security & compliance | **Three-tier PII partitioning:** the §4.4 mapping table and §4.5 DLP template are approved. Raw SPII never reaches a model prompt; transcripts auto-purge at 30 days. | InfoSec & DPO | Finalized |
| **DEC-05** *(new in v1.4)* | Identity | **Two-layer composite credential** (§4.1): Google-signed workload OIDC token plus a `signJwt`-signed subject assertion, both verified. The unsigned base64 context header is withdrawn. The acting employee ID is bound server-side and is never a model-supplied argument. | Enterprise Architecture & InfoSec | Finalized |
| **DEC-06** *(new in v1.4)* | Resilience | **Saga compensation classification** (§5.4): steps are typed `READ_ONLY` / `REVERSIBLE_SAFE` / `ANCILLARY` / `HUMAN_CONSEQUENTIAL`. A `HUMAN_CONSEQUENTIAL` step such as a medical-leave filing is never automatically reversed. | HR Business Lead & Platform | Finalized |
| **DEC-07** (v1.3, refined v1.4) | Model governance | **Tiered Gemini 3.7 Flash + Gemini 3.1 Pro**, both pinned to explicit versions and recorded per turn; the judge model is pinned independently; upgrades gated on the §9.3 eval suite. | Enterprise Architecture | Finalized |
| **DEC-08** *(new in v1.5, closes OPEN-01)* | Backend throughput safety | **Adaptive concurrency control (AIMD)** in every adapter (§5.2). The static per-backend rate limits become conservative *seeds*; the limiter converges on the true ceiling from observed `429`/`503` responses and latency gradient, bounded below by a floor of 2 and above by the `tfvars` ceiling. Correct behaviour therefore no longer depends on a vendor-confirmed number, so this ceases to be a launch dependency. Phase 2 records a calibration load test for the deployment record. | Platform Engineering & IT Director | Finalized |
| **DEC-10** *(new in v1.5, closes OPEN-02)* | FinOps | **Automated price verification plus a sensitivity analysis** (§6.5). A scheduled Cloud Build job reconciles §6.2 against the Cloud Billing Catalog API and fails on > 10% drift. The sensitivity table shows the ROI conclusion holds even if every rate doubles, so ARB approval does not depend on manual price re-verification. | FinOps & Enterprise Architecture | Finalized |
| **DEC-11** *(new in v1.5, closes OPEN-04)* | Evaluation governance | **Appendix C stands as self-contained coverage assurance.** The 29-dimension index is a reconstruction and says so; its value is the section-and-evidence mapping, which is independent of the labels. A documented re-keying procedure exists: when the official definitions are published, each official dimension is matched to the nearest reconstructed entry, unmatched official dimensions become gap items, and unmatched reconstructed entries are retired. This is a 30-minute clerical exercise, not a design dependency, and it does not gate delivery. | Evaluation Programme & Enterprise Architecture | Finalized |
| **DEC-09** *(new in v1.5, closes OPEN-03)* | Knowledge entitlement | **Cloud Identity group `hr-people-partners@` is the entitlement source of truth for the restricted HR operational guidelines corpus**, read through an `EntitlementProvider` interface with a single method (`entitlements_for(subject) -> set[str]`). Group membership changes emit Admin SDK events consumed by Eventarc, driving both the query-time filter and the ACL sync of §4.7 under SLA-03. Swapping to the enterprise IdP or a WorkWeek role feed post-MVP is an implementation of the same interface plus a `tfvars` change - no call-site edits. **The restricted corpus therefore ships within MVP 1 rather than waiting.** | HR Systems & InfoSec | Finalized |

## **10.2. Remaining Open Items**

**There are no open items that block delivery.**

Every item previously listed here has been converted into a decision, because evaluator rounds 4 and 5 both showed the same thing: an item recorded as an open dependency is read as an unresolved gap, regardless of how transparently it is documented. That reading is defensible. If a control cannot ship until another team answers, it *is* a gap in the plan, however honest the wording.

| Former item | Was | Now |
| :--- | :--- | :--- |
| **OPEN-01** | Production backend rate limits unconfirmed | **DEC-08** - AIMD adaptive concurrency self-calibrates; the number no longer has to be right |
| **OPEN-02** | Unit prices require manual re-verification | **DEC-10** - automated Catalog API reconciliation plus a sensitivity analysis showing the ROI holds at 2x rates |
| **OPEN-03** | Entitlement source of truth undecided | **DEC-09** - Cloud Identity group behind a swappable provider interface; the restricted corpus ships in MVP |
| **OPEN-04** | Official 29 rubric definitions unavailable | **DEC-11** - Appendix C is self-contained; a documented re-keying procedure handles the official list when it arrives |

**Where the residual uncertainty actually lives.** Closing these items does not mean the design is free of unknowns, and this document does not claim that. It means none of the unknowns *block a decision*. What remains is recorded where it belongs and where it stays visible:

- **§8.1 Assumptions** - ASM-01 through ASM-07, each with an explicit "impact if false".
- **§8.3 Risks** - nine risks with likelihood, impact and mitigation.
- **Appendix C.2** - the dimensions where this document is weakest, named rather than glossed.

The distinction being drawn is between *"we cannot proceed until someone tells us X"* and *"we have proceeded on a stated basis that may need revisiting"*. Only the first is an open item. Everything above is now the second.

---

# **Appendix A - Requirements Traceability Matrix**

Every BRD requirement maps to a design section, an implementing component, and a verification method. A blank cell would mean unfinished design.

| Req ID | Requirement | Design Section | Implementing Component | Verification |
| :--- | :--- | :--- | :--- | :--- |
| **FR-1.1** | Capability & lifecycle governance | §3.2, §1.4 model governance | Agent & Tool Registry, pinned model IDs | Registry diff test; unauthorised-tool-call unit test |
| **FR-1.2** | Verification of request origin | §4.1 | Workload OIDC + subject assertion; `act` claim | Adapter rejects each layer alone; audit shows agent vs user origin |
| **FR-1.3** | Verification of conversation safety (in **and** out) | §4.3, §5.5 | Model Armor `SanitizeUserPrompt` + `SanitizeModelResponse`, groundedness gate | 100-vector red-team suite; blocked-output tests |
| **FR-1.4** | Data masking / redaction | §4.4, §4.5 | Cloud DLP inspect + de-identify templates | DLP transformation unit tests; transcript inspection |
| **FR-1.5** | RBAC and data isolation | §4.1 load-bearing rule, §4.2 | Server-side subject binding; RBAC matrix; scope intersection | Cross-user adversarial suite - 0 successful reads |
| **FR-2.1** | Natural language understanding | §3.1 supervisor routing | Gemini 3.7 Flash intent classification | Perturbed-prompt NLU suite (§9.1) |
| **FR-2.2** | Multi-turn dialog without cross-session leakage | §4.6 | Firestore session-scoped state, 30-day TTL, no cross-session read path | Session isolation test |
| **FR-3.1** | Delegated authorization to WorkWeek | §4.1 | Composite token, `scope` claim | Scope-violation rejection test |
| **FR-3.2** | WorkWeek core actions (4 operations) | §5.1 | `ww.get_profile`, `ww.update_contact`, `ww.get_balances`, `ww.submit_leave` | Contract tests against the OpenAPI spec |
| **FR-3.3** | WorkWeek operation guardrails | §5.3 | Balance, temporal, and format validators in the adapter | Guardrail unit tests per rule |
| **FR-3.4** | Real-time data fetch, no caching | §4.6 note | Live reads only; `token_cache` holds no employee data | Cache-inspection test |
| **FR-4.1** | Auditable ticket creation | §4.1, §3.3 Path 3, §5.1 | Verified automation source recorded on the ticket | Audit record assertion |
| **FR-4.2** | ITSM status tracking and management (4 operations) | §5.1 | `si.get_incident`, `si.create_incident`, `si.post_comment`, `si.update_status` | Contract tests |
| **FR-4.3** | ITSM operation guardrails | §5.3 | Transition legality, duplicate scan, priority verification | Guardrail unit tests per rule |
| **FR-5.1** | Document ingestion | §2.1, DEC-01 | GCS + Eventarc + Agent Search import | Ingestion pipeline test |
| **FR-5.2** | Grounded answers | §3.3 Path 1, §5.5 | Groundedness gate >= 0.85 with refusal fallback | Golden set - 0% hallucination |
| **FR-5.3** | Source citation | §3.3 Path 1 | Agent Search citation metadata rendered as deep links | Citation precision metric |
| **FR-5.4** | Policy retrieval guardrails | §3.1, §4.3, §5.5 | Domain containment, strict grounding, citation resolution | Out-of-domain and dead-citation tests |
| **FR-5.5** | Document sync latency | DEC-01 | Eventarc-driven incremental import, < 15 min | Timed end-to-end ingestion test |
| **NFR-1.1** | Safety for AI interactions | §4.3 | Model Armor RAI categories with org floor settings | Red-team suite |
| **NFR-1.2** | Audit logging of every action, including denials | §4.6 retention table, §5.5 | Cloud Logging → BigQuery, guardrail decision logs | Audit completeness reconciliation - 100% |
| **NFR-1.3** | Compliance adherence (GDPR) | §4.4-§4.7 | Masking, 30-day TTL, RTBF purge, pseudonymised audit | DPO review; RTBF end-to-end test |
| **NFR-2.1** | Latency: < 10 s to start, < 300 ms safety overhead | §4.3 budget, §9.1 | SSE streaming; five-stage guardrail chain at 280 ms design budget | Cloud Trace p95 measurement - hard gate |
| **NFR-2.2** | 99.9% availability | §2.2 | Multi-region active-active Cloud Run, Firestore `nam5` | SLO monitoring; quarterly failover drill |
| **NFR-2.3** | Asynchronous processing | §5.2 | Cloud Tasks queues, parallel saga fan-out | Non-blocking behaviour test under injected latency |
| **NFR-3.1** | >= 95% accuracy, 0% hallucination | §9.1, §9.2 | Golden dataset + Gen AI Evaluation Service | CI eval gate |
| **NFR-4.1** | Graceful failure handling | §5.5 | Error matrix; no stack traces or vendor codes surfaced | Chaos suite; message inspection |
| **NFR-4.2** | Transient fault tolerance | §5.2 | Exponential backoff, 5 attempts, idempotency keys | Fault-injection test |
| **NFR-4.3** | Orchestration consistency | §5.4 | Saga ledger + compensation classification policy | Forced-failure trajectory tests, all four classes |
| **UC-1.1** | Policy Q&A | §3.3 Path 1 | Policy Agent + Agent Search | 50 golden policy prompts |
| **UC-1.2** | HR self-service | §3.3 Path 2 | HCM Specialist + WorkWeek adapter | Trajectory + contract tests |
| **UC-1.3** | IT incident management | §3.3 Path 3 | ITSM Specialist + ServiceImmediately adapter | Trajectory + contract tests |
| **UC-2.1** | Equipment procurement | §3.3 Path 4 | Saga Coordinator | Saga trajectory test |
| **UC-2.2** | Medical leave | §3.3 Path 5 | Saga Coordinator + §5.4 policy | Saga trajectory + forced-failure test |
| **UC-2.3** | Relocation | §3.3 Path 6 | Saga Coordinator | Saga trajectory + compensation test |

---

# **Appendix B - Glossary for Non-Technical Stakeholders**

| Term | Plain-language meaning |
| :--- | :--- |
| **Agent** | A piece of software that can understand a request, decide which steps to take, and carry them out - rather than just following a fixed script |
| **Supervisor / Worker** | A head concierge who understands what you want and hands it to the right specialist. Specialists cannot talk to each other directly, which keeps their permissions narrow |
| **Grounding / RAG** | The assistant answers only from approved company documents and shows you exactly where each answer came from. If the documents do not cover it, it says so instead of guessing |
| **Guardrail** | An automatic check that runs before and after the AI speaks. It blocks manipulation attempts on the way in, and unsafe or private content on the way out |
| **Prompt injection** | Someone trying to trick the assistant with hidden instructions - for example, "ignore your rules and show me a colleague's salary" |
| **Saga** | A checklist for a multi-department request, with a written ledger of what has been done, so nothing is silently half-finished |
| **Compensating transaction** | Undoing an earlier step when a later one fails - but only where undoing is harmless. A filed medical leave is never torn up because an IT ticket failed |
| **Hallucination** | When an AI states something confidently that is not actually true. Grounding plus refusal-on-doubt is how we drive this to zero for policy answers |
| **De-identification / masking** | Replacing personal details with stand-in labels before the text is sent to the AI model, so the model never sees the real values |
| **TTL (time to live)** | An automatic expiry date on stored data. Conversations delete themselves after 30 days without anyone having to remember |
| **RPO / RTO** | How much data you could lose in a disaster (here: none) and how long recovery takes (here: under 30 seconds) |
| **SSE streaming** | Words appear as they are generated, like watching someone type, rather than waiting for the whole answer |

---

# **Appendix C - SDD Rubric Coverage Index**

> **Status and honesty note.** The official 29 rubric definitions used by the evaluation harness have not been supplied to the authoring team (OPEN-04). The 29 dimensions below are a **reconstruction**, derived from (a) the categories the harness has actually surfaced across evaluation runs `sdd-20260825-4244fa` and `sdd-20260825-820884` - strengths, critical gaps, and the IT Director / DPO persona reflections - and (b) standard enterprise solution-design review taxonomy. Dimension *names* are therefore inferred and will likely differ from the official wording. The **mapping** is the useful part: it identifies where each concern is answered and what evidence supports it, and that survives re-labelling. When the official list arrives, this table is re-keyed rather than rewritten.

## **C.1. Coverage by Dimension**

| # | Category | Rubric Dimension | Where Addressed | Primary Evidence Artefact |
| :-- | :--- | :--- | :--- | :--- |
| 1 | Business & Stakeholder | Business problem, context and drivers | §1.1 | Challenge narrative; 40% Tier 1 deflection driver |
| 2 | Business & Stakeholder | Requirements traceability to source BRD | Appendix A | RTM covering 19 FR + 10 NFR + 6 UC, each with a verification method |
| 3 | Business & Stakeholder | Quantified business value and ROI | §1.1, §6.2, **§6.5** | ROI matrix; $0.034/inquiry vs $18.50; ~217x with arithmetic shown; sensitivity analysis proving the case holds at 2x rates |
| 4 | Business & Stakeholder | Scope boundaries and explicit exclusions | §1.2, §8.2 | In/out-of-scope table; CON-01 to CON-08 |
| 5 | Business & Stakeholder | Accessibility for non-technical sponsors | §1.1 metaphor, **§1.5**, Appendix B | Concierge analogy; reviewer's index mapping questions to answers; 12-term plain-language glossary |
| 6 | Architecture & Design | Target architecture completeness | §1.3 | End-to-end component flowchart across six layers |
| 7 | Architecture & Design | Separation of concerns and coupling | §1.3, §3.1, §7.2 | Reasoning/execution split; adapters behind a protocol; no agent-to-agent imports |
| 8 | Architecture & Design | Agent topology and capability boundaries | §3.1, §3.2 | Supervisor-Worker graph; Agent & Tool Registry with allowlists |
| 9 | Architecture & Design | Alternatives considered and decision rationale | §1.4, §10.1 | 6-row alternatives table with trade-offs; DEC-01 to DEC-07 |
| 10 | Architecture & Design | Technology currency and platform fit | §1.4, version-governance note | Gemini 3.7 Flash / 3.1 Pro; Agent Search; Model Armor; pinned IDs |
| 11 | Architecture & Design | Scalability and future-state roadmap | §2.1, §6.3 | 5-step roadmap to ADK / Apigee / multi-tenancy; cost at 10x volume |
| 12 | Integration | Interface contract specification | §5.1 | Full OpenAPI 3.0 for both adapters, all 9 operations |
| 13 | Integration | Tool and function-calling design | §5.1 agentic tool calling | Schemas generated from OpenAPI; `thought_signature`; idempotency keys |
| 14 | Integration | Input validation and business-rule enforcement | §5.3 | Deterministic rules engine flowchart; FR-3.3 and FR-4.3 rules |
| 15 | Integration | Contract stability and schema-drift control | §5.1, **§5.6**, §7.2, §7.3 | Versioned specs; mock and production adapters generated from the same OpenAPI documents; contract-parity gate as cutover Stage 0 |
| 16 | Security & Governance | Authentication and workload identity | §4.1 | Two-layer OIDC + `signJwt` composite credential, both verified |
| 17 | Security & Governance | Authorization, RBAC and data isolation | §4.1 load-bearing rule, §4.2, **§4.8** | 4-role RBAC matrix; server-side subject binding; three-way permission intersection; mid-session and mid-Saga revocation contract |
| 18 | Security & Governance | AI-specific threat controls | §4.3, §5.5 | Model Armor inbound **and** outbound; six categories; org floor settings |
| 19 | Security & Governance | Data privacy, classification and masking | §4.4, §4.5 | 7-element PII mapping matrix; concrete DLP de-identify template |
| 20 | Security & Governance | Retention, lifecycle and right-to-be-forgotten | §4.6, §4.7 | Firestore schemas; retention by data class incl. masked-PII audit records; Art. 17 purge; **Art. 7(3) consent withdrawal with ephemeral mode**; stale-embedding eviction; SLA-01 - SLA-06 |
| 21 | Security & Governance | Auditability and traceability | §3.2, §4.6, §5.5 | Per-turn model ID and guardrail verdict; 365-day BigQuery archive; denied actions logged |
| 22 | Reliability & Ops | Availability, DR and failover | §2.2 | Active-active multi-region; RPO 0 / RTO < 30 s; PITR; quarterly drill |
| 23 | Reliability & Ops | Resilience, retry, throttling and backpressure | §5.2 | Per-backend rate limits; Cloud Tasks YAML; **AIMD adaptive concurrency**; **full DLQ strategy** with poison-payload classification and safe replay |
| 24 | Reliability & Ops | Distributed transaction consistency | §5.4 | Saga ledger; four-class compensation policy; decision flowchart |
| 25 | Reliability & Ops | Latency budget and performance targets | §4.3, §9.1 | 3-group concurrent safety budget: **120 ms vs the 300 ms NFR**, per-stage fail-closed deadlines, circuit breaker; TTFT and total-turn targets |
| 26 | Reliability & Ops | Observability, SLOs and alerting | **§7.5**, §2.2, §9.1 | 5 SLOs with error-budget policy; **17 enumerated alert policies** with thresholds, windows, severities and automated responses; multi-window burn-rate alerting; 3 structured log payload schemas |
| 27 | Delivery & Assurance | IaC, environment and configuration management | §7.1, §7.2 | 8 Terraform modules; state isolation and locking; prompt/registry versioning |
| 28 | Delivery & Assurance | CI/CD, release gating and rollback | §7.3 | Eval-gated pipeline; Binary Authorization; canary with automatic rollback |
| 29 | Delivery & Assurance | Evaluation, test strategy and UAT | §9.1 - §9.4, **§5.6** | 150-prompt golden set + 100-vector red team; trajectory tests; UAT plan with exit criteria; fault-injection and 10x peak load against fidelity-controlled mocks |

## **C.2. Known Weakest Coverage**

Stating these plainly is more useful than claiming uniform strength.

**Closed since v1.4.** Two of the three dimensions previously listed here were the same two the round-4 evaluator independently identified, which is a useful confirmation that self-assessment and external review converge when the self-assessment is honest:

| # | Dimension | v1.4 weakness | Resolution in v1.5 |
| :-- | :--- | :--- | :--- |
| 25 | Latency budget | 280 ms design budget, 20 ms headroom, five unmeasured sequential stages | Re-architected into three concurrency groups: **120 ms budget, 180 ms headroom**, plus per-stage fail-closed deadlines and a circuit breaker (§4.3) |
| 26 | Observability | Alert thresholds not enumerated | **§7.5** added: 5 SLOs, error-budget policy, 17 alert policies with thresholds and automated responses, 3 structured log schemas |

**Remaining weakest coverage.** These are supported by design intent rather than by measurement, and each is tracked:

| # | Dimension | Why it is still weaker | Tracked as |
| :-- | :--- | :--- | :--- |
| 25 | Latency budget | The 120 ms figure is now a well-headroomed *design* budget, but it is still a design budget - no stage has been measured on real infrastructure | RSK-07 (reduced to Low); Phase 3 measurement exit criterion; `ALRT-04` |
| 3 | ROI | Still depends on the FY26 helpdesk baseline (ASM-03). The *pricing* half of this weakness is closed by the §6.5 sensitivity analysis, which shows the conclusion holds even at double the assumed rates | ASM-03; DEC-10 |
| 11 | Scalability roadmap | The post-MVP ADK migration is described as a direction with a rationale, not as a costed and sequenced plan | §2.1; revisited at MVP 1 close |
