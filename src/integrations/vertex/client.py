"""
Vertex AI Gemini 3.7 Flash Client.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §2.2, §3.1 & §3.2.
Provides structured output generation and tool call selection using Gemini 3.7 Flash.
"""

import json
import logging
import os
import subprocess
import time
from typing import Any, Dict, Optional, Type, TypeVar
import httpx
from pydantic import BaseModel

from config.settings import get_settings
from src.core.models.routing import SupervisorRoutingDecision, WorkWeekToolSelection

logger = logging.getLogger("integrations.vertex")

T = TypeVar("T", bound=BaseModel)


class VertexGeminiClient:
    """
    Client for Google Cloud Vertex AI Gemini models.
    Supports structured JSON generation via response_schema and function calling declarations.
    """

    SUPERVISOR_SYSTEM_INSTRUCTION = (
        "You are the Chief Concierge & Supervisor Intent Router for an Enterprise HR/IT Agentic System, "
        "operating strictly under SDD §3.1 & §3.2.\n"
        "Your sole role is DELEGATION ONLY. You classify the employee prompt and route it to the authorized specialist:\n\n"
        "1. UC_1_1_POLICY_QA (target: POLICY_SPECIALIST):\n"
        "   - Inquiries about corporate handbook, leave policies, bereavement, parental leave rules, entitlement guidelines.\n"
        "2. UC_1_2_WORKWEEK_LEAVE (target: WORKWEEK_SPECIALIST):\n"
        "   - WorkWeek HCM self-service operations: checking leave balances (vacation/sick/PTO), submitting leave requests, "
        "canceling leave, viewing leave history/requests, checking personal profile, job title, manager, department, phone, address.\n"
        "3. UC_1_3_SERVICE_IMMEDIATELY_INCIDENT (target: ITSM_SPECIALIST):\n"
        "   - IT service desk incidents: viewing open IT tickets, reporting hardware/laptop issues, VPN failures, WiFi/network drops.\n"
        "4. UC_2_1_EQUIPMENT_PROCUREMENT (target: SAGA_COORDINATOR):\n"
        "   - Cross-system equipment order: checking WorkWeek remote work status AND ordering monitors/hardware via ITSM.\n"
        "5. UC_2_2_MEDICAL_LEAVE_DELEGATION (target: SAGA_COORDINATOR):\n"
        "   - Cross-system medical leave: booking sick/medical leave in WorkWeek AND delegating system access in ITSM.\n"
        "6. UC_2_3_RELOCATION_ALLOWANCE_BADGE (target: SAGA_COORDINATOR):\n"
        "   - Cross-system relocation: updating office location in WorkWeek AND requesting facilities building badge in ITSM.\n"
        "7. OUT_OF_DOMAIN (target: DOMAIN_CONTAINMENT):\n"
        "   - Requests outside HR/IT scope: weather, personal advice, stock market, recipes, jokes, general knowledge.\n\n"
        "Respond strictly with the provided JSON schema."
    )

    WORKWEEK_TOOL_SYSTEM_INSTRUCTION = (
        "You are the WorkWeek HCM Specialist Agent operating under SDD §3.2 & §5.1.\n"
        "Your role is to analyze the employee's request and select the appropriate WorkWeek FastMCP tool and extract arguments:\n\n"
        "- get_employee_balances: For checking remaining/accrued vacation, sick leave, PTO balance.\n"
        "- get_leave_requests: For viewing leave history, submitted requests, or upcoming time-off.\n"
        "- request_time_off: For submitting a vacation or sick leave request. Extract start_date (YYYY-MM-DD), "
        "end_date (YYYY-MM-DD), days (number), leave_type ('Vacation' or 'Sick'), and reason.\n"
        "- cancel_leave_request: For canceling an existing leave request. Extract request_id (string/integer).\n"
        "- update_personal_info: For updating employee contact info. Extract home_address and/or phone_number.\n"
        "- get_employee_profile: For retrieving profile details like job title, manager, department, or full profile.\n"
        "- none: If the prompt is purely conversational and requires no tool call.\n\n"
        "Respond strictly with the provided JSON schema."
    )

    def __init__(
        self,
        project_id: Optional[str] = None,
        region: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self.project_id = project_id or getattr(settings, "PROJECT_ID", "pe-group5")
        self.region = region or getattr(settings, "REGION", "us-central1")
        self.model_id = model_id or "gemini-3.7-flash"
        self._cached_token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _get_auth_token(self) -> str:
        """Obtain a valid Google Cloud OAuth2 access token."""
        now = time.time()
        if self._cached_token and now < self._token_expiry:
            return self._cached_token

        # Priority 1: Environment override
        env_token = os.environ.get("VERTEX_AI_TOKEN") or os.environ.get("GCP_ACCESS_TOKEN")
        if env_token:
            self._cached_token = env_token
            self._token_expiry = now + 3600
            return env_token

        # Priority 2: Cloud Run / GCE Metadata Server
        try:
            with httpx.Client(timeout=1.5) as client:
                res = client.get(
                    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
                    headers={"Metadata-Flavor": "Google"},
                )
                if res.status_code == 200:
                    data = res.json()
                    self._cached_token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                    self._token_expiry = now + expires_in - 60
                    logger.debug("Successfully retrieved access token from Cloud Run metadata server.")
                    return self._cached_token
        except Exception:
            pass

        # Priority 3: Local gcloud CLI
        try:
            proc = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                capture_output=True,
                text=True,
                timeout=4.0,
                check=False,
            )
            if proc.returncode == 0:
                token = proc.stdout.strip()
                if token:
                    self._cached_token = token
                    self._token_expiry = now + 3300
                    return token
        except Exception:
            pass

        raise PermissionError(
            "Could not authenticate to Vertex AI. Ensure Google ADC, Cloud Run Metadata Server, "
            "or VERTEX_AI_TOKEN environment variable is set."
        )

    def generate_structured(
        self,
        prompt: str,
        system_instruction: str,
        response_model: Type[T],
        temperature: float = 0.0,
    ) -> T:
        """
        Invokes Vertex AI Gemini 3.7 Flash with a strict Pydantic response schema.
        """
        token = self._get_auth_token()
        url = (
            f"https://{self.region}-aiplatform.googleapis.com/v1/projects/{self.project_id}/"
            f"locations/{self.region}/publishers/google/models/{self.model_id}:generateContent"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        schema = response_model.model_json_schema()
        # Clean $defs / titles for Gemini OpenAPI schema compatibility
        clean_schema = self._clean_schema(schema)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "systemInstruction": {
                "role": "system",
                "parts": [{"text": system_instruction}],
            },
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseSchema": clean_schema,
            },
        }

        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.error(f"Vertex AI request failed ({resp.status_code}): {resp.text}")
                raise RuntimeError(f"Vertex AI API call failed: {resp.status_code} {resp.text}")

            data = resp.json()
            try:
                raw_json_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed_dict = json.loads(raw_json_text)
                return response_model.model_validate(parsed_dict)
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                logger.error(f"Failed to parse Gemini structured output: {data}. Error: {e}")
                raise ValueError(f"Invalid structured output from Gemini: {e}")

    def route_intent(self, prompt: str) -> SupervisorRoutingDecision:
        """Classify user intent using Gemini 3.7 Flash Supervisor Router."""
        return self.generate_structured(
            prompt=prompt,
            system_instruction=self.SUPERVISOR_SYSTEM_INSTRUCTION,
            response_model=SupervisorRoutingDecision,
            temperature=0.0,
        )

    def select_workweek_tool(self, prompt: str) -> WorkWeekToolSelection:
        """Select WorkWeek FastMCP tool and extract arguments using Gemini 3.7 Flash."""
        return self.generate_structured(
            prompt=prompt,
            system_instruction=self.WORKWEEK_TOOL_SYSTEM_INSTRUCTION,
            response_model=WorkWeekToolSelection,
            temperature=0.0,
        )

    def _clean_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize Pydantic JSON schema for Vertex AI Gemini OpenAPI compatibility."""
        sanitized = dict(schema)
        # Remove unsupported top-level OpenAPI keys if present
        for key in ["$defs", "title", "description"]:
            sanitized.pop(key, None)
        return sanitized


# Global default instance
vertex_gemini_client = VertexGeminiClient()
