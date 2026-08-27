"""Immutable audit logging and telemetry emitter."""
import datetime
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    """Structured audit record adhering to enterprise compliance standards."""
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    caller_employee_id: str
    origin: str = "HR_AGENT_ORCHESTRATOR_V1"
    action_type: str
    status: str  # SUCCESS, FAILED, COMPENSATED, REFUSED
    details: Dict[str, Any] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = None


class AuditLogger:
    """Manages audit logging for agent actions and system events."""

    def __init__(self) -> None:
        self._records: List[AuditRecord] = []
        self._logger = logging.getLogger("hr_agent_audit")
        self._logger.setLevel(logging.INFO)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('{"time":"%(asctime)s", "level":"%(levelname)s", "audit":%(message)s}')
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

    def log_event(
        self,
        caller_employee_id: str,
        action_type: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
        origin: str = "HR_AGENT_ORCHESTRATOR_V1",
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditRecord:
        """Create and store an audit record."""
        record = AuditRecord(
            caller_employee_id=caller_employee_id,
            origin=origin,
            action_type=action_type,
            status=status,
            details=details or {},
            metadata=metadata
        )
        self._records.append(record)
        self._logger.info(record.model_dump_json())
        return record

    def get_records(
        self,
        caller_employee_id: Optional[str] = None,
        action_type: Optional[str] = None
    ) -> List[AuditRecord]:
        """Retrieve filtered audit records."""
        results = self._records
        if caller_employee_id:
            results = [r for r in results if r.caller_employee_id == caller_employee_id]
        if action_type:
            results = [r for r in results if r.action_type == action_type]
        return results

    def clear(self) -> None:
        """Clear records (used primarily in test teardowns)."""
        self._records.clear()


# Global singleton audit logger
audit_logger = AuditLogger()
