"""
Supervisor Agent & Intent Router.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.1, §3.2 (FR-1.1, FR-5.4).
Model: Gemini 3.7 Flash (Pinned).
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from src.core.state import AgentState

logger = logging.getLogger("agents.supervisor")


class SupervisorAgentNode:
    """
    Supervisor Agent node (Gemini 3.7 Flash).
    Routes user turns to specialist workers or the cross-system Saga coordinator.
    Enforces Domain Containment (FR-5.4) and capability allowlists (FR-1.1).
    """

    AGENT_ID = "sup-1.4.0"
    MODEL_ID = "gemini-3.7-flash@2026-08"

    ESCALATION_KEYWORDS: ClassVar[list[str]] = [
        "human", "representative", "agent please", "speak to someone", "operator"
    ]

    def __init__(self, router: Any | None = None) -> None:
        if router is None:
            from src.integrations.vertex.client import vertex_gemini_client
            router = vertex_gemini_client
        self._router = router

    async def execute(self, state: AgentState) -> AgentState:
        """
        Evaluates user input using Gemini 3.7 Flash and assigns `route` and `next_node`.
        """
        user_text = state.get("masked_input", state.get("user_input", "")).strip()

        logger.info("[%s] Processing intent for session %s", self.AGENT_ID, state.get('session_id'))

        # 1. Check for human escalation keywords (§5.7)
        if any(kw in user_text.lower() for kw in self.ESCALATION_KEYWORDS):
            state["route"] = "escalate"
            state["next_node"] = "human_escalation"
            return state

        # 2. Invoke Gemini 3.7 Flash Supervisor Router
        decision = self._router.route_intent(user_text)
        state["intent"] = decision.intent
        state["routing_confidence"] = decision.confidence
        state["routing_reasoning"] = decision.reasoning
        # A compound turn carries requests this route will not serve. Carried on
        # the state as a list rather than as prose: the graph serves what it can
        # of them after this node's route has run, and only the residue becomes
        # a sentence the employee reads.
        state["unaddressed_requests"] = list(decision.unaddressed_requests)

        # 3. Domain Containment Refusal (FR-5.4)
        if decision.intent == "OUT_OF_DOMAIN":
            state["route"] = "end"
            state["next_node"] = "guardrails_out"
            state["final_response"] = (
                "I can assist with HR policies, WorkWeek profile/balances/leaves, and IT service tickets. "
                "That request is outside my domain boundaries."
            )
            return state

        # 4. Cross-System Saga Intents (UC-2.1, UC-2.2, UC-2.3)
        if decision.intent == "UC_2_1_EQUIPMENT_PROCUREMENT":
            state["route"] = "saga"
            state["saga_type"] = "UC-2.1-EQUIPMENT"
            state["next_node"] = "saga_coordinator"
            return state

        if decision.intent == "UC_2_2_MEDICAL_LEAVE_DELEGATION":
            state["route"] = "saga"
            state["saga_type"] = "UC-2.2-MEDICAL-LEAVE"
            state["next_node"] = "saga_coordinator"
            return state

        if decision.intent == "UC_2_3_RELOCATION_ALLOWANCE_BADGE":
            state["route"] = "saga"
            state["saga_type"] = "UC-2.3-RELOCATION"
            state["next_node"] = "saga_coordinator"
            return state

        # 5. Single-System HCM Intents (UC-1.2)
        if decision.intent == "UC_1_2_WORKWEEK_LEAVE":
            state["route"] = "hcm"
            state["next_node"] = "hcm_specialist"
            return state

        # 6. Single-System ITSM Intents (UC-1.3)
        if decision.intent == "UC_1_3_SERVICE_IMMEDIATELY_INCIDENT":
            state["route"] = "itsm"
            state["next_node"] = "itsm_specialist"
            return state

        # 7. Default to Policy Specialist (UC-1.1 Policy Q&A RAG)
        state["route"] = "policy"
        state["next_node"] = "policy_specialist"
        return state
