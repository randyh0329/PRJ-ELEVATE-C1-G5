"""
Routing & Tool Selection Schemas.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.1 & §3.2.
"""

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


class SupervisorRoutingDecision(BaseModel):
    """
    Structured output schema for the Supervisor Agent (Gemini 3.7 Flash).
    Delegates user requests to domain specialists or rejects out-of-domain prompts.
    """
    intent: Literal[
        "UC_1_1_POLICY_QA",
        "UC_1_2_WORKWEEK_LEAVE",
        "UC_1_3_SERVICE_IMMEDIATELY_INCIDENT",
        "UC_2_1_EQUIPMENT_PROCUREMENT",
        "UC_2_2_MEDICAL_LEAVE_DELEGATION",
        "UC_2_3_RELOCATION_ALLOWANCE_BADGE",
        "OUT_OF_DOMAIN",
    ] = Field(
        description="The classified enterprise intent corresponding to MVP 1 use cases or OUT_OF_DOMAIN."
    )
    target_agent: Literal[
        "POLICY_SPECIALIST",
        "WORKWEEK_SPECIALIST",
        "ITSM_SPECIALIST",
        "SAGA_COORDINATOR",
        "DOMAIN_CONTAINMENT",
    ] = Field(
        description="The authorized specialist worker or coordinator agent to delegate to."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 of the classification."
    )
    reasoning: str = Field(
        description="Brief natural language rationale explaining the routing decision."
    )
    extracted_action: Optional[str] = Field(
        default=None,
        description="Specific sub-action identified if applicable (e.g. check_balance, submit_leave, get_profile, create_ticket)."
    )


class WorkWeekToolSelection(BaseModel):
    """
    Structured output schema for WorkWeek HCM Specialist (Gemini 3.7 Flash Function Calling).
    Identifies which FastMCP tool to invoke along with typed arguments.
    """
    tool_name: Literal[
        "get_employee_balances",
        "get_leave_requests",
        "request_time_off",
        "cancel_leave_request",
        "update_personal_info",
        "get_employee_profile",
        "none",
    ] = Field(
        description="The specific FastMCP tool to call, or 'none' if general conversational response."
    )
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary of parameters to pass to the FastMCP tool (e.g. start_date, end_date, days, leave_type, request_id)."
    )
    reasoning: str = Field(
        description="Reasoning for selecting this specific tool and argument extraction."
    )
    direct_response: Optional[str] = Field(
        default=None,
        description="Optional direct message if no tool call is needed."
    )
