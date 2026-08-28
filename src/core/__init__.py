"""Core agent orchestration and safety components."""
from typing import Any


def __getattr__(name: str) -> Any:
    if name == "HREnterpriseAgent":
        from src.core.agent import HREnterpriseAgent
        return HREnterpriseAgent
    if name in ("DLPRedactor", "ModelArmor", "dlp_redactor", "model_armor"):
        from src.core import safety
        return getattr(safety, name)
    if name in ("SagaCoordinator", "SagaResult", "SagaStep"):
        from src.core import saga
        return getattr(saga, name)
    if name in ("SessionMemory", "session_store"):
        from src.core import session
        return getattr(session, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DLPRedactor",
    "HREnterpriseAgent",
    "ModelArmor",
    "SagaCoordinator",
    "SagaResult",
    "SagaStep",
    "SessionMemory",
    "dlp_redactor",
    "model_armor",
    "session_store",
]
