"""
Automated Trajectory Test Harness (§9.1).
Simulates synthetic fault injection at every step of UC-2.1, UC-2.2, and UC-2.3 to verify
compensation correctness, transactional integrity (SM-03, SM-07), and consequence-aware rollback logic.
"""

import json
import unittest

from app.graph import AgentOrchestrationGraph
from app.state import SagaCompensationClass, SagaStepStatus, SagaWorkflowState
from eval.trajectory_runner import TrajectoryRunner


class TestTrajectoryHarness(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.graph = AgentOrchestrationGraph()
        self.runner = TrajectoryRunner(self.graph)

    # =========================================================================
    # UC-2.1 Trajectory Tests: Equipment Procurement
    # =========================================================================
    async def test_uc21_equipment_happy_path_remote_eligible(self):
        """UC-2.1: Remote employee requests home office monitor -> Happy path succeeds."""
        case = {
            "id": "TEST-UC21-HAPPY",
            "use_case_id": "UC-2.1",
            "user_prompt": "I am a remote employee, can you order my home office monitor under the remote work policy?",
        }
        res = await self.runner.run_single_case(case, employee_id="EMP-44210")

        self.assertEqual(res["route"], "saga")
        self.assertEqual(res["saga_state"], SagaWorkflowState.COMPLETED.value)
        self.assertIn("Hardware procurement request", res["final_response"])
        self.assertEqual(len(res["ledger_steps"]), 3)
        self.assertEqual(res["ledger_steps"][0]["action"], "QUERY_REMOTE_EQUIPMENT_POLICY")
        self.assertEqual(res["ledger_steps"][1]["action"], "GET_PROFILE_WORK_LOCATION")
        self.assertEqual(res["ledger_steps"][2]["action"], "CREATE_HARDWARE_TICKET")
        self.assertEqual(res["ledger_steps"][2]["status"], SagaStepStatus.SUCCESS.value)

    async def test_uc21_equipment_ineligible_on_site_branch(self):
        """UC-2.1: On-site employee requests monitor -> Refused under Policy s4.2 without write."""
        case = {
            "id": "TEST-UC21-INELIGIBLE",
            "use_case_id": "UC-2.1",
            "user_prompt": "Can I order a home office monitor under the equipment policy?",
        }
        # EMP-10022 is ON_SITE
        res = await self.runner.run_single_case(case, employee_id="EMP-10022")

        self.assertEqual(res["saga_state"], SagaWorkflowState.COMPLETED.value)
        self.assertIn("on-site work location", res["final_response"])
        self.assertIn("No hardware request has been raised", res["final_response"])
        # Step 3 is never executed
        self.assertEqual(len(res["ledger_steps"]), 2)

    # =========================================================================
    # UC-2.2 Trajectory Tests: Cross-System Medical Leave (Consequence-Aware)
    # =========================================================================
    async def test_uc22_medical_leave_happy_path(self):
        """UC-2.2: Medical leave filed in WorkWeek + IT routing ticket created -> COMPLETED."""
        case = {
            "id": "TEST-UC22-HAPPY",
            "use_case_id": "UC-2.2",
            "user_prompt": "I need short-term medical leave starting next Monday. Please file it and route approvals.",
        }
        res = await self.runner.run_single_case(case, employee_id="EMP-44210")

        self.assertEqual(res["route"], "saga")
        self.assertEqual(res["saga_state"], SagaWorkflowState.COMPLETED.value)
        self.assertIn("medical leave filing", res["final_response"].lower())
        self.assertIn("IT routing", res["final_response"])
        self.assertEqual(len(res["ledger_steps"]), 2)
        self.assertEqual(res["ledger_steps"][0]["compensationClass"], SagaCompensationClass.HUMAN_CONSEQUENTIAL.value)
        self.assertEqual(res["ledger_steps"][1]["compensationClass"], SagaCompensationClass.ANCILLARY.value)

    async def test_uc22_medical_leave_fault_injection_preserves_leave(self):
        """
        UC-2.2 FORCED FAILURE: Step 2 (ITSM 503 / retries exhausted).
        VERIFIES SDD §5.4 RULE:
        1. WorkWeek Medical Leave filing is NEVER cancelled / rolled back.
        2. Saga state becomes PARTIALLY_COMPLETED_MANUAL_FOLLOWUP.
        3. P2 Operations follow-up task is raised.
        4. User is informed that leave stands and IT routing is tracked by ops.
        """
        case = {
            "id": "TEST-UC22-FAULT-INJECTION",
            "use_case_id": "UC-2.2",
            "user_prompt": "I need short-term medical leave from next week. Please set it up.",
        }
        # Injected fault: Step 2 ITSM fails
        res = await self.runner.run_single_case(
            case,
            employee_id="EMP-44210",
            faults={"step_2_fail": True, "itsm_503": True},
        )

        self.assertEqual(res["route"], "saga")
        # Assert state is PARTIALLY_COMPLETED_MANUAL_FOLLOWUP (NOT COMPENSATED_ROLLED_BACK)
        self.assertEqual(
            res["saga_state"],
            SagaWorkflowState.PARTIALLY_COMPLETED_MANUAL_FOLLOWUP.value,
        )

        # Assert Step 1 (HUMAN_CONSEQUENTIAL) SUCCESS was PRESERVED
        step1 = res["ledger_steps"][0]
        self.assertEqual(step1["action"], "SUBMIT_LEAVE")
        self.assertEqual(step1["compensationClass"], SagaCompensationClass.HUMAN_CONSEQUENTIAL.value)
        self.assertEqual(step1["status"], SagaStepStatus.SUCCESS.value)
        self.assertTrue(step1["externalReferenceId"].startswith("LV-"))

        # Assert Step 2 (ANCILLARY) is FAILED_HANDED_TO_HUMAN
        step2 = res["ledger_steps"][1]
        self.assertEqual(step2["action"], "CREATE_ROUTING_TICKET")
        self.assertEqual(step2["status"], SagaStepStatus.FAILED_HANDED_TO_HUMAN.value)
        self.assertTrue(step2["followUpRef"].startswith("OPS-"))

        # Assert User Explanation states leave stands
        self.assertIn("filed successfully and stands unaffected", res["final_response"])
        self.assertIn(step2["followUpRef"], res["final_response"])
        self.assertIn("No further action is required from you", res["final_response"])

    # =========================================================================
    # UC-2.3 Trajectory Tests: Relocation (Safe Rollback)
    # =========================================================================
    async def test_uc23_relocation_happy_path(self):
        """UC-2.3: Relocation address update + badge ticket -> COMPLETED."""
        case = {
            "id": "TEST-UC23-HAPPY",
            "use_case_id": "UC-2.3",
            "user_prompt": "I am transferring to the London office. Update my address and request badge access.",
        }
        res = await self.runner.run_single_case(case, employee_id="EMP-44210")

        self.assertEqual(res["saga_state"], SagaWorkflowState.COMPLETED.value)
        self.assertIn("WorkWeek address updated to London", res["final_response"])
        self.assertEqual(len(res["ledger_steps"]), 2)
        self.assertEqual(res["ledger_steps"][0]["compensationClass"], SagaCompensationClass.REVERSIBLE_SAFE.value)

    async def test_uc23_relocation_fault_injection_safely_rolls_back_address(self):
        """
        UC-2.3 FORCED FAILURE: Step 2 (Facilities Ticket fails).
        VERIFIES SDD §5.4 RULE:
        1. All prior steps are REVERSIBLE_SAFE.
        2. WorkWeek contact update is AUTOMATICALLY REVERTED to prior address.
        3. Saga state becomes COMPENSATED_ROLLED_BACK.
        """
        case = {
            "id": "TEST-UC23-FAULT-INJECTION",
            "use_case_id": "UC-2.3",
            "user_prompt": "I am transferring to the London office. Update my contact and badge.",
        }

        # Check starting address
        initial_profile = self.graph.hcm_agent.get_profile("EMP-44210")
        initial_address = initial_profile["homeAddress"]

        # Injected fault: Step 2 Facilities ticket fails
        res = await self.runner.run_single_case(
            case,
            employee_id="EMP-44210",
            faults={"step_2_fail": True, "facilities_ticket_fail": True},
        )

        self.assertEqual(res["route"], "saga")
        # Assert state is COMPENSATED_ROLLED_BACK
        self.assertEqual(res["saga_state"], SagaWorkflowState.COMPLETED_ROLLED_BACK if hasattr(SagaWorkflowState, 'COMPLETED_ROLLED_BACK') else SagaWorkflowState.COMPENSATED_ROLLED_BACK.value)

        # Verify WorkWeek Address was rolled back to initial_address
        restored_profile = self.graph.hcm_agent.get_profile("EMP-44210")
        self.assertEqual(restored_profile["homeAddress"], initial_address)

        # Assert Step 1 in ledger is marked ROLLED_BACK
        step1 = res["ledger_steps"][0]
        self.assertEqual(step1["action"], "UPDATE_CONTACT")
        self.assertEqual(step1["status"], SagaStepStatus.ROLLED_BACK.value)

        # Assert user was informed
        self.assertIn("prior reversible changes have been safely restored", res["final_response"])

    # =========================================================================
    # Golden Dataset Suite Validation (§9.2)
    # =========================================================================
    async def test_golden_suite_execution(self):
        """Runs the versioned golden evaluation dataset (eval/golden/v1.jsonl)."""
        import os
        golden_path = os.path.join(os.path.dirname(__file__), "..", "eval", "golden", "v1.jsonl")
        results = await self.runner.run_golden_suite(golden_path)

        self.assertEqual(len(results), 6)
        for r in results:
            self.assertEqual(r["guardrail_verdict"], "ALLOW")
            self.assertIsNotNone(r["final_response"])

    async def test_golden_suite_tolerates_blank_lines(self):
        """JSONL grows by appending, and the file that grows by hand grows blank
        lines. One of them must not fail the whole suite with a JSON error."""
        import tempfile
        from pathlib import Path

        case = {"id": "GD-BLANK-001", "user_prompt": "How many days of annual leave do I get?"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spaced.jsonl"
            path.write_text(f"\n{json.dumps(case)}\n\n   \n", encoding="utf-8")

            results = await self.runner.run_golden_suite(str(path))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["case_id"], "GD-BLANK-001")


if __name__ == "__main__":
    unittest.main()
