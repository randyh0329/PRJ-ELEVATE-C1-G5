"""Deployment settings that are only wrong once the deploy is already running.

A bad probe budget or a duplicated IAM writer produces no test failure, no lint
error and no build error. It produces a revision Cloud Run refuses, minutes
later, with a message about the container rather than about the setting that
rejected it. These read the Terraform and the workflow as text so the feedback
arrives in the suite instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TERRAFORM = (_REPO_ROOT / "terraform" / "main.tf").read_text()
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "deploy-cloud-run.yml"

#: `build_app` measures ~12s warm - FAISS index already built, embedding model
#: already on local disk. A cold instance pays an image import (2m6s observed)
#: and a cold page cache on top. 35s rejected revision 00008-p7l with
#: ERROR_CONNECTION_FAILED; this is the floor that would have let it through.
MINIMUM_STARTUP_BUDGET_SECONDS = 180


def _services() -> dict[str, str]:
    """Each `google_cloud_run_v2_service` block, by resource label."""
    out: dict[str, str] = {}
    for match in re.finditer(r'resource "google_cloud_run_v2_service" "(\w+)"', _TERRAFORM):
        end = _TERRAFORM.find("\nresource ", match.end())
        out[match.group(1)] = _TERRAFORM[match.start(): end if end != -1 else len(_TERRAFORM)]
    return out


def _startup_budget(block: str) -> int | None:
    """`initial_delay + failure_threshold * period`, as Cloud Run computes it."""
    probe = re.search(r"startup_probe \{(.*?)\n      \}", block, re.S)
    if not probe:
        return None
    v = {k: int(n) for k, n in re.findall(r"(\w+)\s*=\s*(\d+)", probe.group(1))}
    return v.get("initial_delay_seconds", 0) + v.get("failure_threshold", 1) * v.get("period_seconds", 10)


def test_the_terraform_declares_the_services_these_tests_assume():
    assert set(_services()) >= {"hr_agentic_service", "hr_policy_rag_service"}


@pytest.mark.parametrize("service", sorted(_services()))
def test_startup_probe_allows_enough_time_to_load_the_model(service):
    """The failure this file was written for.

    These services load the FAISS index and the embedding model *before* uvicorn
    binds the port, so a tight budget rejects a container that is starting
    correctly, just slowly, and reports it as ERROR_CONNECTION_FAILED.
    """
    budget = _startup_budget(_services()[service])
    if budget is None:
        pytest.skip(f"{service} relies on the Cloud Run default startup probe")

    assert budget >= MINIMUM_STARTUP_BUDGET_SECONDS, (
        f"{service} gives startup {budget}s; a cold instance needs more than that "
        "and the revision will be rejected before it ever answers a probe"
    )


@pytest.mark.parametrize("service", sorted(_services()))
def test_startup_probe_stays_within_what_cloud_run_accepts(service):
    """Cloud Run caps the budget at 240s and rejects the service definition
    outright above it - which fails the apply rather than the deploy."""
    budget = _startup_budget(_services()[service])
    if budget is None:
        pytest.skip(f"{service} relies on the Cloud Run default startup probe")

    assert budget <= 240, f"{service} asks for {budget}s; Cloud Run's maximum is 240s"


def test_the_policy_rag_index_is_baked_rather_than_built_at_startup():
    """`|| true` here is not a soft landing, it is the startup-probe failure.

    The orchestrator can lose its index and still answer from the curated
    register, so its ingest stays soft. This service *is* the index: losing it
    means the runtime auto-ingest runs inside `build_app`, before the port is
    bound, and the container never becomes reachable.
    """
    joined = re.sub(r"\\\n", "", (_REPO_ROOT / "Dockerfile.policy_rag").read_text())
    ingest = [ln for ln in joined.splitlines() if "policy_rag.cli ingest" in ln]

    assert ingest, "Dockerfile.policy_rag no longer builds the index"
    assert "|| true" not in ingest[0], (
        "a failed ingest would ship an image whose first act is to rebuild the "
        "index before binding the port - the container cannot pass its probe"
    )


def test_the_policy_rag_build_rejects_an_empty_index():
    """Ingest can exit 0 having written nothing if the corpus globs stop
    matching. An empty index answers every question with confident silence."""
    joined = re.sub(r"\\\n", "", (_REPO_ROOT / "Dockerfile.policy_rag").read_text())
    checks = [ln for ln in joined.splitlines() if ln.startswith("RUN python -c") and "PolicyIndex.load" in ln]

    assert checks, "nothing asserts the built index is non-empty"
    assert "SystemExit" in checks[0]


# --- who owns the invoker policy ----------------------------------------------


def _deploy_step() -> str:
    """The deploy step's shell body, minus comments.

    Comments are stripped because the step explains at length *why* it no longer
    passes `--allow-unauthenticated`, and a naive substring search finds the
    explanation and reports the thing it is explaining.
    """
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text())
    steps = [s for job in workflow["jobs"].values() for s in job.get("steps", [])]
    body = next(s["run"] for s in steps if s.get("id") == "deploy")
    return "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("#"))


def test_the_workflow_does_not_rewrite_the_invoker_policy():
    """Terraform owns these bindings. gcloud re-asserting them on every deploy is
    a second writer to one policy, and the deployer's roles/run.developer cannot
    call setIamPolicy anyway - it just prints a warning that looks like a cause.
    """
    step = _deploy_step()

    assert "--allow-unauthenticated" not in step, (
        "the deploy step is rewriting Cloud Run IAM that terraform/main.tf owns"
    )


def test_terraform_still_says_who_may_invoke_each_service():
    """The corollary: having removed it from CI, it has to be here."""
    assert 'member   = "allUsers"' in _TERRAFORM, "nothing makes the orchestrator public"
    assert _TERRAFORM.count('role     = "roles/run.invoker"') >= 3


@pytest.mark.parametrize(
    "account", ["policy-rag-sa", "saas-adapter-sa", "hr-agent-runner-sa"]
)
def test_each_service_still_deploys_under_its_own_identity(account):
    """Dropping the auth flags must not disturb the runtime service accounts."""
    assert f'--service-account "{account}@' in _deploy_step()


# --- what Terraform declares vs what the deploy actually applies ---------------
#
# Nothing in this repository runs `terraform apply`. terraform/main.tf describes
# the services; `gcloud run deploy` is what creates their revisions, and it
# inherits any setting the command line does not mention. So raising the startup
# budget in Terraform alone changed nothing: revision
# hr-policy-rag-service-00009-vgq was created with the old 35s budget and
# rejected exactly as before. These tests exist because the Terraform reads
# correct and the deploy still ships the old value - the file is not the state.


def _workflow_probe_budgets() -> list[int]:
    """Startup budget from each `--startup-probe` on the deploy command line."""
    budgets = []
    for flag in re.findall(r"--startup-probe\s+\"([^\"]+)\"", _deploy_step()):
        expanded = flag.replace("${PROBE_TIMING}", _probe_timing_var())
        v = {k: int(n) for k, n in re.findall(r"(\w+)=(\d+)", expanded)}
        budgets.append(
            v.get("initialDelaySeconds", 0)
            + v.get("failureThreshold", 1) * v.get("periodSeconds", 10)
        )
    return budgets


def _probe_timing_var() -> str:
    """The shared PROBE_TIMING assignment the three deploys interpolate."""
    match = re.search(r'PROBE_TIMING="([^"]+)"', _deploy_step())
    return match.group(1) if match else ""


def test_the_deploy_command_sets_the_startup_probe_itself():
    """The bug this section documents.

    A budget that lives only in Terraform is not applied by anything. It has to
    be on the command line that creates the revision.
    """
    budgets = _workflow_probe_budgets()

    assert len(budgets) == 3, (
        f"expected all 3 services to set --startup-probe, found {len(budgets)}; "
        "a service without it inherits whatever the live revision already has"
    )


@pytest.mark.parametrize("index", range(3))
def test_the_deployed_startup_budget_is_large_enough(index):
    budgets = _workflow_probe_budgets()
    if index >= len(budgets):
        pytest.fail("a deploy is missing --startup-probe; see the test above")

    assert MINIMUM_STARTUP_BUDGET_SECONDS <= budgets[index] <= 240, (
        f"deploy #{index} asks for {budgets[index]}s; Cloud Run caps the budget at "
        f"240s and a cold start needs at least {MINIMUM_STARTUP_BUDGET_SECONDS}s"
    )


def test_the_workflow_and_terraform_agree_on_the_budget():
    """Two writers, one setting. They should not drift apart silently."""
    declared = {_startup_budget(b) for b in _services().values()} - {None}
    applied = set(_workflow_probe_budgets())

    assert declared == applied, (
        f"terraform declares {sorted(declared)}s but the deploy applies "
        f"{sorted(applied)}s; the deploy is what takes effect"
    )


def _deploy_blocks() -> dict[str, str]:
    """Each `gcloud run deploy` invocation, keyed by the service it deploys.

    The workflow names services through `${{ env.SERVICE_NAME_* }}`, so the
    literal names only exist in the workflow-level `env:` block. Resolving them
    here keeps the expectations below written in terms of real service names.
    """
    workflow = yaml.safe_load(_WORKFLOW_PATH.read_text())
    names = {k: v for k, v in workflow["env"].items() if k.startswith("SERVICE_NAME_")}

    blocks: dict[str, str] = {}
    for raw in _deploy_step().split("gcloud run deploy ")[1:]:
        for var, service in names.items():
            if f"env.{var}" in raw.split("\n")[0]:
                blocks[service] = raw
    return blocks


@pytest.mark.parametrize(
    ("service", "path"),
    [
        ("hr-policy-rag-service", "/healthz"),
        ("saas-integration-adapters", "/health"),
        ("hr-agentic-service", "/health"),
    ],
)
def test_the_probe_points_at_a_path_that_service_actually_serves(service, path):
    """A probe on the wrong path fails a container that is working fine.

    The policy RAG app serves `/healthz` (a2a_app/server.py); the other two are
    FastAPI apps serving `/health` (src/main.py, src/integrations/mcp/server.py).
    Getting these crossed turns a healthy deployment into a rejected revision -
    and the two services that currently deploy fine are the ones with the most
    to lose from a careless probe.
    """
    blocks = _deploy_blocks()

    assert service in blocks, f"no `gcloud run deploy` block found for {service}"
    assert f"httpGet.path={path}" in blocks[service], (
        f"{service} serves {path}; its startup probe points somewhere else"
    )
