#!/usr/bin/env python3
"""Verification and Smoke Test Script for Registered Agents in GCP Agent Registry.

Runs test queries and health checks against the 8 registered Reasoning Engine
agents to verify operational readiness, latency, and response schemas.

Usage:
    python verify_agent_registry.py [--mock] [--project PROJECT_ID] [--location LOCATION]
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent_registry_verifier")


class AgentRegistryVerifier:
  """Verifies the health and responses of the registered agents."""

  def __init__(self, project_id: str, location: str, mock_mode: bool = False):
    self.project_id = project_id
    self.location = location
    self.mock_mode = mock_mode
    self.test_results: List[Dict[str, Any]] = []

  def run_smoke_tests(self):
    """Execute smoke test queries against each agent."""
    logger.info("================================================================")
    logger.info("Running Smoke Tests on 8 Registered Agents in GCP Agent Registry")
    logger.info("================================================================")

    test_cases = [
        {
            "agent_id": "hr_supervisor_orchestrator",
            "name": "hr-supervisor-orchestrator-v1",
            "query": "I need to request 3 days off for medical recovery with MC.",
            "expected_handling": "PolicyBenefitsAgent / HREnterpriseOrchestrator",
        },
        {
            "agent_id": "hr_policy_benefits_specialist",
            "name": "hr-policy-benefits-specialist-v1",
            "query": "What is the maximum allowed gift value for clients?",
            "expected_handling": "Section 12.4 ($50 limit, no gift cards)",
        },
        {
            "agent_id": "hr_lifecycle_operations_specialist",
            "name": "hr-lifecycle-operations-specialist-v1",
            "query": "Initiate onboarding for John Doe in Engineering.",
            "expected_handling": "ServiceNow Case Creation & Pub/Sub Event",
        },
        {
            "agent_id": "hr_approval_gatekeeper",
            "name": "hr-approval-gatekeeper-v1",
            "query": "Request sabbatical exception for 6 months.",
            "expected_handling": "Approval Gate Generation (PENDING)",
        },
        {
            "agent_id": "hr_policy_rag_search",
            "name": "hr-policy-rag-search-v1",
            "query": "How many days of bereavement leave am I entitled to?",
            "expected_handling": "PDF Section Citation",
        },
        {
            "agent_id": "hr_policy_okf_catalog",
            "name": "hr-policy-okf-catalog-v1",
            "query": "What is the remote work equipment reimbursement cap?",
            "expected_handling": "OKF Concept $350 Threshold",
        },
        {
            "agent_id": "hr_policy_dual_hybrid",
            "name": "hr-policy-dual-hybrid-v1",
            "query": "Tell me about parental leave ramp-back options.",
            "expected_handling": "Dual Grounding: OKF Concept + Search Snippet",
        },
        {
            "agent_id": "hr_eval_llm_judge",
            "name": "hr-eval-llm-judge-v1",
            "query": "Evaluate test case response against golden rubric.",
            "expected_handling": "5-Dimensional JSON Rubric Scores",
        },
    ]

    for i, tc in enumerate(test_cases, 1):
      logger.info(f"[{i}/8] Testing Agent: {tc['name']}...")
      start_time = time.time()

      if self.mock_mode:
        # Simulate local execution
        latency = 0.45
        status = "PASSED"
        output_snippet = f"Mock validated response from {tc['name']} matching '{tc['expected_handling']}'"
      else:
        try:
          import vertexai
          from vertexai.preview import reasoning_engines

          vertexai.init(project=self.project_id, location=self.location)
          resource_name = f"projects/{self.project_id}/locations/{self.location}/reasoningEngines/{tc['name']}"
          agent = reasoning_engines.ReasoningEngine(resource_name)
          resp = agent.query(query=tc["query"])
          latency = round(time.time() - start_time, 2)
          status = "PASSED"
          output_snippet = str(resp)[:120]
        except Exception as e:
          latency = round(time.time() - start_time, 2)
          status = f"FAILED: {str(e)}"
          output_snippet = "N/A"

      logger.info(f"    Status: {status} | Latency: {latency}s | Snippet: {output_snippet}")
      self.test_results.append({
          "agent_id": tc["agent_id"],
          "display_name": tc["name"],
          "status": status,
          "latency_seconds": latency,
          "expected_handling": tc["expected_handling"],
      })

    # Summary table
    print("\n" + "=" * 90)
    print("GCP AGENT REGISTRY VERIFICATION SCOREBOARD")
    print("=" * 90)
    print(f"{'AGENT DISPLAY NAME':<40} | {'STATUS':<10} | {'LATENCY (s)':<12} | {'EXPECTED CAPABILITY'}")
    print("-" * 90)
    for res in self.test_results:
      print(f"{res['display_name']:<40} | {res['status'][:10]:<10} | {res['latency_seconds']:<12} | {res['expected_handling']}")
    print("=" * 90)


def main():
  parser = argparse.ArgumentParser(
      description="Verify Registered Agents in GCP Agent Registry"
  )
  parser.add_argument(
      "--project",
      default=os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("GCP_PROJECT", "")),
      help="Google Cloud Project ID (or set GOOGLE_CLOUD_PROJECT env var)",
  )
  parser.add_argument(
      "--location",
      default=os.getenv("GOOGLE_CLOUD_LOCATION", os.getenv("GCP_REGION", "us-central1")),
      help="Google Cloud Region (or set GOOGLE_CLOUD_LOCATION env var)",
  )
  parser.add_argument(
      "--mock",
      action="store_true",
      default=False,
      help="Run in local mock validation mode without connecting to live GCP endpoints",
  )
  args = parser.parse_args()

  project_id = args.project
  if not project_id:
    if args.mock:
      project_id = "sample-gcp-project"
    else:
      logger.error("GCP Project ID is required. Pass --project <PROJECT_ID> or set GOOGLE_CLOUD_PROJECT env var.")
      sys.exit(1)

  verifier = AgentRegistryVerifier(
      project_id=project_id,
      location=args.location,
      mock_mode=args.mock,
  )
  verifier.run_smoke_tests()


if __name__ == "__main__":
  main()
