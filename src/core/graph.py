"""
StateGraph Multi-Agent Orchestration Engine.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.1, §3.2, §4.3, §5.4.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from src.core.agents.hcm import HCMSpecialistNode
from src.core.agents.itsm import ITSMSpecialistNode
from src.core.agents.policy import PolicySpecialistNode
from src.core.agents.saga import SagaCoordinatorNode
from src.core.agents.supervisor import SupervisorAgentNode
from src.core.state import AgentState
from src.grounding.policy_rag.multilingual import localize, understand
from src.models.routing import MAX_REQUESTS_PER_TURN, render_unaddressed_note
from src.saga.ledger import SagaLedgerManager
from src.security.dlp import CloudDLPInterceptor
from src.security.model_armor import ModelArmorSanitizer
from src.security.token_minter import CompositeTokenMinter

logger = logging.getLogger("agent.graph")


class AgentOrchestrationGraph:
    """
    Core Multi-Agent Execution Graph.
    Implements deterministic conditional routing, distributed state transitions,
    and end-to-end security guardrails.
    """

    #: Routes that reach a node which actually does something. `escalate` and
    #: `end` are excluded: each has already accounted for the whole turn.
    SERVING_ROUTES: ClassVar[frozenset[str]] = frozenset({"policy", "hcm", "itsm", "saga"})

    def __init__(
        self,
        ledger: SagaLedgerManager | None = None,
        dlp: CloudDLPInterceptor | None = None,
        model_armor: ModelArmorSanitizer | None = None,
        token_minter: CompositeTokenMinter | None = None,
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
        if route in self.SERVING_ROUTES:
            state = await self._dispatch(state, route)
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

        # Stage 3b: Serve the other requests the turn carried, and disclose any
        # this runtime declined. Both only apply where a node actually ran - a
        # containment refusal and an escalation have each already accounted for
        # the whole turn.
        if route in self.SERVING_ROUTES:
            state = await self._serve_remaining_requests(state, route)
            note = state.get("unaddressed_note", "")
            if note and state.get("final_response"):
                state["final_response"] = state["final_response"] + note

        # Stage 4: Outbound Security Guardrails
        raw_response = state.get("final_response", "")
        out_verdict, out_reason = self.model_armor.sanitize_model_response(raw_response)
        if out_verdict == "BLOCK":
            state["guardrail_verdict"] = "BLOCK"
            state["final_response"] = out_reason
            return state

        # Stage 5: Answer in the language the employee wrote in.
        #
        # The specialist nodes build their responses from English templates -
        # "Your vacation request for 3.0 days ... has been submitted in
        # WorkWeek" - so an employee who typed Chinese got an English receipt for
        # a transaction they had described in Chinese. Translating here rather
        # than in each template keeps one English source of truth to test
        # against, and means a node added later is localised without knowing it.
        localized = self._localize_response(raw_prompt, raw_response, surrogate_map)

        # Re-identification last: everything above this line, including anything
        # sent to the translator, has only ever seen de-identified text (§4.4).
        final_text = self.dlp.reidentify(localized, surrogate_map)
        state["final_response"] = final_text

        return state

    async def _dispatch(self, state: AgentState, route: str) -> AgentState:
        """Run the one node that serves `route`.

        Extracted from `invoke` so a compound turn can reach a second node
        without `invoke` growing a second copy of the routing table.
        """
        if route == "policy":
            return await self.policy_agent.execute(state)
        if route == "hcm":
            return await self.hcm_agent.execute(state)
        if route == "itsm":
            return await self.itsm_agent.execute(state)
        return await self.saga_coordinator.execute(state)

    async def _serve_remaining_requests(self, state: AgentState, route: str) -> AgentState:
        """Serve the other requests the turn carried; report what was declined.

        A turn is classified once, so `我的電腦壞了請開單 + 10/10 - 10/03 要請病假`
        used to open the IT ticket and drop the leave. The router now names the
        requests its chosen intent does not cover, and each is re-classified and
        dispatched on its own - so one turn can reach the ITSM node and the HCM
        node, each doing its own job, each with its own audit trail.

        The invariant that replaces "one node per turn" is *one node per
        request*, and three bounds hold it there:

        * `MAX_REQUESTS_PER_TURN` caps the fan-out.
        * A route that has already run this turn does not run again. A route is
          one backing system, so this is the rule that forecloses two bookings
          against WorkWeek from one sentence - far likelier to be the router
          splitting a single request in two than an employee asking twice, and
          the employee pays for the wrong guess by having to cancel one.
        * A follow-up may not fan out again: only the sentence the employee
          typed adds work, or the chain has no end.

        Failure is per-request and never retroactive - these are independent
        requests, not saga steps, so a leave booking that fails does not make
        the IT ticket wrong. Nothing is compensated, and nothing is hidden:
        what failed is named in the reply.

        The request strings are safe to re-enter the graph with. They were
        written by the router, which is only ever shown `masked_input`, so they
        carry surrogates rather than SPII (§4.4).
        """
        requests = [str(r).strip() for r in state.get("unaddressed_requests") or [] if str(r).strip()]
        state["unaddressed_requests"] = []
        state["unaddressed_note"] = ""
        if not requests:
            return state

        answers = [state.get("final_response") or ""]
        routes_served = {route}
        deferred = requests[MAX_REQUESTS_PER_TURN - 1:]

        for request in requests[: MAX_REQUESTS_PER_TURN - 1]:
            try:
                part: AgentState = dict(state)  # type: ignore[assignment]
                part["user_input"] = request
                part["masked_input"] = request
                part["final_response"] = ""
                part["unaddressed_requests"] = []
                part = await self.supervisor.execute(part)
                part_route = part.get("route", "policy")
                if part_route not in self.SERVING_ROUTES or part_route in routes_served:
                    # Out of domain, an escalation, or a system already written
                    # to. None of them is served here; all of them are declared.
                    deferred.append(request)
                    continue
                part = await self._dispatch(part, part_route)
                routes_served.add(part_route)
                if part.get("final_response"):
                    answers.append(part["final_response"])
                for citation in part.get("citations") or []:
                    if citation not in state.setdefault("citations", []):
                        state["citations"].append(citation)
            except Exception:
                logger.warning("compound request part failed: %r", request, exc_info=True)
                deferred.append(request)

        state["final_response"] = "\n\n".join(answer for answer in answers if answer)
        state["unaddressed_requests"] = deferred
        state["unaddressed_note"] = render_unaddressed_note(deferred)
        return state

    def _localize_response(
        self, prompt: str, response: str, surrogate_map: dict[str, str]
    ) -> str:
        """Translate an outbound response, or return it unchanged.

        Ordered deliberately between the outbound guard and re-identification.
        Before the guard, and Model Armor - whose blocklists are English - would
        be inspecting text it cannot read. After re-identification, and the
        employee's real phone number would be sent to a translation endpoint.
        Here, the guard has already passed on English and the translator only
        ever sees `[PHONE_1]`.

        Which makes those surrogates load-bearing: a translation that drops or
        rewrites one leaves a token that `reidentify` can no longer resolve, and
        the employee reads `[PHONE_1]` where their number should be. Cheaper to
        check than to trust, so it is checked, and a mangled translation is
        discarded in favour of the English that was known to be correct.
        """
        if not response.strip():
            return response
        try:
            language = understand(prompt).language
            if not language.cross_lingual:
                return response
            translated = localize(response, language)
        except Exception:
            # NFR-4.1. An unreachable translator costs the employee their
            # preferred language, never their answer.
            logger.warning("outbound localisation failed; answering in English", exc_info=True)
            return response

        missing = [s for s in surrogate_map if s in response and s not in translated]
        if missing:
            logger.warning(
                "discarding %s translation: it dropped surrogates %s",
                language.code, missing,
            )
            return response
        return translated
