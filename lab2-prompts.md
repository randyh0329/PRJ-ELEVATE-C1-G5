# Lab 2 — Cymbal Group AdServer Production Migration (AWS → GCP)

Three prompts for the agy CLI. Run them in order; each is self-contained, so a `/clear` or a
session restart between them is fine.

| Prompt | Covers | Lab tasks |
| --- | --- | --- |
| **1 — Config** | workspace clone, AWS baseline audit, cross-cloud mapping + diagrams, org-policy Terraform (authored, not applied) | Prerequisite + Tasks 1–3 |
| **2 — Deploy** | auth, init/plan/apply, live GCP verification, executive proposal | Tasks 4–5 |
| **3 — Review** | evidence-based audit of all five checkpoints | run before *Check my progress* |

Approve tool permissions when agy asks, and monitor long runs with `/tasks` rather than
re-prompting — `terraform apply` for GKE takes ~10 minutes and a second prompt mid-apply can
start a duplicate apply against the same state.

**Environment:** Antigravity `agy` CLI, Gemini 3.6, remote session desktop with VS Code
available for inspecting workspace files.

**Lab constants**

| Item | Value |
| --- | --- |
| Workspace root | `~/Desktop/Cymbal/aws_to_gcp_migration` |
| Upstream repo | `https://github.com/Ashwinikumar1/aws_to_gcp_migration` |
| Source of truth | `aws_environment.json` (also downloadable from Student Resources) |
| Generated docs | `generated/` |
| Terraform | `terraform/main.tf`, `terraform/variables.tf` |
| GKE cluster name | `adserver1-prd` |
| **Region** | **`us-central1`** — fixed by the lab; do not substitute |
| Naming rule | every resource name must contain `adserver`; otherwise keep names unchanged |

**Known AWS baseline** (use to detect hallucination — the analysis must independently
derive these from the JSON, not be told them):

- VPC `10.17.0.0/16`, two AZs: `us-east-1a`, `us-east-1b`
- EKS cluster `adserver1-prd`, node pool of `c5.large` (2 vCPU / 4 GB)
- S3 deployment bucket + AWS KMS customer-managed key

> **Region is `us-central1` everywhere.** The graded checks look in that region. The trap is
> not the region string itself — it is *consistency*. The subnet, the GKE cluster, the Cloud
> Router/NAT, the KMS key ring, and the GCS bucket must all be in `us-central1`. A key ring in
> `us-central1` with a bucket in the multi-region `US` location makes the CMEK binding fail at
> apply time, and a bucket in `US` may not satisfy the regional check. Pin all five.

### Operating notes for the agy CLI (Gemini 3.6)

Behaviours worth compensating for in how you prompt and review:

- **Force writes to disk.** Gemini will happily render a full document in the chat response
  and consider the task done. Every phase below names an absolute output path and says
  "write the file" — keep that phrasing. After each phase, `ls` the path yourself; do not
  accept "I've created the file" as evidence.
- **Approve tool permissions.** agy prompts before running shell commands. Long Terraform runs
  will stall silently waiting on an approval you didn't notice.
- **Use `/tasks` for long runs.** Monitor there rather than re-prompting, which can spawn a
  duplicate apply against the same state.
- **Re-anchor the region and naming rule.** Constraints stated once, many turns ago, drift.
  Each Terraform-touching phase below repeats `us-central1` and the `adserver` naming rule
  verbatim for that reason.
- **Verify the file it edited is the file you think.** If the repo already ships a
  `terraform/main.tf`, confirm the model edited that one rather than creating a second copy
  elsewhere in the tree.

---

## Prompt 1 — Config

```text
You are my lead platform cloud engineer for the Cymbal Group AdServer migration lab. This is
part 1 of 3: get the workspace cloned, the AWS baseline audited, the migration proposal
written, and the Terraform authored. Do NOT authenticate to GCP, do NOT run terraform apply,
and do NOT create any cloud resource in this session — that is part 2.

OPERATING RULES
- Work through the phases in order. If a phase fails, STOP, paste the full error, diagnose it
  from evidence, and ask me before retrying. Never loosen a security setting, drop a
  requirement, or soften a finding to force a green result.
- Write every artifact to disk with your file-write tool; printing to chat does not count.
  Run `ls -la ~/Desktop/Cymbal/aws_to_gcp_migration/generated/` after each document phase and
  paste the output as proof.
- Quote the command you are about to run before running it.
- Print detailed background on what is happening under the hood as you go.
- Report honestly. A failed tool call, an empty table, or a partial pass is a finding.
- Every AWS-side fact must come from aws_environment.json. Do not infer, do not fill gaps
  from general AWS knowledge, and do not invent resources that are not in the JSON. If a
  value is absent from the export, write "not present in export" rather than guessing.

PHASE 1 — WORKSPACE SETUP  [checkpoint: prerequisite]
  a. Create a folder named `Cymbal` on my Desktop (~/Desktop/Cymbal). Do not nest it inside
     any other folder.
  b. Clone https://github.com/Ashwinikumar1/aws_to_gcp_migration into that folder, so the
     final path is exactly ~/Desktop/Cymbal/aws_to_gcp_migration. Check for accidental
     nesting — the repo contents must be directly under aws_to_gcp_migration/, NOT under
     Cymbal/aws_to_gcp_migration/aws_to_gcp_migration/.
  c. Make ~/Desktop/Cymbal/aws_to_gcp_migration the working directory for the rest of this
     session. Show me the directory tree two levels deep.
  d. Confirm aws_environment.json is present and is valid JSON:
     `python3 -m json.tool aws_environment.json > /dev/null && echo VALID`. Report its size
     and its top-level JSON keys.
  e. Inventory what else shipped in the repo: list every file, and specifically report
     whether aws_to_gcp_migration_analysis.md, a terraform/ directory, and a generated/
     directory already exist. I need to know what is pre-existing versus what you generate.
  f. Confirm `git status --short` is clean. Do not modify, reformat, or regenerate any
     cloned file.

PHASE 2 — AWS BASELINE ANALYSIS  [checkpoint: task 1]
  Act as a cloud infrastructure auditor performing brownfield discovery. Read
  aws_environment.json in full and parse it directly.

  Extract and document every legacy primitive across these five domains:
   1. NETWORK — VPC ID and CIDR block, every subnet with its CIDR, Availability Zone, and
      public/private designation, route tables, internet/NAT gateways, and every security
      group with its inbound and outbound rules.
   2. CONTAINER — the EKS cluster: name, Kubernetes version, endpoint access configuration
      (public/private), the node groups, and the IAM roles attached.
   3. COMPUTE — every EC2 instance type in use, its vCPU/memory profile, the node count, AMI
      or image details, and whether nodes are publicly addressable.
   4. STORAGE — every S3 bucket, its purpose, versioning, public-access settings, and
      encryption configuration.
   5. KEY MANAGEMENT — every KMS key, its key policy, rotation setting, and which resources
      consume it.

  Write the audit report to generated/aws_environment_analysis.md (create generated/ if it
  does not exist). It must contain:
   - An executive summary of the adserver1-prd workload.
   - One section per domain above, with resource tables (Resource | Identifier | Key
     attributes | Source JSON path).
   - A dedicated SECURITY FINDINGS section explicitly calling out each violation of the
     Cymbal Organization Zero-Trust standards: publicly addressable cluster nodes,
     unrestricted KMS key policies, absence of hardware-rooted boot integrity, and any
     over-permissive security group rule. State the risk and blast radius for each. A generic
     "security could be improved" paragraph does not count — tie every finding to a resource.
   - A COST OBSERVATIONS section noting the non-optimized c5.large footprint and the
     operational overhead of fragmented AWS-native IAM/KMS controls.
   - An OPEN QUESTIONS section listing anything the JSON does not tell us that a migration
     would need to know.

  Cite the JSON path for every claim. Then enumerate every top-level resource in the JSON and
  confirm each one appears somewhere in the report — tell me about any you could not place.

PHASE 3 — CROSS-CLOUD MAPPING & TECHNICAL DELIVERABLES  [checkpoint: task 2]
  Act as a Lead Platform Cloud Engineer authoring the migration proposal. Inputs are
  aws_environment.json and generated/aws_environment_analysis.md.

  Write generated/gcp_migration_proposal.md containing, in this order:

   1. EXECUTIVE SUMMARY — the business case in under 300 words, framed for Cymbal Direct and
      Cymbal Shops leadership: lower ad-serving latency, unified Cloud KMS protection,
      mandatory Zero-Trust posture, and cost optimization.
   2. SERVICE MAPPING MATRIX — columns: AWS Service | AWS Configuration (actual, from the
      export) | GCP Target Service | GCP Configuration | Migration Notes / Risks. Cover at
      minimum: VPC -> VPC, subnets/AZs -> regional subnets with secondary ranges, EKS -> GKE,
      EC2 c5.large node group -> GKE node pool machine type, S3 -> Cloud Storage, AWS KMS CMK
      -> Cloud KMS key ring + crypto key, IAM roles -> IAM service accounts + Workload
      Identity, security groups -> VPC firewall rules, NAT gateway -> Cloud NAT.
      Justify the compute sizing explicitly: state the vCPU/memory of c5.large and of the GCP
      machine type you select, and confirm they are comparable.
   3. AS-IS ARCHITECTURE DIAGRAM — a fenced ```mermaid block showing the legacy AWS topology:
      VPC boundary, both AZs as subgraphs, public node placement, EKS control plane, EC2
      nodes, S3, and KMS. Visually mark the security violations. This diagram must NOT depict
      any target-state component.
   4. TO-BE ARCHITECTURE DIAGRAM — a separate fenced ```mermaid block showing the GCP target:
      VPC and subnet with secondary ranges for pods and services, PRIVATE GKE cluster with
      nodes clearly inside a private perimeter and no external IPs, Cloud NAT for egress,
      Shielded VM node pool, CMEK-encrypted Cloud Storage bucket, and Cloud KMS key ring with
      service-agent-scoped IAM bindings.
   5. ZERO-TRUST COMPLIANCE MAPPING — a table mapping each Cymbal Organization mandate
      (private nodes only, Shielded VM with Secure Boot, service-agent-restricted KMS
      bindings) to the specific GCP control that enforces it and how it will be verified.
   6. TCO & VALUE PROPOSITION — cost comparison of the current AWS footprint versus the GCP
      target. Show your arithmetic: instance count x hourly rate x 730 hours, storage, egress,
      and key management. State every pricing assumption and its date explicitly, and label
      any figure you cannot source as an ESTIMATE. Include committed-use-discount and
      sustained-use-discount scenarios. Do not present unsourced numbers as fact, and compare
      both clouds on equivalent terms — same instance count, same hours, same storage volume.
   7. MIGRATION PHASES & RISK REGISTER — phased plan with entry/exit criteria, rollback
      strategy, and a risk table (risk | likelihood | impact | mitigation).

  Both Mermaid blocks must be syntactically valid and render standalone — walk each one node
  by node before you write it and check for unbalanced brackets, a subgraph without a
  matching `end`, reserved words as node IDs, and unescaped characters in edge labels. The
  GCP target region is `us-central1` throughout the matrix and the To-Be diagram.
  Confirm generated/aws_environment_analysis.md was NOT overwritten.

PHASE 4 — ORG-POLICY COMPLIANT TERRAFORM  [checkpoint: task 3]
  Author production-grade Terraform under ~/Desktop/Cymbal/aws_to_gcp_migration/terraform/,
  split across main.tf and variables.tf (plus outputs.tf if useful). Write the files to disk
  at those paths — do not only print them.

  NAMING AND REGION RULES — the lab's automated verification depends on these:
   - The region is `us-central1`. Every regional resource must be in `us-central1`: the
     subnet, the GKE cluster, the Cloud Router and Cloud NAT, the Cloud KMS key ring, and the
     GCS bucket location. Do not use a multi-region location for the bucket — a bucket in `US`
     with a key ring in `us-central1` will fail the CMEK binding at apply time.
   - Every resource name must contain the string `adserver`. Otherwise keep names unchanged
     from the AWS baseline where a direct analogue exists.
   - The GKE cluster must be named exactly `adserver1-prd`.
   - Parameterise project ID, region, and zone through variables.tf with the real values as
     defaults; no hardcoded project IDs scattered through main.tf. Before writing any file,
     run `gcloud config get-value project` (read-only, no auth flow) and tell me the project
     ID you will use as the default.

  RESOURCES TO CREATE, mapped from the AWS baseline:
   1. Custom-mode VPC (auto_create_subnetworks = false) with a subnet in the lab region, plus
      secondary IP ranges for GKE pods and services (VPC-native cluster).
   2. Cloud Router + Cloud NAT for the subnet. This is mandatory — private nodes have no
      external IP and cannot pull container images without it.
   3. Private GKE cluster `adserver1-prd`:
        - private_cluster_config with enable_private_nodes = true and a master_ipv4_cidr_block
          (a /28) that does not overlap the subnet or secondary ranges
        - ip_allocation_policy referencing the secondary ranges by their exact declared names
        - master_authorized_networks_config restricting control-plane access
        - workload_identity_config enabled
        - database_encryption in ENCRYPTED state referencing the Cloud KMS crypto key
   4. A separately managed node pool (remove_default_node_pool = true, initial_node_count = 1)
      sized comparably to the AWS c5.large (2 vCPU / 4 GB), with node_config containing:
        - shielded_instance_config { enable_secure_boot = true, enable_integrity_monitoring = true }
        - a dedicated least-privilege service account (not the default compute SA)
        - oauth_scopes limited to cloud-platform
        - metadata = { disable-legacy-endpoints = "true" }
   5. Cloud KMS key ring and crypto key with rotation configured.
   6. Cloud Storage deployment bucket with uniform_bucket_level_access = true,
      public_access_prevention = "enforced", versioning enabled, and
      encryption.default_kms_key_name pointing at the crypto key.
   7. KMS IAM bindings scoped to SERVICE AGENTS ONLY — no allUsers, no allAuthenticatedUsers,
      no broad user or group grants. Grant roles/cloudkms.cryptoKeyEncrypterDecrypter to:
        - the GKE service agent: service-<PROJECT_NUMBER>@container-engine-robot.iam.gserviceaccount.com
        - the Cloud Storage service agent: service-<PROJECT_NUMBER>@gs-project-accounts.iam.gserviceaccount.com
      Derive PROJECT_NUMBER from a `data "google_project"` block, not a hardcoded literal.
      Ensure these bindings are created BEFORE the resources that consume the key — a missing
      depends_on here causes an intermittent first-apply failure.
   8. Firewall rules replacing the AWS security groups, following least privilege — no
      0.0.0.0/0 ingress.
   9. google_project_service blocks enabling: container, compute, cloudkms, storage,
      servicenetworking, and iam — and have the resources depend on them.

  Add outputs for the cluster name, cluster endpoint, subnet self-link, bucket name, and
  crypto key ID.

  Before you finish, prove arithmetically that the subnet primary range, both secondary
  ranges, and master_ipv4_cidr_block do not overlap. Then run `terraform fmt`,
  `terraform init -backend=false`, and `terraform validate`, paste the raw output, and show me
  the full main.tf and variables.tf. Do not apply anything.

HAND-OFF
  Stop here. Print: the absolute workspace path, the project ID you used as the variables.tf
  default, `ls -la generated/`, `ls -la terraform/`, the `terraform validate` result, and the
  GCP machine type you selected with its vCPU/memory. Then list anything unresolved that
  part 2 needs to know about. Do not authenticate and do not apply.
```

---

## Prompt 2 — Deploy

Phase numbering continues from Prompt 1 so it stays aligned with the lab's tasks.

```text
You are my lead platform cloud engineer for the Cymbal Group AdServer migration lab. This is
part 2 of 3. Part 1 already cloned https://github.com/Ashwinikumar1/aws_to_gcp_migration into
~/Desktop/Cymbal/aws_to_gcp_migration, wrote generated/aws_environment_analysis.md and
generated/gcp_migration_proposal.md, and authored validated Terraform under terraform/.
The target region is `us-central1`.

RE-ESTABLISH CONTEXT FIRST — verify, do not assume. If any check fails, STOP and tell me
rather than silently redoing part 1:
  - cd into ~/Desktop/Cymbal/aws_to_gcp_migration and `pwd`.
  - `ls -la generated/` — aws_environment_analysis.md and gcp_migration_proposal.md should
    already be there, non-empty.
  - `ls -la terraform/` — confirm main.tf and variables.tf exist. Confirm there is no second,
    parallel Terraform tree elsewhere in the workspace: `find ~/Desktop/Cymbal -name "*.tf"`.
    Applying the wrong copy is a silent, expensive mistake.
  - Re-run `terraform validate` in terraform/ and paste the output before going further.
  - Confirm the GKE cluster in the config is named exactly `adserver1-prd` and that every
    region/location/zone argument reads `us-central1`. Quote the grep output.

OPERATING RULES
- Work through the phases in order. If a phase fails, STOP, paste the full error, diagnose it
  from evidence, and ask me before retrying. Never loosen a security setting to get past an
  error — no widening a KMS binding, no opening a firewall, no flipping nodes public.
- Quote the command you are about to run before running it.
- Print detailed background on what is happening under the hood as you go.
- Report honestly. A failed command, an empty result, or a partial pass is a finding.
- Write every document artifact to disk with your file-write tool; printing to chat does not
  count.

PHASE 5 — DEPLOY  [checkpoint: task 4]
  5a. AUTHENTICATE. Run `gcloud auth application-default login` and complete the flow. Then
      confirm the active account and project with `gcloud auth list` and
      `gcloud config get-value project`. Show me these values and STOP if the project is not
      my lab project. Never print a token.
  5b. `cd ~/Desktop/Cymbal/aws_to_gcp_migration/terraform` and run `terraform init`. Paste the
      output.
  5c. Run `terraform plan -out=tfplan`. Show me the plan summary and the full list of
      resources to be created, and confirm the counts are what we expect. Do not apply until
      I have seen the plan.
  5d. Run `terraform apply tfplan`. GKE provisioning takes roughly 10 minutes — do not abort,
      do not retry on slowness, and do not start a second apply against the same state.
      Report progress as it goes so I can follow along in /tasks.
  5e. If apply fails, paste the FULL error, diagnose the root cause, propose a fix, and wait
      for my approval before re-running. The three failures most likely here, in order:
        - Missing or misconfigured Cloud NAT — nodes come up NotReady and image pulls fail,
          while apply may still report success.
        - KMS location mismatch between the key ring, the bucket, and the cluster region.
        - KMS IAM bindings racing the resources that consume the key.
      Diagnose from the actual error text, not from this list.
  5f. On success, print all Terraform outputs.

PHASE 6 — LIVE VERIFICATION
  A green apply is not evidence. Run each of these and paste the RAW output:
    gcloud container clusters list
    gcloud container clusters describe adserver1-prd --region=us-central1 --format=json
    gcloud container node-pools list --cluster=adserver1-prd --region=us-central1
    gcloud compute networks subnets list --filter="region:us-central1"
    gcloud compute instances list --filter="name~gke-adserver"
    gcloud storage buckets list
    gcloud kms keyrings list --location=us-central1
    gcloud kms keys list --keyring=<keyring> --location=us-central1
    gcloud kms keys get-iam-policy <key> --keyring=<ring> --location=us-central1
  Then confirm, each as an explicit PASS or FAIL:
   1. Cluster name is exactly adserver1-prd, status RUNNING, and
      privateClusterConfig.enablePrivateNodes is true. Report the master CIDR and the
      authorized networks.
   2. Node pool status RUNNING, machine type matches the proposal, and
      config.shieldedInstanceConfig shows enableSecureBoot=true AND
      enableIntegrityMonitoring=true. Confirm the default node pool is gone.
   3. The EXTERNAL_IP column is EMPTY for every gke-adserver node. `enable_private_nodes` on
      the cluster and an actually-empty external IP column are different assertions — check
      the column.
   4. Fetch cluster credentials and run `kubectl get nodes`. Every node Ready. Nodes stuck
      NotReady almost always means Cloud NAT is missing or misrouted.
   5. The subnet has its primary range and BOTH secondary ranges (pods and services), with
      the exact names the cluster references.
   6. The bucket name contains `adserver`, uniformBucketLevelAccess is enabled,
      publicAccessPrevention is "enforced", encryption.defaultKmsKeyName points at the Cloud
      KMS key, and the bucket location is us-central1 (not the multi-region US).
   7. The key ring and key exist in us-central1, the key is ENABLED, and rotation is
      configured. The key IAM policy members are ONLY service agents
      (container-engine-robot and gs-project-accounts). Any allUsers, allAuthenticatedUsers,
      `user:`, or `group:` binding is a FAIL — quote it.
   8. NAMING SWEEP: list every created resource and confirm each name contains `adserver`.
      The grader keys on this; one renamed resource is a silent point loss.
  Finally re-run `terraform plan`. It must report "No changes." Any drift means the apply was
  incomplete — enumerate every drifted resource.

PHASE 7 — EXECUTIVE PROPOSAL (optional task 5)
  Synthesize an executive migration business proposal for Cymbal Group leadership. Inputs:
  aws_environment.json, generated/aws_environment_analysis.md, and
  generated/gcp_migration_proposal.md. Where GCP Migration Center AI assessment output is
  available in the Console, incorporate its findings and cite them as such.

  Write generated/gcp_value_proposition_analysis.md. Audience is executive leadership —
  business-outcome language, not Terraform. Frame everything around Cymbal Direct and Cymbal
  Shops ad-serving revenue. Required sections:
   1. EXECUTIVE SUMMARY — the recommendation and headline numbers, one page maximum,
      standing alone.
   2. BUSINESS DRIVERS — tie each of the three identified bottlenecks (security/governance
      non-compliance, high operating cost with fragmented IAM, container scalability and
      security risk) to a quantified business impact on retail ad revenue.
   3. MODERNIZATION OUTCOMES — Private GKE Zero-Trust perimeter, unified Cloud KMS
      encryption, Shielded VM boot integrity, autoscaling for peak global sales campaigns,
      and reduced ad latency. For each, state the before/after and how it will be measured.
   4. FINANCIAL ANALYSIS — TCO comparison, projected savings, ROI, and payback period. Show
      all arithmetic. Label every assumption and its source. Mark unsourced figures as
      ESTIMATE and give a range rather than a false-precision point value. Include migration
      COST (labour, dual-running, training), not only steady-state savings.
   5. RISK & MITIGATION — migration risks with mitigations and rollback posture.
   6. PHASED ROADMAP — timeline with milestones and decision gates.
   7. RECOMMENDATION & NEXT STEPS — a specific ask of leadership.

  Every number here must agree with the two earlier documents. Three documents with three
  different savings figures destroys credibility — cross-check before you write, and tell me
  about any figure you had to reconcile. Be honest about uncertainty: a defensible range with
  stated assumptions beats a confident number you cannot source.

FINISH
  Table of all five checkpoints (prerequisite, task 1, task 2, task 3, task 4, plus task 5 if
  done) with PASS/FAIL and the strongest evidence for each — the earlier ones carried over
  from part 1, re-checked against the artifacts on disk rather than restated. Then
  `ls -la generated/` and `ls -la terraform/`. State plainly anything that did not deploy,
  anything still provisioning, any command that errored, any security setting loosened during
  troubleshooting, and any step skipped.
```

---

## Prompt 3 — Review

```text
Act as an independent verifier for the Cymbal Group AdServer migration lab. Another session
did the build in two parts (part 1: workspace, AWS analysis, migration proposal, Terraform;
part 2: deploy, live verification, executive proposal). Do not trust either session's
summaries — re-verify everything from live command output and the filesystem, pasting raw
output for every claim. Separate what you OBSERVED from what you ASSUMED. PASS/FAIL per
checkpoint. Start by cd-ing into ~/Desktop/Cymbal/aws_to_gcp_migration and reporting the
project ID from `gcloud config get-value project`.

Region is `us-central1`. The GKE cluster is `adserver1-prd`. Every resource name must contain
`adserver`.

CHECKPOINT 0 — WORKSPACE
  - `ls -la ~/Desktop/Cymbal` — aws_to_gcp_migration exists, not nested one level deeper.
  - `git -C ~/Desktop/Cymbal/aws_to_gcp_migration remote -v` and `... log --oneline -5`. The
    remote must be github.com/Ashwinikumar1/aws_to_gcp_migration.
  - aws_environment.json exists and is valid JSON:
    `python3 -m json.tool aws_environment.json > /dev/null && echo VALID`. Report size and
    top-level keys.
  - Report which files were pre-existing in the clone versus generated by the build session —
    specifically whether aws_to_gcp_migration_analysis.md, terraform/, and generated/ shipped
    with the repo. `git status --short` distinguishes them.
  - `find ~/Desktop/Cymbal -name "*.tf"` — confirm there is exactly ONE Terraform tree. A
    second parallel copy means the applied config may not be the reviewed config.

CHECKPOINT 1 — AWS BASELINE ANALYSIS
  - generated/aws_environment_analysis.md exists and is non-empty. Report byte size and line
    count.
  - GROUNDING AUDIT, the core of this checkpoint. For EVERY resource identifier, CIDR,
    instance type, AZ, key ARN, and bucket name asserted in the report, locate it in
    aws_environment.json and cite the JSON path. Build a table:
      Claim | JSON path | Found in source? | Hallucinated?
    Flag both directions: anything in the report that is NOT in the JSON (hallucination), and
    anything in the JSON that is NOT in the report (coverage gap). Enumerate every top-level
    resource in the JSON and confirm each appears in the audit.
  - KNOWN-BASELINE CROSS-CHECK — independently verify these against the JSON and confirm the
    report states them correctly: VPC CIDR 10.17.0.0/16; two AZs us-east-1a and us-east-1b;
    EKS cluster adserver1-prd; node instance type c5.large; an S3 deployment bucket and an AWS
    KMS customer-managed key exist. Any discrepancy is a FAIL — say which side is wrong.
  - COMPLETENESS — all five domains (network, container, compute, storage, KMS) have
    substantive sections, plus SECURITY FINDINGS, COST OBSERVATIONS, and OPEN QUESTIONS. The
    security findings must explicitly name public cluster nodes, unrestricted KMS key policy,
    and missing boot integrity, each tied to a specific resource. A generic "security could be
    improved" paragraph is a FAIL.
  - REFERENCE COMPARISON — diff against the repo's reference file
    aws_to_gcp_migration_analysis.md. Produce three lists: facts the reference covers that the
    report misses; facts the report covers that the reference does not (verify each against
    the JSON — extra is fine if true, a FAIL if invented); and direct CONTRADICTIONS, saying
    which is correct per the JSON.

CHECKPOINT 2 — MIGRATION PROPOSAL
  - generated/gcp_migration_proposal.md exists, is non-empty, and contains all seven required
    sections. Confirm generated/aws_environment_analysis.md was NOT overwritten.
  - AWS-SIDE ACCURACY — every AWS configuration value in the mapping matrix matches
    aws_environment.json. Spot-check each row and flag mismatches. Confirm the c5.large spec
    is stated correctly (2 vCPU / 4 GB) and the proposed GCP machine type is genuinely
    comparable; a materially larger or smaller machine is an unjustified sizing change.
  - MAPPING COMPLETENESS — list every AWS resource in the JSON and confirm each has a matrix
    row. Also flag any GCP service proposed that maps to nothing in the source environment —
    that is scope creep.
  - DIAGRAM VALIDATION:
      1. Exactly TWO fenced ```mermaid blocks, each parsing. Walk them node by node and report
         any syntax error: unbalanced brackets, subgraph without a matching `end`, reserved
         words as node IDs, unescaped characters in edge labels.
      2. The AS-IS diagram shows PUBLIC nodes across two AZs and does NOT depict target state.
      3. The TO-BE diagram shows private nodes with NO external IP path, Cloud NAT for egress,
         and CMEK arrows from Cloud KMS to both GKE and the storage bucket.
      4. Two-column diff: every component in the mapping matrix appears in the relevant
         diagram and vice versa.
  - ZERO-TRUST CLAIMS — for each of the three Cymbal mandates, the proposal names a SPECIFIC
    GCP control and a concrete verification method. Reject anything unfalsifiable.
  - TCO SCRUTINY, be hard on this: every price figure labelled with source and date or clearly
    marked ESTIMATE (an unsourced number presented as fact is a FAIL); recompute the arithmetic
    independently and report math errors; confirm both sides are compared on equivalent terms
    (same instance count, hours, storage volume, discount assumptions) and flag any
    cherry-picked discount applied to only one cloud; confirm egress, support, and
    key-management costs appear on both sides.

CHECKPOINT 3 — TERRAFORM
  - STATIC VALIDATION — run and paste raw output:
      terraform fmt -check -recursive
      terraform init -backend=false
      terraform validate
    Any error is an automatic FAIL. Report it and stop rather than proceeding.
  - GRADER PRECONDITIONS — these four cause most zero-scores despite a successful apply:
      1. Is the GKE cluster named exactly `adserver1-prd`? Quote the line.
      2. Does EVERY resource name contain `adserver`? List every resource address with its
         name attribute and flag non-compliant ones.
      3. Is the region `us-central1` CONSISTENTLY? Grep the whole terraform directory for
         every region, location, and zone argument and print each with file:line. Subnet, GKE
         cluster, Cloud Router, Cloud NAT, KMS key ring, and GCS bucket must all be
         `us-central1`. Flag any other region, any bucket using the multi-region `US`
         location, and any leftover placeholder string.
      4. Is the project ID the actual lab project? Cross-check the variables.tf default
         against `gcloud config get-value project`.
  - ZERO-TRUST COMPLIANCE — quote the exact argument for each; "it's configured" is not an
    acceptable answer:
      1. enable_private_nodes = true, and no external IPs configured anywhere.
      2. shielded_instance_config with enable_secure_boot = true AND
         enable_integrity_monitoring = true on the MANAGED node pool — not only on the default
         pool. Confirm remove_default_node_pool = true so the compliant pool is the one that
         survives. Setting Shielded config on the pool that gets removed is a common miss.
      3. KMS IAM bindings scoped to service agents only. Grep the whole config for `allUsers`,
         `allAuthenticatedUsers`, `roles/owner`, `roles/editor`, and any `member` that is a
         user or group rather than a service agent. Any hit is a compliance FAIL — quote it.
      4. Bucket has uniform_bucket_level_access = true, public_access_prevention = "enforced",
         and default_kms_key_name set.
      5. No firewall rule allows 0.0.0.0/0 ingress. List every source_ranges value.
      6. Node pool uses a dedicated service account, not the default compute service account.
  - APPLY-TIME FAILURE MODES that `terraform validate` will NOT catch:
      1. CLOUD NAT — is there a google_compute_router + google_compute_router_nat covering the
         subnet? Without it private nodes cannot pull images and come up NotReady. This is the
         single most common failure in this lab; check it first and loudly.
      2. CIDR OVERLAP — print the subnet primary range, both secondary ranges, and
         master_ipv4_cidr_block. Prove arithmetically that none overlap. Confirm the master
         CIDR is a /28.
      3. SECONDARY RANGE WIRING — ip_allocation_policy references the secondary ranges by the
         exact names declared on the subnet. A name typo fails at apply.
      4. API ENABLEMENT — google_project_service blocks for container, compute, cloudkms,
         storage, and iam, with resources depending on them.
      5. PROJECT NUMBER — service-agent members built from a `data "google_project"` lookup,
         not a hardcoded number copied from elsewhere.
      6. KMS LOCATION — key ring location matches the bucket location and the cluster region.
      7. ORDERING — KMS IAM bindings exist before the resources that consume the key.
      8. DELETION PROTECTION — note anything that will block lab cleanup.
  - BASELINE FIDELITY — cross-check against generated/gcp_migration_proposal.md: every GCP
    service in the mapping matrix appears in the Terraform, and the node machine type matches
    the sizing justified in the proposal. Report any divergence.
  - OUTPUTS — confirm outputs exist for cluster name, endpoint, subnet, bucket, and crypto
    key. Quote the blocks.

CHECKPOINT 4 — LIVE DEPLOYMENT
  A green `terraform apply` is not acceptable evidence on its own. Every claim needs live
  gcloud output pasted raw.
  - IDEMPOTENCY — re-run `terraform plan`. It must report "No changes." Any drift means the
    apply was incomplete; enumerate every drifted resource.
  - GKE CLUSTER:
    `gcloud container clusters describe adserver1-prd --region=us-central1 --format=json`
    Name exactly adserver1-prd, status RUNNING, privateClusterConfig.enablePrivateNodes true.
    Report the master CIDR and the authorized networks.
  - NODE POOLS: list and describe each. Status RUNNING, machine type matches the proposal,
    config.shieldedInstanceConfig shows enableSecureBoot=true AND
    enableIntegrityMonitoring=true, default node pool gone.
    Then `gcloud compute instances list --filter="name~gke-adserver"` — the EXTERNAL_IP column
    must be EMPTY for every node. A node with a public IP fails the Zero-Trust mandate even if
    the cluster is flagged private.
    Then fetch credentials and `kubectl get nodes` — every node Ready. NotReady almost always
    means Cloud NAT is missing.
  - VPC SUBNETS: `gcloud compute networks subnets list --filter="region:us-central1"` and
    describe the subnet. Primary range and BOTH secondary ranges (pods and services) exist
    with the names the cluster references.
  - CLOUD STORAGE: `gcloud storage buckets describe gs://<bucket> --format=json`. Name
    contains `adserver`, uniformBucketLevelAccess enabled, publicAccessPrevention "enforced",
    encryption.defaultKmsKeyName points at the Cloud KMS key, location is correct.
  - CLOUD KMS: key ring and key exist in us-central1, key is ENABLED, rotation configured.
    Then `gcloud kms keys get-iam-policy <key> --keyring=<ring> --location=us-central1` —
    members are ONLY service agents (container-engine-robot and gs-project-accounts). Any
    allUsers, allAuthenticatedUsers, `user:`, or `group:` binding is a FAIL. Quote it.
  - NAMING SWEEP: list every created resource and confirm each name contains `adserver`.
  - NEGATIVE TESTS: confirm the GKE control plane is not reachable from an unauthorized
    network (check master authorized networks), and that the bucket is not publicly readable
    (confirm public access prevention blocks anonymous access).

CHECKPOINT 5 — EXECUTIVE PROPOSAL (if attempted)
  - generated/gcp_value_proposition_analysis.md exists with all seven sections. Assess
    register: flag any paragraph that is engineer-facing detail (resource names, HCL, CIDR
    blocks) rather than business outcome. The executive summary must stand alone in under one
    page.
  - FACTUAL CONSISTENCY — cross-check every technical and financial claim against
    aws_environment_analysis.md and gcp_migration_proposal.md. Table: Claim | Source doc |
    Consistent? Any number contradicting the earlier deliverables is a FAIL.
  - FINANCIAL RIGOUR, assume a hostile CFO: recompute every calculation and report arithmetic
    errors; confirm every assumption is stated with a source and a date; confirm unsourced
    figures are marked ESTIMATE and given as ranges; confirm ROI/payback is internally
    consistent with the TCO table; confirm migration COST (labour, dual-running, training) is
    included, not only steady-state savings; confirm AWS and GCP are compared on equivalent
    terms. List every number a CFO could challenge and say whether the document survives it.
  - UNSUPPORTED CLAIMS — flag every superlative with no supporting evidence ("dramatically
    faster", "significantly more secure", "industry-leading"). Each must be quantified and
    sourced or removed.
  - COMPLETENESS — the three named bottlenecks each appear with a quantified impact, and
    Private GKE, Cloud KMS, and Shielded VM outcomes each have a measurable before/after.

CROSS-CUTTING
  - `ls -la generated/` — all expected documents present, none overwritten by a later phase.
  - Consistency table across all three documents: machine type | cost figures | region |
    resource names. Any mismatch means one document is stale.
  - Grep every artifact for unsubstituted placeholders (PROJECT_ID, <bucket>, TODO).
  - Both Mermaid diagrams still parse and still match the infrastructure that actually exists.
    Reconcile the To-Be diagram against the live gcloud inventory node by node.
  - SECURITY LOOSENED DURING TROUBLESHOOTING — compare the applied config against the
    Zero-Trust mandates and report any control that was relaxed to make the apply succeed. If
    one was, flag it as a blocker; do not present it as a pass.

OUTPUT
  One table: Checkpoint | PASS/FAIL | strongest evidence. Then severity-ordered remediation
  (Blocker / Major / Minor) with exact commands and exact .tf diffs for every Blocker. State
  plainly anything you could not verify, any step skipped, and any setting loosened during
  troubleshooting. Do not soften a failure.
```

---

## Reviewer's Own Checklist (human, not AI)

The AI will report PASS on several things worth verifying yourself:

- **The file actually exists on disk.** Gemini 3.6 in agy will sometimes print a complete
  document in chat and report success without writing it. `ls -la generated/` after every doc
  phase, and open it in VS Code.
- **`us-central1` in all five places.** Subnet, cluster, Router/NAT, KMS key ring, GCS bucket.
  A bucket left in the multi-region `US` location breaks CMEK at apply time.
- **`adserver` in every name.** The graders key on it. One renamed-by-the-model resource is a
  silent point loss.
- **No duplicate Terraform tree.** Confirm the model wrote to `terraform/main.tf` and did not
  create a parallel copy elsewhere that you then apply from — or worse, apply the wrong one.
- **Cloud NAT.** Private nodes with no NAT come up NotReady and image pulls fail. `terraform
  apply` can still report success while the cluster is functionally dead.
- **Shielded config on the *managed* node pool.** Setting it on the default pool that gets
  removed is a very common miss.
- **Nodes with no external IP.** `enable_private_nodes = true` on the cluster and an actually
  empty EXTERNAL_IP column are different assertions. Check the column.
- **KMS IAM members.** Grep for `allUsers` / `allAuthenticatedUsers` yourself — this is the
  exact violation the migration exists to eliminate.
- **Security loosened during troubleshooting.** If the assistant hit a permission error and
  "fixed" it by broadening a binding, the deployment works and the mandate is broken.
- **Mermaid actually renders.** Paste both diagrams into the VS Code preview or mermaid.live.
- **Consistent numbers across all three documents.** Analysis, proposal, and value
  proposition must agree.
