"""Enterprise system integration adapters for Workday, ServiceNow, and Pub/Sub."""

import logging
from typing import Any, Dict, List, Optional
import uuid
from google3.experimental.users.choirul.hr_enterprise_design.backend.schemas import (
    ApprovalStatus,
    CasePriority,
    CaseStatus,
    EmployeeProfile,
    HRCase,
    Jurisdiction,
    UserRole,
)

logger = logging.getLogger(__name__)


class WorkdayClient:
  """Adapter for Workday Core HCM and Time Off Management APIs."""

  def __init__(self, tenant_id: str = "enterprise_prod"):
    self.tenant_id = tenant_id
    self._mock_employees: Dict[str, EmployeeProfile] = {
        "EMP-1001": EmployeeProfile(
            employee_id="EMP-1001",
            email="alex.chen@enterprise.com",
            full_name="Alex Chen",
            department="Engineering",
            jurisdiction=Jurisdiction.SINGAPORE,
            manager_id="MGR-2001",
            role=UserRole.EMPLOYEE,
        ),
        "EMP-1002": EmployeeProfile(
            employee_id="EMP-1002",
            email="sarah.connor@enterprise.com",
            full_name="Sarah Connor",
            department="Sales",
            jurisdiction=Jurisdiction.US_CALIFORNIA,
            manager_id="MGR-2002",
            role=UserRole.EMPLOYEE,
        ),
        "MGR-2001": EmployeeProfile(
            employee_id="MGR-2001",
            email="david.miller@enterprise.com",
            full_name="David Miller",
            department="Engineering",
            jurisdiction=Jurisdiction.SINGAPORE,
            manager_id="DIR-3001",
            role=UserRole.MANAGER,
        ),
        "HRBP-5001": EmployeeProfile(
            employee_id="HRBP-5001",
            email="emily.watson@enterprise.com",
            full_name="Emily Watson",
            department="PeopleOps",
            jurisdiction=Jurisdiction.GLOBAL,
            manager_id=None,
            role=UserRole.HRBP,
        ),
    }
    self._leave_balances: Dict[str, Dict[str, float]] = {
        "EMP-1001": {"ANNUAL_LEAVE": 18.0, "OUTPATIENT_SICK": 14.0, "HOSPITALIZATION": 60.0},
        "EMP-1002": {"PTO": 20.0, "SICK_LEAVE": 10.0, "BEREAVEMENT": 5.0},
    }

  def get_employee(self, employee_id: str) -> Optional[EmployeeProfile]:
    """Retrieve canonical worker profile from Workday."""
    return self._mock_employees.get(employee_id)

  def get_leave_balance(self, employee_id: str, plan_type: str = "ANNUAL_LEAVE") -> float:
    """Retrieve employee leave balance for a given plan."""
    balances = self._leave_balances.get(employee_id, {})
    return balances.get(plan_type, 0.0)

  def deduct_leave(self, employee_id: str, plan_type: str, days: float) -> bool:
    """Atomically deduct leave units upon approved request."""
    if employee_id not in self._leave_balances:
      return False
    current = self._leave_balances[employee_id].get(plan_type, 0.0)
    if current < days:
      return False
    self._leave_balances[employee_id][plan_type] = current - days
    return True


class ServiceNowClient:
  """Adapter for ServiceNow HR Service Delivery (HRSD) ticketing system."""

  def __init__(self, instance_url: str = "https://enterprise.service-now.com"):
    self.instance_url = instance_url
    self._cases: Dict[str, HRCase] = {}

  def create_case(
      self,
      employee_id: str,
      category: str,
      subcategory: str,
      summary: str,
      priority: CasePriority = CasePriority.MEDIUM,
      context_payload: Optional[Dict[str, Any]] = None,
  ) -> HRCase:
    """Create a new ServiceNow HRSD ticket."""
    case_id = f"HRC-{uuid.uuid4().hex[:8].upper()}"
    hr_case = HRCase(
        case_id=case_id,
        employee_id=employee_id,
        category=category,
        subcategory=subcategory,
        priority=priority,
        status=CaseStatus.OPEN,
        summary=summary,
        context_payload=context_payload or {},
    )
    self._cases[case_id] = hr_case
    logger.info(f"ServiceNow Case {case_id} created for {employee_id}")
    return hr_case

  def get_case(self, case_id: str) -> Optional[HRCase]:
    """Retrieve an existing HR case."""
    return self._cases.get(case_id)

  def update_status(self, case_id: str, status: CaseStatus) -> Optional[HRCase]:
    """Update lifecycle status of a ticket."""
    if case_id in self._cases:
      self._cases[case_id].status = status
      return self._cases[case_id]
    return None


class PubSubEventPublisher:
  """Asynchronous enterprise event dispatcher for Cloud Pub/Sub."""

  def __init__(self, project_id: str = "enterprise-hr-cloud"):
    self.project_id = project_id
    self.published_events: List[Dict[str, Any]] = []

  def publish_event(self, topic: str, payload: Dict[str, Any]) -> str:
    """Publish an event to a designated topic."""
    message_id = f"msg-{uuid.uuid4().hex[:12]}"
    event_record = {
        "message_id": message_id,
        "topic": topic,
        "payload": payload,
    }
    self.published_events.append(event_record)
    logger.info(f"Published to topic {topic}: {message_id}")
    return message_id
