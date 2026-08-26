# Lab 1 — HR Vacation Request Subsystem Multi-Region Migration

## Review Prompts (validation harness for each task)

Unlike [Lab 2](lab2-prompts.md) and [Lab 3](lab3-prompts.md), which ship a config prompt and a
deploy prompt alongside their review prompt, Lab 1 is **review-only**. Use the lab's own task
instructions to drive the build, and this file to audit the result.

These are **review prompts**, not build prompts. After Antigravity (or any AI assistant)
completes a task, paste the matching review prompt back into the assistant to have it
audit its own output against the customer's acceptance criteria. Each prompt is written
to force *evidence* (file paths, command output, resource IDs) rather than a narrative
claim of success, and to end in an explicit **PASS / FAIL** verdict with a remediation
list.

**Lab constants**

| Item | Value |
| --- | --- |
| Project ID | `qwiklabs-gcp-00-c061b4ab6c6f` |
| Docs bucket | `qwiklabs-gcp-00-c061b4ab6c6f-docs` |
| Primary region | `us-central1` |
| Secondary region | `europe-west1` |
| Workspace root | `~/Desktop/ce-sample-hr-vacation` |
| Upstream repo | `https://github.com/Ashwinikumar1/ce-sample-hr-vaccation` (note: upstream repo name is spelled `vaccation`; the local directory must be `ce-sample-hr-vacation`) |

**How to use**

1. Run the build prompt for task *N*.
2. Paste review prompt *N* into the same Antigravity session.
3. Fix everything in the remediation list, then re-run review prompt *N* until it returns PASS.
4. Only then move to task *N+1* — later tasks consume the artifacts of earlier ones.

---

## Review Prompt 0 — Prerequisite: Workspace Setup

```text
Act as an independent reviewer. Do not assume any prior step succeeded — verify everything
from the filesystem and from command output.

Validate the workspace prerequisite for the HR Vacation Request Subsystem lab:

1. Confirm the directory ~/Desktop/ce-sample-hr-vacation exists. Run `ls -la ~/Desktop`
   and paste the raw output.
2. Confirm it is a valid git working tree cloned from the upstream repository. Run
   `git -C ~/Desktop/ce-sample-hr-vacation remote -v` and
   `git -C ~/Desktop/ce-sample-hr-vacation log --oneline -5`, and paste the output.
   The remote must point at github.com/Ashwinikumar1/ce-sample-hr-vaccation.
3. Confirm the clone landed at the correct depth — the application source must be directly
   under ce-sample-hr-vacation/, NOT nested inside a second
   ce-sample-hr-vacation/ce-sample-hr-vaccation/ folder. Show the top two levels of the
   tree.
4. Inventory what was actually cloned: list the application source directories, the
   Dockerfile(s), any terraform/ or infra/ directory, and any existing docs/ directory.
5. Confirm the working tree is clean (`git status --short` returns nothing).

Report a table of Check / Expected / Actual / PASS-FAIL, then an overall verdict.
If any check FAILS, give the exact shell commands to remediate — do not fix anything yet,
just propose the commands.
```

**Manual spot-check:** open the Files app or VS Code on the remote desktop and confirm
`ce-sample-hr-vacation` is visible on the Desktop.

---

## Review Prompt 1 — Workload Discovery & Baseline Architecture

```text
Act as a senior Google Cloud architecture reviewer performing an independent QA pass on
the baseline discovery deliverables. Read the actual files — do not rely on your memory of
what you generated.

Scope: ~/Desktop/ce-sample-hr-vacation

A. ARTIFACT EXISTENCE
   Run `ls -la ~/Desktop/ce-sample-hr-vacation/docs/` and confirm both files exist and are
   non-empty:
     - docs/baseline_summary.md
     - docs/baseline_architecture.md
   Report byte size and line count for each.

B. GROUNDING CHECK (most important — this is where AI output usually fails)
   For every GCP service, resource name, region, port, database name, and environment
   variable named in baseline_summary.md, cite the file and line in the repository that
   proves it. Build a table: Claim | Evidence file:line | Verified? | Hallucinated?
   Explicitly flag anything asserted in the doc that you cannot trace to a source file,
   a Terraform resource, a Dockerfile, an app config, or a deployment manifest.
   Also flag the inverse: any GCP service that IS present in the repo but MISSING from
   the summary.

C. CONTENT COMPLETENESS — baseline_summary.md must cover:
   1. Every active GCP service in the single-region deployment (Cloud Run app service with
      internal-only ingress, AlloyDB for PostgreSQL, Cloud DNS private zone, VPC,
      Serverless VPC Access connector, Private Service Connect / Private Service Access).
   2. Network boundaries: VPC name, subnet CIDRs, the ingress setting on Cloud Run, egress
      path from Cloud Run to the database, and why the database is not publicly reachable.
   3. Database dependencies: which app components talk to which datastore, the connection
      hostname (and whether it is resolved via the private DNS zone), and the schema
      domains in play (workflows, notifications, employees, accrual balances).
   4. An explicit, enumerated SPOF register. Each entry must state: the component, the
      single region it is pinned to, the blast radius if that region degrades, the current
      RTO/RPO (or "undefined"), and the business impact on Cymbal Group.
   5. The three problems named by the customer must each be addressed by name:
      regional blocker, database scalability limitation, coupled traffic routing.
   Report any of these five that is missing or is covered only superficially.

D. DIAGRAM VALIDITY — baseline_architecture.md must:
   1. Contain a fenced ```mermaid block with valid Mermaid syntax (graph/flowchart). Parse
      it mentally node by node and report any syntax error: unbalanced brackets, reserved
      words used as node IDs, subgraph blocks without a matching `end`, edge labels with
      unescaped special characters.
   2. Depict the SINGLE-region topology only — it must NOT show a second region, a global
      load balancer, read replicas, or Memorystore. Those belong to Task 2. Flag any
      forward-leaking target-state component.
   3. Show the user -> ingress -> Cloud Run -> VPC connector -> private networking ->
      AlloyDB path, with the region boundary drawn as a subgraph.
   4. Visually mark the SPOFs (e.g. a distinct class/style) and be consistent with the SPOF
      register in baseline_summary.md — cross-check the two lists match exactly.

E. VERDICT
   Give PASS or FAIL per artifact plus an overall verdict, then a numbered remediation list
   ordered by severity. For each remediation item, quote the current text and give the exact
   replacement text. Do not rewrite the files yet — wait for my approval.
```

---

## Review Prompt 2 — Customer Directives & Multi-Region Blueprint

```text
Act as the Cymbal Group Enterprise Architecture reviewer signing off on the target-state
design. Your job is to prove the design satisfies every customer mandate, and to catch any
mandate that was silently dropped or invented.

Scope: ~/Desktop/ce-sample-hr-vacation

A. REQUIREMENTS TRACEABILITY MATRIX (the core of this review)
   Read docs/customer_requirements.md in full. Extract EVERY discrete mandate as a numbered
   requirement — including implicit ones stated in prose. Then build a traceability matrix:

     Req ID | Requirement (verbatim quote) | Where satisfied (updated_summary.md section or
     updated_architecture.md node) | Satisfied fully / partially / NOT AT ALL

   Rules:
     - Every row must cite a quote from the deliverable, not a paraphrase.
     - Any requirement with no citation is a FAIL. List these first, loudly.
     - Also list REVERSE-TRACEABILITY gaps: design decisions present in updated_summary.md
       that no customer requirement asks for. These are scope creep or hallucination — call
       each one out and state whether it is defensible.

B. ARTIFACT EXISTENCE
   Confirm docs/updated_summary.md and docs/updated_architecture.md exist, are non-empty,
   and that the earlier baseline artifacts were NOT overwritten or deleted.

C. TECHNICAL DEPTH — updated_summary.md must specify, concretely (named resources, regions,
   and numbers — not adjectives):
   1. Multi-region footprint across us-central1 and europe-west1: VPC subnets and their
      non-overlapping CIDR ranges in both regions.
   2. AlloyDB topology: primary cluster region, cross-region read-replica / secondary
      cluster region, active-passive DR posture, replication mode (async vs sync) and the
      resulting data-consistency model, plus stated RTO and RPO targets and the failover
      procedure (manual promotion vs automatic).
   3. The read/write split: which traffic goes to the primary and which to the replica, and
      how the application chooses — specifically how Cloud DNS private zones abstract the DB
      hostname to allow a zero-code-change regional failover.
   4. Caching tier: Memorystore for Redis instance per region, what is cached (session,
      accrual-balance reads, notification fan-out), TTL / invalidation strategy, and
      cache-miss behaviour.
   5. Global load balancing: GCLB with a single global Anycast IP, serverless NEG backends
      for the Cloud Run service in each region, health checks, outlier detection / failover
      behaviour, and how latency-based routing sends EU subsidiaries to europe-west1.
   6. Cloud Run in both regions retaining internal-and-cloud-load-balancing ingress, so the
      service remains reachable only via the GCLB.
   7. An explicit statement of how each of the three original SPOFs from
      docs/baseline_summary.md is now eliminated. Cross-reference the baseline SPOF register
      one-for-one; any SPOF left unaddressed is a FAIL.

D. DIAGRAM VALIDITY — updated_architecture.md must:
   1. Contain a syntactically valid fenced ```mermaid block; report any parse error.
   2. Show the global Anycast IP / GCLB at the top fanning out to BOTH regional subgraphs.
   3. Show, inside each of the us-central1 and europe-west1 subgraphs: Cloud Run, Serverless
      VPC connector, Memorystore Redis, and the AlloyDB node (primary in one region,
      replica/secondary in the other).
   4. Show the cross-region AlloyDB replication edge, directionally correct
      (primary -> replica), and labelled with the replication type.
   5. Show the Cloud DNS private zone as the indirection point in front of the DB endpoint.
   6. Be internally consistent with updated_summary.md — every component in the prose must
      appear in the diagram and vice versa. Produce a two-column diff of prose components vs
      diagram nodes.

E. VERDICT
   PASS/FAIL per artifact and overall, then a severity-ordered remediation list with exact
   replacement text. Do not edit the files until I approve.
```

---

## Review Prompt 3 — GCS Bucket & Artifact Upload

```text
Act as a release verifier. Prove — with live gcloud/gsutil output, not assertions — that the
architecture deliverables are correctly published for automated grading. Paste the raw
output of every command you run.

Target bucket: gs://qwiklabs-gcp-00-c061b4ab6c6f-docs
Project:       qwiklabs-gcp-00-c061b4ab6c6f

A. IDENTITY & PROJECT
   Run `gcloud config get-value project` and `gcloud auth list`. Confirm the active project
   is exactly qwiklabs-gcp-00-c061b4ab6c6f. A bucket created in the wrong project fails the
   lab even if the name is right.

B. BUCKET EXISTENCE AND NAMING
   Run `gcloud storage buckets describe gs://qwiklabs-gcp-00-c061b4ab6c6f-docs --format=json`.
   Verify:
     - The bucket name is character-for-character qwiklabs-gcp-00-c061b4ab6c6f-docs
       (no suffix, no prefix, no typo, all lowercase).
     - It resolves inside the lab project.
     - Report its location, storage class, and public-access-prevention setting.
   If the describe call errors, report the exact error and stop — do not claim success.

C. OBJECT INVENTORY
   Run `gcloud storage ls -l gs://qwiklabs-gcp-00-c061b4ab6c6f-docs/**`.
   Confirm all four objects exist:
     baseline_summary.md, baseline_architecture.md, updated_summary.md, updated_architecture.md
   For each object report: full object path, size in bytes, and update time.

D. PATH-SHAPE CHECK (common silent failure)
   State whether the objects sit at the BUCKET ROOT (gs://<bucket>/baseline_summary.md) or
   under a docs/ prefix (gs://<bucket>/docs/baseline_summary.md). Report which layout is
   present. If a recursive copy nested them unexpectedly, flag it — automated verification
   may only look at one of the two layouts. Recommend uploading to both locations if there
   is any ambiguity.

E. CONTENT INTEGRITY
   For each of the four files, compare the local copy in
   ~/Desktop/ce-sample-hr-vacation/docs/ against the uploaded object:
     - Compare byte size.
     - Compare MD5/CRC32C: `gcloud storage hash --hex <local file>` vs the hash reported by
       `gcloud storage ls -L`.
   Any mismatch means a stale version is in the bucket — flag it and report which local file
   is newer.

F. NON-EMPTY / NON-PLACEHOLDER CHECK
   Confirm no uploaded file is 0 bytes or a stub. Print the first 15 lines of each object via
   `gcloud storage cat` and confirm each contains real content (and, for the two architecture
   files, a ```mermaid fence).

G. VERDICT
   PASS/FAIL per check, overall verdict, and the exact `gcloud storage cp` commands needed to
   remediate any failure.
```

---

## Review Prompt 4 — Terraform Refactor to Multi-Region

```text
Act as a Terraform code reviewer and cloud architect. Review the refactored configuration for
correctness, for fidelity to the approved blueprint, and for anything that will explode at
apply time. Read the .tf files directly and quote them.

Scope: ~/Desktop/ce-sample-hr-vacation/terraform/ (or root .tf files if that is the layout —
state which layout is actually present and list every .tf file with its line count).

A. STATIC VALIDATION — run these and paste raw output:
     terraform fmt -check -recursive
     terraform init -backend=false
     terraform validate
   Any error or non-zero exit is an automatic FAIL. Do not proceed past a validate failure —
   report it and stop.

B. BLUEPRINT FIDELITY
   Re-read docs/updated_summary.md and docs/updated_architecture.md. Build a matrix:

     Blueprint component | Terraform resource address(es) | file:line | Present? | Matches spec?

   Every component in the blueprint must map to at least one resource address. Every resource
   in the config should map back to the blueprint — flag orphans.

C. REQUIRED RESOURCES — confirm each exists, and report its resource address and key arguments:
   1. VPC + subnets in BOTH us-central1 and europe-west1, with non-overlapping CIDRs. Print
      each CIDR and prove no overlap arithmetically.
   2. AlloyDB: primary cluster + primary instance in one region, and a cross-region
      secondary/read-replica cluster + instance in the other. Confirm the secondary is
      actually configured as a secondary (cluster_type / secondary_config referencing the
      primary), not a second independent primary.
   3. Cloud Run services in BOTH regions. Confirm ingress is
      INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER (or internal-and-cloud-load-balancing) — NOT
      "all". An ingress of "all" violates the customer's internal-only mandate and is a FAIL.
   4. Serverless VPC Access connector (or Direct VPC egress) in each region, wired to that
      region's Cloud Run service.
   5. Memorystore for Redis instance in each region, in the correct region's subnet /
      authorized network.
   6. GCLB: global external IP address (Anycast), forwarding rule, target proxy, URL map, and
      a serverless NEG per region attached as backends of a single global backend service.
      Confirm the backend service has BOTH regional NEGs — a single-NEG backend silently
      defeats the whole lab.
   7. Cloud DNS private managed zone + records abstracting the AlloyDB endpoint, and confirm
      the app config/env var points at the DNS name and not a raw IP.
   8. Private Service Connect / Private Service Access (service networking connection +
      allocated IP range) for the AlloyDB clusters.

D. HARDCODING & PARAMETERISATION
   Grep for hardcoded project IDs, region strings, and IP addresses. Confirm project, regions,
   and CIDRs come from variables with sane defaults, and that
   qwiklabs-gcp-00-c061b4ab6c6f is the project value in terraform.tfvars or the variable
   default. List every remaining hardcoded literal with its file:line.

E. FAILURE-MODE REVIEW (things terraform validate will NOT catch)
   1. Dependency ordering: does the AlloyDB secondary cluster depend on the primary? Does the
      service networking connection precede the AlloyDB clusters? Do the NEGs depend on the
      Cloud Run services? List any missing depends_on that will cause a race on first apply.
   2. Required APIs: is there a google_project_service block (or documented manual step) for
      compute, run, alloydb, servicenetworking, redis, dns, and vpcaccess? A missing API
      enablement is the single most common apply failure in this lab.
   3. Quota/naming: any resource name that exceeds length limits, uses invalid characters, or
      would collide across regions (same name in two regions where the resource is global).
   4. Deletion protection / lifecycle flags that would block iteration.
   5. Region-availability: confirm every resource type used is actually available in
      europe-west1.
   6. IAM: does the Cloud Run service account have the roles it needs (alloydb.client,
      redis.editor / network access)? Is the run.invoker binding correct for LB-only access?

F. OUTPUTS
   Confirm an output exists for the GCLB global IP address / application URL — Task 5 depends
   on it. Quote the output block.

G. VERDICT
   PASS/FAIL overall plus a severity-ranked remediation list (Blocker / Major / Minor). For
   each blocker, give the exact .tf diff. Do not apply anything.
```

---

## Review Prompt 5 — Provision & Verify the Deployment

```text
Act as the deployment verifier for the Cymbal Group multi-region migration. Confirm the
infrastructure is genuinely live and symmetric across both regions. Use live gcloud output
for every claim — a green `terraform apply` alone is NOT acceptable evidence.

Project: qwiklabs-gcp-00-c061b4ab6c6f | Regions: us-central1, europe-west1

A. APPLY RESULT
   Report the terraform apply summary line (added/changed/destroyed) and then run
   `terraform plan` again. A clean re-plan must report "No changes. Your infrastructure
   matches the configuration." Any drift means the apply was incomplete — list every drifted
   resource.

B. LIVE RESOURCE INVENTORY — run each command and paste raw output:
     gcloud run services list --project=qwiklabs-gcp-00-c061b4ab6c6f
     gcloud alloydb clusters list --region=us-central1
     gcloud alloydb clusters list --region=europe-west1
     gcloud alloydb instances list --cluster=<each cluster> --region=<each region>
     gcloud redis instances list --region=us-central1
     gcloud redis instances list --region=europe-west1
     gcloud compute networks subnets list --filter="region:(us-central1 europe-west1)"
     gcloud compute addresses list --global
     gcloud compute backend-services list --global
     gcloud compute network-endpoint-groups list
     gcloud compute forwarding-rules list --global
     gcloud dns managed-zones list

C. SYMMETRY AUDIT
   Build a two-column table, us-central1 vs europe-west1, one row per resource type
   (subnet, Cloud Run service, VPC connector, Memorystore, AlloyDB cluster, serverless NEG).
   Every row must be populated on BOTH sides. Any single-sided row is a FAIL — the entire
   point of this lab is symmetry. Also confirm each resource reports a READY / RUNNABLE /
   ACTIVE state, not CREATING or FAILED.

D. LOAD BALANCER WIRING
   1. Print the global backend service config and confirm it lists TWO backends — the
      serverless NEG from each region.
   2. Confirm the URL map and forwarding rule reference the global Anycast IP.
   3. Confirm each Cloud Run service's ingress is internal-and-cloud-load-balancing, so the
      direct *.run.app URLs are NOT publicly reachable. Prove it: curl the raw Cloud Run URL
      and confirm it returns 403/404, not 200.

E. DATABASE REPLICATION
   Confirm one AlloyDB cluster is PRIMARY and the other is SECONDARY, and that the secondary
   names the primary in its config. Report the replication state / lag if available.

F. END-TO-END APPLICATION TEST — the real acceptance criterion:
   1. Report the final GCLB application access URL (http:// or https:// + the global IP or
      hostname).
   2. Run `curl -sSI <URL>` and paste headers. Expect a 200 (or an expected redirect chain
      that terminates in 200).
   3. Run `curl -sS <URL>` and confirm the HR Vacation Request UI HTML is returned, not a
      Google 404/502 error page.
   4. Exercise one API/transactional path that touches the database and report the response.
   5. Note that a newly created GCLB can take 5-10 minutes to serve traffic — if you get 404
      or 502, wait and retry, and report how many retries were needed rather than declaring
      failure or success prematurely.

G. HONEST REPORTING
   State plainly anything that did NOT get deployed, any resource still provisioning, any
   command that errored, and any step you skipped. Do not paper over partial success.

H. VERDICT
   Overall PASS/FAIL, the confirmed application access URL on its own line, and a remediation
   list for anything short of PASS.
```

---

## Cross-Task Final Sweep

```text
Final end-to-end audit before I hand this to the customer. Verify the whole chain is
internally consistent, not just each task in isolation:

1. Every SPOF listed in docs/baseline_summary.md is explicitly remediated in
   docs/updated_summary.md, is represented in the Terraform config, and is observable in the
   deployed infrastructure. Produce one table: SPOF -> design remedy -> terraform resource ->
   live resource -> verified?
2. Every mandate in docs/customer_requirements.md traces all the way to a live resource.
   Flag any requirement that stops at the document stage.
3. The four .md files in gs://qwiklabs-gcp-00-c061b4ab6c6f-docs are the CURRENT versions —
   re-run the hash comparison, since Tasks 4 and 5 may have prompted doc edits after upload.
   If the local docs changed, re-upload and say so.
4. Both Mermaid diagrams still parse and still match the infrastructure that actually exists.
   Reconcile the updated diagram against the live gcloud inventory node by node.
5. List, in priority order, everything still outstanding. If nothing is outstanding, say so
   plainly and give the single application access URL as the deliverable.
```

---

## Reviewer's Own Checklist (human, not AI)

Things the AI will report as PASS that are worth eyeballing yourself:

- **Directory name.** Upstream is `ce-sample-hr-vaccation`; a naive `git clone` produces the
  misspelled folder. The lab checks for `ce-sample-hr-vacation`.
- **Mermaid actually renders.** Paste each diagram into the VS Code Mermaid preview or
  mermaid.live. "Valid-looking" and "parses" are different things.
- **Bucket object layout.** Root vs `docs/` prefix — if in doubt, upload to both.
- **Cloud Run ingress.** If the assistant "fixed" a 403 by setting ingress to `all`, the lab
  requirement is broken even though the URL works.
- **Two NEGs on one backend service.** A single-region backend still returns 200 and looks
  successful.
- **AlloyDB secondary vs second primary.** Both list as "a cluster in europe-west1"; only one
  of them satisfies the DR mandate.
- **Re-upload docs after Tasks 4-5** if the design documents were edited during refactoring.
