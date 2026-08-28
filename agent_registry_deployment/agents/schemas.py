"""Pydantic v2 data schemas and contracts for HR Enterprise Design (HRED)."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class UserRole(str, Enum):
  """User persona and authorization role."""
  EMPLOYEE = "EMPLOYEE"
  MANAGER = "MANAGER"
  HRBP = "HRBP"
  HR_ADMIN = "HR_ADMIN"
  AUDITOR = "AUDITOR"


class Jurisdiction(str, Enum):
  """Jurisdictions supported by the enterprise policy engine."""
  GLOBAL = "GLOBAL"
  SINGAPORE = "SG"
  US_CALIFORNIA = "US-CA"
  US_NEWYORK = "US-NY"
  UNITED_KINGDOM = "UK"
  JAPAN = "JP"


class CasePriority(str, Enum):
  """Priority levels for HR cases."""
  LOW = "LOW"
  MEDIUM = "MEDIUM"
  HIGH = "HIGH"
  CRITICAL = "CRITICAL"


class CaseStatus(str, Enum):
  """Lifecycle status of an HR case."""
  OPEN = "OPEN"
  IN_PROGRESS = "IN_PROGRESS"
  PENDING_APPROVAL = "PENDING_APPROVAL"
  RESOLVED = "RESOLVED"
  CLOSED = "CLOSED"


class ApprovalStatus(str, Enum):
  """Status of human-in-the-loop approval requests."""
  PENDING = "PENDING"
  APPROVED = "APPROVED"
  REJECTED = "REJECTED"
  ESCALATED = "ESCALATED"


class EmployeeProfile(BaseModel):
  """Canonical employee profile record."""
  employee_id: str = Field(..., description="Unique employee identifier")
  email: str = Field(..., description="Corporate email address")
  full_name: str = Field(..., description="Employee full name")
  department: str = Field(..., description="Organizational department")
  jurisdiction: Jurisdiction = Field(default=Jurisdiction.GLOBAL)
  manager_id: Optional[str] = Field(default=None)
  role: UserRole = Field(default=UserRole.EMPLOYEE)
  is_active: bool = Field(default=True)
  created_at: datetime = Field(default_factory=datetime.utcnow)


class PolicyCitation(BaseModel):
  """Audit citation pointing to specific policy clauses."""
  policy_id: str = Field(..., description="Unique policy identifier")
  section: str = Field(..., description="Specific section or clause")
  title: str = Field(..., description="Policy title")
  source_file: str = Field(..., description="Markdown or document path")
  confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)


class HRCase(BaseModel):
  """Canonical HR ticket entity federated with ServiceNow/Workday."""
  case_id: str = Field(..., description="Unique case identifier")
  employee_id: str = Field(..., description="Requester employee ID")
  category: str = Field(..., description="Primary case category")
  subcategory: str = Field(..., description="Granular subcategory")
  priority: CasePriority = Field(default=CasePriority.MEDIUM)
  status: CaseStatus = Field(default=CaseStatus.OPEN)
  assigned_agent: str = Field(default="SupervisorAgent")
  summary: str = Field(..., description="Short summary of the case")
  details: Optional[str] = Field(default=None)
  context_payload: Dict[str, Any] = Field(default_factory=dict)
  citations: List[PolicyCitation] = Field(default_factory=list)
  created_at: datetime = Field(default_factory=datetime.utcnow)
  updated_at: datetime = Field(default_factory=datetime.utcnow)
  resolved_at: Optional[datetime] = Field(default=None)


class ApprovalRequest(BaseModel):
  """Human-in-the-loop approval gate request."""
  request_id: str = Field(..., description="Unique approval identifier")
  case_id: str = Field(..., description="Associated HR case ID")
  requester_id: str = Field(..., description="Employee requesting approval")
  approver_id: str = Field(..., description="Target manager or HRBP ID")
  approval_type: str = Field(..., description="Approval tier (e.g. MANAGER_L1, HRBP_L2)")
  status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
  action_summary: str = Field(..., description="Summary of action to be approved")
  decision_notes: Optional[str] = Field(default=None)
  decision_timestamp: Optional[datetime] = Field(default=None)
  created_at: datetime = Field(default_factory=datetime.utcnow)


class AuditLogEntry(BaseModel):
  """Immutable audit record for regulatory compliance."""
  audit_id: str = Field(..., description="Unique audit event ID")
  entity_type: str = Field(..., description="Entity category (CASE, APPROVAL, QUERY)")
  entity_id: str = Field(..., description="Target entity ID")
  actor_id: str = Field(..., description="Actor performing the operation")
  action: str = Field(..., description="Action name (CREATE, UPDATE, APPROVE, QUERY)")
  details: Dict[str, Any] = Field(default_factory=dict)
  policy_citation: Optional[str] = Field(default=None)
  timestamp: datetime = Field(default_factory=datetime.utcnow)


# API Request / Response DTOs
class UserQueryRequest(BaseModel):
  """Inbound user conversational or service desk query."""
  employee_id: str = Field(..., description="Employee ID making the query")
  query: str = Field(..., description="Natural language question or request")
  session_id: Optional[str] = Field(default=None)
  channel: str = Field(default="PORTAL", description="Channel: PORTAL, CHAT, EMAIL")


class CaseCreateRequest(BaseModel):
  """Explicit case creation request."""
  employee_id: str = Field(...)
  category: str = Field(...)
  subcategory: str = Field(...)
  priority: CasePriority = Field(default=CasePriority.MEDIUM)
  summary: str = Field(...)
  details: Optional[str] = Field(default=None)
  context_payload: Dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionRequest(BaseModel):
  """Manager or HRBP approval decision submission."""
  request_id: str = Field(...)
  approver_id: str = Field(...)
  decision: ApprovalStatus = Field(..., description="APPROVED or REJECTED")
  notes: Optional[str] = Field(default=None)


class AgentResponse(BaseModel):
  """Standardized response from the multi-agent mesh."""
  session_id: str
  handling_agent: str
  response_text: str
  citations: List[PolicyCitation] = Field(default_factory=list)
  case_id: Optional[str] = Field(default=None)
  requires_approval: bool = Field(default=False)
  approval_request_id: Optional[str] = Field(default=None)
  timestamp: datetime = Field(default_factory=datetime.utcnow)
