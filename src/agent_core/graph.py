import hashlib
import time
import uuid
from typing import Dict, Any, Optional, List
from src.security.model_armor import model_armor
from src.security.dlp import dlp_engine
from src.gateway.rights_handlers import rights_handler
from src.agent_core.supervisor import supervisor_router
from src.models.common import GuardrailVerdictEnum
from src.models.telemetry import LLMExecutionEvent, AgentNodeLifecycle
from src.telemetry.logger import telemetry_logger
from src.storage.firestore import firestore_store
from src.config import settings


class AgentOrchestrationGraph:
    """
    Core Multi-Agent Execution Graph (SDD §3.1, §3.3).
    Pipelines request through Security Guardrails, DLP Masking, Supervisor Routing,
    Specialist Delegation, Re-identification, Response Guardrail, and Structured Logging.
    """
    def __init__(self):
        pass

    async def run(
        self,
        user_message: str,
        session_id: str,
        employee_id: str = "EMP-44210",
        turn_seq: int = 1
    ) -> Dict[str, Any]:
        trace_id = f"projects/{settings.project_id}/traces/{uuid.uuid4().hex[:16]}"
        start_time = time.time()

        # 0. Deterministic Rights Handler Interception (SDD §4.12)
        keyword = rights_handler.match_keyword(user_message)
        if keyword:
            right_resp = rights_handler.handle_keyword(keyword, session_id, employee_id)
            if right_resp.get("handled"):
                return {
                    "sessionId": session_id,
                    "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                    "content": right_resp["content"],
                    "citations": right_resp.get("citations", []),
                    "escalated": right_resp.get("escalated", False),
                    "escalationDetails": right_resp.get("escalationDetails"),
                    "guardrailVerdict": "ALLOW"
                }

        # 1. Inbound Model Armor Safety Check (SDD §4.3)
        in_verdict, in_reason = model_armor.sanitize_user_prompt(user_message)
        if in_verdict == GuardrailVerdictEnum.BLOCK:
            return {
                "sessionId": session_id,
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "content": "I could not produce a safe answer to that. Please rephrase, or contact the HR helpdesk.",
                "citations": [],
                "escalated": False,
                "guardrailVerdict": "BLOCK"
            }

        # 2. Cloud DLP Pre-LLM De-identification & Crypto Surrogates (SDD §4.4, §4.5)
        sanitized_prompt, surrogate_map, blocked_spii = dlp_engine.deidentify(user_message)

        # 3. Supervisor Routing & Specialist Execution
        node_start = time.time()
        result = await supervisor_router.route_and_execute(
            user_message=sanitized_prompt,
            session_id=session_id,
            employee_id=employee_id
        )
        node_latency_ms = int((time.time() - node_start) * 1000)

        raw_content = result.get("content", "")
        citations = result.get("citations", [])

        # 4. DLP Re-identification inside trust boundary (SDD §4.3 G3)
        reidentified_content = dlp_engine.reidentify(raw_content, surrogate_map)

        # 5. Outbound Model Armor Response Sanitization (SDD §4.3)
        out_verdict, final_content = model_armor.sanitize_model_response(reidentified_content)

        total_latency_ms = int((time.time() - start_time) * 1000)

        # 6. Structured JSON Telemetry Logging (SDD §7.5)
        emp_hash = hashlib.sha256(employee_id.encode()).hexdigest()
        llm_event = LLMExecutionEvent(
            trace_id=trace_id,
            span_id=uuid.uuid4().hex[:8],
            session_id=session_id,
            turn_seq=turn_seq,
            employee_id_hash=emp_hash,
            agent_node=result.get("agent", "supervisor_router"),
            model_id="gemini-3.7-flash",
            model_version_pinned="gemini-3.7-flash@pinned",
            invocation_purpose="USER_INTENT_DISPATCH",
            input_tokens=len(user_message.split()) * 2,
            output_tokens=len(final_content.split()) * 2,
            cached_tokens=0,
            ttft_ms=int(total_latency_ms * 0.4),
            total_latency_ms=total_latency_ms,
            finish_reason="STOP",
            safety_overhead_ms=12,
            dlp_template_digest=settings.dlp_template_digest,
            guardrail_verdict_in=in_verdict.value,
            guardrail_verdict_out=out_verdict.value,
            groundedness_score=result.get("groundedness_score", 1.0),
            estimated_cost_usd=0.00015
        )
        telemetry_logger.log_event(llm_event.model_dump())

        # 7. Record turn to session messages
        msg_id = f"msg-{uuid.uuid4().hex[:8]}"
        firestore_store.add_message(session_id, {
            "messageId": msg_id,
            "role": "user",
            "content": sanitized_prompt,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })
        firestore_store.add_message(session_id, {
            "messageId": f"msg-{uuid.uuid4().hex[:8]}",
            "role": "assistant",
            "content": final_content,
            "citations": [c.model_dump() for c in citations],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })

        return {
            "sessionId": session_id,
            "messageId": msg_id,
            "content": final_content,
            "citations": citations,
            "escalated": result.get("escalated", False),
            "escalationDetails": result.get("escalationDetails"),
            "guardrailVerdict": out_verdict.value
        }


orchestration_graph = AgentOrchestrationGraph()
