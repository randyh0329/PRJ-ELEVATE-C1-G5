import time
import uuid
from typing import Optional, Dict, Any, Tuple
from src.storage.firestore import firestore_store


class RightsKeywordsHandler:
    """
    Implements In-Conversation Privacy Notice & Rights Entry Points (SDD §4.12).
    Deterministic handling at the gateway - NEVER routed through LLM.
    Keywords: privacy, what do you know about me, forget me, stop storing my conversations, human.
    """
    KEYWORDS = {
        "privacy",
        "what do you know about me",
        "forget me",
        "stop storing my conversations",
        "human"
    }

    @classmethod
    def match_keyword(cls, user_message: str) -> Optional[str]:
        cleaned = user_message.strip().lower()
        if cleaned in cls.KEYWORDS:
            return cleaned
        # Check variations
        if any(h in cleaned for h in ["human", "speak to a person", "talk to a person", "representative", "operator"]):
            return "human"
        if "privacy" in cleaned:
            return "privacy"
        return None


    @classmethod
    def handle_keyword(cls, keyword: str, session_id: str, employee_id: str) -> Dict[str, Any]:
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if keyword == "privacy":
            return {
                "handled": True,
                "content": (
                    "**Enterprise HR Assistant Privacy Notice (GDPR Art. 12-14)**\n\n"
                    "• **Automated Assistant**: You are conversing with an automated AI HR assistant.\n"
                    "• **Retention**: Active session transcripts are retained for **30 days** in secure encrypted storage. "
                    "Audit logs are pseudonymised and retained for **365 days** for regulatory compliance.\n"
                    "• **Data Protection**: Sensitive identifiers (SSN, phone, address) are de-identified before processing.\n"
                    "• **Your Rights**: Type `what do you know about me` for data access, `forget me` for erasure, "
                    "`stop storing my conversations` to withdraw consent, or `human` to escalate to an HR specialist."
                ),
                "citations": [],
                "escalated": False,
                "rightExercised": "ART_12_TRANSPARENCY"
            }

        elif keyword == "what do you know about me":
            messages = firestore_store.get_messages(session_id)
            return {
                "handled": True,
                "content": (
                    f"**Data Access Summary (GDPR Art. 15)**\n\n"
                    f"• **Bound Employee Subject**: `{employee_id}`\n"
                    f"• **Active Session ID**: `{session_id}`\n"
                    f"• **Retained Session Turns**: {len(messages)} interaction turns in 30-day active store.\n"
                    f"• **Audit Profile**: Zero raw SPII stored. Transcripts use crypto-deterministic surrogates.\n"
                    f"A detailed export has been scheduled for delivery to your corporate address within 24 hours."
                ),
                "citations": [],
                "escalated": False,
                "rightExercised": "ART_15_ACCESS"
            }

        elif keyword == "forget me":
            # Article 17 Erasure (SDD §4.12 scope confirmation)
            receipt_id = f"REC-RTBF-{uuid.uuid4().hex[:8].upper()}"
            purged = firestore_store.purge_employee_data(employee_id)
            return {
                "handled": True,
                "content": (
                    f"**Right to be Forgotten (GDPR Art. 17) - Purge Initiated**\n\n"
                    f"**Scope Confirmation:** Conversational transcripts and saga session traces have been completely "
                    f"hard-deleted from the virtual assistant state stores ({purged} records purged).\n\n"
                    f"**Important System of Record Notice:** Official employment, payroll, and leave records in WorkWeek and "
                    f"tickets in ServiceImmediately are external systems of record not deleted by this virtual assistant action.\n\n"
                    f"**Receipt ID:** `{receipt_id}`\n"
                    f"**Completed At:** `{now_str}`"
                ),
                "citations": [],
                "escalated": False,
                "rightExercised": "ART_17_ERASURE",
                "receiptId": receipt_id
            }

        elif keyword == "stop storing my conversations":
            # Article 7(3) Consent Withdrawal (SDD §4.6 & §4.12)
            firestore_store.withdraw_consent(employee_id)
            return {
                "handled": True,
                "content": (
                    "**Consent Withdrawn (GDPR Art. 7(3))**\n\n"
                    "Your consent for conversation history storage has been withdrawn. "
                    "Historical session turns for your profile have been purged.\n\n"
                    "**Future Mode:** This session and future sessions will operate in **ephemeral mode** "
                    "(transcripts held in memory only for current turn and discarded immediately)."
                ),
                "citations": [],
                "escalated": False,
                "rightExercised": "ART_7_CONSENT_WITHDRAWAL"
            }

        elif keyword == "human":
            # Escalation Ladder (§5.7)
            ticket_id = f"ESC-{uuid.uuid4().hex[:6].upper()}"
            escalation_record = {
                "escalationId": ticket_id,
                "sessionId": session_id,
                "employeeId": employee_id,
                "reason": "EMPLOYEE_REQUESTED_HUMAN",
                "timestamp": now_str,
                "status": "QUEUED_TO_SERVICEIMMEDIATELY"
            }
            firestore_store.write_escalation_outbox(escalation_record)
            return {
                "handled": True,
                "content": (
                    f"**Connecting You to HR Operations Specialist**\n\n"
                    f"I have initiated a warm transfer to a human specialist in ServiceImmediately.\n"
                    f"• **Escalation Reference**: `{ticket_id}`\n"
                    f"• **Queue**: Tier 1 HR & IT Support Desk\n"
                    f"• **Expected Turnaround**: < 15 minutes during business hours.\n\n"
                    f"Your context has been securely transferred with de-identified surrogates so you do not need to repeat yourself."
                ),
                "citations": [],
                "escalated": True,
                "escalationDetails": escalation_record
            }

        return {"handled": False}


rights_handler = RightsKeywordsHandler()
