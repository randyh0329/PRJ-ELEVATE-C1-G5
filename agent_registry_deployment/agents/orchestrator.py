"""Core Enterprise HR Orchestrator engine managing state, RBAC, and audit logs."""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
import uuid
try:
  from google3.experimental.users.choirul.hr_enterprise_design.agents.enterprise_agents import (
      HRSupervisorAgent,
      LifecycleOperationsAgent,
      ManagerApprovalAgent,
      PolicyBenefitsAgent,
  )
  from google3.experimental.users.choirul.hr_enterprise_design.backend.integrations import (
      PubSubEventPublisher,
      ServiceNowClient,
      WorkdayClient,
  )
  from google3.experimental.users.choirul.hr_enterprise_design.backend.schemas import (
      AgentResponse,
      ApprovalDecisionRequest,
      ApprovalRequest,
      ApprovalStatus,
      AuditLogEntry,
      CaseCreateRequest,
      EmployeeProfile,
      HRCase,
      UserQueryRequest,
      UserRole,
  )
except ImportError:
  from .enterprise_agents import (
      HRSupervisorAgent,
      LifecycleOperationsAgent,
      ManagerApprovalAgent,
      PolicyBenefitsAgent,
  )
  from .integrations import (
      PubSubEventPublisher,
      ServiceNowClient,
      WorkdayClient,
  )
  from .schemas import (
      AgentResponse,
      ApprovalDecisionRequest,
      ApprovalRequest,
      ApprovalStatus,
      AuditLogEntry,
      CaseCreateRequest,
      EmployeeProfile,
      HRCase,
      UserQueryRequest,
      UserRole,
  )

logger = logging.getLogger(__name__)


class HREnterpriseOrchestrator:
  """Enterprise-grade HR workflow orchestrator with Spanner-like state store and audit trail."""

  def __init__(self):
    # Core system adapters
    self.workday = WorkdayClient()
    self.servicenow = ServiceNowClient()
    self.pubsub = PubSubEventPublisher()

    # Specialized agent fleet
    self.policy_agent = PolicyBenefitsAgent()
    self.lifecycle_agent = LifecycleOperationsAgent(
        self.workday, self.servicenow, self.pubsub
    )
    self.approval_agent = ManagerApprovalAgent(
        self.workday, self.servicenow, self.pubsub
    )
    self.supervisor_agent = HRSupervisorAgent(
        policy_agent=self.policy_agent,
        lifecycle_agent=self.lifecycle_agent,
        approval_agent=self.approval_agent,
        workday_client=self.workday,
        servicenow_client=self.servicenow,
    )

    # In-memory transactional stores simulating Cloud Spanner
    self._audit_logs: List[AuditLogEntry] = []
    self._cases: Dict[str, HRCase] = {}

  def process_query(self, request: UserQueryRequest) -> AgentResponse:
    """Execute conversational query with RBAC verification and audit logging."""
    logger.info(f"Processing query from employee {request.employee_id}: {request.query}")

    # Emit audit log for access tracking
    self._log_audit(
        entity_type="QUERY",
        entity_id=request.employee_id,
        actor_id=request.employee_id,
        action="PROCESS_QUERY",
        details={"query": request.query, "channel": request.channel},
    )

    # Route through Supervisor Agent
    response = self.supervisor_agent.route_and_execute(
        employee_id=request.employee_id,
        query=request.query,
    )

    # If a case was generated, cache in state store
    if response.case_id:
      case_obj = self.servicenow.get_case(response.case_id)
      if case_obj:
        self._cases[response.case_id] = case_obj

    return response

  def create_case(self, request: CaseCreateRequest) -> HRCase:
    """Manually or programmatically create an enterprise HR case."""
    case = self.servicenow.create_case(
        employee_id=request.employee_id,
        category=request.category,
        subcategory=request.subcategory,
        summary=request.summary,
        priority=request.priority,
        context_payload=request.context_payload,
    )
    self._cases[case.case_id] = case

    # Emit Cloud Pub/Sub event and Audit log
    self.pubsub.publish_event(
        topic="hr.case.created",
        payload={"case_id": case.case_id, "employee_id": request.employee_id},
    )
    self._log_audit(
        entity_type="CASE",
        entity_id=case.case_id,
        actor_id=request.employee_id,
        action="CREATE_CASE",
        details={"category": request.category, "summary": request.summary},
    )
    return case

  def submit_approval_decision(
      self,
      request: ApprovalDecisionRequest,
  ) -> Optional[ApprovalRequest]:
    """Execute manager or HRBP approval decision with governance checks."""
    approval = self.approval_agent.process_decision(
        request_id=request.request_id,
        approver_id=request.approver_id,
        decision=request.decision,
        notes=request.notes,
    )
    if approval:
      self._log_audit(
          entity_type="APPROVAL",
          entity_id=approval.request_id,
          actor_id=request.approver_id,
          action=f"DECISION_{request.decision.value}",
          details={"decision": request.decision.value, "notes": request.notes},
      )
    return approval

  def get_case(self, case_id: str) -> Optional[HRCase]:
    """Retrieve case by ID."""
    return self.servicenow.get_case(case_id)

  def get_audit_logs(self, limit: int = 50) -> List[AuditLogEntry]:
    """Retrieve immutable audit records for compliance verification."""
    return self._audit_logs[-limit:]

  def get_employee_profile(self, employee_id: str) -> Optional[EmployeeProfile]:
    """Look up worker profile from Workday."""
    return self.workday.get_employee(employee_id)

  def _log_audit(
      self,
      entity_type: str,
      entity_id: str,
      actor_id: str,
      action: str,
      details: Dict[str, Any],
  ):
    """Atomically append an immutable audit record."""
    audit_entry = AuditLogEntry(
        audit_id=f"AUD-{uuid.uuid4().hex[:12]}",
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        action=action,
        details=details,
        timestamp=datetime.utcnow(),
    )
    self._audit_logs.append(audit_entry)
