"""Boilerplate adapters for live enterprise SaaS and Agent-to-Agent (A2A) integration."""
from src.integrations.saas_boilerplate.a2a_protocol import A2AProtocolBoilerplate
from src.integrations.saas_boilerplate.servicenow_live import ServiceNowLiveClientBoilerplate
from src.integrations.saas_boilerplate.workday_live import WorkdayLiveClientBoilerplate

__all__ = [
    "A2AProtocolBoilerplate",
    "ServiceNowLiveClientBoilerplate",
    "WorkdayLiveClientBoilerplate",
]
