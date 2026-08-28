"""
Evaluation and Trajectory Runner Engine.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §9.1, §9.2, §9.3.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.graph import AgentOrchestrationGraph
from app.state import AgentState


class TrajectoryRunner:
    """
    Executes golden dataset cases and synthetic fault injection scenarios.
    Measures trajectory correctness, compensation validity, and grounding adherence.
    """

    def __init__(self, graph: AgentOrchestrationGraph | None = None):
        self.graph = graph or AgentOrchestrationGraph()

    async def run_single_case(
        self,
        case: dict[str, Any],
        employee_id: str = "EMP-44210",
        faults: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Executes a single test case through the orchestration graph.
        """
        state: AgentState = {
            "session_id": f"sess-{case.get('id', 'test')}",
            "turn_id": "turn-001",
            "employee_id": employee_id,
            "user_roles": ["EMPLOYEE"],
            "scopes": ["policy.read", "ww.read", "ww.write", "itsm.read", "itsm.write"],
            "user_input": case["user_prompt"],
            "masked_input": "",
            "messages": [{"role": "user", "content": case["user_prompt"]}],
            "route": "supervisor",
            "next_node": None,
            "saga_id": None,
            "saga_type": None,
            "saga_state": None,
            "saga_ledger": [],
            "current_step_index": 0,
            "guardrail_verdict": "ALLOW",
            "grounding_score": 0.0,
            "citations": [],
            "final_response": None,
            "injected_faults": faults or {},
            "context_package": None,
        }

        output_state = await self.graph.invoke(state)

        # Extract executed tool trajectory from Saga ledger if present
        executed_trajectory = []
        for step in output_state.get("saga_ledger", []):
            executed_trajectory.append(step.action)

        return {
            "case_id": case.get("id"),
            "use_case_id": case.get("use_case_id"),
            "route": output_state.get("route"),
            "saga_id": output_state.get("saga_id"),
            "saga_state": output_state.get("saga_state"),
            "guardrail_verdict": output_state.get("guardrail_verdict"),
            "executed_trajectory": executed_trajectory,
            "citations": output_state.get("citations", []),
            "final_response": output_state.get("final_response"),
            "ledger_steps": [s.to_dict() for s in output_state.get("saga_ledger", [])],
        }

    async def run_golden_suite(self, golden_file_path: str) -> list[dict[str, Any]]:
        """
        Loads and executes all golden test cases from a JSONL file.
        """
        results = []
        path = Path(golden_file_path)
        with open(path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                case = json.loads(line)
                res = await self.run_single_case(case)
                results.append(res)
        return results
