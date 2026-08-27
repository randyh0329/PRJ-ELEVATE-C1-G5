import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, Header, HTTPException, status
from src.models.workweek import (
    EmployeeProfile,
    ContactUpdateRequest,
    ContactUpdateResponse,
    BalancesResponse,
    LeaveRequest,
    LeaveResponse,
    LeaveStatusEnum,
    Balance,
)
from src.mocks.state_manager import state_manager
from src.mocks.fidelity import fidelity_engine

router = APIRouter(prefix="/api/v1/employees/me", tags=["WorkWeek HCM Mock"])


def resolve_subject(request: Request, x_subject_assertion: Optional[str] = None) -> str:
    """Resolves employeeId from X-Subject-Assertion or authenticated header."""
    assertion = x_subject_assertion or request.headers.get("X-Subject-Assertion")
    if not assertion:
        # Check Authorization header
        auth = request.headers.get("Authorization")
        if auth and "EMP-" in auth:
            return auth.split()[-1]
        # In mock build default to baseline employee if not provided, or 401 if strict
        return "EMP-44210"
    
    # If JWT format, decode without verification in mock or parse sub
    if "." in assertion:
        try:
            import jwt
            payload = jwt.decode(assertion, options={"verify_signature": False})
            return payload.get("sub", "EMP-44210")
        except Exception:
            return "EMP-44210"
    return assertion


@router.get("/profile", response_model=EmployeeProfile, operation_id="ww.get_profile")
async def get_profile(
    request: Request,
    x_subject_assertion: Optional[str] = Header(None, alias="X-Subject-Assertion")
):
    await fidelity_engine.apply_fidelity(request, "ww.get_profile")
    employee_id = resolve_subject(request, x_subject_assertion)
    emp = state_manager.get_employee(employee_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    return EmployeeProfile(
        employeeId=emp["employeeId"],
        name=emp["name"],
        email=emp["email"],
        department=emp["department"],
        role=emp["role"],
        manager=emp["manager"],
        hireDate=emp["hireDate"],
        homeAddress=emp.get("homeAddress"),
        phoneNumber=emp.get("phoneNumber")
    )


@router.patch("/contact", response_model=ContactUpdateResponse, operation_id="ww.update_contact")
async def update_contact(
    payload: ContactUpdateRequest,
    request: Request,
    x_subject_assertion: Optional[str] = Header(None, alias="X-Subject-Assertion"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key")
):
    await fidelity_engine.apply_fidelity(request, "ww.update_contact")
    fidelity_engine.check_and_record_idempotency(x_idempotency_key)

    employee_id = resolve_subject(request, x_subject_assertion)
    result = state_manager.update_employee_contact(
        employee_id,
        address=payload.homeAddress,
        phone=payload.phoneNumber
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    resp = ContactUpdateResponse(**result)
    fidelity_engine.record_idempotency_result(x_idempotency_key, resp.model_dump())
    return resp


@router.get("/balances", response_model=BalancesResponse, operation_id="ww.get_balances")
async def get_balances(
    request: Request,
    x_subject_assertion: Optional[str] = Header(None, alias="X-Subject-Assertion")
):
    await fidelity_engine.apply_fidelity(request, "ww.get_balances")
    employee_id = resolve_subject(request, x_subject_assertion)
    emp = state_manager.get_employee(employee_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    balances = emp.get("balances", {})
    vacation = balances.get("vacation", {"accruedHours": 0.0, "usedHours": 0.0, "remainingHours": 0.0})
    sick = balances.get("sick", {"accruedHours": 0.0, "usedHours": 0.0, "remainingHours": 0.0})

    return BalancesResponse(
        vacation=Balance(**vacation),
        sick=Balance(**sick)
    )


@router.post("/leaves", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED, operation_id="ww.submit_leave")
async def submit_leave(
    payload: LeaveRequest,
    request: Request,
    x_subject_assertion: Optional[str] = Header(None, alias="X-Subject-Assertion"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key")
):
    await fidelity_engine.apply_fidelity(request, "ww.submit_leave")
    fidelity_engine.check_and_record_idempotency(x_idempotency_key)

    employee_id = resolve_subject(request, x_subject_assertion)
    emp = state_manager.get_employee(employee_id)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    # FR-3.3 Business Rules Validation: Temporal Validity
    try:
        start_dt = datetime.strptime(payload.startDate, "%Y-%m-%d").date()
        end_dt = datetime.strptime(payload.endDate, "%Y-%m-%d").date()
        today = datetime.now().date()
        if start_dt > end_dt:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "TEMPORAL_VIOLATION", "detail": "Start date must be before or equal to end date"}
            )
        if start_dt < today:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "TEMPORAL_VIOLATION", "detail": "Start date cannot be in the past"}
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "FORMAT_VIOLATION", "detail": "Invalid date format. Expected YYYY-MM-DD"}
        )

    # Balance check
    hours_requested = payload.workDays * 8.0
    if payload.leaveType.value != "Medical":
        cat = "vacation" if payload.leaveType.value == "Vacation" else "sick"
        remaining = emp.get("balances", {}).get(cat, {}).get("remainingHours", 0.0)
        if hours_requested > remaining:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "INSUFFICIENT_BALANCE",
                    "detail": f"Requested {hours_requested}h exceeds remaining balance of {remaining}h"
                }
            )
        state_manager.deduct_leave_balance(employee_id, payload.leaveType.value, hours_requested)

    leave_id = f"LV-{random_id()}"
    leave_status = LeaveStatusEnum.PENDING_APPROVAL

    state_manager.add_leave(employee_id, {
        "leaveId": leave_id,
        "startDate": payload.startDate,
        "endDate": payload.endDate,
        "leaveType": payload.leaveType.value,
        "workDays": payload.workDays,
        "reason": payload.reason,
        "status": leave_status.value
    })

    resp = LeaveResponse(leaveId=leave_id, status=leave_status)
    fidelity_engine.record_idempotency_result(x_idempotency_key, resp.model_dump())
    return resp


@router.delete("/leaves/{leave_id}", operation_id="ww.cancel_leave")
async def cancel_leave(
    leave_id: str,
    request: Request,
    x_subject_assertion: Optional[str] = Header(None, alias="X-Subject-Assertion")
):
    await fidelity_engine.apply_fidelity(request, "ww.cancel_leave")
    employee_id = resolve_subject(request, x_subject_assertion)
    success = state_manager.cancel_leave(employee_id, leave_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave not found or not owned by subject")
    return {"status": "CANCELLED", "leaveId": leave_id}


def random_id() -> str:
    return str(uuid.uuid4().int)[:4]
