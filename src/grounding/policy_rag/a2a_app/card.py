"""The A2A agent card.

The card is the contract other agents discover this service through. It is
served at `/.well-known/agent-card.json` and lists three skills, deliberately
separated because they have different trust properties:

* ``policy_search``  - returns chunks and citations, no prose. This is what a
  calling agent that owns its own LLM should use: it grounds its own generation
  and keeps the generation inside its own guardrail chain (SDD §4.3).
* ``policy_answer``  - returns a composed, cited answer with the guards applied.
  For callers that want a finished answer rather than material.
* ``corpus_status``  - index provenance and freshness, for an orchestrator that
  needs to know how current the knowledge base is before quoting it.
"""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentProvider, AgentSkill
from a2a.utils.constants import PROTOCOL_VERSION_CURRENT, TransportProtocol

AGENT_NAME = "altostrat-hr-policy-rag"
AGENT_VERSION = "0.1.0"

SKILL_POLICY_SEARCH = "policy_search"
SKILL_POLICY_ANSWER = "policy_answer"
SKILL_CORPUS_STATUS = "corpus_status"

SKILL_IDS = (SKILL_POLICY_SEARCH, SKILL_POLICY_ANSWER, SKILL_CORPUS_STATUS)

_DESCRIPTION = (
    "Grounded retrieval over the Altostrat Singapore employee policy handbook and its "
    "OKF v0.2 concept bundle. Answers are extracted from the corpus with resolvable "
    "citations, refused below the retrieval relevance gate, and escalated - never "
    "guessed - where the source handbook contradicts itself."
)


def build_agent_card(public_url: str) -> AgentCard:
    """Construct the card advertised at the well-known path.

    `public_url` must be the externally reachable base URL of the JSON-RPC
    endpoint; a card advertising `127.0.0.1` is useless to a remote caller.
    """
    return AgentCard(
        name=AGENT_NAME,
        description=_DESCRIPTION,
        version=AGENT_VERSION,
        documentation_url="src/grounding/policy_rag/README.md",
        provider=AgentProvider(organization="Altostrat HR Knowledge Team", url=public_url),
        supported_interfaces=[
            AgentInterface(
                url=public_url,
                protocol_binding=TransportProtocol.JSONRPC.value,
                protocol_version=PROTOCOL_VERSION_CURRENT,
            )
        ],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["text/plain", "application/json"],
        skills=[
            AgentSkill(
                id=SKILL_POLICY_SEARCH,
                name="Search HR policy",
                description=(
                    "Retrieve the policy passages relevant to a question, with calibrated "
                    "relevance scores and resolvable deep-link citations. Returns no prose - "
                    "the caller grounds its own generation on the returned chunks."
                ),
                tags=["hr", "policy", "retrieval", "rag", "citations"],
                examples=[
                    "How many vacation days after 8 years of service?",
                    "What notice is required before booking leave?",
                    "Gift value threshold requiring pre-approval",
                ],
                input_modes=["text/plain", "application/json"],
                output_modes=["application/json"],
            ),
            AgentSkill(
                id=SKILL_POLICY_ANSWER,
                name="Answer an HR policy question",
                description=(
                    "Return a cited answer composed only from retrieved policy text. Refuses "
                    "when retrieval falls below the relevance gate, and escalates to People Ops "
                    "when the source handbook is self-contradictory on the point asked about."
                ),
                tags=["hr", "policy", "grounded-answer", "citations", "singapore"],
                examples=[
                    "What is the bereavement leave policy?",
                    "Am I allowed to accept a US$150 gift from a supplier?",
                    "How much notice do I need to give before taking vacation?",
                ],
                input_modes=["text/plain", "application/json"],
                output_modes=["text/plain", "application/json"],
            ),
            AgentSkill(
                id=SKILL_CORPUS_STATUS,
                name="Knowledge base status",
                description=(
                    "Report index provenance: chunk and document counts per corpus, the "
                    "embedding model the index was built with, build timestamp, and whether "
                    "any ingested source has changed since."
                ),
                tags=["observability", "provenance", "freshness"],
                examples=["What is in the policy knowledge base?", "When was the corpus last indexed?"],
                input_modes=["text/plain", "application/json"],
                output_modes=["application/json"],
            ),
        ],
    )
