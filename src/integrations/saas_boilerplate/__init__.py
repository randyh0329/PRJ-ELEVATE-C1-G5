"""Boilerplate adapters for live enterprise SaaS and Agent-to-Agent (A2A) integration."""
from src.integrations.saas_boilerplate.workday_live import WorkdayLiveClientBoilerplate
from src.integrations.saas_boilerplate.servicenow_live import ServiceNowLiveClientBoilerplate
from src.integrations.saas_boilerplate.a2a_protocol import A2AProtocolBoilerplate

__all__ = [
    "WorkdayLiveClientBoilerplate",
    "ServiceNowLiveClientBoilerplate",
    "A2AProtocolBoilerplate",
]
