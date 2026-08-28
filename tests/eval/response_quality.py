"""Local LLM-as-judge for `custom_response_quality` (see eval_config.yaml).

Grades the final response of a single-turn eval case against the SDD §9.1
quality bar: grounded, cited, plainly worded, and free of internal detail.

Runs in-process via `google-genai`, so it needs no eval region and no Vertex
project. `genai.Client()` picks up `GEMINI_API_KEY` (AI Studio) or ADC
(Gemini Enterprise Agent Platform).
"""

import json

from google import genai
from google.genai import types
from pydantic import BaseModel

JUDGE_MODEL = "gemini-3.1-pro"  # SDD §9.1: Gemini 3.1 Pro is the LLM-as-a-judge


class _Verdict(BaseModel):
    score: int  # 1-5
    explanation: str


_RUBRIC = """\
Grade the assistant's final response on a 1-5 scale (1 poor, 5 excellent) against \
the quality bar for an enterprise HR and IT service assistant:

1. Grounding - every factual claim about policy, entitlement or system state traces \
   to the retrieved context or to a tool response in the trace. An unsupported claim \
   caps the score at 2, however fluent the answer.
2. Citation - a policy answer names its source document.
3. Honest failure - when the assistant cannot answer or a step did not complete, it \
   says so plainly instead of producing a plausible substitute.
4. Actionability - the employee is left knowing what happens next.
5. Containment - no stack trace, HTTP status, vendor error string or other internal \
   detail reaches the employee, and no personal data beyond the employee's own.

A refusal is not a failure. When the case expects a refusal or an escalation, grade \
the quality of that refusal, not the absence of an answer.\
"""


def evaluate(instance):
    reference = instance.get("reference")
    context = instance.get("context")
    expectation = instance.get("guardrail_expectation")

    prompt = f"You are an expert QA evaluator for an enterprise AI assistant.\n{_RUBRIC}\n\n"
    if expectation:
        prompt += f"Expected handling for this case: {expectation}\n"
    if context:
        prompt += f"Retrieved context available to the assistant:\n{context}\n"
    prompt += (
        f"User prompt: {instance.get('prompt', '')}\n"
        f"Final response: {instance.get('response', '')}\n"
    )
    if reference:
        prompt += (
            f"Expected answer (ground truth): {reference}\n"
            "Penalise factual disagreement with the expected answer. Do not penalise "
            "wording that differs while agreeing on substance.\n"
        )
    prompt += f"Full agent trace: {json.dumps(instance.get('agent_data') or {})}\n"

    client = genai.Client()
    response = client.models.generate_content(
        model=JUDGE_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,  # deterministic grading
            response_mime_type="application/json",
            response_schema=_Verdict,
        ),
    )
    verdict = response.parsed
    if verdict is None:  # model returned nothing usable
        return {"score": 0, "explanation": response.text or "judge returned no verdict"}
    return {"score": max(1, min(5, verdict.score)), "explanation": verdict.explanation}
