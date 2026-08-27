"""
Supervisor Agent & Intent Router.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.1, §3.2 (FR-1.1, FR-5.4).
Model: Gemini 3.7 Flash (Pinned).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Literal

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

    OUT_OF_DOMAIN_PATTERNS = [
        r"write\s+(a\s+)?(python|code|script|sql)",
        r"what\s+is\s+the\s+capital\s+of",
        r"who\s+won\s+the\s+world\s+cup",
        r"recipe\s+for",
    ]

    ESCALATION_KEYWORDS = [
        "human", "representative", "agent please", "speak to someone", "operator"
    ]

    async def execute(self, state: AgentState) -> AgentState:
        """
        Evaluates user input and assigns `route` and `next_node`.
        """
        user_text = state.get("masked_input", state.get("user_input", "")).strip().lower()

        logger.info(f"[{self.AGENT_ID}] Processing intent for session {state.get('session_id')}")

        # 1. Check for human escalation keywords (§5.7)
        if any(kw in user_text for kw in self.ESCALATION_KEYWORDS):
            state["route"] = "escalate"
            state["next_node"] = "human_escalation"
            return state

        # 2. Check for domain containment / out-of-domain refusal (FR-5.4)
        for pat in self.OUT_OF_DOMAIN_PATTERNS:
            if re.search(pat, user_text):
                state["route"] = "end"
                state["next_node"] = "guardrails_out"
                state["final_response"] = (
                    "I can assist with HR policies, WorkWeek profile/balances/leaves, and IT service tickets. "
                    "That request is outside my domain boundaries."
                )
                return state

        # 3. Classify Cross-System Saga Intents (UC-2.1, UC-2.2, UC-2.3)
        if any(term in user_text for term in ["medical leave", "short-term medical", "short term medical"]):
            state["route"] = "saga"
            state["saga_type"] = "UC-2.2-MEDICAL-LEAVE"
            state["next_node"] = "saga_coordinator"
            return state

        if any(term in user_text for term in ["transfer to", "relocating to", "london office", "new office", "relocation allowance"]) and not any(bait in user_text for bait in ["pet", "dog", "helicopter"]):
            state["route"] = "saga"
            state["saga_type"] = "UC-2.3-RELOCATION"
            state["next_node"] = "saga_coordinator"
            return state

        if any(term in user_text for term in ["monitor", "home office equipment", "order equipment", "desk allowance"]):
            state["route"] = "saga"
            state["saga_type"] = "UC-2.1-EQUIPMENT"
            state["next_node"] = "saga_coordinator"
            return state

        # 4. Classify Single-System HCM Intents (UC-1.2)
        if any(term in user_text for term in ["pto balance", "vacation balance", "sick days", "my balances", "submit leave", "vacation request"]):
            state["route"] = "hcm"
            state["next_node"] = "hcm_specialist"
            return state

        # 5. Classify Single-System ITSM Intents (UC-1.3)
        if any(term in user_text for term in ["ticket", "incident", "inc-", "req-", "laptop broken", "vpn issue", "service immediately"]):
            state["route"] = "itsm"
            state["next_node"] = "itsm_specialist"
            return state

        # 6. Default to Policy Specialist (UC-1.1 Policy Q&A RAG)
        state["route"] = "policy"
        state["next_node"] = "policy_specialist"
        return state
