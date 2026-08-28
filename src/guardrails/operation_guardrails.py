"""Operational guardrail engine enforcing business constraints and policy rules."""
import datetime
from typing import ClassVar

from pydantic import BaseModel

from src.core.clock import business_today


class GuardrailValidationResult(BaseModel):
    """Result of an operational guardrail evaluation."""
    is_valid: bool
    error_message: str | None = None
    rule_name: str


class OperationGuardrailEngine:
    """Enforces strict transactional and operational guardrails across HR and ITSM operations."""

    #: The ITSM lifecycle of SDD §5.9 (`enum: [New, In Progress, On Hold,
    #: Resolved, Closed]`). The vocabulary matters as much as the edges: the
    #: table previously read "Work in Progress" / "Pending User Info", so a
    #: ticket in the enum's "In Progress" matched no key at all and *every*
    #: transition off it was refused as illegal.
    #:
    #: `Closed` is terminal and `New -> Closed` is absent, which are the two
    #: rules §5.3 names explicitly (S1 and S2 in the rules-engine flowchart).
    VALID_TICKET_TRANSITIONS: ClassVar[dict[str, list[str]]] = {
        "New": ["In Progress", "On Hold", "Resolved"],
        "In Progress": ["On Hold", "Resolved"],
        "On Hold": ["In Progress", "Resolved"],
        "Resolved": ["Closed", "In Progress"],
        "Closed": []
    }

    VALID_PRIORITIES: ClassVar[list[str]] = ["1 - Critical", "2 - High", "3 - Moderate", "4 - Low"]

    def validate_leave_request(
        self,
        days_requested: float,
        remaining_balance: float,
        start_date: datetime.date,
        end_date: datetime.date,
        reference_date: datetime.date | None = None
    ) -> GuardrailValidationResult:
        """Validate leave request against balance, temporal, and calendar constraints."""
        today = reference_date or business_today()

        # 1. Days positivity
        if days_requested <= 0:
            return GuardrailValidationResult(
                is_valid=False,
                error_message="Leave duration must be greater than 0 days.",
                rule_name="LEAVE_POSITIVE_DAYS_CONSTRAINT"
            )

        # 2. Balance constraint: days <= remaining_balance
        if days_requested > remaining_balance:
            return GuardrailValidationResult(
                is_valid=False,
                error_message=f"Insufficient leave balance. Requested {days_requested} days, but only {remaining_balance} days available.",
                rule_name="LEAVE_BALANCE_LIMIT_CONSTRAINT"
            )

        # 3. Temporal validity: start_date <= end_date
        if start_date > end_date:
            return GuardrailValidationResult(
                is_valid=False,
                error_message="Leave start date cannot be after end date.",
                rule_name="LEAVE_TEMPORAL_ORDER_CONSTRAINT"
            )

        # 4. Past date constraint: start_date >= today
        if start_date < today:
            return GuardrailValidationResult(
                is_valid=False,
                error_message="Leave requests cannot be submitted for dates in the past.",
                rule_name="LEAVE_PAST_DATE_CONSTRAINT"
            )

        return GuardrailValidationResult(
            is_valid=True,
            error_message=None,
            rule_name="LEAVE_VALIDATION_PASSED"
        )

    def validate_contact_update(self, phone_number: str | None, home_address: str | None) -> GuardrailValidationResult:
        """Validate phone number and address syntax constraints."""
        if phone_number is not None:
            clean_phone = phone_number.strip().replace(" ", "").replace("-", "")
            if not (clean_phone.startswith("+") or clean_phone.isdigit()) or len(clean_phone) < 7:
                return GuardrailValidationResult(
                    is_valid=False,
                    error_message="Invalid phone number format. Must include valid dial code and digits.",
                    rule_name="CONTACT_PHONE_SYNTAX_CONSTRAINT"
                )

        if home_address is not None and len(home_address.strip()) < 8:
            return GuardrailValidationResult(
                is_valid=False,
                error_message="Address must be at least 8 characters long.",
                rule_name="CONTACT_ADDRESS_LENGTH_CONSTRAINT"
            )

        return GuardrailValidationResult(
            is_valid=True,
            error_message=None,
            rule_name="CONTACT_VALIDATION_PASSED"
        )

    def validate_ticket_deduplication(
        self,
        requester_id: str,
        category: str,
        existing_tickets: list[dict],
        window_minutes: int = 10,
        now: datetime.datetime | None = None
    ) -> GuardrailValidationResult:
        """Prevent duplicate ticket creation within a defined rolling window.

        Ten minutes is the window FR-4.3 specifies ("same requestor, category,
        10-minute window"), not a tunable default.
        """
        current_time = now or datetime.datetime.now(datetime.timezone.utc)

        for ticket in existing_tickets:
            if ticket.get("requester_id") == requester_id and ticket.get("category") == category:
                ticket_created_str = ticket.get("created_at")
                if ticket_created_str:
                    try:
                        ticket_created = datetime.datetime.fromisoformat(ticket_created_str)
                        if ticket_created.tzinfo is None:
                            ticket_created = ticket_created.replace(tzinfo=datetime.timezone.utc)
                        delta = (current_time - ticket_created).total_seconds() / 60.0
                        if delta < window_minutes:
                            return GuardrailValidationResult(
                                is_valid=False,
                                error_message=f"Duplicate ticket detected for category '{category}' created within the last {int(delta)} minutes (Ticket ID: {ticket.get('ticket_id')}).",
                                rule_name="TICKET_DUPLICATION_MITIGATION_CONSTRAINT"
                            )
                    except ValueError:
                        pass

        return GuardrailValidationResult(
            is_valid=True,
            error_message=None,
            rule_name="TICKET_DEDUPLICATION_PASSED"
        )

    def validate_ticket_transition(self, current_status: str, new_status: str) -> GuardrailValidationResult:
        """Enforce strict status transition state machine."""
        allowed_transitions = self.VALID_TICKET_TRANSITIONS.get(current_status, [])
        if new_status not in allowed_transitions:
            return GuardrailValidationResult(
                is_valid=False,
                error_message=f"Invalid ticket status transition from '{current_status}' to '{new_status}'. Allowed transitions: {allowed_transitions}",
                rule_name="TICKET_STATE_MACHINE_CONSTRAINT"
            )

        return GuardrailValidationResult(
            is_valid=True,
            error_message=None,
            rule_name="TICKET_TRANSITION_PASSED"
        )

    def verify_priority_assignment(self, category: str, description: str, requested_priority: str) -> str:
        """Adjust or verify incident priority based on enterprise policy guidelines."""
        desc_lower = description.lower()
        if "outage" in desc_lower or "system wide down" in desc_lower or "production down" in desc_lower:
            return "1 - Critical"
        if "urgent" in desc_lower or "cannot work" in desc_lower or "blocked" in desc_lower:
            return "2 - High"
        if requested_priority in self.VALID_PRIORITIES:
            # If critical was requested without outage context, downgrade to Moderate
            if requested_priority == "1 - Critical":
                return "3 - Moderate"
            return requested_priority
        return "3 - Moderate"


# Global singleton guardrail engine
guardrail_engine = OperationGuardrailEngine()
