"""
State definition and Saga data models for the agent-core orchestrator.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.1, §4.6, §5.4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict


class SagaCompensationClass(str, Enum):
    """
    Saga Compensation Classification Policy (§5.4).
    Determines failure and rollback behavior across distributed agent steps.
    """
    READ_ONLY = "READ_ONLY"                    # No state change (balance check, profile read)
    REVERSIBLE_SAFE = "REVERSIBLE_SAFE"        # Reversible write with prior value captured (contact update)
    ANCILLARY = "ANCILLARY"                    # Supporting step; failure does not invalidate main outcome (IT routing ticket)
    HUMAN_CONSEQUENTIAL = "HUMAN_CONSEQUENTIAL"# Consequential HR/legal write; NEVER auto-reversed (Medical Leave)


class SagaStepStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED_HANDED_TO_HUMAN = "FAILED_HANDED_TO_HUMAN"
    ASYNC_QUEUED = "ASYNC_QUEUED"


class SagaWorkflowState(str, Enum):
    STARTED = "STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    COMPENSATED_ROLLED_BACK = "COMPENSATED_ROLLED_BACK"
    PARTIALLY_COMPLETED_MANUAL_FOLLOWUP = "PARTIALLY_COMPLETED_MANUAL_FOLLOWUP"
    FAILED = "FAILED"


@dataclass
class SagaStepRecord:
    """
    Individual step entry in the distributed Firestore Saga Ledger (§4.6, §5.4).
    """
    step_index: int
    target_system: str                         # "Policy", "WorkWeek", "ServiceImmediately"
    action: str                                # e.g. "SUBMIT_LEAVE", "CREATE_ROUTING_TICKET", "UPDATE_CONTACT"
    compensation_class: SagaCompensationClass
    status: SagaStepStatus = SagaStepStatus.PENDING
    external_ref_id: Optional[str] = None      # e.g. "LV-4012", "INC-5510", "REQ-8830"
    compensation_payload: Optional[Dict[str, Any]] = None  # Captured prior state for REVERSIBLE_SAFE
    follow_up_ref: Optional[str] = None        # e.g. "OPS-2214" for ANCILLARY / HUMAN_CONSEQUENTIAL follow-up
    error_message: Optional[str] = None
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stepIndex": self.step_index,
            "targetSystem": self.target_system,
            "action": self.action,
            "compensationClass": self.compensation_class.value if isinstance(self.compensation_class, SagaCompensationClass) else self.compensation_class,
            "status": self.status.value if isinstance(self.status, SagaStepStatus) else self.status,
            "externalReferenceId": self.external_ref_id,
            "compensationPayload": self.compensation_payload,
            "followUpRef": self.follow_up_ref,
            "errorMessage": self.error_message,
            "timestamp": self.timestamp,
        }


class AgentState(TypedDict):
    """
    Complete LangGraph / StateGraph execution state for agent-core (§3.1, §4.6).
    """
    # 1. Identity & Context (Server-Side Bound, never model-supplied - §4.1)
    session_id: str
    turn_id: str
    employee_id: str                          # Bound server-side from gateway session
    user_roles: List[str]
    scopes: List[str]

    # 2. Conversation & Routing State
    user_input: str
    masked_input: str                         # Pre-LLM DLP de-identified input (§4.3)
    messages: List[Dict[str, Any]]
    route: Literal["supervisor", "policy", "hcm", "itsm", "saga", "escalate", "end"]
    next_node: Optional[str]

    # 3. Cross-System Saga Ledger State (§4.6, §5.4)
    saga_id: Optional[str]
    saga_type: Optional[str]                  # "UC-2.1-EQUIPMENT", "UC-2.2-MEDICAL-LEAVE", "UC-2.3-RELOCATION"
    saga_state: Optional[str]                 # SagaWorkflowState
    saga_ledger: List[SagaStepRecord]
    current_step_index: int

    # 4. Agent Outputs, Guardrails & Grounding (§4.3, §5.4, §9.1)
    guardrail_verdict: Literal["ALLOW", "BLOCK"]
    grounding_score: float
    citations: List[Dict[str, str]]
    # Which corpus answered - "faiss" (indexed handbook) or "curated" (the mock
    # datastore used when no index has been built) - and how the guards disposed
    # of the query. Recorded so an auditor can tell a grounded answer from a
    # degraded one, and an escalation from a refusal.
    grounding_source: str
    policy_decision: Literal["answer", "escalate", "refuse"]
    final_response: Optional[str]

    # 5. Fault Injection (For §9.1 Trajectory Testing Harness)
    injected_faults: Dict[str, Any]           # e.g. {"step_2_status": 503, "max_retries_fail": True}

    # 6. Escalation Package (§5.7)
    context_package: Optional[Dict[str, Any]]
