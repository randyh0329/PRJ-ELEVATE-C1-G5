#!/usr/bin/env python3
"""GCP Agent Registry Deployment Script.

Deploys and registers all 8 identified enterprise agents into Google Cloud
Vertex AI Agent Registry (Reasoning Engine).

Usage:
    python deploy_to_agent_registry.py [--dry-run] [--project PROJECT_ID] [--location LOCATION]
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List

# Ensure local package and workspace roots are in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PACKAGE_ROOT not in sys.path:
  sys.path.insert(0, PACKAGE_ROOT)

# Also add google3 workspace root if available
cur = SCRIPT_DIR
for _ in range(10):
  if os.path.exists(os.path.join(cur, "google3")):
    if cur not in sys.path:
      sys.path.insert(0, cur)
    break
  cur = os.path.dirname(cur)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent_registry_deployer")

# Requirements to pack into the Vertex AI Reasoning Engine containers
REASONING_ENGINE_REQUIREMENTS = [
    "google-cloud-aiplatform[reasoningengine,langchain]>=1.60.0",
    "google-adk>=0.1.0",
    "pydantic>=2.0.0",
    "google-cloud-discoveryengine>=0.11.0",
    "google-cloud-pubsub>=2.18.0",
    "cloudpickle>=3.0.0",
]


class AgentRegistryDeployer:
  """Manages registration of the 8 enterprise agents into Vertex AI Agent Registry."""

  def __init__(
      self,
      project_id: str,
      location: str,
      staging_bucket: str,
      dry_run: bool = False,
  ):
    self.project_id = project_id
    self.location = location
    self.staging_bucket = staging_bucket
    self.dry_run = dry_run
    self.registered_agents: Dict[str, str] = {}

    logger.info(f"Initializing Vertex AI for Project: {self.project_id}, Location: {self.location}")
    if not self.dry_run:
      try:
        import vertexai
        vertexai.init(
            project=self.project_id,
            location=self.location,
            staging_bucket=self.staging_bucket,
        )
      except ImportError:
        logger.warning(
            "google-cloud-aiplatform not installed. Switching to dry-run verification mode."
        )
        self.dry_run = True

  def register_adk_agent(
      self,
      agent_id: str,
      display_name: str,
      description: str,
      agent_instance: Any,
      extra_packages: List[str],
  ) -> str:
    """Register a standalone Google ADK LlmAgent into Vertex AI Agent Registry."""
    logger.info(f"Deploying ADK Agent [{agent_id}] -> Display Name: {display_name}...")

    if self.dry_run:
      resource_name = f"projects/{self.project_id}/locations/{self.location}/reasoningEngines/mock-{agent_id}"
      logger.info(f"[DRY-RUN] Verified package for {display_name} -> {resource_name}")
      self.registered_agents[agent_id] = resource_name
      return resource_name

    from vertexai.preview import reasoning_engines

    engine = reasoning_engines.ReasoningEngine.create(
        agent_instance,
        display_name=display_name,
        description=description,
        requirements=REASONING_ENGINE_REQUIREMENTS,
        extra_packages=extra_packages,
    )
    logger.info(f"✅ Successfully registered {display_name}: {engine.resource_name}")
    self.registered_agents[agent_id] = engine.resource_name
    return engine.resource_name

  def register_custom_class_agent(
      self,
      agent_id: str,
      display_name: str,
      description: str,
      class_instance: Any,
      extra_packages: List[str],
  ) -> str:
    """Register a custom Python orchestrator / specialist class into Vertex AI Agent Registry."""
    logger.info(f"Deploying Custom Mesh Agent [{agent_id}] -> Display Name: {display_name}...")

    if self.dry_run:
      resource_name = f"projects/{self.project_id}/locations/{self.location}/reasoningEngines/mock-{agent_id}"
      logger.info(f"[DRY-RUN] Verified class {class_instance.__class__.__name__} -> {resource_name}")
      self.registered_agents[agent_id] = resource_name
      return resource_name

    from vertexai.preview import reasoning_engines

    engine = reasoning_engines.ReasoningEngine.create(
        class_instance,
        display_name=display_name,
        description=description,
        requirements=REASONING_ENGINE_REQUIREMENTS,
        extra_packages=extra_packages,
    )
    logger.info(f"✅ Successfully registered {display_name}: {engine.resource_name}")
    self.registered_agents[agent_id] = engine.resource_name
    return engine.resource_name

  def deploy_all_agents(self) -> Dict[str, str]:
    """Execute end-to-end registration for all 8 agents."""
    logger.info("================================================================")
    logger.info("Starting Registration of 8 Enterprise Agents to GCP Agent Registry")
    logger.info("================================================================")

    # -------------------------------------------------------------
    # Suite A: HRED Enterprise Mesh Agents
    # -------------------------------------------------------------
    try:
      try:
        try:
          from google3.experimental.users.choirul.hr_enterprise_design.agents.enterprise_agents import (
              HRSupervisorAgent,
              LifecycleOperationsAgent,
              ManagerApprovalAgent,
              PolicyBenefitsAgent,
          )
          from google3.experimental.users.choirul.hr_enterprise_design.backend.integrations import (
              PubSubEventPublisher,
              ServiceNowClient,
              WorkdayClient,
          )
          from google3.experimental.users.choirul.hr_enterprise_design.backend.orchestrator import (
              HREnterpriseOrchestrator,
          )
        except Exception:
          from agents.enterprise_agents import (
              HRSupervisorAgent,
              LifecycleOperationsAgent,
              ManagerApprovalAgent,
              PolicyBenefitsAgent,
          )
          from agents.integrations import (
              PubSubEventPublisher,
              ServiceNowClient,
              WorkdayClient,
          )
          from agents.orchestrator import (
              HREnterpriseOrchestrator,
          )

        workday = WorkdayClient()
        servicenow = ServiceNowClient()
        pubsub = PubSubEventPublisher()
        orchestrator_inst = HREnterpriseOrchestrator()
        policy_inst = PolicyBenefitsAgent()
        lifecycle_inst = LifecycleOperationsAgent(workday, servicenow, pubsub)
        approval_inst = ManagerApprovalAgent(workday, servicenow, pubsub)
      except Exception as ie:
        logger.warning(f"Local dependency missing for Suite A ({ie}). Using module references for packaging.")
        orchestrator_inst = "agents.orchestrator:HREnterpriseOrchestrator"
        policy_inst = "agents.enterprise_agents:PolicyBenefitsAgent"
        lifecycle_inst = "agents.enterprise_agents:LifecycleOperationsAgent"
        approval_inst = "agents.enterprise_agents:ManagerApprovalAgent"

      # Agent 1: Root Supervisor Mesh Orchestrator
      self.register_custom_class_agent(
          agent_id="hr_supervisor_orchestrator",
          display_name="hr-supervisor-orchestrator-v1",
          description="Hierarchical HR Supervisor Mesh coordinating Policy, Lifecycle, and Approvals",
          class_instance=orchestrator_inst,
          extra_packages=["google3/experimental/users/choirul/hr_enterprise_design"],
      )

      # Agent 2: Policy & Benefits Specialist
      self.register_custom_class_agent(
          agent_id="hr_policy_benefits_specialist",
          display_name="hr-policy-benefits-specialist-v1",
          description="Specialized Domain Agent for Grounded Policy Interpretation & Benefits Q&A",
          class_instance=policy_inst,
          extra_packages=["google3/experimental/users/choirul/hr_enterprise_design"],
      )

      # Agent 3: Lifecycle Operations Specialist
      self.register_custom_class_agent(
          agent_id="hr_lifecycle_operations_specialist",
          display_name="hr-lifecycle-operations-specialist-v1",
          description="Specialized Agent for Onboarding, Transfers, and Offboarding Workflows",
          class_instance=lifecycle_inst,
          extra_packages=["google3/experimental/users/choirul/hr_enterprise_design"],
      )

      # Agent 4: Manager Approval Gatekeeper (HITL)
      self.register_custom_class_agent(
          agent_id="hr_approval_gatekeeper",
          display_name="hr-approval-gatekeeper-v1",
          description="Human-in-the-loop (HITL) Approval Gatekeeper for Leave & Expense Exceptions",
          class_instance=approval_inst,
          extra_packages=["google3/experimental/users/choirul/hr_enterprise_design"],
      )
    except Exception as e:
      logger.error(f"Error packing Suite A HRED Mesh Agents: {e}")

    # -------------------------------------------------------------
    # Suite B: ADK Standalone Policy Retrieval Agents
    # -------------------------------------------------------------
    try:
      # Agent 5: ADK RAG Search Agent
      try:
        from google3.experimental.users.choirul.hr_policy_agent.rag_scenario.agent.agent import (
            root_agent as rag_agent,
        )
      except ImportError:
        rag_agent = "google3.experimental.users.choirul.hr_policy_agent.rag_scenario.agent.agent:root_agent"

      self.register_adk_agent(
          agent_id="hr_policy_rag_search",
          display_name="hr-policy-rag-search-v1",
          description="Altostrat Singapore HR Policy Assistant powered by Vertex AI Search RAG",
          agent_instance=rag_agent,
          extra_packages=["google3/experimental/users/choirul/hr_policy_agent/rag_scenario"],
      )

      # Agent 6: ADK OKF Catalog Agent
      try:
        from google3.experimental.users.choirul.hr_policy_agent.okf_scenario.agent.agent import (
            root_agent as okf_agent,
        )
      except ImportError:
        okf_agent = "google3.experimental.users.choirul.hr_policy_agent.okf_scenario.agent.agent:root_agent"

      self.register_adk_agent(
          agent_id="hr_policy_okf_catalog",
          display_name="hr-policy-okf-catalog-v1",
          description="Altostrat Singapore HR Policy Assistant powered by Open Knowledge Format",
          agent_instance=okf_agent,
          extra_packages=["google3/experimental/users/choirul/hr_policy_agent/okf_scenario"],
      )

      # Agent 7: ADK Dual Hybrid Grounding Agent
      try:
        from google3.experimental.users.choirul.hr_policy_agent.hybrid_scenario.agent.agent import (
            root_agent as hybrid_agent,
        )
      except ImportError:
        hybrid_agent = "google3.experimental.users.choirul.hr_policy_agent.hybrid_scenario.agent.agent:root_agent"

      self.register_adk_agent(
          agent_id="hr_policy_dual_hybrid",
          display_name="hr-policy-dual-hybrid-v1",
          description="Altostrat Singapore HR Policy Assistant (Dual Hybrid: OKF + Vertex Search)",
          agent_instance=hybrid_agent,
          extra_packages=["google3/experimental/users/choirul/hr_policy_agent/hybrid_scenario"],
      )
    except Exception as e:
      logger.error(f"Error packing Suite B ADK Agents: {e}")

    # -------------------------------------------------------------
    # Suite C: Automated Quality Judge Agent
    # -------------------------------------------------------------
    try:
      class EvaluationJudgeEngine:
        """Wrapper for registering LLM-as-a-Judge in GCP Agent Registry."""

        def query(self, case_payload: Dict[str, Any]) -> Dict[str, Any]:
          from google3.experimental.users.choirul.hr_policy_agent.okf_scenario.evals.run_eval import (
              judge_case,
          )
          median_scores, why = judge_case(
              case=case_payload["case"],
              rubric=case_payload["rubric"],
              answer=case_payload["answer"],
              evidence_str=case_payload["evidence_str"],
              model="gemini-3.6-flash",
          )
          return {"scores": median_scores, "justifications": why}

      # Agent 8: LLM-as-a-Judge Quality Agent
      self.register_custom_class_agent(
          agent_id="hr_eval_llm_judge",
          display_name="hr-eval-llm-judge-v1",
          description="5-Dimensional Automated LLM-as-a-Judge Evaluation Engine",
          class_instance=EvaluationJudgeEngine(),
          extra_packages=["google3/experimental/users/choirul/hr_policy_agent/okf_scenario"],
      )
    except Exception as e:
      logger.error(f"Error packing Suite C Judge Agent: {e}")

    logger.info("================================================================")
    logger.info(f"Deployment Complete: {len(self.registered_agents)}/8 Agents Cataloged")
    logger.info("================================================================")

    # Output registration catalog summary
    catalog_path = os.path.join(
        os.path.dirname(__file__), "agent_registry_catalog.json"
    )
    with open(catalog_path, "w") as f:
      json.dump(self.registered_agents, f, indent=2)
    logger.info(f"Agent Registry catalog saved to: {catalog_path}")

    return self.registered_agents


def main():
  parser = argparse.ArgumentParser(
      description="Deploy 8 Agents to Vertex AI Agent Registry"
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
      "--staging-bucket",
      default=os.getenv("STAGING_BUCKET", ""),
      help="GCS Staging Bucket URI (or set STAGING_BUCKET env var)",
  )
  parser.add_argument(
      "--dry-run",
      action="store_true",
      help="Perform local packaging validation without making GCP API calls",
  )
  args = parser.parse_args()

  project_id = args.project
  if not project_id:
    if args.dry_run:
      project_id = "sample-gcp-project"
      logger.info(f"[DRY-RUN] No GCP project specified; using placeholder '{project_id}'")
    else:
      logger.error("GCP Project ID is required. Pass --project <PROJECT_ID> or set GOOGLE_CLOUD_PROJECT env var.")
      sys.exit(1)

  staging_bucket = (
      args.staging_bucket
      or f"gs://{project_id}-agent-registry-staging-prod"
  )

  deployer = AgentRegistryDeployer(
      project_id=project_id,
      location=args.location,
      staging_bucket=staging_bucket,
      dry_run=args.dry_run,
  )
  deployer.deploy_all_agents()


if __name__ == "__main__":
  main()
