from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings
from src.mocks.workweek_mock import router as workweek_router
from src.mocks.itsm_mock import router as itsm_router
from src.mocks.state_manager import state_manager

mock_app = FastAPI(
    title="WorkWeek & ServiceImmediately Mock Services",
    version="1.4.0",
    description="Deterministic mock microservices for HR Agentic Solution (MVP 1)"
)

mock_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mock_app.include_router(workweek_router)
mock_app.include_router(itsm_router)


@mock_app.get("/healthz", tags=["System"])
async def health_check():
    return {"status": "HEALTHY", "service": "mock-backends", "version": "1.4.0"}


@mock_app.post("/api/test/reset-state", tags=["Testing"])
async def reset_mock_state(
    x_test_authorization: str = Header(..., alias="X-Test-Authorization")
):
    """
    Automated State Reset Endpoint (SDD §7.6).
    Atomically wipes dynamic test state, restores initial vacation balances to 56h,
    and resets open tickets in < 200 ms.
    """
    if x_test_authorization != settings.test_auth_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid X-Test-Authorization secret"
        )
    result = state_manager.reset_state()
    return result
