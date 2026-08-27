"""
StateGraph Multi-Agent Orchestration Engine.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.1, §3.2, §4.3, §5.4.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.core.agents.hcm import HCMSpecialistNode
from src.core.agents.itsm import ITSMSpecialistNode
from src.core.agents.policy import PolicySpecialistNode
from src.core.agents.saga import SagaCoordinatorNode
from src.core.agents.supervisor import SupervisorAgentNode
from src.saga.ledger import SagaLedgerManager
from src.security.dlp import CloudDLPInterceptor
from src.security.model_armor import ModelArmorSanitizer
from src.security.token_minter import CompositeTokenMinter
from src.core.state import AgentState

logger = logging.getLogger("agent.graph")


class AgentOrchestrationGraph:
    """
    Core Multi-Agent Execution Graph.
    Implements deterministic conditional routing, distributed state transitions,
    and end-to-end security guardrails.
    """

    def __init__(
        self,
        ledger: Optional[SagaLedgerManager] = None,
        dlp: Optional[CloudDLPInterceptor] = None,
        model_armor: Optional[ModelArmorSanitizer] = None,
        token_minter: Optional[CompositeTokenMinter] = None,
    ):
        self.ledger = ledger or SagaLedgerManager()
        self.dlp = dlp or CloudDLPInterceptor()
        self.model_armor = model_armor or ModelArmorSanitizer()
        self.token_minter = token_minter or CompositeTokenMinter()

        # Specialist & Coordinator Nodes
        self.supervisor = SupervisorAgentNode()
        self.policy_agent = PolicySpecialistNode()
        self.hcm_agent = HCMSpecialistNode(token_minter=self.token_minter)
        self.itsm_agent = ITSMSpecialistNode(token_minter=self.token_minter)
        self.saga_coordinator = SagaCoordinatorNode(
            ledger=self.ledger,
            policy_agent=self.policy_agent,
            hcm_agent=self.hcm_agent,
            itsm_agent=self.itsm_agent,
        )

    async def invoke(self, state: AgentState) -> AgentState:
        # Stage 1: Inbound Security Guardrails
        raw_prompt = state.get("user_input", "")
        verdict, block_reason = self.model_armor.sanitize_user_prompt(raw_prompt)
        if verdict == "BLOCK":
            state["guardrail_verdict"] = "BLOCK"
            state["final_response"] = block_reason
            return state

        masked_text, surrogate_map = self.dlp.deidentify(raw_prompt)
        state["masked_input"] = masked_text
        state["guardrail_verdict"] = "ALLOW"

        # Stage 2: Supervisor Routing
        state = await self.supervisor.execute(state)
        route = state.get("route", "policy")

        # Stage 3: Specialist / Saga Execution Node Dispatch
        if route == "policy":
            state = await self.policy_agent.execute(state)
        elif route == "hcm":
            state = await self.hcm_agent.execute(state)
        elif route == "itsm":
            state = await self.itsm_agent.execute(state)
        elif route == "saga":
            state = await self.saga_coordinator.execute(state)
        elif route == "escalate":
            state["context_package"] = {
                "sessionId": state.get("session_id"),
                "employeeId": state.get("employee_id"),
                "turnId": state.get("turn_id"),
                "maskedInput": state.get("masked_input"),
                "severity": "P2",
            }
            state["final_response"] = (
                "I am transferring your request to a human HR/IT specialist. "
                "A support ticket with your de-identified conversation context has been opened."
            )

        # Stage 4: Outbound Security Guardrails & Re-identification
        raw_response = state.get("final_response", "")
        out_verdict, out_reason = self.model_armor.sanitize_model_response(raw_response)
        if out_verdict == "BLOCK":
            state["guardrail_verdict"] = "BLOCK"
            state["final_response"] = out_reason
            return state

        final_text = self.dlp.reidentify(raw_response, surrogate_map)
        state["final_response"] = final_text

        return state
