"""A2A `AgentExecutor` binding the RAG service to the protocol.

Request shape
-------------
The question is the message's text part(s). Optional parameters travel in a
JSON data part, or in `message.metadata`::

    {
      "skill": "policy_answer",     # policy_search | policy_answer | corpus_status
      "top_k": 5,
      "corpora": ["okf-handbook"],
      "doc_types": ["policy"]
    }

Entitlements are the one thing a caller may **not** put in the payload. They are
resolved from the transport - an `X-Altostrat-Entitlements` header set by the
gateway that authenticated the principal - because a payload field is under the
control of whatever produced the message, and in an agent-to-agent chain that
may be an LLM acting on text an employee typed. SDD §4.1 makes the same point
about `employee_id`: the subject is bound from the authenticated session, never
model-supplied. A payload that tries to set entitlements is ignored and logged.

Response shape
--------------
One artifact with two parts: a text part carrying the human-readable answer, and
a JSON data part carrying the structured result (decision, relevance,
groundedness, citations, chunks) for a programmatic caller.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from a2a.helpers import new_task
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState
from google.protobuf import json_format, struct_pb2

from src.grounding.policy_rag.a2a_app.card import (
    SKILL_CORPUS_STATUS,
    SKILL_IDS,
    SKILL_POLICY_ANSWER,
    SKILL_POLICY_SEARCH,
)
from src.grounding.policy_rag.config import GENERAL_ENTITLEMENT
from src.grounding.policy_rag.ingest import detect_drift
from src.grounding.policy_rag.service import PolicyRagService

logger = logging.getLogger(__name__)

#: Header the authenticating gateway sets. Comma-separated entitlement names.
ENTITLEMENTS_HEADER = "x-altostrat-entitlements"
#: Escape hatch for local development against a server with no gateway in front.
TRUST_PAYLOAD_ENTITLEMENTS_ENV = "POLICY_RAG_TRUST_PAYLOAD_ENTITLEMENTS"

ARTIFACT_NAME = "policy-rag-result"


def _to_value(payload: Any) -> struct_pb2.Value:
    return json_format.ParseDict(payload, struct_pb2.Value())


def data_part(payload: dict) -> Part:
    return Part(data=_to_value(payload), media_type="application/json")


def _payload_from_message(context: RequestContext) -> dict:
    """Merge parameters from data parts, JSON text parts and metadata.

    Both metadata slots are read. `RequestContext.metadata` is the *params*
    metadata (`MessageSendParams.metadata`), which is not the same field as
    `Message.metadata`, and a caller has no particular reason to prefer one -
    the spec offers both. Params metadata wins on a key collision because it is
    the outer, per-call envelope.
    """
    merged: dict[str, Any] = {}

    message = context.message
    if message is not None:
        for part in message.parts:
            if part.HasField("data"):
                value = json_format.MessageToDict(part.data)
                if isinstance(value, dict):
                    merged.update(value)
            elif part.text and part.media_type == "application/json":
                try:
                    parsed = json.loads(part.text)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    merged.update(parsed)

        if message.HasField("metadata"):
            message_metadata = json_format.MessageToDict(message.metadata)
            if isinstance(message_metadata, dict):
                merged.update(message_metadata)

    metadata = context.metadata or {}
    if isinstance(metadata, dict):
        merged.update(metadata)

    return merged


def _question_from_message(context: RequestContext, payload: dict) -> str:
    """Prefer the message text; fall back to an explicit `query` parameter."""
    text_parts: list[str] = []
    message = context.message
    if message is not None:
        for part in message.parts:
            if part.text and part.media_type != "application/json":
                text_parts.append(part.text)
    question = "\n".join(t.strip() for t in text_parts if t.strip()).strip()
    if question:
        return question
    return str(payload.get("query") or payload.get("question") or "").strip()


def resolve_entitlements(context: RequestContext, payload: dict) -> list[str]:
    """Entitlements come from the transport, not from the message body."""
    headers: dict[str, str] = {}
    call_context = context.call_context
    if call_context is not None:
        raw_headers = call_context.state.get("headers") or {}
        headers = {str(k).lower(): str(v) for k, v in raw_headers.items()}

    from_header = headers.get(ENTITLEMENTS_HEADER, "")
    entitlements = [e.strip() for e in from_header.split(",") if e.strip()]

    if "entitlements" in payload:
        if os.environ.get(TRUST_PAYLOAD_ENTITLEMENTS_ENV) == "1":
            payload_entitlements = payload.get("entitlements") or []
            if isinstance(payload_entitlements, list):
                entitlements.extend(str(e) for e in payload_entitlements)
        else:
            logger.warning(
                "ignoring caller-supplied entitlements in message payload; "
                "entitlements are bound from the %s header only",
                ENTITLEMENTS_HEADER,
            )

    # Every authenticated caller holds the general corpus entitlement; anything
    # above it has to be granted explicitly.
    if GENERAL_ENTITLEMENT not in entitlements:
        entitlements.append(GENERAL_ENTITLEMENT)
    return entitlements


def _resolve_skill(payload: dict) -> str:
    skill = str(payload.get("skill") or SKILL_POLICY_ANSWER).strip()
    if skill not in SKILL_IDS:
        logger.warning("unknown skill %r requested; defaulting to %s", skill, SKILL_POLICY_ANSWER)
        return SKILL_POLICY_ANSWER
    return skill


def _as_top_k(value: Any) -> int | None:
    """Coerce a wire `top_k` to a positive int, or to None for "use the default".

    JSON has one number type and a protobuf `Struct` follows it, so a `top_k` of
    5 arrives here as `5.0` however the caller wrote it. Anything that is not a
    usable count - a bool, a string, a negative - is dropped rather than guessed
    at: retrieving the configured default is a sane outcome, retrieving zero
    passages is not.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    return count if count > 0 else None


def _as_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return None


class PolicyRagExecutor(AgentExecutor):
    """Executes the three card skills against a `PolicyRagService`."""

    def __init__(self, service: PolicyRagService) -> None:
        self.service = service

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = await self._begin(context, event_queue)

        payload = _payload_from_message(context)
        skill = _resolve_skill(payload)
        entitlements = resolve_entitlements(context, payload)

        if skill == SKILL_CORPUS_STATUS:
            result = self._corpus_status()
            await self._emit(updater, self._render_status(result), result, skill)
            return

        question = _question_from_message(context, payload)
        if not question:
            body = {
                "decision": "REFUSE",
                "reason": "empty_query",
                "skill": skill,
                "answer": "No question was supplied. Send the question as a text part.",
            }
            await self._emit(updater, body["answer"], body, skill)
            return

        common = {
            "entitlements": entitlements,
            "top_k": _as_top_k(payload.get("top_k")),
            "corpora": _as_str_list(payload.get("corpora")),
            "doc_types": _as_str_list(payload.get("doc_types")),
        }

        logger.info("skill=%s entitlements=%s query=%r", skill, entitlements, question)

        if skill == SKILL_POLICY_SEARCH:
            retrieval = self.service.search(question, **common)
            body = retrieval.to_dict()
            body["skill"] = skill
            text = self._render_search(retrieval)
        else:
            answer = self.service.answer(question, **common)
            body = answer.to_dict()
            body["skill"] = skill
            text = answer.text

        await self._emit(updater, text, body, skill)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id or "", context.context_id or "")
        await updater.cancel()

    # --- helpers ------------------------------------------------------------

    @staticmethod
    async def _begin(context: RequestContext, event_queue: EventQueue) -> TaskUpdater:
        """Open the task and return an updater bound to it.

        The server rejects a `TaskStatusUpdateEvent` for a task it has never
        seen (`InvalidAgentResponseError: Agent should enqueue Task before ...`),
        so the *first* event on a fresh request has to be the `Task` itself -
        `TaskUpdater.submit()` is not enough, because it only publishes a status
        update. On a follow-up message the task already exists and re-enqueueing
        it would be ignored with an error log, so we only create it once.
        """
        task = context.current_task
        if task is None:
            task = new_task(
                context.task_id or "",
                context.context_id or "",
                TaskState.TASK_STATE_SUBMITTED,
                history=[context.message] if context.message is not None else None,
            )
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        return updater

    async def _emit(self, updater: TaskUpdater, text: str, body: dict, skill: str) -> None:
        await updater.add_artifact(
            [Part(text=text, media_type="text/plain"), data_part(body)],
            name=ARTIFACT_NAME,
            metadata={"skill": skill},
            last_chunk=True,
        )
        await updater.complete()

    def _corpus_status(self) -> dict:
        stats = self.service.stats()
        try:
            stats["drifted_sources"] = detect_drift(self.service.config)
        except Exception:  # pragma: no cover - drift is advisory, never fatal
            logger.exception("drift detection failed")
            stats["drifted_sources"] = None
        stats["skill"] = SKILL_CORPUS_STATUS
        return stats

    @staticmethod
    def _render_status(stats: dict) -> str:
        manifest = stats.get("manifest", {})
        drifted = stats.get("drifted_sources") or []
        lines = [
            f"{stats.get('chunks', 0)} chunks from {manifest.get('document_count', 0)} documents",
            f"embedder: {manifest.get('embedder_fingerprint')}",
            f"built at: {manifest.get('built_at')}",
            f"corpora: {stats.get('by_corpus')}",
        ]
        lines.append(
            f"{len(drifted)} source(s) changed since the index was built" if drifted else "index is current"
        )
        return "\n".join(lines)

    @staticmethod
    def _render_search(result) -> str:
        if not result.hits:
            return (
                f"No passage cleared the relevance gate ({result.gate}); "
                f"best score was {result.best_relevance:.3f}."
            )
        lines = [f"{len(result.hits)} passage(s) above the {result.gate} relevance gate:"]
        for i, hit in enumerate(result.hits, start=1):
            lines.append(f"[{i}] {hit.relevance:.3f} {hit.chunk.doc_title} - {hit.chunk.heading_trail}")
            lines.append(f"    {hit.citation.uri}")
        return "\n".join(lines)
