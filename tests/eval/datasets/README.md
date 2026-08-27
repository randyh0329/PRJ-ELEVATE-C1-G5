# Evaluation Datasets

Dataset files here follow the **Gemini Enterprise Agent Platform Evaluation
dataset format** consumed by `agents-cli eval`. They are the executable form of
the golden corpus specified in **SDD §9.2 (Golden Dataset Specification)**.

| File | Shape | Cases | Config to grade with |
| :--- | :--- | :--- | :--- |
| `eval-data.json` | single-prompt | 12 | `../eval_config.yaml` |
| `eval-multi-turn.json` | continued conversation | 6 | `../eval_config_multi_turn.yaml` |
| `eval-red-team.json` | single-prompt | 10 | `../eval_config.yaml` |

The red-team corpus is a **separate file on purpose**. SDD §9.2 keeps the
100 adversarial vectors out of the 150 golden prompts because mixing them
distorts per-domain accuracy scores. Grade it as its own run and report its
numbers separately.

## The two case shapes

An eval case uses **either** `prompt` **or** `agent_data` — never both.

### (a) Single-prompt case — `eval-data.json`, `eval-red-team.json`

The agent runs from scratch against one user message.

```json
{
  "eval_cases": [
    {
      "eval_case_id": "GD-UC12-001",
      "prompt": {
        "role": "user",
        "parts": [{"text": "How much vacation time do I have left this year?"}]
      }
    }
  ]
}
```

### (b) Continued-conversation case — `eval-multi-turn.json`

Prior turns are carried in `agent_data`, the last event is a user message, and
`eval generate` appends the agent's next response — the "N+1" pattern. This is
how the saga paths (UC-2.1–UC-2.3) and the FR-2.2 multi-turn dialog cases are
expressed: the conversation is *primed* to the interesting turn rather than
replayed from the beginning.

```json
{
  "eval_cases": [
    {
      "eval_case_id": "GD-UC22-014",
      "agent_data": {
        "agents": {
          "hcm_specialist": {
            "agent_id": "hcm_specialist",
            "agent_type": "SpecialistAgent",
            "instruction": "Execute WorkWeek HCM operations."
          }
        },
        "turns": [
          {
            "turn_index": 0,
            "events": [
              {"author": "user", "content": {"role": "user", "parts": [{"text": "First user message"}]}},
              {"author": "hcm_specialist", "content": {"role": "model", "parts": [{"function_call": {"name": "ww.get_balances", "args": {}}}]}},
              {"author": "hcm_specialist", "content": {"role": "model", "parts": [{"function_response": {"name": "ww.get_balances", "response": {"vacation": {"accruedHours": 96}}}}]}},
              {"author": "hcm_specialist", "content": {"role": "model", "parts": [{"text": "First agent reply"}]}},
              {"author": "user", "content": {"role": "user", "parts": [{"text": "Follow-up user message"}]}}
            ]
          }
        ]
      }
    }
  ]
}
```

## Standard fields

| Field | Purpose |
| :--- | :--- |
| `eval_cases` | Array of cases. Required. |
| `eval_case_id` | Unique identifier. Here it is the SDD §9.2 golden record ID (`GD-…`, `RT-…`) so a failing case maps straight back to a requirement. |
| `prompt` | The single user message. Shape (a) only. |
| `agent_data.turns` | Prior conversation, ending with a user message. Shape (b) only. |
| `reference` | Ground truth, wrapped as `{"response": {"role": "model", "parts": [...]}}`. Read by `final_response_match` and by the local judge. |
| `context` | Source text for the `grounding` metric. Carried by the `policy_qa` cases. |
| `rubric_groups` | Per-case pass/fail criteria. Every case here uses exactly one group, `case_criteria`. |

## Project-specific fields

The schema permits extra fields on a case, and custom metrics receive them on
`instance`. These carry the SDD §9.2 golden record attributes through into the
run, so an eval result is traceable to a requirement without a side lookup:

| Field | Used by |
| :--- | :--- |
| `domain` | Partitioning scores per SDD §9.2 (`policy_qa`, `single_system`, `cross_system`, `degradation`, `privacy_rights`, `escalation`, `red_team`). |
| `use_case_id`, `requirement_refs` | Appendix A traceability. Every requirement must appear in at least one `requirement_refs` array. |
| `expected_tool_trajectory` | `tool_trajectory_coverage` metric. |
| `expected_citations` | `citation_presence` metric. |
| `guardrail_expectation` | Read by the local judge so a refusal is graded as a refusal. |
| `expected_compensation_class` | `compensation_class_respected` metric (NFR-4.3 / §5.4). |
| `failure_injection` | Names the fault the mock backend must inject; see the fidelity profiles in SDD §5.6. |
| `difficulty`, `owner` | Reporting and corpus governance. |

## Running

```bash
# Single-turn golden slice
agents-cli eval run --config ../eval_config.yaml --dataset eval-data.json

# Adversarial suite, reported separately
agents-cli eval run --config ../eval_config.yaml --dataset eval-red-team.json

# Multi-turn / saga slice
agents-cli eval run --config ../eval_config_multi_turn.yaml --dataset eval-multi-turn.json
```

Full methodology, thresholds and the CI gate: [`../evaluation_report.md`](../evaluation_report.md).

## Common mistakes

| Mistake | Fix |
| :--- | :--- |
| `"role": "assistant"` | Use `"role": "model"` — the Vertex convention. |
| Missing `turn_index` | Always set sequential 0-based indices. |
| Tool result as plain text | Wrap it in a `function_response` part. |
| `prompt` **and** `agent_data` on one case | Use one or the other. |
| Single-turn and multi-turn cases in one file | Metrics apply to every case in a run, and single-turn built-ins 400 on a multi-turn trace. Keep the files split. |
