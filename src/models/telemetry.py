from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class LLMExecutionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = "llm_execution_event"
    trace_id: str
    span_id: str
    session_id: str
    turn_seq: int
    employee_id_hash: str
    agent_node: str
    model_id: str
    model_version_pinned: str
    invocation_purpose: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    ttft_ms: int
    total_latency_ms: int
    finish_reason: str = "STOP"
    safety_overhead_ms: int
    dlp_template_digest: str
    guardrail_verdict_in: str
    guardrail_verdict_out: str
    groundedness_score: float
    estimated_cost_usd: float


class AgentNodeLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = "agent_node_lifecycle"
    trace_id: str
    session_id: str
    turn_seq: int
    node_name: str
    transition: str
    target_node: Optional[str] = None
    routing_confidence: float
    routing_rationale_class: str
    authorized_tools_at_node: List[str]
    saga_id: Optional[str] = None
    state_size_bytes: int
    node_latency_ms: int
    outcome: str


class ToolExecutionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = "tool_execution_event"
    trace_id: str
    session_id: str
    turn_seq: int
    tool_name: str
    operation_id: str
    backend: str
    http_method: str
    http_status: int
    actor_type: str = "AUTOMATED_AGENT"
    acting_employee_id_hash: str
    subject_assertion_jti: str
    idempotency_key: str
    saga_id: Optional[str] = None
    saga_step_index: Optional[int] = None
    compensation_class: Optional[str] = None
    adaptive_limit_at_dispatch: int
    queue_wait_ms: int = 0
    backend_latency_ms: int
    retry_attempt: int = 0
    validation_rules_applied: List[str]
    outcome: str


class PriorStepRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int
    system: str
    ref: str
    compensation_class: str
    action_taken: str


class SagaCompensationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = "saga_compensation_event"
    trace_id: str
    saga_id: str
    session_id: str
    employee_id_hash: str
    trigger: str
    failed_step_index: int
    failed_step_action: str
    compensation_class: str
    compensation_decision: str
    compensation_target_system: str
    external_reference_id: Optional[str] = None
    prior_step_refs: List[PriorStepRef] = Field(default_factory=list)
    payload_pointer: str
    payload_digest: str
    field_names_only: List[str]
    human_followup_ticket: Optional[str] = None
    outcome: str
    timestamp: str
