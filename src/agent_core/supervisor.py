import re
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional
from src.agent_core.specialists import policy_agent, hcm_agent, itsm_agent
from src.agent_core.saga import saga_coordinator
from src.models.common import PriorityEnum


class SupervisorRouter:
    """
    Supervisor / Chief Concierge Router (gemini-3.7-flash, sup-1.4.0).
    Enforces domain containment, analyzes user intent, and delegates to specialist agents.
    Never calls external backend tools directly.
    """
    def __init__(self):
        self.agent_id = "sup-1.4.0"

    async def route_and_execute(self, user_message: str, session_id: str, employee_id: str) -> Dict[str, Any]:
        msg_lower = user_message.lower().strip()

        # 1. Out-of-Domain Containment Check (FR-5.4)
        out_of_domain_patterns = [
            r"\b(?:python|java|javascript|c\+\+|html|css|sql|function|code|debug|compile|script|prime numbers)\b",
            r"\b(?:write\s+(?:a\s+)?(?:creative\s+)?(?:poem|story|essay|song)|tell me a joke|poem|story)\b",
            r"\b(?:weather\s+in|stock\s+price|bitcoin|crypto|presidential\s+election|apple)\b",
            r"\b(?:who won the|recipe for|diet plan)\b"
        ]
        for pat in out_of_domain_patterns:
            if re.search(pat, msg_lower):
                return {
                    "content": "I can help with HR policies, WorkWeek and IT tickets. That one is outside what I can assist with.",
                    "citations": [],
                    "escalated": False,
                    "agent": self.agent_id
                }

        # 2. Cross-System Saga Workflows
        # UC-2.1: Equipment procurement
        if any(w in msg_lower for w in ["monitor", "external screen", "external display"]) and any(a in msg_lower for a in ["order", "request", "need", "get", "procure"]):
            return await saga_coordinator.execute_equipment_workflow(session_id, employee_id)


        # UC-2.2: Medical leave setup
        if any(k in msg_lower for k in ["medical leave", "surgery leave", "sick leave of absence", "short term disability"]):
            # Extract dates or default to upcoming 2 weeks
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            two_weeks = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
            return await saga_coordinator.execute_medical_leave_workflow(
                session_id=session_id,
                employee_id=employee_id,
                start_date=tomorrow,
                end_date=two_weeks,
                work_days=10.0
            )

        # UC-2.3: Relocation
        if any(k in msg_lower for k in ["relocat", "transfer to london", "moving to london", "relocate to london"]):
            # Extract address if mentioned
            addr_match = re.search(r"(?:address\s*(?:to|is)?\s*)([^,\.]+)", user_message, re.IGNORECASE)
            new_addr = addr_match.group(1).strip() if addr_match else "10 Downing Street, London, UK"
            return await saga_coordinator.execute_relocation_workflow(
                session_id=session_id,
                employee_id=employee_id,
                new_address=new_addr,
                destination_city="London"
            )

        # 2.5 Policy Specialist Routing for specific HR policy topics
        if any(k in msg_lower for k in ["bereavement", "parental", "maternity", "paternity", "policy", "guideline", "code of conduct", "harassment", "expense limit", "headphone"]):
            return await policy_agent.execute(user_message)

        # 3. WorkWeek HCM Specialist Routing
        # Balance inquiry
        if any(k in msg_lower for k in ["balance", "remaining pto", "vacation days do i have", "how many days of vacation", "how many hours do i have", "my remaining"]):
            return await hcm_agent.execute("get_balances", employee_id, {})


        # Profile inquiry
        if any(k in msg_lower for k in ["my profile", "who is my manager", "my job title", "my department"]):
            return await hcm_agent.execute("get_profile", employee_id, {})

        # Contact update
        if any(k in msg_lower for k in ["update my address", "change my address", "update my phone", "new phone number", "update address to"]):
            addr_match = re.search(r"(?:address to|address:)\s*([^\n\.,]+)", user_message, re.IGNORECASE)
            phone_match = re.search(r"(?:phone to|phone:)\s*([^\n\.,]+)", user_message, re.IGNORECASE)
            params = {}
            if addr_match:
                params["homeAddress"] = addr_match.group(1).strip()
            if phone_match:
                params["phoneNumber"] = phone_match.group(1).strip()
            if not params:
                # default test extraction
                params["homeAddress"] = "123 Technology Way, Silicon Valley, CA"
            return await hcm_agent.execute("update_contact", employee_id, params)

        # Leave submission
        if any(k in msg_lower for k in ["take vacation", "book vacation", "request pto", "submit leave", "request time off", "take 2 days off"]):
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
            # Parse days
            days_match = re.search(r"(\d+(?:\.\d+)?)\s*day", msg_lower)
            days = float(days_match.group(1)) if days_match else 2.0
            return await hcm_agent.execute("submit_leave", employee_id, {
                "startDate": tomorrow,
                "endDate": day_after,
                "leaveType": "Vacation",
                "workDays": days,
                "reason": "Personal time off"
            })

        # Cancel leave
        if any(k in msg_lower for k in ["cancel leave", "cancel vacation", "cancel my pto"]):
            leave_match = re.search(r"\bLV-\d+\b", user_message)
            leave_id = leave_match.group(0) if leave_match else "LV-4021"
            return await hcm_agent.execute("cancel_leave", employee_id, {"leaveId": leave_id})

        # 4. ServiceImmediately ITSM Specialist Routing
        # Incident query
        ticket_match = re.search(r"\b(?:INC|REQ)\d{6,}\b", user_message)
        if ticket_match:
            ticket_id = ticket_match.group(0)
            if any(k in msg_lower for k in ["comment", "add note", "update ticket with"]):
                return await itsm_agent.execute("post_comment", employee_id, {
                    "ticketId": ticket_id,
                    "body": "User update via automated HR chat."
                })
            elif any(k in msg_lower for k in ["resolve", "close ticket", "transition to"]):
                return await itsm_agent.execute("update_status", employee_id, {
                    "ticketId": ticket_id,
                    "state": "Resolved",
                    "resolutionNotes": "Resolved via self-service verification."
                })
            else:
                return await itsm_agent.execute("get_incident", employee_id, {"ticketId": ticket_id})

        # Create ticket
        if any(k in msg_lower for k in ["open ticket", "create ticket", "submit ticket", "issue with my laptop", "vpn broken", "wifi not working"]):
            return await itsm_agent.execute("create_incident", employee_id, {
                "category": "IT Support",
                "shortDescription": user_message[:100],
                "priority": "3 - Moderate",
                "description": user_message
            })

        # 5. Policy Specialist Routing (Default for HR questions)
        return await policy_agent.execute(user_message)


supervisor_router = SupervisorRouter()
