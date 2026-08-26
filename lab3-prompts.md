# Lab 3 — Cymbal Navigation & Planner Agent

Three prompts for the agy CLI. Run them in order; each is self-contained, so a `/clear` or a
session restart between them is fine.

| Prompt | Covers | Lab tasks |
| --- | --- | --- |
| **1 — Config** | install, auth, Maps key, clone, `.env`, preflight, workspace audit, local playground, 6-metric eval | Step 0 + Tasks 1–3 |
| **2 — Deploy & Publish** | scaffold upgrade, BigQuery plugin, deploy, register to `apac-track-3`, 4-tier observability audit | Tasks 4–6 |
| **3 — Review** | evidence-based audit of all six checkpoints | run before *Check my progress* |

Approve tool permissions when agy asks, and monitor long runs with `/tasks` rather than
re-prompting — a second prompt mid-deploy can start a duplicate deploy.

---

## Manual pre-steps

Not promptable — remote-desktop and TUI work.

1. Open the remote session, allow clipboard access, and launch Chrome from **Application
   Launcher → Internet → Google Chrome** (starting it another way has init problems).
2. **Application Launcher → System → Konsole**, run `agy`.
3. Sign in with **Use a Google Cloud project**, complete the browser auth flow, set the
   Antigravity location to **`global`**, pick a colour scheme, accept the ToS.
4. `/config` — confirm the project and location took.
5. `/model` — select **`gemini-3.5-flash`** as the lab requires.

Five separate "model" and "location" settings are in play. Do not conflate them:

| Setting | Value | What it controls |
| --- | --- | --- |
| agy `/model` | `gemini-3.5-flash` | the assistant you are prompting |
| agy `/config` location | `global` | the assistant's own endpoint |
| `Agent(model=...)` in `agent.py` | `gemini-2.5-flash` | the deployed Cymbal agent — **do not change** |
| `GOOGLE_CLOUD_LOCATION` in `.env` | `global` | model resolution for that agent |
| `region:` in the manifest | `us-central1` | where the runtime is deployed |

Setting agy's own model to Gemini 3.5 Flash does **not** make Gemini 3.5 Flash available in
`us-central1` for the v2 eval specs — see Phase 4c.

---

## Prompt 1 — Config

```text
You are my platform engineer for the Cymbal Navigation Agent lab. This is part 1 of 3: get the
environment configured, the agent running locally, and the quality flywheel scored. Do NOT
deploy, publish, or touch Gemini Enterprise in this session — that is part 2. My GCP project
ID is <PASTE_PROJECT_ID>.

OPERATING RULES
- Work through the phases in order. If a phase fails, STOP, paste the full error, diagnose it
  from evidence, and ask me before retrying. Never disable telemetry, drop a flag, or weaken a
  test case to force a green result.
- This repo ships Agent Skills in skills/ but do NOT assume your harness auto-loads them.
  Before each phase, explicitly `cat` the relevant SKILL.md and follow its numbered
  Instructions literally. Quote the command you are about to run before running it.
- Those SKILL.md files also say to read the CLI's own `google-agents-cli-{eval,workflow}`
  skills first (deploy/publish/observability come in part 2). They ship with the CLI via
  `uvx google-agents-cli setup`. After setup, locate them on disk (try ~/.agents/skills,
  ~/.claude/skills, ./.google-agents-cli/) and `cat` the relevant one per phase. If you cannot
  find them, tell me — do not silently skip.
- Note there is NO .agents/skills/ directory in this repo despite what the lab text says.
- Write every artifact to disk with your file-write tool; printing to chat does not count. Run
  `ls -la artifacts/docs/` after each phase.
- Print detailed background on what is happening under the hood as you go.
- Report honestly. A failed tool call, an empty table, or a partial pass is a finding.
- Never print the raw Google Maps API key — mask to last 4 chars, in your own prose and in any
  command output you paste back.

PHASE 1 — SETUP AND PREFLIGHT  [checkpoint: preflight]
  a. Note that `agy` (Antigravity CLI, what you are) and `agents-cli` (google-agents-cli) are
     different tools. The lab's ">= 1.0.0" requirement is on agents-cli.
     Install it and its specialized skills: `uvx google-agents-cli setup`. Verify with
     `agents-cli info` and print the version (current PyPI is 1.4.1). Ensure it is on PATH
     persistently and tell me which profile file you edited.
  b. `gcloud auth login` and `gcloud auth application-default login`; set the project; confirm
     with `gcloud config list`.
  c. Create a Google Maps API key with **Places API** and **Directions API** enabled — the
     tools call maps.googleapis.com/maps/api/place/textsearch/json and
     /maps/api/directions/json specifically. Scope the key to those two if possible.
  d. Clone https://github.com/Ashwinikumar1/cymbal-navigation-agent and cd in.
  e. Write .env in the repo root:
       GOOGLE_GENAI_USE_VERTEXAI=true
       GOOGLE_CLOUD_PROJECT=<PASTE_PROJECT_ID>
       GOOGLE_CLOUD_LOCATION=global
       GOOGLE_MAPS_API_KEY=<key>
       GEMINI_ENTERPRISE_APP_ID=projects/<PASTE_PROJECT_ID>/locations/global/collections/default_collection/engines/apac-track-3
     GOOGLE_CLOUD_LOCATION is the literal string `global`, not a region. The lab lists only the
     first four variables, but the publish skill needs the fifth and it must be the FULL
     resource path — a bare `apac-track-3` will not work.
  f. scripts/preflight_check.sh reads EXPORTED vars, not .env. Run
     `set -a; source .env; set +a` then `bash scripts/preflight_check.sh`. Paste the complete
     output and `echo $?`. Confirm all 7 APIs enabled (aiplatform, cloudresourcemanager, iam,
     logging, monitoring, bigquery, discoveryengine) AND that the Maps key and GE app ID show
     as exported. Those last two are informational — the script exits 0 without them, so exit
     0 alone is not a pass.

PHASE 2 — ORIENT (read-only, brief)
  cat agents-cli-manifest.yaml, pyproject.toml, agent.py, tools.py, evals/evalset.json.
  Confirm: App name `cymbal_navigation_agent`, root agent `cymbal_navigation_planner`, model
  `gemini-2.5-flash`, manifest region `us-central1`, deployment_target `agent_runtime`,
  agent_directory resolves, all three tools registered, and the evalset schema
  {"eval_cases":[{"eval_case_id","prompt":{"role","parts":[{"text"}]}}]}.
  Also confirm this known defect is still present and report it (do not fix yet): in tools.py
  both search_google_maps and get_route_directions fall through with NO return statement when
  the key is missing, the request fails, or results are empty — they implicitly return None.
  It explains hallucinated answers later.

PHASE 3 — LOCAL VALIDATION  [checkpoint: local playground]
  Start `agents-cli playground` in the background (its --port default is 8080). Curl
  http://127.0.0.1:8080/dev-ui/ and report the HTTP status before declaring it ready. The URL
  is http://127.0.0.1:8080/dev-ui/?app=cymbal_navigation_agent — the ?app= value comes from
  App(name=...) in agent.py, underscores. Tell me how to stop the server.
  Then smoke test with `agents-cli run "..."`, showing the FULL trajectory each time — tool
  selected, arguments, RAW tool response, final answer:
    1. "What major tech conferences are happening in San Francisco soon, and how do I get to
       Moscone Center from SFO airport?"  -> expect google_search AND get_route_directions
    2. "Look up the address and rating for Moscone Center using Google Maps."
       -> expect search_google_maps with a real formatted_address and rating
    3. "Provide transit directions from SFO Airport to Moscone Center."
       -> expect get_route_directions with travel_mode=transit
  Given the tools.py defect, a `None` return is the signature of a broken Maps key. For each
  Maps call state explicitly whether it returned a populated dict with "status": "success" or
  returned None/empty. If any returned None, STOP and fix the key or API enablement — do not
  proceed to evaluation with broken tools, it will corrupt every metric.

PHASE 4 — EVALUATION  [checkpoint: evaluation & dataset expansion]
  `cat skills/evaluation/SKILL.md` and follow it, plus the `google-agents-cli-eval` skill.
  Three things the lab text omits — verify each against `agents-cli eval run --help` and
  `agents-cli eval metric list` before relying on my description:
    (i) `eval run` grades only `final_response_quality` by default. All six must be requested.
    (ii) `--dataset` defaults to tests/eval/datasets/basic-dataset.json, so you MUST pass
         `--dataset evals/evalset.json`.
    (iii) `navigation_accuracy_judge` is NOT a predefined metric — the other five are. It must
          be authored as a custom metric.
  a. Create tests/eval/eval_config.yaml (the default --config path):
       metrics_to_run:
         - multi_turn_task_success
         - multi_turn_tool_use_quality
         - multi_turn_trajectory_quality
         - final_response_quality
         - hallucination
         - navigation_accuracy_judge
       custom_metrics:
         - name: navigation_accuracy_judge
           custom_function_file: navigation_accuracy_judge.py
     Then write tests/eval/navigation_accuracy_judge.py with an `evaluate(instance)` function
     returning {'score': <0..1>}. It should judge navigation correctness: did the agent call a
     Maps tool for address/route questions, and does the final answer's address / distance /
     duration actually match what the tool returned? Explain your scoring rubric to me.
  b. Expand evals/evalset.json from its 3 cases, keeping the EXACT schema. Cover: search-only,
     maps-lookup-only, driving directions, walking or bicycling mode, a compound multi-tool
     single turn, a multi-turn exchange with context carryover, one adversarial case tempting
     the agent to answer an address or travel time from memory, and one out-of-scope case
     where declining is correct. Show me each new case before running.
  c. Run:
       uv sync && uvx google-agents-cli eval run --dataset evals/evalset.json --config tests/eval/eval_config.yaml
     If `final_response_quality` or `hallucination` fail to resolve, that is the known v2
     regional issue — the bare names resolve to _v2 specs which need Gemini 3.5 Flash, not
     available in us-central1. Pin `final_response_quality_v1` and `hallucination_v1` in the
     config and re-run. Tell me if you had to do this.
  d. The CLI writes traces to artifacts/traces/ and scores to artifacts/grade_results/. It
     does NOT write the lab's deliverable — synthesise artifacts/docs/eval_report.md yourself
     from grade_results: per-metric scores, each metric's threshold, overall verdict, a
     per-case table, and root-cause analysis for every failing case. State explicitly whether
     a high `hallucination` score is good or bad here. Do not tune thresholds or weaken cases.

HAND-OFF
  Stop here. Print: the absolute path of the cloned repo, the agents-cli version actually in
  use, the five .env keys (values masked), whether the Maps tools returned real data or None in
  Phase 3, the six metric scores, and `ls -la artifacts/docs/`. Then list anything unresolved
  that part 2 needs to know about. Do not deploy.
```

---

## Prompt 2 — Deploy & Publish

Phase numbering continues from Prompt 1 so it stays aligned with the six checkpoints.

```text
You are my platform engineer for the Cymbal Navigation Agent lab. This is part 2 of 3. Part 1
already installed google-agents-cli, authenticated gcloud, created a Google Maps API key,
cloned https://github.com/Ashwinikumar1/cymbal-navigation-agent, wrote .env, passed
scripts/preflight_check.sh, validated the agent in the local playground, and ran the 6-metric
evaluation into artifacts/docs/eval_report.md. My GCP project ID is <PASTE_PROJECT_ID>.

RE-ESTABLISH CONTEXT FIRST — verify, do not assume. If any check fails, STOP and tell me
rather than silently redoing part 1:
  - cd into the cloned cymbal-navigation-agent directory and `pwd`.
  - `set -a; source .env; set +a`, then confirm all five variables are set (mask the Maps key):
    GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION (literally `global`),
    GOOGLE_MAPS_API_KEY, and GEMINI_ENTERPRISE_APP_ID — which must be the FULL resource path
    projects/<PASTE_PROJECT_ID>/locations/global/collections/default_collection/engines/apac-track-3,
    not the bare `apac-track-3`. If it is missing or bare, fix it now; Phase 6 depends on it.
  - `agents-cli info` — print the version and pin every later command to it explicitly.
  - `gcloud config list`, and confirm ADC works by exit code alone (never print a token).
  - `ls -la artifacts/docs/` — eval_report.md should already be there.

OPERATING RULES
- Work through the phases in order. If a phase fails, STOP, paste the full error, diagnose it
  from evidence, and ask me before retrying. Never disable telemetry, drop a flag, or weaken a
  test case to force a green result.
- This repo ships Agent Skills in skills/ but do NOT assume your harness auto-loads them.
  Before each phase, explicitly `cat` the relevant SKILL.md and follow its numbered
  Instructions literally. Quote the command you are about to run before running it.
- Those SKILL.md files also say to read `google-agents-cli-{deploy,publish,observability,
  workflow}` first. Those ship with the CLI via `uvx google-agents-cli setup`. Locate them on
  disk (try ~/.agents/skills, ~/.claude/skills, ./.google-agents-cli/) and `cat` the relevant
  one per phase. If you cannot find them, tell me — do not silently skip.
- Note there is NO .agents/skills/ directory in this repo despite what the lab text says.
- Write every artifact to disk with your file-write tool; printing to chat does not count. Run
  `ls -la artifacts/docs/` after each phase.
- Print detailed background on what is happening under the hood as you go.
- Report honestly. A failed tool call, an empty table, or a partial pass is a finding.
- Never print the raw Google Maps API key — mask to last 4 chars. This applies to command
  output you paste back, not just to your own prose: `agents-cli deploy` echoes a full
  "Environment Variables:" block containing the key in plaintext. Redact it before pasting,
  and scrub it from artifacts/docs/deploy_log.txt after writing that file. If the key does
  reach a log or the transcript, stop and tell me to rotate it.

PHASE 5 — DEPLOY  [checkpoint: deploy to Agent Platform]
  `cat skills/deployment/SKILL.md` and follow it, plus `google-agents-cli-deploy`. Two blockers
  in this repo that the lab text does not mention — handle both BEFORE deploying.

  5a. CONTAINER MIGRATION. This project's manifest says version 0.4.0. agent_runtime switched
      to container builds at CLI 0.6.0, so deploy will abort with "Dockerfile not found in the
      project root directory." Fix it with the CLI, NOT by hand-writing a Dockerfile or a
      FastAPI/uvicorn entry point.
        - `git add -A && git commit -m "pre-upgrade checkpoint"` first, so the merge is
          reversible.
        - Pin the CLI version explicitly (`uvx google-agents-cli@1.4.1`) and use the same pin
          for every later command. Tell me the version you are actually running.
        - Run `agents-cli scaffold upgrade --dry-run` FIRST and paste the full diff. Stop and
          show me before applying. I specifically want to know whether it touches
          cymbal_navigation_agent/agent.py, pyproject.toml, or tests/eval/eval_config.yaml.
          The scaffold template defaults the model to gemini-3.7-flash — this repo must stay
          gemini-2.5-flash. Flag any attempt to change it.
        - After applying, print the backup path under ~/.agents-cli/backups/ and confirm
          App(name="cymbal_navigation_agent") is UNCHANGED. That string is the dev-ui ?app=
          value and the grading chain depends on it.
      Do NOT take the CLI's other suggestion (`uvx google-agents-cli@0.4.0 deploy`). 0.4.0 has
      no BigQuery support at all, which forfeits Task 4 and the T3 observability tier.

  5b. BIGQUERY ANALYTICS IS CODE, NOT A FLAG. There is no `--bq` flag on `agents-cli deploy` in
      any version — verify this yourself with `agents-cli deploy --help`. `--bq-analytics`
      belongs to `scaffold create`, where it injects a plugin into the generated agent.py. This
      repo was scaffolded without it, so the plugin is absent. Add it to
      cymbal_navigation_agent/agent.py:

        from google.adk.plugins.bigquery_agent_analytics_plugin import (
            BigQueryAgentAnalyticsPlugin, BigQueryLoggerConfig)
        from google.cloud import bigquery

        _project_id = os.environ["GOOGLE_CLOUD_PROJECT"]
        _dataset_id = os.environ.get("BQ_ANALYTICS_DATASET_ID", "adk_agent_analytics")
        bigquery.Client(project=_project_id).create_dataset(
            f"{_project_id}.{_dataset_id}", exists_ok=True)
        _plugins = [BigQueryAgentAnalyticsPlugin(
            project_id=_project_id, dataset_id=_dataset_id,
            location="us-central1",            # NOT GOOGLE_CLOUD_LOCATION
            config=BigQueryLoggerConfig())]

        app = App(root_agent=root_agent, name="cymbal_navigation_agent", plugins=_plugins)

      Two deliberate deviations from the upstream template, do not "correct" them: it reads
      location from GOOGLE_CLOUD_LOCATION, which is `global` here and is NOT a valid BigQuery
      dataset location; and it wraps the whole block in try/except that swallows the resulting
      failure into a logging.warning. Together those give a green deploy with zero rows
      forever. Hardcode a real location and let failures raise.
      DEPENDENCIES. The repo pins bare `google-adk==2.5.0` with no extras, so the plugin's
      pyarrow dependency is absent and the container dies at import with ModuleNotFoundError.
      ADK's own error tells you to install `google-adk[bigquery-analytics]` — that extra DOES
      NOT EXIST in 2.5.0 or 2.6.0. Do not use it, and do not bump the version. Change:
        google-adk==2.5.0   ->   google-adk[gcp,otel-gcp]==2.5.0
      `gcp` supplies pyarrow>=14 (the real source of it in 2.5.0), plus
      opentelemetry-exporter-gcp-trace which OTEL_TRACES_EXPORTER=gcp_trace requires,
      google-cloud-discoveryengine for the Task 5 publish, and google-cloud-bigquery.
      `otel-gcp` supplies opentelemetry-instrumentation-google-genai, which emits the call_llm
      spans — without it Task 6 T1 yields flat traces with no child spans.
      Then `uv sync` and confirm all five resolved before deploying:
        uv pip list | grep -Ei "pyarrow|exporter-gcp-trace|instrumentation-google-genai|cloud-bigquery|discoveryengine"

  5c. DEPLOY. Rule 3 of the deployment skill applies: model gemini-2.5-flash on a us-central1
      manifest, so `GOOGLE_CLOUD_LOCATION=global` is mandatory or model resolution fails.
      Show me `agents-cli deploy --help` and confirm every flag below exists before running:
        uv sync && agents-cli deploy --deployment-target agent_runtime --no-confirm-project \
          --update-env-vars GOOGLE_CLOUD_LOCATION=global,OTEL_TRACES_EXPORTER=gcp_trace,GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true,BQ_ANALYTICS_DATASET_ID=<dataset>
  Show me the command first. This takes several minutes — do not abort, do not re-run, do not
  start a second deploy.
  Write raw stdout/stderr to artifacts/docs/deploy_log.txt and the endpoint URI / resource
  name to artifacts/docs/deploy_report.md. Confirm
  cymbal_navigation_agent/deployment_metadata.json now exists — phases 6 and 7 need it.
  Report the BigQuery dataset and its ACTUAL table names via `bq ls <dataset>` — the lab text
  says `events` in one place and `agent_events` in another, so read the real name rather than
  assuming. Then run and paste `SELECT * FROM <project>.<dataset>.<table> LIMIT 10;`. Zero rows
  before traffic is expected — say so plainly, do not call telemetry verified.
  Then send ONE live query to the deployed agent and re-run COUNT(*). If it is still zero, the
  BigQuery plugin did not initialize — search the deployment logs for "Failed to initialize
  BigQuery Analytics" and for an invalid-location error, and report what you find. Do not move
  on to Phase 6 with a dead analytics pipeline; Task 6's T3 tier depends on it.
  On failure, per SKILL.md: do NOT guess or switch deployment target. Run `gcloud logging read`
  with resource.type="aiplatform.googleapis.com/ReasoningEngine" for the real traceback, fix
  from that evidence, redeploy.

PHASE 6 — PUBLISH  [checkpoint: register to Gemini Enterprise]
  `cat skills/publish/SKILL.md` and follow it, plus `google-agents-cli-publish`. Confirm
  deployment_metadata.json exists and GEMINI_ENTERPRISE_APP_ID is exported as the full path
  ending /engines/apac-track-3. Register INTO that pre-enabled app; do not create a new one.
  The repo README defaults to `cymbal-app` — ignore it, the lab uses apac-track-3.
    agents-cli publish gemini-enterprise --gemini-enterprise-app-id "$GEMINI_ENTERPRISE_APP_ID" \
      --display-name "Cymbal Navigation Agent" \
      --description "AI Travel and Navigation Planner powered by Google Search & Google Maps"
  Write raw output to artifacts/docs/publish_log.txt and the engine/collection details, display
  name, registration type (adk vs a2a), status and agent URL to
  artifacts/docs/publish_report.md. Print the agent URL on its own line.
  Verify independently by LISTING the agents registered under apac-track-3 — do not trust the
  command's own success message.

PHASE 7 — OBSERVABILITY  [checkpoint: live queries & observability]
  `cat skills/observability/SKILL.md` and follow it, plus `google-agents-cli-observability`.
  Send at least 5 live queries to the DEPLOYED agent — not the local playground — covering an
  events search, a Maps place lookup, driving directions, transit directions, and a multi-turn
  exchange. Include "How do I get from SFO Airport to Moscone Center?". Record the traffic
  window timestamps.
  Audit the four tiers the SKILL.md actually names (note the lab text lists only three and
  calls the fourth "FinOps" — the skill's fourth tier is Third-Party Integrations):
    T1 Cloud Trace — verify the `invocation` / `call_llm` / `execute_tool` span hierarchy and
       that otel_to_cloud or automatic Agent Runtime tracing is on. Show one full trace with
       child spans and per-span latency.
    T2 Prompt-Response Logging — report the actual
       OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT mode in effect (NO_CONTENT is the
       default) and LOGS_BUCKET_NAME, read from the deployed config. State what a reader of
       this telemetry can see, and confirm the Maps key appears nowhere in spans, logs or BQ.
    T3 BigQuery Agent Analytics — confirm the dataset (BQ_ANALYTICS_DATASET_ID) and query the
       events table scoped to the traffic window. Paste the SQL and the real rows, event types,
       counts, and which fields are NULL.
    T4 Third-Party Integrations — check for AgentOps/Phoenix/MLflow config and report "none
       configured" if that is the truth. Do not invent one to fill the tier.
  Then the FinOps piece: from the BigQuery events data report input/output token counts per
  request and in aggregate, and the most expensive query type. If token fields are absent, say
  "not captured" rather than estimating.
  Write raw output to artifacts/docs/observability_log.txt and the verified configuration,
  active tiers, privacy settings and status to artifacts/docs/observability_report.md.

FINISH
  Table of all six checkpoints with PASS/FAIL and the strongest evidence for each — 1-3 carried
  over from part 1 (re-check the artifacts on disk, do not just restate them), 4-6 from this
  session. Then `ls -la artifacts/docs/` — expect 7 files: eval_report.md, deploy_log.txt,
  deploy_report.md, publish_log.txt, publish_report.md, observability_log.txt,
  observability_report.md. List anything outstanding.
```

---

## Prompt 3 — Review

```text
Act as an independent verifier for the Cymbal Navigation Agent lab. Another session did the
build in two parts (part 1: setup, preflight, local playground, evaluation; part 2: deploy,
publish, observability). Do not trust either session's summaries — re-verify everything from
live command output and the filesystem, pasting raw output for every claim. Separate what you
OBSERVED from what you ASSUMED. PASS/FAIL per checkpoint. Start by cd-ing into the cloned
cymbal-navigation-agent directory and running `set -a; source .env; set +a`.

CHECKPOINT 1 — PREFLIGHT
  - `agents-cli info` and version >= 1.0.0, raw output. `which agents-cli` resolves. The PATH
    change persists in a shell profile, not just this session. (Note agents-cli is a different
    tool from agy, the Antigravity CLI; the >= 1.0.0 requirement is on agents-cli.) Report BOTH
    versions. uvx may serve a cached older build — if it is not 1.4.1, say which version ran,
    since deploy behaviour differs sharply across 0.4.0 / 0.6.0 / 1.x.
  - Report whether commands print the "project was scaffolded with agents-cli 0.4.0" mismatch
    warning. If they still do after Phase 5, the scaffold upgrade did not complete.
  - Confirm `uvx google-agents-cli setup` actually installed the specialized skills. Locate
    google-agents-cli-eval / -deploy / -publish / -observability on disk and print the paths.
    If absent, the repo's SKILL.md prerequisites were never met — report it.
  - gcloud: active account, working ADC (confirm exit 0, do not print the token), project ==
    lab project.
  - .env has 5 vars, MASKED: GOOGLE_GENAI_USE_VERTEXAI=true, GOOGLE_CLOUD_PROJECT,
    GOOGLE_CLOUD_LOCATION exactly `global` (NOT a region), GOOGLE_MAPS_API_KEY, and
    GEMINI_ENTERPRISE_APP_ID as the FULL path
    projects/<project>/locations/global/collections/default_collection/engines/apac-track-3.
    A bare `apac-track-3` is a FAIL. Flag quotes, trailing whitespace, duplicate keys.
  - .env is gitignored and not stageable in `git status --short`.
  - Re-run `set -a; source .env; set +a; bash scripts/preflight_check.sh`. Paste full output
    and `echo $?`. Confirm all 7 APIs enabled AND the Maps key and GE app ID report as
    exported. The script exits 0 even when those are missing — exit 0 alone is not a pass.
  - THE MAPS KEY ACTUALLY WORKS: curl the two endpoints the tools use —
    maps.googleapis.com/maps/api/place/textsearch/json and /maps/api/directions/json — and
    report the JSON `status` field. Anything but OK (REQUEST_DENIED, API_NOT_ACTIVATED,
    ZERO_RESULTS) is a FAIL. Mask the key.

CHECKPOINT 2 — LOCAL PLAYGROUND
  - Something listening on 8080; dev-ui returns 200; the working URL uses
    ?app=cymbal_navigation_agent (underscores, from App(name=...), not the repo dir and not
    the root agent name cymbal_navigation_planner).
  - Per smoke test: tool invoked, arguments, RAW tool response, final answer.
  - THE CRITICAL CHECK — tools.py has no return statement on any failure path, so a bad key,
    non-200, or empty result all yield None. For every Maps call confirm the raw response was
    a populated dict with "status": "success" and a real formatted_address / distance /
    duration. A None or empty tool response followed by a confident specific answer is a
    HALLUCINATION — flag it loudly. It renders perfectly in the UI.
  - Confirm test 1 invoked BOTH google_search and get_route_directions.

CHECKPOINT 3 — EVALUATION
  - artifacts/docs/eval_report.md exists on disk (ls -la, size, line count).
  - Confirm the run used `--dataset evals/evalset.json`. If it ran against the CLI default
    tests/eval/datasets/basic-dataset.json, the whole evaluation is invalid — check the
    command actually executed.
  - Confirm tests/eval/eval_config.yaml exists with all six names under metrics_to_run, and
    that navigation_accuracy_judge is defined under custom_metrics with a real scoring
    function (print the function). Only five of the six are predefined metrics — if there is
    no custom definition, that metric cannot have run, whatever the report claims.
  - All SIX metrics scored WITH thresholds. Any missing / N/A / skipped is a FAIL — say which
    and why. Confirm the report reads `hallucination` in the correct direction.
  - If final_response_quality or hallucination resolved to _v2 specs, confirm they actually
    graded — v2 needs Gemini 3.5 Flash, unavailable in us-central1. A silently-skipped metric
    here is the most likely failure. Report which spec version each one used.
  - THE RUN WAS REAL: point to artifacts/traces/traces_<ts>.json and artifacts/grade_results/;
    confirm the per-case table row count equals the case count in evals/evalset.json;
    spot-check three cases for real tool calls with real arguments. Investigate suspiciously
    uniform scores. If you cannot evidence a real run, say so — a fabricated report is worse
    than a failing one.
  - Dataset: count before (3) and after. Every new case matches the exact schema
    {eval_case_id, prompt:{role, parts:[{text}]}} — a mismatch causes silent skipping, not an
    error. Map each required category to a case; list uncovered ones.
  - NO SILENT TUNING: `git diff evals/evalset.json` against HEAD. Confirm the 3 original cases
    are intact, no threshold lowered, no metric dropped from the config. Report every change
    to a pre-existing file.

CHECKPOINT 4 — DEPLOY
  - Confirm `--update-env-vars GOOGLE_CLOUD_LOCATION=global` was present. Mandatory for
    gemini-2.5-flash on a us-central1 manifest; without it the deploy can succeed and then fail
    model resolution at invocation. Confirm NO `--bq` flag was passed — it does not exist on
    deploy, and a command containing it did not run. Quote the exact command executed.
  - CONTAINER MIGRATION: confirm a Dockerfile now exists in the project root and that it came
    from `agents-cli scaffold upgrade`, not hand-authored. Print the backup path under
    ~/.agents-cli/backups/. Then `git diff <pre-upgrade-commit> -- cymbal_navigation_agent/agent.py`
    and confirm App(name="cymbal_navigation_agent") survived and the model is still
    gemini-2.5-flash, not the scaffold default gemini-3.7-flash. Confirm the deploy did NOT
    fall back to `uvx google-agents-cli@0.4.0`, which has no BigQuery support at all.
  - BIGQUERY PLUGIN: confirm BigQueryAgentAnalyticsPlugin is actually constructed in agent.py
    AND passed to App(plugins=...). Print those lines. Confirm its `location` is a valid
    BigQuery location and is NOT reading GOOGLE_CLOUD_LOCATION (which is `global` — invalid,
    and the usual cause of a silently empty dataset). Confirm there is no try/except swallowing
    initialization failure into a warning. Confirm google-cloud-bigquery is in pyproject.toml.
    If the plugin is absent, Task 4 and observability tier T3 cannot pass regardless of what
    any report claims — say so.
  - DEPENDENCIES: confirm pyproject.toml reads `google-adk[gcp,otel-gcp]==2.5.0`. A bare
    `google-adk==2.5.0` means the container will die at import on missing pyarrow. Confirm
    nobody added the nonexistent `bigquery-analytics` extra that ADK's error message suggests,
    and that the version was not bumped off 2.5.0. Then paste
      uv pip list | grep -Ei "pyarrow|exporter-gcp-trace|instrumentation-google-genai|cloud-bigquery|discoveryengine"
    and confirm all five are installed.
  - CONTAINER ACTUALLY STARTED: a successful CLI exit is not proof. Read
    reasoning_engine_stderr for this deployment and confirm a clean uvicorn startup with no
    ImportError or traceback.
  - CREDENTIAL HYGIENE: `agents-cli deploy` echoes an "Environment Variables:" block with
    GOOGLE_MAPS_API_KEY in plaintext. Grep artifacts/docs/deploy_log.txt and every other
    artifact for the key. If present, report a leak and tell me to rotate.
  - artifacts/docs/deploy_log.txt and deploy_report.md exist with real identifiers. Grep for
    PROJECT_ID / DATASET_NAME / <agent-id> placeholders.
  - cymbal_navigation_agent/deployment_metadata.json exists — print it.
  - List Agent Runtime / Reasoning Engine instances; ours appears, state active (not
    CREATING/FAILED), region reported.
  - `bq ls` shows the dataset; `bq ls <dataset>` shows the real table name — report whether it
    is `events` or `agent_events`, since the lab text says both. `bq show` for the schema. Run
    SELECT * … LIMIT 10 plus COUNT(*) and paste real rows. Empty is not automatically a pass.
  - Send one query to the DEPLOYED agent, re-run COUNT(*), confirm it increased.

CHECKPOINT 5 — PUBLISH
  - Command matches skills/publish/SKILL.md including --display-name and --description.
  - LIST agents registered under the apac-track-3 engine; confirm ours appears. Confirm the
    app ID resolved to the full path ending /engines/apac-track-3, that no NEW app was
    created, and that it did not default to `cymbal-app` from the README — any of those is a
    FAIL.
  - Confirm the registration points at the same resource as deployment_metadata.json — quote
    both. A stale pointer serves the wrong agent while looking fine.
  - State is published/enabled, not draft. Report registration type (adk vs a2a).
  - publish_log.txt and publish_report.md exist with the real agent URL; report the URL and its
    HTTP status.
  - Run "How do I get from SFO Airport to Moscone Center?" against the PUBLISHED agent and
    confirm get_route_directions was actually invoked and returned real data. If you cannot
    invoke it programmatically, say so and give the Console click-path — do not claim a preview
    you did not run.

CHECKPOINT 6 — OBSERVABILITY
  - Confirm the 5+ queries hit the DEPLOYED runtime, not 127.0.0.1:8080 — state how you can
    tell. Local traffic produces zero Cloud Trace and zero BigQuery rows, and the audit then
    describes stale or empty data. This is the most common shortcut.
  - T1: paste raw span output. Confirm the invocation / call_llm / execute_tool hierarchy. A
    single flat span per request means tool-level instrumentation is not working even though
    traces "exist" — that is a FAIL.
  - T2: report the actual OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT mode and
    LOGS_BUCKET_NAME read from the deployed configuration, not the default you assume. Grep
    spans, logs and BQ fields for the Maps key; if present, report a credential leak and tell
    me to rotate.
  - T3: paste actual SQL and actual rows. Confirm timestamps fall inside the traffic window —
    old rows do not verify today's deploy. Report all-NULL fields. An empty table here almost
    always means BigQueryAgentAnalyticsPlugin never initialized (invalid `global` location, or
    the plugin was never added to App(plugins=...)) rather than an absence of traffic — check
    deployment logs for "Failed to initialize BigQuery Analytics" before concluding otherwise.
  - T4: report third-party integrations or "none configured" if that is the truth.
  - FinOps: confirm token counts came from telemetry rows, not an estimate. Quote the SQL. If
    token fields are absent, "not captured" is correct — flag any invented number. Recompute
    any cost arithmetic; flag unsourced prices.
  - observability_log.txt and observability_report.md exist, a section per tier, raw evidence.

CROSS-CUTTING
  - `ls -la artifacts/docs/` — all 7 files present, none overwritten by a later phase.
  - Consistency table across artifacts: Agent Runtime resource name | BigQuery dataset | GE app
    ID. Any mismatch means one document is stale.
  - Grep every artifact for unsubstituted placeholders and for the raw API key.
  - Re-run the deployed-agent smoke query and the events query to confirm the pipeline is live
    right now.

OUTPUT
  Six-row table: Checkpoint | PASS/FAIL | strongest evidence. Then severity-ordered remediation
  with exact commands. State plainly anything you could not verify, any step skipped, and any
  setting loosened during troubleshooting. Do not soften a failure.
```
