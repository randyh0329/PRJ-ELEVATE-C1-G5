import json
import logging
from typing import Dict, Any, List


class TelemetryLogger:
    def __init__(self):
        self.logger = logging.getLogger("elevate.telemetry")
        self.events: List[Dict[str, Any]] = []

    def log_event(self, event_data: Dict[str, Any]):
        self.events.append(event_data)
        try:
            # Emit as structured single-line JSON log (SDD §7.5)
            line = json.dumps(event_data)
            self.logger.info(line)
        except Exception as e:
            self.logger.error(f"Failed to log structured event: {e}")

    def get_events(self, event_type: str = None) -> List[Dict[str, Any]]:
        if event_type:
            return [e for e in self.events if e.get("event_type") == event_type]
        return self.events

    def clear(self):
        self.events.clear()


telemetry_logger = TelemetryLogger()
