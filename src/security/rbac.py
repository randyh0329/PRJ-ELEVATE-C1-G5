from typing import Set, Dict, Optional
from fastapi import HTTPException, status


class RBACManager:
    """
    Implements Enterprise Role-Based Access Control (RBAC) Matrix (SDD §4.2, FR-1.5).
    Effective permission = (role grant) ∩ (subject assertion scope) ∩ (agent tool allowlist).
    """
    ROLE_PERMISSIONS: Dict[str, Set[str]] = {
        "EMPLOYEE": {
            "ww.get_profile",
            "ww.update_contact",
            "ww.get_balances",
            "ww.submit_leave",
            "ww.cancel_leave",
            "si.get_incident",
            "si.create_incident",
            "si.post_comment",
            "agent_search.query",
        },
        "PEOPLE_PARTNER": {
            "ww.get_profile",
            "ww.get_balances",
            "si.get_incident",
            "si.post_comment",
            "agent_search.query",
            "agent_search.query_restricted",
        },
        "IT_SUPPORT": {
            "ww.get_profile",
            "si.get_incident",
            "si.create_incident",
            "si.post_comment",
            "si.update_status",
            "agent_search.query",
        },
        "COMPLIANCE_ADMIN": {
            "agent_search.query",
            "audit.read",
        }
    }

    @classmethod
    def check_permission(cls, role: str, tool_name: str, subject_id: str, target_id: Optional[str] = None):
        """
        Enforces that users can only access their own data or authorized information (FR-1.5).
        """
        allowed_tools = cls.ROLE_PERMISSIONS.get(role, set())
        if tool_name not in allowed_tools:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Role '{role}' is not authorized to execute '{tool_name}'."
            )

        # Standard employee self-only restriction
        if role == "EMPLOYEE" and target_id and target_id != subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Employees are strictly restricted to self-only data access (FR-1.5)."
            )


rbac_manager = RBACManager()
