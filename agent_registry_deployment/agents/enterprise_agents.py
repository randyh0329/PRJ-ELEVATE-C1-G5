"""Specialized Enterprise Agent implementations for HRED."""

from typing import Any, Dict, List, Optional
import uuid
try:
  from google3.experimental.users.choirul.hr_enterprise_design.backend.integrations import (
      PubSubEventPublisher,
      ServiceNowClient,
      WorkdayClient,
  )
  from google3.experimental.users.choirul.hr_enterprise_design.backend.schemas import (
      AgentResponse,
      ApprovalRequest,
      ApprovalStatus,
      CasePriority,
      CaseStatus,
      EmployeeProfile,
      HRCase,
      PolicyCitation,
      UserRole,
  )
except ImportError:
  from .integrations import (
      PubSubEventPublisher,
      ServiceNowClient,
      WorkdayClient,
  )
  from .schemas import (
      AgentResponse,
      ApprovalRequest,
      ApprovalStatus,
      CasePriority,
      CaseStatus,
      EmployeeProfile,
      HRCase,
      PolicyCitation,
      UserRole,
  )


class PolicyBenefitsAgent:
  """Specialized agent for grounded HR policy interpretation and benefits queries."""

  def __init__(self):
    # Deterministic knowledge base representing grounded enterprise policies
    self._policy_registry = {
        "sick_leave": {
            "title": "Sick Leave & Medical Certificate Guidelines",
            "section": "Section 19.2",
            "source_file": "knowledge/19-sick-leave/19.2-outpatient.md",
            "content": (
                "Employees are entitled to up to 14 days of paid outpatient sick leave per calendar"
                " year. An official Medical Certificate (MC) must be submitted via WorkWeek within"
                " 48 hours of returning to work."
            ),
        },
        "ramp_back": {
            "title": "Ramp-Back Time After Extended Leave",
            "section": "Section 28.1",
            "source_file": "knowledge/28-ramp-back/28.1-overview.md",
            "content": (
                "Returning primary caregivers may work a reduced schedule (≥50% normal hours) for"
                " up to 2 weeks following parental leave while receiving 100% full salary."
            ),
        },
        "gift_policy": {
            "title": "Business Gifts & Anti-Bribery Policy",
            "section": "Section 12.4",
            "source_file": "knowledge/12-conduct/12.4-gifts.md",
            "content": (
                "Promotional items up to $50 are permissible. However, gift cards, cash, or"
                " cash equivalents are STRICTLY PROHIBITED regardless of the dollar amount."
            ),
        },
        "vacation_accrual": {
            "title": "Vacation Accrual & Service Tiers",
            "section": "Section 03.1",
            "source_file": "knowledge/03-vacation/03.1-accrual.md",
            "content": (
                "Employees with 5+ years of tenure accrue 21 vacation days annually. Unused days up"
                " to a maximum of 5 days may be carried over with manager approval."
            ),
        },
    }

  def answer_query(
      self,
      query: str,
      employee: EmployeeProfile,
  ) -> AgentResponse:
    """Analyze query and return grounded answer with precise policy citations."""
    q_lower = query.lower()
    citations: List[PolicyCitation] = []
    response_text = ""

    if "sick" in q_lower or "mc" in q_lower or "medical certificate" in q_lower:
      policy = self._policy_registry["sick_leave"]
      citations.append(
          PolicyCitation(
              policy_id="POL-SICK-19",
              section=policy["section"],
              title=policy["title"],
              source_file=policy["source_file"],
              confidence_score=0.98,
          )
      )
      response_text = (
          f"According to {policy['title']} ({policy['section']}):\n"
          f"{policy['content']}\n\n"
          f"For {employee.jurisdiction.value} employees, ensure your MC is uploaded to WorkWeek."
      )

    elif "ramp" in q_lower or "ramp-back" in q_lower or "parental return" in q_lower:
      policy = self._policy_registry["ramp_back"]
      citations.append(
          PolicyCitation(
              policy_id="POL-RAMP-28",
              section=policy["section"],
              title=policy["title"],
              source_file=policy["source_file"],
              confidence_score=0.99,
          )
      )
      response_text = (
          f"According to {policy['title']} ({policy['section']}):\n"
          f"{policy['content']}"
      )

    elif "gift" in q_lower or "host" in q_lower or "voucher" in q_lower:
      policy = self._policy_registry["gift_policy"]
      citations.append(
          PolicyCitation(
              policy_id="POL-GIFT-12",
              section=policy["section"],
              title=policy["title"],
              source_file=policy["source_file"],
              confidence_score=0.95,
          )
      )
      response_text = (
          f"According to {policy['title']} ({policy['section']}):\n"
          f"{policy['content']}\n\n"
          "Note: Gift cards or cash equivalents are explicitly prohibited."
      )

    elif "vacation" in q_lower or "pto" in q_lower or "leave balance" in q_lower:
      policy = self._policy_registry["vacation_accrual"]
      citations.append(
          PolicyCitation(
              policy_id="POL-VAC-03",
              section=policy["section"],
              title=policy["title"],
              source_file=policy["source_file"],
              confidence_score=0.96,
          )
      )
      response_text = (
          f"According to {policy['title']} ({policy['section']}):\n"
          f"{policy['content']}"
      )

    else:
      response_text = (
          "I could not locate an exact codified policy for your query in the Enterprise Knowledge"
          " Base. To ensure you receive accurate guidance, I recommend opening a case with your"
          " PeopleOps Business Partner."
      )

    return AgentResponse(
        session_id=str(uuid.uuid4()),
        handling_agent="PolicyBenefitsAgent",
        response_text=response_text,
        citations=citations,
    )


class LifecycleOperationsAgent:
  """Specialized agent for employee onboarding, transfers, and offboarding workflows."""

  def __init__(
      self,
      workday_client: WorkdayClient,
      servicenow_client: ServiceNowClient,
      event_publisher: PubSubEventPublisher,
  ):
    self.workday = workday_client
    self.servicenow = servicenow_client
    self.pubsub = event_publisher

  def initiate_onboarding(
      self,
      candidate_name: str,
      department: str,
      manager_id: str,
  ) -> AgentResponse:
    """Trigger enterprise onboarding workflow."""
    case = self.servicenow.create_case(
        employee_id="TEMP-NEW-HIRE",
        category="ONBOARDING",
        subcategory="NEW_HIRE_PROVISIONING",
        summary=f"New Hire Onboarding: {candidate_name} ({department})",
        priority=CasePriority.HIGH,
        context_payload={"manager_id": manager_id, "department": department},
    )

    self.pubsub.publish_event(
        topic="hr.lifecycle.transition",
        payload={
            "case_id": case.case_id,
            "type": "ONBOARDING",
            "candidate": candidate_name,
            "manager_id": manager_id,
        },
    )

    return AgentResponse(
        session_id=str(uuid.uuid4()),
        handling_agent="LifecycleOperationsAgent",
        response_text=(
            f"Onboarding workflow initiated for {candidate_name} in {department}. "
            f"ServiceNow Case [{case.case_id}] created. Automated IT hardware provisioning "
            "and Google Workspace account creation dispatched."
        ),
        case_id=case.case_id,
    )

  def submit_resignation_notice(
      self,
      employee: EmployeeProfile,
      last_working_day: str,
      reason: Optional[str] = None,
  ) -> AgentResponse:
    """Record resignation and start offboarding clearance."""
    case = self.servicenow.create_case(
        employee_id=employee.employee_id,
        category="OFFBOARDING",
        subcategory="VOLUNTARY_RESIGNATION",
        summary=f"Resignation Notice: {employee.full_name} (LWD: {last_working_day})",
        priority=CasePriority.HIGH,
        context_payload={
            "last_working_day": last_working_day,
            "manager_id": employee.manager_id,
            "reason": reason,
        },
    )

    self.pubsub.publish_event(
        topic="hr.lifecycle.transition",
        payload={
            "case_id": case.case_id,
            "employee_id": employee.employee_id,
            "type": "OFFBOARDING",
            "last_working_day": last_working_day,
        },
    )

    return AgentResponse(
        session_id=str(uuid.uuid4()),
        handling_agent="LifecycleOperationsAgent",
        response_text=(
            f"Resignation notice for {employee.full_name} recorded with Last Working Day: {last_working_day}. "
            f"ServiceNow Case [{case.case_id}] opened. Manager and HRBP notified for exit interview and asset handover."
        ),
        case_id=case.case_id,
    )


class ManagerApprovalAgent:
  """Specialized agent for human-in-the-loop approval workflows."""

  def __init__(
      self,
      workday_client: WorkdayClient,
      servicenow_client: ServiceNowClient,
      event_publisher: PubSubEventPublisher,
  ):
    self.workday = workday_client
    self.servicenow = servicenow_client
    self.pubsub = event_publisher
    self._approval_store: Dict[str, ApprovalRequest] = {}

  def create_approval_gate(
      self,
      case_id: str,
      requester: EmployeeProfile,
      action_summary: str,
      approval_tier: str = "MANAGER_L1",
  ) -> ApprovalRequest:
    """Create a pending approval gate requiring human sign-off."""
    approver_id = requester.manager_id or "HRBP-5001"
    request_id = f"APPR-{uuid.uuid4().hex[:8].upper()}"

    approval = ApprovalRequest(
        request_id=request_id,
        case_id=case_id,
        requester_id=requester.employee_id,
        approver_id=approver_id,
        approval_type=approval_tier,
        status=ApprovalStatus.PENDING,
        action_summary=action_summary,
    )
    self._approval_store[request_id] = approval

    self.pubsub.publish_event(
        topic="hr.approval.requested",
        payload={
            "request_id": request_id,
            "case_id": case_id,
            "requester_id": requester.employee_id,
            "approver_id": approver_id,
            "action": action_summary,
        },
    )
    return approval

  def process_decision(
      self,
      request_id: str,
      approver_id: str,
      decision: ApprovalStatus,
      notes: Optional[str] = None,
  ) -> Optional[ApprovalRequest]:
    """Process an authorized approval or rejection."""
    approval = self._approval_store.get(request_id)
    if not approval:
      return None

    # Validate approver authorization
    if approval.approver_id != approver_id:
      # Check if approver is HRBP/Admin override
      approver_profile = self.workday.get_employee(approver_id)
      if not approver_profile or approver_profile.role not in (UserRole.HRBP, UserRole.HR_ADMIN):
        raise PermissionError(f"User {approver_id} is not authorized to approve request {request_id}")

    approval.status = decision
    approval.decision_notes = notes

    self.pubsub.publish_event(
        topic="hr.approval.completed",
        payload={
            "request_id": request_id,
            "case_id": approval.case_id,
            "decision": decision.value,
            "approver_id": approver_id,
            "notes": notes,
        },
    )

    # If linked to a ServiceNow case, update the case status
    if decision == ApprovalStatus.APPROVED:
      self.servicenow.update_status(approval.case_id, CaseStatus.RESOLVED)
    elif decision == ApprovalStatus.REJECTED:
      self.servicenow.update_status(approval.case_id, CaseStatus.CLOSED)

    return approval


class HRSupervisorAgent:
  """Root supervisor agent managing session routing and multi-agent coordination."""

  def __init__(
      self,
      policy_agent: PolicyBenefitsAgent,
      lifecycle_agent: LifecycleOperationsAgent,
      approval_agent: ManagerApprovalAgent,
      workday_client: WorkdayClient,
      servicenow_client: ServiceNowClient,
  ):
    self.policy_agent = policy_agent
    self.lifecycle_agent = lifecycle_agent
    self.approval_agent = approval_agent
    self.workday = workday_client
    self.servicenow = servicenow_client

  def route_and_execute(
      self,
      employee_id: str,
      query: str,
  ) -> AgentResponse:
    """Analyze intent, verify RBAC, and dispatch to specialized domain sub-agent."""
    employee = self.workday.get_employee(employee_id)
    if not employee:
      return AgentResponse(
          session_id=str(uuid.uuid4()),
          handling_agent="HRSupervisorAgent",
          response_text=f"Authentication Error: Employee ID [{employee_id}] not found in Workday.",
      )

    q_lower = query.lower()

    # Intent Classification
    if any(k in q_lower for k in ["onboard", "new hire", "join"]):
      # Lifecycle onboarding
      return self.lifecycle_agent.initiate_onboarding(
          candidate_name="New Team Member",
          department=employee.department,
          manager_id=employee.employee_id,
      )

    elif any(k in q_lower for k in ["resign", "resignation", "quit", "leave company", "notice"]):
      # Lifecycle offboarding
      return self.lifecycle_agent.submit_resignation_notice(
          employee=employee,
          last_working_day="30 days from today",
          reason="Personal reasons",
      )

    elif any(k in q_lower for k in ["sabbatical", "unpaid leave", "exception", "carryover"]):
      # Requires human approval gate
      case = self.servicenow.create_case(
          employee_id=employee.employee_id,
          category="LEAVE",
          subcategory="SPECIAL_LEAVE_EXCEPTION",
          summary=f"Special Leave Exception Request: {query}",
          priority=CasePriority.HIGH,
      )
      approval = self.approval_agent.create_approval_gate(
          case_id=case.case_id,
          requester=employee,
          action_summary=f"Special leave request: {query}",
          approval_tier="MANAGER_L1",
      )
      return AgentResponse(
          session_id=str(uuid.uuid4()),
          handling_agent="ManagerApprovalAgent",
          response_text=(
              f"Your request involves a special leave exception requiring managerial authorization. "
              f"ServiceNow Case [{case.case_id}] created. Approval Request [{approval.request_id}] "
              f"dispatched to your manager ({employee.manager_id})."
          ),
          case_id=case.case_id,
          requires_approval=True,
          approval_request_id=approval.request_id,
      )

    else:
      # Policy / Benefits inquiry
      return self.policy_agent.answer_query(query, employee)
