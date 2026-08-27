"""Reference A2A consumer.

This is the shape another agent - the Policy Specialist of SDD §3.2, say - uses
to reach this knowledge base. It discovers the card, calls a named skill, and
reads both the text and the structured data part off the returned artifact.

    python -m policy_rag.a2a_app.client_demo --url http://127.0.0.1:8080 \
        --skill policy_answer "How many vacation days after 8 years?"

Entitlements are sent as a transport header, never in the message body - see the
module docstring of `executor.py` for why.
"""

from __future__ import annotations

import argparse
import asyncio
import json

import httpx
from a2a.client import ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest
from google.protobuf import json_format

from src.grounding.policy_rag.a2a_app.card import SKILL_IDS, SKILL_POLICY_ANSWER
from src.grounding.policy_rag.a2a_app.executor import ENTITLEMENTS_HEADER


def _artifact_payloads(response) -> tuple[list[str], list[dict]]:
    """Pull text and JSON data parts out of whatever the server streamed back."""
    texts: list[str] = []
    payloads: list[dict] = []

    artifacts = []
    if response.HasField("artifact_update"):
        artifacts.append(response.artifact_update.artifact)
    elif response.HasField("task"):
        artifacts.extend(response.task.artifacts)
    elif response.HasField("message"):
        for part in response.message.parts:
            if part.text:
                texts.append(part.text)

    for artifact in artifacts:
        for part in artifact.parts:
            if part.HasField("data"):
                value = json_format.MessageToDict(part.data)
                if isinstance(value, dict):
                    payloads.append(value)
            elif part.text:
                texts.append(part.text)

    return texts, payloads


async def ask(
    url: str,
    question: str,
    *,
    skill: str = SKILL_POLICY_ANSWER,
    entitlements: list[str] | None = None,
    top_k: int | None = None,
) -> tuple[list[str], list[dict]]:
    headers = {}
    if entitlements:
        headers[ENTITLEMENTS_HEADER] = ",".join(entitlements)

    async with httpx.AsyncClient(headers=headers, timeout=60.0) as http_client:
        client = await create_client(url, ClientConfig(streaming=False, httpx_client=http_client))

        parameters: dict = {"skill": skill}
        if top_k:
            parameters["top_k"] = top_k

        request = SendMessageRequest(
            message=Message(
                role=Role.ROLE_USER,
                message_id=f"demo-{abs(hash(question)) % 10**12}",
                parts=[Part(text=question, media_type="text/plain")],
                metadata=parameters,
            )
        )

        texts: list[str] = []
        payloads: list[dict] = []
        async for response in client.send_message(request):
            new_texts, new_payloads = _artifact_payloads(response)
            texts.extend(new_texts)
            payloads.extend(new_payloads)
        return texts, payloads


def main() -> int:
    parser = argparse.ArgumentParser(description="A2A client for the HR policy RAG")
    parser.add_argument("question", nargs="?", default="What is the bereavement leave policy?")
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--skill", default=SKILL_POLICY_ANSWER, choices=list(SKILL_IDS))
    parser.add_argument("--entitlement", action="append", dest="entitlements", default=None)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="print the structured data part only")
    args = parser.parse_args()

    texts, payloads = asyncio.run(
        ask(
            args.url,
            args.question,
            skill=args.skill,
            entitlements=args.entitlements,
            top_k=args.top_k,
        )
    )

    if args.json:
        print(json.dumps(payloads, indent=2))
    else:
        for text in texts:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
