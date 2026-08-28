"""A2A protocol surface for the policy RAG service."""

from src.grounding.policy_rag.a2a_app.card import build_agent_card
from src.grounding.policy_rag.a2a_app.executor import PolicyRagExecutor
from src.grounding.policy_rag.a2a_app.server import build_app

__all__ = ["PolicyRagExecutor", "build_agent_card", "build_app"]
