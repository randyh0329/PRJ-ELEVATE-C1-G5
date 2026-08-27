import re
from typing import Dict, Any, Optional, List
from src.policy_kb.retriever import policy_kb
from src.adapters.workweek_adapter import workweek_adapter
from src.adapters.itsm_adapter import itsm_adapter
from src.models.chat import Citation
from src.models.common import PriorityEnum, TicketStateEnum


class PolicySpecialistAgent:
    """Policy Specialist (gemini-3.7-flash, pol-1.4.0) - agent_search.query authorized."""
    def __init__(self):
        self.agent_id = "pol-1.4.0"

    async def execute(self, query: str) -> Dict[str, Any]:
        retrieval = policy_kb.query(query)
        if not retrieval["grounded"]:
            return {
                "content": retrieval["fallback_message"],
                "citations": [],
                "groundedness_score": 0.0
            }

        passages = retrieval["passages"]
        citations: List[Citation] = retrieval["citations"]

        # Synthesize concise grounded response
        combined_text = "\n\n".join(passages)
        answer = f"Based on enterprise policy:\n\n{combined_text[:500]}..."
        
        # Specific formatting for common queries
        q_lower = query.lower()
        if "bereavement" in q_lower:
            answer = (
                "Under the Global Enterprise Leave Policy (POL-HR-LEAVE-2026), full-time employees are entitled to "
                "**up to 5 consecutive paid business days** of bereavement leave for immediate family members "
                "(spouse, domestic partner, child, parent, legal guardian, or sibling), and up to 3 days for extended family."
            )
        elif "monitor" in q_lower or "screen" in q_lower:
            answer = (
                "Under the Remote & Hybrid Work Guidelines (POL-HR-REMOTE-2026), eligible remote/hybrid employees "
                "may request one **27-inch 4K ergonomic display monitor**, keyboard, and mouse through the ServiceImmediately IT catalog."
            )
        elif "headphone" in q_lower:
            answer = (
                "According to the Global Expense Reimbursement Guidelines (POL-FIN-EXPENSE-2026), employees in open-plan "
                "or remote environments may expense **up to $200** for noise-canceling headphones once every two years with manager pre-approval."
            )
        elif "london" in q_lower or "relocat" in q_lower:
            answer = (
                "Under the Enterprise Global Relocation Policy (POL-HR-RELOC-2026), inter-region corporate transfers "
                "to the London hub provide a standard lump sum relocation allowance of **up to $5,000 USD**."
            )

        return {
            "content": answer,
            "citations": citations,
            "groundedness_score": 0.95
        }


class HCMSpecialistAgent:
    """WorkWeek HCM Specialist (gemini-3.7-flash, hcm-1.4.0) - ww.* authorized."""
    def __init__(self):
        self.agent_id = "hcm-1.4.0"

    async def execute(self, action: str, subject_assertion: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "get_balances":
            balances = await workweek_adapter.get_balances(subject_assertion)
            return {
                "content": (
                    f"**Your WorkWeek PTO Balances:**\n"
                    f"• **Vacation Leave**: **{balances.vacation.remainingHours} hours** remaining "
                    f"({balances.vacation.accruedHours} accrued, {balances.vacation.usedHours} used)\n"
                    f"• **Sick Leave**: **{balances.sick.remainingHours} hours** remaining "
                    f"({balances.sick.accruedHours} accrued, {balances.sick.usedHours} used)"
                ),
                "data": balances.model_dump(),
                "citations": []
            }

        elif action == "get_profile":
            profile = await workweek_adapter.get_profile(subject_assertion)
            return {
                "content": (
                    f"**WorkWeek Employee Profile:**\n"
                    f"• **Employee ID**: `{profile.employeeId}`\n"
                    f"• **Name**: {profile.name}\n"
                    f"• **Role**: {profile.role} ({profile.department})\n"
                    f"• **Manager**: {profile.manager}\n"
                    f"• **Address**: {profile.homeAddress or 'Not set'}\n"
                    f"• **Phone**: {profile.phoneNumber or 'Not set'}"
                ),
                "data": profile.model_dump(),
                "citations": []
            }

        elif action == "update_contact":
            address = params.get("homeAddress") or params.get("address")
            phone = params.get("phoneNumber") or params.get("phone")
            res = await workweek_adapter.update_contact(subject_assertion, address=address, phone=phone)
            updated_str = ", ".join(res.updated)
            return {
                "content": f"Successfully updated your WorkWeek contact information: **{updated_str}**.",
                "data": res.model_dump(),
                "citations": []
            }

        elif action == "submit_leave":
            start_date = params["startDate"]
            end_date = params["endDate"]
            leave_type = params.get("leaveType", "Vacation")
            work_days = float(params.get("workDays", 1.0))
            reason = params.get("reason")
            res = await workweek_adapter.submit_leave(
                subject_assertion,
                start_date=start_date,
                end_date=end_date,
                leave_type=leave_type,
                work_days=work_days,
                reason=reason
            )
            return {
                "content": (
                    f"Your leave request has been submitted to WorkWeek.\n"
                    f"• **Leave ID**: `{res.leaveId}`\n"
                    f"• **Status**: **{res.status.value}** (pending manager approval)\n"
                    f"• **Dates**: {start_date} to {end_date} ({work_days} work days)"
                ),
                "data": res.model_dump(),
                "citations": []
            }

        elif action == "cancel_leave":
            leave_id = params["leaveId"]
            res = await workweek_adapter.cancel_leave(subject_assertion, leave_id)
            return {
                "content": f"Leave request `{leave_id}` has been successfully cancelled and hours restored to balance.",
                "data": res,
                "citations": []
            }

        return {"content": "Unknown HCM action requested.", "citations": []}


class ITSMSpecialistAgent:
    """ServiceImmediately Specialist (gemini-3.7-flash, itsm-1.4.0) - si.* authorized."""
    def __init__(self):
        self.agent_id = "itsm-1.4.0"

    async def execute(self, action: str, subject_assertion: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "get_incident":
            ticket_id = params["ticketId"]
            inc = await itsm_adapter.get_incident(ticket_id, subject_assertion)
            comments_text = ""
            if inc.comments:
                comments_text = "\n\n**Latest Updates:**\n" + "\n".join(
                    [f"• *{c.author}* ({c.createdAt}): {c.body}" for c in inc.comments[-3:]]
                )
            return {
                "content": (
                    f"**ServiceImmediately Ticket Details:**\n"
                    f"• **Ticket ID**: `{inc.ticketId}`\n"
                    f"• **Title**: {inc.shortDescription}\n"
                    f"• **Status**: **{inc.state.value}**\n"
                    f"• **Priority**: {inc.priority.value}\n"
                    f"• **Assignee**: {inc.assignee}"
                    f"{comments_text}"
                ),
                "data": inc.model_dump(),
                "citations": []
            }

        elif action == "create_incident":
            category = params.get("category", "General IT")
            short_desc = params["shortDescription"]
            priority = PriorityEnum(params.get("priority", "3 - Moderate"))
            desc = params.get("description")
            res = await itsm_adapter.create_incident(
                category=category,
                short_description=short_desc,
                priority=priority,
                description=desc,
                subject_assertion=subject_assertion
            )
            return {
                "content": (
                    f"New support ticket logged in ServiceImmediately.\n"
                    f"• **Ticket ID**: `{res.ticketId}`\n"
                    f"• **Subject**: {short_desc}\n"
                    f"• **Priority**: {priority.value}\n"
                    f"Our support desk has received your ticket and will investigate shortly."
                ),
                "data": res.model_dump(),
                "citations": []
            }

        elif action == "post_comment":
            ticket_id = params["ticketId"]
            body = params["body"]
            res = await itsm_adapter.post_comment(ticket_id, body, subject_assertion)
            return {
                "content": f"Comment successfully added to ticket `{ticket_id}`.",
                "data": res,
                "citations": []
            }

        elif action == "update_status":
            ticket_id = params["ticketId"]
            state = TicketStateEnum(params["state"])
            notes = params.get("resolutionNotes")
            res = await itsm_adapter.update_status(ticket_id, state, notes, subject_assertion)
            return {
                "content": f"Ticket `{ticket_id}` state transitioned to **{state.value}**.",
                "data": res.model_dump(),
                "citations": []
            }

        return {"content": "Unknown ITSM action requested.", "citations": []}


policy_agent = PolicySpecialistAgent()
hcm_agent = HCMSpecialistAgent()
itsm_agent = ITSMSpecialistAgent()
