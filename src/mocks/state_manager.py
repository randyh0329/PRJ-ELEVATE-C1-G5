import copy
import json
import time
from typing import Dict, Any, Optional
from src.config import settings
from src.mocks.fidelity import fidelity_engine


class MockStateManager:
    def __init__(self):
        self.initial_workweek: Dict[str, Any] = {}
        self.initial_itsm: Dict[str, Any] = {}
        self.workweek_state: Dict[str, Any] = {}
        self.itsm_state: Dict[str, Any] = {}
        self.recent_creations: Dict[str, float] = {}
        self.load_seeds()

    def load_seeds(self):
        ww_file = settings.fixtures_dir / "workweek-seed-v3.json"
        itsm_file = settings.fixtures_dir / "serviceimmediately-seed-v3.json"

        if ww_file.exists():
            with open(ww_file, "r") as f:
                self.initial_workweek = json.load(f)
        else:
            self.initial_workweek = {"employees": {}}

        if itsm_file.exists():
            with open(itsm_file, "r") as f:
                self.initial_itsm = json.load(f)
        else:
            self.initial_itsm = {"incidents": {}}

        self.reset_state()

    def reset_state(self) -> Dict[str, Any]:
        """Atomically restores fixtures in < 200 ms and wipes dynamic state."""
        start_time = time.time()
        self.workweek_state = copy.deepcopy(self.initial_workweek)
        self.itsm_state = copy.deepcopy(self.initial_itsm)
        self.recent_creations.clear()
        fidelity_engine.clear()

        elapsed_ms = (time.time() - start_time) * 1000.0
        return {
            "status": "RESET_COMPLETE",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_ms": round(elapsed_ms, 2),
            "stats": {
                "employees_count": len(self.workweek_state.get("employees", {})),
                "incidents_count": len(self.itsm_state.get("incidents", {}))
            }
        }

    # WorkWeek State Accessors
    def get_employee(self, employee_id: str) -> Optional[Dict[str, Any]]:
        return self.workweek_state.get("employees", {}).get(employee_id)

    def update_employee_contact(self, employee_id: str, address: Optional[str], phone: Optional[str]) -> Optional[Dict[str, Any]]:
        emp = self.get_employee(employee_id)
        if not emp:
            return None
        updated_fields = []
        prev_addr = emp.get("homeAddress")
        prev_phone = emp.get("phoneNumber")

        if address is not None:
            emp["homeAddress"] = address
            updated_fields.append("homeAddress")
        if phone is not None:
            emp["phoneNumber"] = phone
            updated_fields.append("phoneNumber")

        return {
            "updated": updated_fields,
            "previousAddress": prev_addr,
            "previousPhone": prev_phone
        }

    def deduct_leave_balance(self, employee_id: str, leave_type: str, hours: float) -> bool:
        emp = self.get_employee(employee_id)
        if not emp:
            return False
        cat = "vacation" if leave_type.lower() == "vacation" else "sick"
        balance = emp.get("balances", {}).get(cat)
        if not balance:
            return False
        if balance["remainingHours"] < hours:
            return False
        balance["remainingHours"] -= hours
        balance["usedHours"] += hours
        return True

    def restore_leave_balance(self, employee_id: str, leave_type: str, hours: float):
        emp = self.get_employee(employee_id)
        if not emp:
            return
        cat = "vacation" if leave_type.lower() == "vacation" else "sick"
        balance = emp.get("balances", {}).get(cat)
        if balance:
            balance["remainingHours"] += hours
            balance["usedHours"] = max(0.0, balance["usedHours"] - hours)

    def add_leave(self, employee_id: str, leave_record: Dict[str, Any]):
        emp = self.get_employee(employee_id)
        if emp:
            if "leaves" not in emp:
                emp["leaves"] = []
            emp["leaves"].append(leave_record)

    def cancel_leave(self, employee_id: str, leave_id: str) -> bool:
        emp = self.get_employee(employee_id)
        if not emp or "leaves" not in emp:
            return False
        for leave in emp["leaves"]:
            if leave.get("leaveId") == leave_id:
                leave["status"] = "CANCELLED"
                # restore balance
                leave_type = leave.get("leaveType", "Vacation")
                hours = leave.get("workDays", 1.0) * 8.0
                self.restore_leave_balance(employee_id, leave_type, hours)
                return True
        return False

    # ITSM State Accessors
    def get_incident(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        return self.itsm_state.get("incidents", {}).get(ticket_id)

    def create_incident(self, incident: Dict[str, Any]):
        ticket_id = incident["ticketId"]
        self.itsm_state.setdefault("incidents", {})[ticket_id] = incident

    def add_incident_comment(self, ticket_id: str, comment: Dict[str, Any]) -> bool:
        inc = self.get_incident(ticket_id)
        if not inc:
            return False
        inc.setdefault("comments", []).append(comment)
        inc["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return True

    def update_incident_status(self, ticket_id: str, state: str, notes: Optional[str] = None) -> bool:
        inc = self.get_incident(ticket_id)
        if not inc:
            return False
        inc["state"] = state
        if notes:
            inc.setdefault("comments", []).append({
                "author": "System Agent (Status Update)",
                "body": f"State transitioned to {state}. Resolution notes: {notes}",
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        inc["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return True


state_manager = MockStateManager()
