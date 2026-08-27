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
    Also extracts tool parameters in the same turn to avoid redundant LLM round-trips.
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
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 of the classification."
    )
    reasoning: str = Field(
        description="Brief natural language rationale explaining the routing decision."
    )
    extracted_action: Optional[str] = Field(
        default=None,
        description="Specific sub-action identified if applicable."
    )

    # WorkWeek tool parameters for single-turn fast-path execution
    tool_name: Optional[Literal[
        "get_employee_balances",
        "get_leave_requests",
        "request_time_off",
        "cancel_leave_request",
        "update_personal_info",
        "get_employee_profile",
        "none",
    ]] = Field(
        default="none",
        description="If WorkWeek operation, the exact FastMCP tool to invoke."
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Leave start date in YYYY-MM-DD format (must be on or after today's reference date)."
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Leave end date in YYYY-MM-DD format."
    )
    days: Optional[float] = Field(
        default=None,
        description="Number of leave days requested."
    )
    leave_type: Optional[str] = Field(
        default=None,
        description="Type of leave: 'Vacation' or 'Sick'."
    )
    reason: Optional[str] = Field(
        default=None,
        description="Reason for leave or update."
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Leave request ID for cancellation."
    )
    home_address: Optional[str] = Field(
        default=None,
        description="New home address for update_personal_info."
    )
    phone_number: Optional[str] = Field(
        default=None,
        description="New phone number for update_personal_info."
    )

    def get_tool_arguments(self) -> Dict[str, Any]:
        """Consolidates extracted fields into a unified argument dictionary."""
        args: Dict[str, Any] = {}
        if self.start_date:
            args["start_date"] = self.start_date
        if self.end_date:
            args["end_date"] = self.end_date
        if self.days is not None:
            args["days"] = self.days
        if self.leave_type:
            args["leave_type"] = self.leave_type
        if self.reason:
            args["reason"] = self.reason
        if self.request_id:
            args["request_id"] = self.request_id
        if self.home_address:
            args["home_address"] = self.home_address
        if self.phone_number:
            args["phone_number"] = self.phone_number
        return args


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
    start_date: Optional[str] = Field(
        default=None,
        description="Leave start date in YYYY-MM-DD format (must be on or after today's reference date)."
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Leave end date in YYYY-MM-DD format."
    )
    days: Optional[float] = Field(
        default=None,
        description="Number of leave days requested."
    )
    leave_type: Optional[str] = Field(
        default=None,
        description="Type of leave: 'Vacation' or 'Sick'."
    )
    reason: Optional[str] = Field(
        default=None,
        description="Reason for leave or update."
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Leave request ID for cancellation."
    )
    home_address: Optional[str] = Field(
        default=None,
        description="New home address for update_personal_info."
    )
    phone_number: Optional[str] = Field(
        default=None,
        description="New phone number for update_personal_info."
    )
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary of parameters to pass to the FastMCP tool."
    )
    reasoning: str = Field(
        description="Reasoning for selecting this specific tool and argument extraction."
    )
    direct_response: Optional[str] = Field(
        default=None,
        description="Optional direct message if no tool call is needed."
    )

    def get_effective_arguments(self) -> Dict[str, Any]:
        """Consolidates explicit fields and generic arguments into a unified dictionary."""
        args = dict(self.arguments or {})
        if self.start_date:
            args["start_date"] = self.start_date
        if self.end_date:
            args["end_date"] = self.end_date
        if self.days is not None:
            args["days"] = self.days
        if self.leave_type:
            args["leave_type"] = self.leave_type
        if self.reason:
            args["reason"] = self.reason
        if self.request_id:
            args["request_id"] = self.request_id
        if self.home_address:
            args["home_address"] = self.home_address
        if self.phone_number:
            args["phone_number"] = self.phone_number
        return args
