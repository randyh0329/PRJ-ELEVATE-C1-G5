"""Local LLM-as-judge for `case_rubric_pass_rate` (see eval_config_multi_turn.yaml).

The managed multi-turn metrics generate their own adaptive rubrics and ignore a
case's `rubric_groups`, so per-case criteria on a multi-turn case have to be
graded locally. This judge reads `rubric_groups.case_criteria` off the instance
and returns the fraction of criteria the conversation satisfies.

Execution stays local: the remote `CodeExecutionMetric` sandbox has no network,
so it could not reach a judge model.
"""

import json

from google import genai
from google.genai import types
from pydantic import BaseModel

JUDGE_MODEL = "gemini-3.1-pro"  # SDD §9.1: Gemini 3.1 Pro is the LLM-as-a-judge


class _RubricVerdict(BaseModel):
    rubric_id: str
    passed: bool
    reasoning: str


class _Verdict(BaseModel):
    verdicts: list[_RubricVerdict]


def _rubrics(instance):
    out = []
    for group in (instance.get("rubric_groups") or {}).values():
        for rubric in group.get("rubrics", []):
            description = (
                rubric.get("content", {}).get("property", {}).get("description", "")
            )
            out.append({"rubric_id": rubric.get("rubric_id", ""), "criterion": description})
    return out


def evaluate(instance):
    rubrics = _rubrics(instance)
    if not rubrics:
        return {"score": 1.0, "explanation": "no case criteria attached to this case"}

    prompt = (
        "You are grading a multi-turn conversation from an enterprise HR and IT "
        "service assistant against per-case criteria. Judge only the criteria given; "
        "do not invent additional ones. A criterion about a tool call is satisfied "
        "only if the trace actually contains that call.\n\n"
        f"Criteria:\n{json.dumps(rubrics, indent=2)}\n\n"
        f"Conversation trace:\n{json.dumps(instance.get('agent_data') or {})}\n\n"
        f"Final response:\n{instance.get('response', '')}\n\n"
        "Return one verdict per criterion."
    )

    client = genai.Client()
    response = client.models.generate_content(
        model=JUDGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=_Verdict,
        ),
    )
    verdict = response.parsed
    if verdict is None:
        return {"score": 0.0, "explanation": response.text or "judge returned no verdict"}

    failed = [v for v in verdict.verdicts if not v.passed]
    score = (len(verdict.verdicts) - len(failed)) / max(1, len(verdict.verdicts))
    if not failed:
        return {"score": score, "explanation": f"all {len(verdict.verdicts)} criteria met"}
    return {
        "score": score,
        "explanation": "; ".join(f"{v.rubric_id}: {v.reasoning}" for v in failed),
    }
