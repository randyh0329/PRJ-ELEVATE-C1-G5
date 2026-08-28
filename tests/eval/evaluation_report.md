# Evaluation Report — Enterprise Agentic Solution, MVP 1

| | |
| :--- | :--- |
| **System under evaluation** | Enterprise Agentic Solution (HR & IT service assistant), MVP 1 |
| **Design of record** | [`Enterprise Agentic Solution Design Document - MVP 1.md`](../../Enterprise%20Agentic%20Solution%20Design%20Document%20-%20MVP%201.md) v2.2 |
| **Harness** | `agents-cli eval` (Gemini Enterprise Agent Platform Evaluation) |
| **Config** | [`eval_config.yaml`](eval_config.yaml), [`eval_config_multi_turn.yaml`](eval_config_multi_turn.yaml) |
| **Datasets** | [`datasets/`](datasets/) |
| **Owner** | HR Knowledge Team (corpus) · Platform Team (harness) |
| **Status** | **Harness and corpus seed committed. No run has been executed** — see [§7 Current results](#7-current-results). |

---

## 1. What this directory is

SDD §9.2 commits to a versioned, owned evaluation corpus — *"a versioned, owned
artefact, not an ad-hoc script"* — and SDD §9.3 makes that corpus the release
gate rather than an after-the-fact report. This directory is that artefact,
expressed in the format `agents-cli eval` executes:

```
tests/eval/
├── eval_config.yaml              # single-turn metric selection + custom metric pool
├── eval_config_multi_turn.yaml   # multi-turn metric selection + custom metric pool
├── response_quality.py           # local LLM-as-judge (single-turn)
├── rubric_judge.py               # local LLM-as-judge for per-case multi-turn criteria
├── evaluation_report.md          # this file
└── datasets/
    ├── README.md                 # dataset schema and field reference
    ├── eval-data.json            # 12 single-turn cases (golden slice)
    ├── eval-multi-turn.json      # 6 continued-conversation cases (saga + dialog)
    └── eval-red-team.json        # 10 adversarial vectors (separate corpus)
```

**These 28 cases are a seed, not the corpus.** SDD §9.2 commits to **150 golden
prompts** (50 policy Q&A, 50 single-system transactions, 50 cross-system saga)
plus a **separate 100-vector red-team suite**. What is checked in here is the
executable skeleton: every domain partition, eight of the ten registered tool
operations, the compensation-class boundary that matters most, and every metric
the full corpus will be graded with. Growing 28 → 250 is corpus work owned by the HR
Knowledge Team; it does not change the harness. §6 states the coverage gap
explicitly rather than letting a green run imply completeness.

## 2. Evaluation approach

### 2.1 Four layers, deliberately

A single LLM judge grading a single dimension is how eval suites end up
confidently wrong. Each case is graded by four independent layers, and the
cheapest, most deterministic layer runs first:

| Layer | Mechanism | Catches |
| :--- | :--- | :--- |
| **1 — Deterministic code** | `custom_function` in the config. No model, no network, no ambiguity. | Missing tool call, missing citation, leaked stack trace, identity passed as a tool parameter, a HUMAN_CONSEQUENTIAL step auto-reversed. |
| **2 — Managed adaptive rubrics** | `multi_turn_task_success`, `multi_turn_trajectory_quality`, `multi_turn_tool_use_quality`, `final_response_quality`. | Goal completion, step sequencing, tool-use semantics — judged against criteria the service generates, so the suite is not only testing what its authors thought to test. |
| **3 — Per-case criteria** | `rubric_groups.case_criteria` on every case, graded by the built-in (single-turn) or `rubric_judge.py` (multi-turn). | The specific thing *this* case exists to prove. `GD-UC22-014-FAIL` exists to prove the leave is **not** cancelled; no generic rubric would check that. |
| **4 — Static safety rubrics** | `hallucination`, `safety`. | Fabricated claims and policy violations, scored by fixed criteria that do not drift with the corpus. |

Layers 1 and 3 are the ones that fail a release. Layers 2 and 4 are the ones
that find the failure modes nobody wrote a case for.

### 2.2 Why the corpus is split across three files

Metrics apply to **every case in a run**, and every single-turn built-in metric
returns `400 Single-turn metric '<name>_v1' received agent_eval_data with N
turns` on a multi-turn trace. So single-turn and multi-turn cases need separate
dataset + config pairs. That is a harness constraint.

The red-team split is a *methodology* choice, and it comes straight from SDD
§9.2: the adversarial corpus is deliberately not part of the golden set, because
mixing 100 hostile prompts into 150 ordinary ones distorts the per-domain
accuracy score that the §9.1 grounding threshold is measured against. Blocked
adversarial prompts would inflate "correct refusal" behaviour into the policy
Q&A numbers. They are graded and reported separately.

### 2.3 Coverage discipline

SDD §9.2 defines coverage in two directions, and both are enforced here:

- **Inside-out.** Every requirement in Appendix A must appear in at least one
  case's `requirement_refs` array. *A requirement with no golden case is an
  unfinished requirement.* The seed corpus covers **21 of the 29** FR/NFRs; §6
  names the eight that are uncovered.
- **Outside-in.** Real UAT and pilot prompts that no case matches are triaged
  weekly (SDD §9.4 captures every unmatched prompt for exactly this). Genuine
  gaps become new cases, and the triage round is recorded so coverage growth is
  visible rather than asserted.

### 2.4 Rubric-based tool checking, not sequence matching

`tool_trajectory_coverage` scores whether every **required** call happened. It
does not require them in order and does not penalise extra calls. Strict
sequence matching is brittle: an agent that geocodes an address before filing a
shipping request, or re-reads a balance to confirm, is not wrong. Sequencing
quality is judged semantically by `multi_turn_trajectory_quality`, and
*forbidden* calls are caught by the deterministic guards
(`subject_binding_respected`, `compensation_class_respected`) rather than by the
absence of a match.

### 2.5 Determinism

Both local judges run at `temperature=0` with a `response_schema`, so a verdict
is schema-valid JSON and repeat runs agree. The single-turn managed judge is
sampled three times (`judge_model_sampling_count: 3`) where configured. A score
that still fluctuates between runs is treated as a finding about the *agent's*
non-determinism, not as a flaky test to be skipped.

## 3. Metric-to-threshold map

Every metric here traces to a pass threshold in **SDD §9.1** and, through it, to
a BRD requirement. A metric that gates nothing does not belong in the suite.

| SDD §9.1 dimension | Pass threshold | Metric(s) | Layer |
| :--- | :--- | :--- | :--- |
| **Policy Grounding** | ≥ 95% accuracy, **0% policy hallucination** | `hallucination`, `policy_grounding_judge`, `custom_response_quality` | 4, 2 |
| *(citation precision)* | Citation resolvable on every policy answer | `citation_presence` | 1 |
| **Guardrail Robustness** | **100% blocked**, < 1% false positives | `safety` + `case_criteria` on `eval-red-team.json`; `RT-FP-001` is the false-positive control | 4, 3 |
| **Transaction Integrity** | 100% correct, **0 unauthorised writes** | `multi_turn_tool_use_quality`, `tool_trajectory_coverage` | 2, 1 |
| **Cross-System Orchestration** | Pass on all UC-2.x, **correct compensation class on every failure branch** | `multi_turn_task_success`, `compensation_class_respected` | 2, 1 |
| **Data Isolation** | **0 successful cross-user reads** | `subject_binding_respected`, `RT-XUSER-001/002` | 1, 3 |
| **Graceful Degradation** | 100% graceful; **no stack traces or internal codes leaked** | `no_internal_error_leakage`, `GD-DEG-001`, `GD-UC12-003` | 1, 3 |
| **NLU Robustness** | ≥ 95% intent accuracy | `final_response_quality` over perturbed variants (see §6) | 2 |
| **Auditability** | 100% of API interactions and safety blocks logged | *Not gradeable here* — reconciliation job, SDD §7.5 | — |
| **Response Latency** | TTFT avg < 1.0 s; total < 3.5 s; safety overhead p95 < 300 ms | *Not gradeable here* — Cloud Trace percentiles, SDD §9.5 | — |

**Two dimensions are deliberately out of scope for this harness.** Latency and
audit completeness are properties of the running system measured by Cloud Trace
spans and a reconciliation job, not properties of a response an LLM judge can
read. Scoring them here would produce a number that looks like evidence and
isn't. They are gated by SDD §9.5 (load profiles, p95 hard gate) and SDD §7.5
respectively. The suite is honest about the boundary rather than papering over
it.

## 4. Running the evaluation

```bash
uv tool install google-agents-cli

# Single-turn golden slice: run the agent, then grade the traces
agents-cli eval run \
  --config tests/eval/eval_config.yaml \
  --dataset tests/eval/datasets/eval-data.json

# Adversarial suite — reported separately, never merged into the golden score
agents-cli eval run \
  --config tests/eval/eval_config.yaml \
  --dataset tests/eval/datasets/eval-red-team.json

# Multi-turn / saga slice
agents-cli eval run \
  --config tests/eval/eval_config_multi_turn.yaml \
  --dataset tests/eval/datasets/eval-multi-turn.json
```

Decoupled form, when traces should be generated once and graded repeatedly —
which is what the CI gate does, so a metric change does not cost another full
agent run:

```bash
agents-cli eval generate --dataset tests/eval/datasets/eval-data.json -o artifacts/traces/
agents-cli eval grade --traces artifacts/traces/ --config tests/eval/eval_config.yaml
```

Against a deployed environment rather than a local process:

```bash
agents-cli eval generate --url https://<uat-endpoint>.run.app --app-name app \
  --dataset tests/eval/datasets/eval-data.json
```

Comparing a candidate against the released baseline — the operation SDD §9.3
actually gates on:

```bash
agents-cli eval compare artifacts/grade_results/baseline.json \
                        artifacts/grade_results/results_<ts>.json
```

Results are written to `artifacts/grade_results/results_<timestamp>.{json,html}`.

### 4.1 Fault injection

`GD-DEG-001` and `GD-UC22-014-FAIL` carry a `failure_injection` field. They are
only meaningful against a mock backend running the fault-injecting fidelity
profile described in SDD §5.6 — against a healthy mock they will pass for the
wrong reason. Run them in the chaos profile or exclude them; do not run them in
the default profile and count the pass.

### 4.2 Region and residency

`eval run` / `eval grade` default to the `global` endpoint and do **not**
inherit the deployment region. Where data-residency rules prohibit that, drop
the managed metrics and run the local ones only — every metric marked *Layer 1*
or *Layer 3* in §2.1 executes in-process with no GCP region required, and the
two local judges can be pointed at a compliant model endpoint:

```bash
agents-cli eval grade --traces artifacts/traces/ \
  --metrics custom_response_quality,tool_trajectory_coverage,citation_presence,no_internal_error_leakage,subject_binding_respected
```

This loses the adaptive-rubric layer. It does not lose the release gate.

## 5. The CI gate

SDD §9.3: before any change to prompts, tools, model IDs, guardrail thresholds
or the agent registry can merge, the full golden set and the red-team suite run
and are compared against the last released baseline. **Any regression on a §9.1
threshold blocks the merge**, and the report is attached to the PR.

Two details matter for anyone wiring this up:

1. **`eval run` exits 0 whatever the scores are.** The exit code is not the
   gate. The gate is a check over `results_<ts>.json` against the §9.1
   thresholds, and it must be written as an explicit step — not inferred from a
   green command.
2. **Hold cases back.** A slice of the corpus stays out of the iteration loop
   and is graded only at release. Without it there is no way to distinguish a
   fix that generalises from one fitted to the cases it was tuned against.

## 6. Known gaps in the seed corpus

Stated plainly, because a green run over 28 cases is not evidence about 250.

| Gap | Consequence | Owner / when |
| :--- | :--- | :--- |
| 12 of 150 golden cases; 10 of 100 red-team vectors | Domain accuracy percentages are not yet statistically meaningful. Report counts, not rates, until the corpus is complete. | HR Knowledge Team, before Phase 4 UAT entry |
| 8 of 29 FR/NFRs uncovered: FR-1.2, FR-2.1, FR-5.1, FR-5.5, NFR-1.2, NFR-2.1, NFR-2.2, NFR-2.3 | Four are out of scope for this harness by §3 (NFR-1.2 audit, NFR-2.1/2.2/2.3 latency, availability, async). The other four — origin verification, NLU, ingestion, sync latency — need cases. | HR Knowledge Team + Platform Team |
| UC-2.3 (relocation) has no case | The third saga path is unexercised. | Platform Team |
| No perturbed-prompt variants | The §9.1 NLU Robustness row (FR-2.1) has no cases behind it yet; it needs typo, synonym and context-shift variants of the policy slice. | HR Knowledge Team |
| `si.update_status` and `ww.cancel_leave` have no positive-path case | Both appear only as calls the agent must *not* make (`GD-UC13-010`, `RT-PRIV-001`, `compensation_class_respected`). The legitimate forward path for each is untested. | Integration Teams |
| Accessibility (WCAG 2.2 AA, DEC-24) is not gradeable here | It is a UI property. Gated by the axe-core CI scan and the two assistive-technology UAT participants (SDD §9.4), not by this suite. | HR Change Lead |
| No baseline `results_*.json` committed | `eval compare` has nothing to compare against until the first release run. | Platform Team, first UAT build |

## 7. Current results

**None. No evaluation run has been executed against this corpus.**

There is no agent implementation in this repository yet — MVP 1 is at design
baseline (SDD v2.2, *Approved — Implementation Baseline*), and Phase 1 of the
SDD §7.4 plan has not started. This directory is the harness the implementation
will be graded by, committed ahead of the code so the bar is set before there is
anything with an interest in lowering it.

When the first run happens, the scores table from `agents-cli eval run` gets
pasted into this section verbatim — every case, not only the ones that pass —
and the `results_<ts>.json` is committed as the `eval compare` baseline. Until
then this section stays empty. An evaluation report with no results is honest;
one with asserted results is worse than useless.

## 8. References

- SDD §9.1 Evaluation Metrics & Success Thresholds
- SDD §9.2 Golden Dataset Specification
- SDD §9.3 Automated CI/CD Evaluation Gate
- SDD §9.4 User Acceptance Testing Plan
- SDD §9.5 Performance Profiling & Latency Validation Plan
- SDD §5.4 Saga Compensation Classification · §5.6 Mock Fidelity Profiles · §7.5 Structured Log Schemas
- SDD Appendix A — Requirements Traceability Matrix
- [`google/agents-cli`](https://github.com/google/agents-cli) — evaluation harness and dataset format
