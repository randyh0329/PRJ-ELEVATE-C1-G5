"""HR Enterprise Design Agents Package."""

from .enterprise_agents import (
    HRSupervisorAgent,
    LifecycleOperationsAgent,
    ManagerApprovalAgent,
    PolicyBenefitsAgent,
)
from .orchestrator import HREnterpriseOrchestrator
from .schemas import (
    AgentResponse,
    ApprovalRequest,
    EmployeeProfile,
    HRCase,
    PolicyCitation,
)

__all__ = [
    "HRSupervisorAgent",
    "PolicyBenefitsAgent",
    "LifecycleOperationsAgent",
    "ManagerApprovalAgent",
    "HREnterpriseOrchestrator",
    "AgentResponse",
    "ApprovalRequest",
    "EmployeeProfile",
    "HRCase",
    "PolicyCitation",
]
