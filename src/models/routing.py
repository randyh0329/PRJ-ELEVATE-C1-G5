"""
Routing & Tool Selection Schemas.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.1 & §3.2.
"""

from typing import Any, Literal

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
    extracted_action: str | None = Field(
        default=None,
        description="Specific sub-action identified if applicable."
    )
    unaddressed_requests: list[str] = Field(
        default_factory=list,
        description=(
            "Any OTHER distinct requests present in the same turn that the chosen intent "
            "does not cover, each written as a short English noun phrase, e.g. "
            "'a sick-leave request for 2026-10-01 to 2026-10-03'. Empty for the normal "
            "single-request turn. One turn is routed to exactly one specialist, so a "
            "compound request leaves the remainder unactioned; naming them here is what "
            "lets the reply say so instead of dropping them silently."
        )
    )

    # WorkWeek tool parameters for single-turn fast-path execution
    tool_name: Literal["get_employee_balances", "get_leave_requests", "request_time_off", "cancel_leave_request", "update_personal_info", "get_employee_profile", "none"] | None = Field(
        default="none",
        description="If WorkWeek operation, the exact FastMCP tool to invoke."
    )
    start_date: str | None = Field(
        default=None,
        description="Leave start date in YYYY-MM-DD format (must be on or after today's reference date)."
    )
    end_date: str | None = Field(
        default=None,
        description="Leave end date in YYYY-MM-DD format."
    )
    days: float | None = Field(
        default=None,
        description="Number of leave days requested."
    )
    leave_type: str | None = Field(
        default=None,
        description="Type of leave: 'Vacation' or 'Sick'."
    )
    reason: str | None = Field(
        default=None,
        description="Reason for leave or update."
    )
    request_id: str | None = Field(
        default=None,
        description="Leave request ID for cancellation."
    )
    home_address: str | None = Field(
        default=None,
        description="New home address for update_personal_info."
    )
    phone_number: str | None = Field(
        default=None,
        description="New phone number for update_personal_info."
    )

    def unaddressed_note(self) -> str:
        """The sentence that stops a compound request being dropped in silence.

        `我的電腦壞了請開單 + 10/10 - 10/03 要請病假` is one turn carrying two
        requests. The router picks one intent, the graph dispatches one node, and
        the employee receives a confident ticket confirmation with nothing to
        suggest that the leave half was ever read - so they discover the missing
        sick leave when payroll does. Actioning both is a saga-level design
        change; saying which one was actioned is a sentence, and it is the part
        that stops the employee being misled in the meantime.

        Appended to the answer rather than replacing it: the half that did run
        really did run, and the receipt for it is still owed.
        """
        items = [str(r).strip() for r in self.unaddressed_requests if str(r).strip()]
        if not items:
            return ""
        return (
            "\n\n_I have handled one part of that request. Still outstanding: "
            + "; ".join(items)
            + ". Send it to me on its own and I will take care of it._"
        )

    def get_tool_arguments(self) -> dict[str, Any]:
        """Consolidates extracted fields into a unified argument dictionary."""
        args: dict[str, Any] = {}
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
    start_date: str | None = Field(
        default=None,
        description="Leave start date in YYYY-MM-DD format (must be on or after today's reference date)."
    )
    end_date: str | None = Field(
        default=None,
        description="Leave end date in YYYY-MM-DD format."
    )
    days: float | None = Field(
        default=None,
        description="Number of leave days requested."
    )
    leave_type: str | None = Field(
        default=None,
        description="Type of leave: 'Vacation' or 'Sick'."
    )
    reason: str | None = Field(
        default=None,
        description="Reason for leave or update."
    )
    request_id: str | None = Field(
        default=None,
        description="Leave request ID for cancellation."
    )
    home_address: str | None = Field(
        default=None,
        description="New home address for update_personal_info."
    )
    phone_number: str | None = Field(
        default=None,
        description="New phone number for update_personal_info."
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary of parameters to pass to the FastMCP tool."
    )
    reasoning: str = Field(
        description="Reasoning for selecting this specific tool and argument extraction."
    )
    direct_response: str | None = Field(
        default=None,
        description="Optional direct message if no tool call is needed."
    )

    def get_effective_arguments(self) -> dict[str, Any]:
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


class ITSMToolSelection(BaseModel):
    """
    Structured output schema for ServiceImmediately ITSM Specialist (Gemini 3.7 Flash Function Calling).
    Identifies which FastMCP tool to invoke along with typed arguments.
    """
    tool_name: Literal[
        "create_incident",
        "get_ticket_details",
        "list_tickets",
        "post_comment",
        "none",
    ] = Field(
        description="The specific ServiceImmediately tool to call, or 'none' if general conversational response."
    )
    category: str | None = Field(
        default="IT_GENERAL",
        description="Ticket category: 'IT_NETWORK', 'IT_HARDWARE', 'IT_ACCESS', or 'IT_GENERAL'."
    )
    short_description: str | None = Field(
        default=None,
        description="Concise description/title of the incident or request."
    )
    priority: str | None = Field(
        default="3 - Moderate",
        description="Priority string: '1 - Critical', '2 - High', '3 - Moderate', or '4 - Low'."
    )
    ticket_id: str | None = Field(
        default=None,
        description="The target ticket ID for lookup or comment (e.g., 'INC-5001', 'INC0003466')."
    )
    comment_body: str | None = Field(
        default=None,
        description="Comment text to post on the ticket."
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary of parameters to pass to the FastMCP tool."
    )
    reasoning: str = Field(
        description="Reasoning for selecting this specific tool and argument extraction."
    )
    direct_response: str | None = Field(
        default=None,
        description="Optional direct message if no tool call is needed."
    )

    def get_effective_arguments(self) -> dict[str, Any]:
        """Consolidates explicit fields and generic arguments into a unified dictionary."""
        args = dict(self.arguments or {})
        if self.category:
            args["category"] = self.category
        if self.short_description:
            args["short_description"] = self.short_description
        if self.priority:
            args["priority"] = self.priority
        if self.ticket_id:
            args["ticket_id"] = self.ticket_id
        if self.comment_body:
            args["body"] = self.comment_body
        return args
