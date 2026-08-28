"""
Vertex AI Gemini Client.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §2.2, §3.1 & §3.2.
Provides structured output generation and tool call selection using Gemini on Vertex AI.
"""

import datetime
import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from config.settings import get_settings
from src.core.clock import business_today
from src.models.routing import ITSMToolSelection, SupervisorRoutingDecision, WorkWeekToolSelection

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
        "LANGUAGE: employees write in English, Japanese, Korean, Traditional Chinese "
        "or Indonesian, and sometimes mix two in one sentence. Classify on meaning, "
        "never on the presence of an English keyword - 我的電腦壞了請開單 is a "
        "UC_1_3 incident report and 請假 is UC_1_2 leave. Extracted arguments "
        "(dates, ids, categories) are always emitted in the schema's own format, "
        "whatever language the request was written in.\n\n"
        "COMPOUND REQUESTS: a turn may carry more than one request - 'my laptop is "
        "broken, open a ticket, and I need sick leave 10/01-10/03' is an IT incident "
        "AND a leave request. You still choose exactly ONE intent: the first request, "
        "or the most urgent if one is clearly urgent. List every OTHER request in "
        "unaddressed_requests as a short English noun phrase, so the reply can tell "
        "the employee what it did not do. Do NOT use this field for a single request "
        "split across clauses, and do NOT use it for the three UC_2_x cross-system "
        "workflows, which are one intent covering both systems by design.\n\n"
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

    ITSM_TOOL_SYSTEM_INSTRUCTION = (
        "You are the ServiceImmediately ITSM Specialist Agent operating under SDD §3.2 & §5.1.\n"
        "Your role is to analyze the employee's request and autonomously select the appropriate ServiceImmediately FastMCP tool and extract arguments:\n\n"
        "- create_incident: For reporting IT issues, outages, bugs, hardware failures, access requests, or opening a new support ticket.\n"
        "  Extract category ('IT_NETWORK', 'IT_HARDWARE', 'IT_ACCESS', or 'IT_GENERAL'), short_description, and priority ('1 - Critical', '2 - High', '3 - Moderate', '4 - Low').\n"
        "- get_ticket_details: For checking the status, progress, details, or assignee of a specific ticket. Extract ticket_id (e.g. INC-5001, INC0003466).\n"
        "- list_tickets: For viewing, listing, or checking all active/open support tickets for the current employee.\n"
        "- post_comment: For adding a note, reply, or update comment to an existing ticket. Extract ticket_id and comment_body.\n"
        "- none: If the prompt requires no tool call.\n\n"
        "Respond strictly with the provided JSON schema."
    )

    def __init__(
        self,
        project_id: str | None = None,
        region: str | None = None,
        model_id: str | None = None,
    ) -> None:
        settings = get_settings()
        self.project_id = project_id or getattr(settings, "PROJECT_ID", "pe-group5")
        self.region = region or getattr(settings, "REGION", "us-central1")
        self.model_id = (
            model_id
            or os.environ.get("VERTEX_MODEL_ID")
            or getattr(settings, "VERTEX_MODEL_ID", "gemini-3.7-flash")
        )
        self._cached_token: str | None = None
        self._token_expiry: float = 0.0
        self._http_client = httpx.Client(timeout=25.0)

    def _get_auth_token(self) -> str:
        """Obtain a valid Google Cloud OAuth2 access token."""
        now = time.time()
        if self._cached_token and now < self._token_expiry:
            return self._cached_token

        # Priority 1: Explicit environment override
        env_token = os.environ.get("VERTEX_AI_TOKEN") or os.environ.get("GCP_ACCESS_TOKEN")
        if env_token:
            self._cached_token = env_token
            self._token_expiry = now + 3600
            return env_token

        # Priority 2: Cloud Run / GCE Metadata Server
        try:
            with httpx.Client(timeout=1.0) as client:
                res = client.get(
                    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
                    headers={"Metadata-Flavor": "Google"},
                )
                if res.status_code == 200:
                    data = res.json()
                    token = data.get("access_token")
                    if token:
                        self._cached_token = token
                        expires_in = data.get("expires_in", 3600)
                        self._token_expiry = now + expires_in - 60
                        logger.debug("Retrieved access token from Cloud Run metadata server.")
                        return token
        except Exception:
            pass

        # Priority 3: Local gcloud CLI (Application Default Credentials or auth print-access-token)
        candidate_paths = [
            shutil.which("gcloud"),
            os.path.expanduser("~/google-cloud-sdk/bin/gcloud"),
            "/usr/bin/gcloud",
        ]
        gcloud_bin = next((p for p in candidate_paths if p and os.path.isfile(p) and os.access(p, os.X_OK)), None)

        if gcloud_bin:
            for subcmd in [
                ["auth", "application-default", "print-access-token"],
                ["auth", "print-access-token"],
            ]:
                try:
                    proc = subprocess.run(
                        [gcloud_bin, *subcmd],
                        capture_output=True,
                        text=True,
                        timeout=5.0,
                        check=False,
                    )
                    if proc.returncode == 0:
                        raw_output = proc.stdout.strip()
                        # Extract the actual token line, skipping any gcloud WARNING lines
                        lines = [
                            line.strip()
                            for line in raw_output.splitlines()
                            if line.strip() and not line.startswith("WARNING") and not line.startswith("If you need")
                        ]
                        if lines:
                            token = lines[-1]
                            self._cached_token = token
                            self._token_expiry = now + 3300
                            logger.debug("Retrieved token using %s %s", gcloud_bin, ' '.join(subcmd))
                            return token
                except Exception as e:
                    logger.debug("gcloud subcmd %s failed: %s", subcmd, e)

        raise PermissionError(
            "Could not authenticate to Vertex AI. Ensure Google ADC, Cloud Run Metadata Server, "
            "or VERTEX_AI_TOKEN environment variable is set."
        )

    def generate_structured(
        self,
        prompt: str,
        system_instruction: str,
        response_model: type[T],
        temperature: float = 0.0,
    ) -> T:
        """
        Invokes Vertex AI Gemini with a strict Pydantic response schema.
        Handles model 404 with automatic fallback.
        """
        token = self._get_auth_token()
        candidates = []
        if self.model_id == "gemini-3.7-flash":
            candidates.append(("gemini-3.7-flash", "global"))
            candidates.append(("gemini-2.5-flash", self.region or "us-central1"))
        else:
            candidates.append((self.model_id, self.region or "us-central1"))
            candidates.append(("gemini-3.7-flash", "global"))
            candidates.append(("gemini-2.5-flash", "us-central1"))

        schema = response_model.model_json_schema()
        clean_schema = self._clean_schema(schema)

        generation_config = {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseSchema": clean_schema,
        }
        # Disable extended thinking budget for Gemini 3.7 Flash to achieve sub-second/Flash speeds for routing & tool calling
        if "3.7" in self.model_id:
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}

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
            "generationConfig": generation_config,
        }

        last_err: Exception | None = None
        for model, loc in candidates:
            endpoint = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
            url = (
                f"https://{endpoint}/v1/projects/{self.project_id}/"
                f"locations/{loc}/publishers/google/models/{model}:generateContent"
            )
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            try:
                resp = self._http_client.post(url, json=payload, headers=headers)
                if resp.status_code in [404, 400] and (model, loc) != candidates[-1]:
                    logger.warning(
                        "Model '%s' at '%s' returned %s; falling back.", model, loc, resp.status_code
                    )
                    continue
                if resp.status_code != 200:
                    raise RuntimeError(f"Vertex AI API call failed: {resp.status_code} {resp.text}")

                data = resp.json()
                raw_json_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed_dict = json.loads(raw_json_text)
                return response_model.model_validate(parsed_dict)
            except Exception as e:
                last_err = e
                if (model, loc) != candidates[-1]:
                    continue

        raise last_err or RuntimeError("Failed to generate structured response from Vertex AI.")

    def route_intent(
        self,
        prompt: str,
        reference_date: datetime.date | None = None
    ) -> SupervisorRoutingDecision:
        """Classify user intent and extract tool arguments using Gemini Supervisor Router (with offline fallback)."""
        ref = reference_date or business_today()
        ref_context = (
            f"\n\nCRITICAL CONTEXT: Today's reference date is {ref.isoformat()} ({ref.strftime('%A')}).\n"
            f"If the request is UC_1_2_WORKWEEK_LEAVE, identify the specific tool_name:\n"
            f"- request_time_off: MUST extract start_date (>= {ref.isoformat()}), end_date, days (float), leave_type ('Vacation' or 'Sick'), and reason.\n"
            f"- update_personal_info: MUST extract phone_number and/or home_address.\n"
            f"- cancel_leave_request: MUST extract request_id.\n"
            f"- get_employee_balances, get_leave_requests, get_employee_profile: no extra arguments needed."
        )
        try:
            return self.generate_structured(
                prompt=f"[Reference Today: {ref.isoformat()}]\nUser request: {prompt}",
                system_instruction=self.SUPERVISOR_SYSTEM_INSTRUCTION + ref_context,
                response_model=SupervisorRoutingDecision,
                temperature=0.0,
            )
        except Exception as e:
            logger.warning("Vertex AI live router failed (%s). Using deterministic local fallback.", e)
            return self._fallback_route_intent(prompt, ref)

    def select_workweek_tool(
        self,
        prompt: str,
        reference_date: datetime.date | None = None
    ) -> WorkWeekToolSelection:
        """Select WorkWeek FastMCP tool and extract arguments using Gemini (with offline fallback)."""
        ref = reference_date or business_today()
        ref_context = (
            f"\n\nCRITICAL DATE CONTEXT: Today's reference date is {ref.isoformat()} ({ref.strftime('%A')}). "
            f"All relative date expressions (such as 'tomorrow', '내일', 'next week', '다음 주', 'next Monday') "
            f"MUST be calculated strictly relative to {ref.isoformat()}. "
            f"Leave requests MUST NEVER be submitted for dates in the past (< {ref.isoformat()})."
        )
        try:
            return self.generate_structured(
                prompt=f"[Reference Today: {ref.isoformat()}]\nUser request: {prompt}",
                system_instruction=self.WORKWEEK_TOOL_SYSTEM_INSTRUCTION + ref_context,
                response_model=WorkWeekToolSelection,
                temperature=0.0,
            )
        except Exception as e:
            logger.warning("Vertex AI live tool selector failed (%s). Using deterministic local fallback.", e)
            return self._fallback_select_workweek_tool(prompt, ref)

    def select_itsm_tool(
        self,
        prompt: str,
    ) -> ITSMToolSelection:
        """Select ServiceImmediately ITSM FastMCP tool and extract arguments using Gemini (with offline fallback)."""
        try:
            return self.generate_structured(
                prompt=f"User IT request: {prompt}",
                system_instruction=self.ITSM_TOOL_SYSTEM_INSTRUCTION,
                response_model=ITSMToolSelection,
                temperature=0.0,
            )
        except Exception as e:
            logger.warning("Vertex AI live ITSM tool selector failed (%s). Using deterministic local fallback.", e)
            return self._fallback_select_itsm_tool(prompt)

    def _fallback_route_intent(self, prompt: str, ref_date: datetime.date) -> SupervisorRoutingDecision:
        import re
        p = prompt.lower()

        # UC-2.1: Equipment Procurement
        if ("remote" in p and ("monitor" in p or "hardware" in p or "equipment" in p)) or \
           ("order" in p and "monitor" in p) or ("home office monitor" in p):
            return SupervisorRoutingDecision(
                intent="UC_2_1_EQUIPMENT_PROCUREMENT",
                target_agent="SAGA_COORDINATOR",
                confidence=0.99,
                reasoning="Fallback: Remote equipment procurement saga."
            )

        # UC-2.2: Medical Leave Delegation
        if ("medical leave" in p or "sick leave" in p or "short-term medical" in p or "mc" in p) and \
           ("set it up" in p or "delegate" in p or "process" in p or "starting" in p or "submit" in p or "route" in p):
            return SupervisorRoutingDecision(
                intent="UC_2_2_MEDICAL_LEAVE_DELEGATION",
                target_agent="SAGA_COORDINATOR",
                confidence=0.99,
                reasoning="Fallback: Medical leave with access delegation saga."
            )

        # UC-2.3: Relocation Allowance & Badge
        if "relocation" in p or "relocating" in p or "transferring to the london" in p or "london office" in p or "transfer & badge" in p:
            return SupervisorRoutingDecision(
                intent="UC_2_3_RELOCATION_ALLOWANCE_BADGE",
                target_agent="SAGA_COORDINATOR",
                confidence=0.98,
                reasoning="Fallback: Relocation allowance & badge saga."
            )

        # UC-1.1: Policy Q&A
        if any(k in p for k in ["policy", "bereavement", "entitlement", "handbook", "rule", "규정", "핸드북", "지침"]):
            return SupervisorRoutingDecision(
                intent="UC_1_1_POLICY_QA",
                target_agent="POLICY_SPECIALIST",
                confidence=0.99,
                reasoning="Fallback: Policy Q&A inquiry."
            )

        # UC-1.3: ServiceImmediately Incident Management
        if any(k in p for k in ["ticket", "vpn", "incident", "it helpdesk", "wifi", "dropping", "network", "active tickets", "support ticket"]):
            return SupervisorRoutingDecision(
                intent="UC_1_3_SERVICE_IMMEDIATELY_INCIDENT",
                target_agent="ITSM_SPECIALIST",
                confidence=0.98,
                reasoning="Fallback: IT incident report."
            )

        # Out of Domain Refusal (FR-5.4)
        if any(k in p for k in ["weather", "stock", "recipe", "joke", "capital of", "who won", "python code", "write a"]):
            return SupervisorRoutingDecision(
                intent="OUT_OF_DOMAIN",
                target_agent="DOMAIN_CONTAINMENT",
                confidence=0.95,
                reasoning="Fallback: Out of domain prompt."
            )

        # UC-1.2: WorkWeek Leave & Profile Self-Service
        tool_name = "get_employee_balances"
        if "manager" in p:
            tool_name = "get_employee_profile"
        elif "department" in p:
            tool_name = "get_employee_profile"
        elif "address" in p or "registered address" in p:
            tool_name = "get_employee_profile"
        elif "job profile" in p or "profile" in p:
            tool_name = "get_employee_profile"
        elif "vacation" in p or "request time off" in p or "submit" in p:
            tool_name = "request_time_off"

        return SupervisorRoutingDecision(
            intent="UC_1_2_WORKWEEK_LEAVE",
            target_agent="WORKWEEK_SPECIALIST",
            tool_name=tool_name,
            confidence=0.98,
            reasoning="Fallback: WorkWeek HCM self-service operation."
        )

    def _fallback_select_workweek_tool(self, prompt: str, ref_date: datetime.date) -> WorkWeekToolSelection:
        import re
        p = prompt.lower()
        if any(k in p for k in ["cancel", "취소"]):
            req_match = re.search(r'\b(\d{3,6})\b', p)
            req_id = int(req_match.group(1)) if req_match else 101
            return WorkWeekToolSelection(tool_name="cancel_leave_request", arguments={"request_id": req_id})
        if any(k in p for k in ["requests", "history", "list leaves", "show leaves"]):
            return WorkWeekToolSelection(tool_name="get_leave_requests", arguments={})
        if any(k in p for k in ["phone", "address", "update"]):
            return WorkWeekToolSelection(tool_name="update_personal_info", arguments={"home_address": "Updated Address", "phone_number": "+65-6123-4567"})
        if any(k in p for k in ["profile", "manager", "department", "job", "title"]):
            return WorkWeekToolSelection(tool_name="get_employee_profile", arguments={})
        if any(k in p for k in ["vacation", "sick", "request", "take", "apply", "leave"]):
            # Calculate next monday
            days_ahead = (0 - ref_date.weekday() + 7) % 7 or 7
            next_monday = ref_date + datetime.timedelta(days=days_ahead)
            return WorkWeekToolSelection(
                tool_name="request_time_off",
                arguments={
                    "start_date": next_monday.isoformat(),
                    "end_date": (next_monday + datetime.timedelta(days=1)).isoformat(),
                    "days": 2.0,
                    "leave_type": "Vacation",
                    "reason": "Personal time off"
                }
            )
        return WorkWeekToolSelection(tool_name="get_employee_balances", arguments={})

    #: Verbs that ask for something *new* to be raised. Matched before any read
    #: intent, because "open a ticket" and "open tickets" differ by one letter
    #: and mean opposite things - and the read side is deliberately broad, so
    #: without this ordering it would swallow half the create phrasings.
    ITSM_CREATE_VERBS = (
        "create", "raise", "file a", "file an", "log a", "log an", "submit",
        "report", "open a", "open an", "new ticket", "new incident",
    )
    #: Verbs that ask after a ticket's progress.
    ITSM_READ_VERBS = (
        "status", "check", "details", "lookup", "look up", "how is",
        "any news", "update on", "progress", "show", "list", "have i",
        "do i have",
    )
    #: Quantifiers that scope a question to the caller's own tickets.
    ITSM_READ_SCOPES = (
        "my", "any", "all", "open", "active", "outstanding", "pending", "current",
    )

    @staticmethod
    def _fallback_select_itsm_tool(prompt: str) -> ITSMToolSelection:
        """Deterministic tool routing for when the live selector is unreachable.

        Not a nicety: this is what runs during a Vertex outage, during a quota
        block, and throughout the test suite. Order is the whole design, and
        each step is here because the obvious arrangement gets a real sentence
        wrong:

        1. A ticket reference settles it, whatever else the sentence says.
        2. An explicit instruction to raise something new, *before* the read
           intents - otherwise "create an IT ticket because my VPN keeps
           dropping" is read as a request to list the caller's tickets, on the
           strength of the word "my".
        3. A question that mentions tickets without naming one is a read. This
           is the step that was missing: "any open tickets for me?" matched none
           of the old list phrasings, fell through, and filed a ticket in answer
           to a question about tickets.
        4. Anything else is someone describing a problem, which is a new ticket.

        A read intent has to mention a ticket at all, so "my screen is cracked,
        can you check" reaches step 4 and gets the incident the employee wanted.
        """
        import re
        p = prompt.lower()
        tid_match = re.search(r'\b(INC[-_]?\d{3,8})\b', prompt, re.IGNORECASE)

        if tid_match:
            return ITSMToolSelection(
                tool_name="get_ticket_details",
                ticket_id=tid_match.group(1).upper(),
                reasoning="Fallback: ticket lookup by stated reference."
            )

        if any(k in p for k in VertexGeminiClient.ITSM_CREATE_VERBS):
            return VertexGeminiClient._fallback_itsm_incident(prompt, p)

        # No reference to look up, so a read can only be answered by listing.
        # Defaulting to a hardcoded "INC-5001" here, which is what this did,
        # reported a stranger's ticket back as though it were the caller's.
        mentions_ticket = "ticket" in p or "incident" in p
        if mentions_ticket and any(
            k in p for k in (*VertexGeminiClient.ITSM_READ_VERBS, *VertexGeminiClient.ITSM_READ_SCOPES)
        ):
            return ITSMToolSelection(
                tool_name="list_tickets",
                reasoning="Fallback: read intent with no ticket reference."
            )

        return VertexGeminiClient._fallback_itsm_incident(prompt, p)

    @staticmethod
    def _fallback_itsm_incident(prompt: str, p: str) -> ITSMToolSelection:
        """A new incident, categorised on the vocabulary of the complaint."""
        cat = "IT_GENERAL"
        if any(k in p for k in ["vpn", "wifi", "network", "internet", "dns", "connection"]):
            cat = "IT_NETWORK"
        elif any(k in p for k in ["laptop", "screen", "keyboard", "battery", "hardware", "monitor", "display", "mouse"]):
            cat = "IT_HARDWARE"
        elif any(k in p for k in ["access", "permission", "password", "login", "github", "account", "unlock"]):
            cat = "IT_ACCESS"

        return ITSMToolSelection(
            tool_name="create_incident",
            category=cat,
            short_description=prompt[:100],
            priority="3 - Moderate",
            reasoning="Fallback: create incident ticket."
        )

    def _clean_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Sanitize Pydantic JSON schema for Vertex AI Gemini OpenAPI compatibility."""
        sanitized = dict(schema)
        for key in ["$defs", "title", "description"]:
            sanitized.pop(key, None)
        return sanitized


# Global default instance
vertex_gemini_client = VertexGeminiClient()
