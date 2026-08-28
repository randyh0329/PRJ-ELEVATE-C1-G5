"""
ADK Root Agent Entrypoint for Vertex AI Agent Engine Deployment.
Compliant with ADK CLI v2.8.0.
"""
from src.adk.supervisor import hr_enterprise_supervisor

# Canonical root agent instance recognized by ADK CLI (adk run / adk deploy)
root_agent = hr_enterprise_supervisor
agent = hr_enterprise_supervisor
