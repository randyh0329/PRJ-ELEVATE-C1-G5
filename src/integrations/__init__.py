"""Integration connectors and mock backend services package."""
from typing import Any


def __getattr__(name: str) -> Any:
    if name == "ServiceImmediatelyClient":
        from src.integrations.service_immediately.client import ServiceImmediatelyClient
        return ServiceImmediatelyClient
    if name == "WorkWeekClient":
        from src.integrations.workweek.client import WorkWeekClient
        return WorkWeekClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ServiceImmediatelyClient", "WorkWeekClient"]
