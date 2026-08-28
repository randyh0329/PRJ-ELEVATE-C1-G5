"""In-memory mock microservice simulating WorkWeek HCM API."""
import datetime
import uuid

from src.integrations.workweek.models import (
    ContactUpdateResponse,
    EmployeeProfile,
    LeaveBalances,
    LeaveRequest,
    LeaveSubmissionResponse,
)


class WorkWeekMockService:
    """Simulates WorkWeek HCM REST backend with deterministic state and error injection."""

    def __init__(self) -> None:
        self._profiles: dict[str, EmployeeProfile] = {}
        self._balances: dict[str, LeaveBalances] = {}
        self._leave_requests: dict[str, LeaveRequest] = {}
        self.init_mock_data()

    def init_mock_data(self) -> None:
        """Initialize mock database with baseline test records."""
        self._profiles = {
            "EMP-1001": EmployeeProfile(
                employee_id="EMP-1001",
                full_name="Jane Doe",
                email="jane.doe@enterprise.corp",
                phone_number="+1-512-555-0199",
                home_address="123 Tech Park Way, Austin, TX",
                work_location_status="REMOTE_FULL_TIME",
                current_office="Austin Campus",
                country="USA",
                job_title="Senior AI Software Engineer",
                manager_id="MGR-2001",
                is_active=True
            ),
            "EMP-1002": EmployeeProfile(
                employee_id="EMP-1002",
                full_name="John Smith",
                email="john.smith@enterprise.corp",
                phone_number="+1-212-555-0144",
                home_address="450 Lexington Ave, New York, NY",
                work_location_status="HYBRID",
                current_office="New York HQ",
                country="USA",
                job_title="Product Manager",
                manager_id="MGR-2002",
                is_active=True
            ),
        }

        self._balances = {
            "EMP-1001": LeaveBalances(
                employee_id="EMP-1001",
                vacation_accrued=18.0,
                vacation_used=4.0,
                vacation_remaining=14.0,
                sick_accrued=14.0,
                sick_used=2.0,
                sick_remaining=12.0
            ),
            "EMP-1002": LeaveBalances(
                employee_id="EMP-1002",
                vacation_accrued=25.0,
                vacation_used=5.0,
                vacation_remaining=20.0,
                sick_accrued=14.0,
                sick_used=0.0,
                sick_remaining=14.0
            ),
        }


        self._leave_requests.clear()

    def get_profile(self, employee_id: str) -> EmployeeProfile | None:
        """Fetch employee profile."""
        return self._profiles.get(employee_id)

    def get_balances(self, employee_id: str) -> LeaveBalances | None:
        """Fetch real-time leave balances directly from backend."""
        return self._balances.get(employee_id)

    def update_contact(
        self,
        employee_id: str,
        home_address: str | None = None,
        phone_number: str | None = None,
        current_office: str | None = None,
        country: str | None = None
    ) -> ContactUpdateResponse:
        """Update employee contact or office assignment."""
        profile = self._profiles.get(employee_id)
        if not profile:
            return ContactUpdateResponse(
                success=False,
                employee_id=employee_id,
                message=f"Employee {employee_id} not found.",
                updated_fields={}
            )

        updated: dict[str, str] = {}
        if home_address:
            profile.home_address = home_address
            updated["home_address"] = home_address
        if phone_number:
            profile.phone_number = phone_number
            updated["phone_number"] = phone_number
        if current_office:
            profile.current_office = current_office
            updated["current_office"] = current_office
        if country:
            profile.country = country
            updated["country"] = country

        return ContactUpdateResponse(
            success=True,
            employee_id=employee_id,
            message="Contact details updated successfully in WorkWeek.",
            updated_fields=updated
        )

    def submit_leave(
        self,
        employee_id: str,
        leave_type: str,
        start_date: str,
        end_date: str,
        days: float,
        origin: str = "HR_AGENT_ORCHESTRATOR_V1"
    ) -> LeaveSubmissionResponse:
        """Submit a leave request and deduct balance."""
        balance = self._balances.get(employee_id)
        if not balance:
            return LeaveSubmissionResponse(
                success=False,
                message=f"No leave record found for employee {employee_id}."
            )

        is_vacation = "vacation" in leave_type.lower()
        if is_vacation:
            if balance.vacation_remaining < days:
                return LeaveSubmissionResponse(
                    success=False,
                    message=f"Insufficient vacation balance. Requested: {days}, Available: {balance.vacation_remaining}"
                )
            balance.vacation_used += days
            balance.vacation_remaining -= days
            remaining = balance.vacation_remaining
        else:
            if balance.sick_remaining < days:
                return LeaveSubmissionResponse(
                    success=False,
                    message=f"Insufficient sick leave balance. Requested: {days}, Available: {balance.sick_remaining}"
                )
            balance.sick_used += days
            balance.sick_remaining -= days
            remaining = balance.sick_remaining

        req_id = f"WW-LV-{uuid.uuid4().hex[:6].upper()}"
        record = LeaveRequest(
            request_id=req_id,
            employee_id=employee_id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            days=days,
            status="SUBMITTED",
            submitted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            origin=origin
        )
        self._leave_requests[req_id] = record

        return LeaveSubmissionResponse(
            success=True,
            request_id=req_id,
            message=f"Leave request {req_id} submitted successfully.",
            remaining_balance=remaining
        )

    def cancel_leave(self, request_id: str) -> bool:
        """Cancel leave request and restore leave balance (Saga compensation)."""
        record = self._leave_requests.get(request_id)
        if not record:
            # Fuzzy match by prefix or substring
            for k, v in self._leave_requests.items():
                if k.lower() == str(request_id).lower() or k.endswith(str(request_id)) or str(request_id) in k:
                    record = v
                    break

        if not record or record.status == "CANCELLED":
            return False

        balance = self._balances.get(record.employee_id)
        if balance:
            if "vacation" in record.leave_type.lower():
                balance.vacation_used -= record.days
                balance.vacation_remaining += record.days
            else:
                balance.sick_used -= record.days
                balance.sick_remaining += record.days

        record.status = "CANCELLED"
        return True

    def get_leave_request(self, request_id: str) -> LeaveRequest | None:
        """Fetch leave request by ID."""
        return self._leave_requests.get(request_id)


# Global singleton mock service
workweek_mock_service = WorkWeekMockService()
