# policy-rag

FAISS-backed grounded retrieval over the Altostrat Singapore employee handbook
and its OKF v0.2 bundle, served to other agents over the A2A protocol.

This is the retrieval substrate behind the Policy Specialist of
[SDD](../../../Enterprise%20Agentic%20Solution%20Design%20Document%20-%20MVP%201.md) §3.2.
It answers only what the corpus says, cites every claim, and refuses or escalates
when it cannot — the design premise is that a confidently wrong HR answer costs
far more than a missed one (BRD NFR-3.1, "0% hallucination on policy figures").

It sits inside the grounding package as the second `BaseRAGPipeline` backend,
alongside the deferred Vertex AI Search adapter — see
[Using it from the rest of the codebase](#using-it-from-the-rest-of-the-codebase).

---

## What is ingested

Two corpora, declared in [`config/corpus.yaml`](../../../config/corpus.yaml) and nowhere else:

| Corpus id | Source | Authority | In default search? |
| :--- | :--- | :--- | :--- |
| `okf-handbook` | [`okf/altostrat-sg-handbook/`](../../../okf/altostrat-sg-handbook/) | `governing` | yes |
| `handbook-source` | [the raw handbook](../../../ALTOSTRAT%20SINGAPORE%20EMPLOYEE%20POLICY%20HANDBOOK%20&%20CONDUCT%20GUIDELINES.md) | `source` | no |

Both are indexed; only the OKF bundle is searched by default. The raw handbook
restates most leave and ethics content twice at two different levels of detail,
and the OKF bundle exists precisely to apply the datasheet's detail-layer-wins
precedence rule. Searching both together would reintroduce the conflict the
bundle resolves. A caller that genuinely needs verbatim source text asks for
`handbook-source` by corpus id.

Current index: **480 chunks from 81 documents** (306 OKF, 174 handbook sections).

## Quickstart

Every command runs from the **repo root** — the corpus paths in `corpus.yaml` and
the index location are both resolved relative to it.

```bash
python -m venv .venv && .venv/bin/pip install -e ".[local-embeddings]"

rag=".venv/bin/python -m src.grounding.policy_rag.cli"
$rag ingest                 # build var/index/ (downloads the embedding model once)
$rag query "How many vacation days after 8 years of service?"
$rag serve --port 8080      # A2A server
```

| Command | Purpose |
| :--- | :--- |
| `ingest` | Build `faiss.index` + `chunks.jsonl` + `manifest.json`, then run canary probes |
| `query` | Full retrieve → guard → compose path, with citations |
| `search` | Retrieval only — no guards, no composition. Useful for debugging relevance |
| `stats` | Chunk counts, corpus breakdown, embedder fingerprint, build time |
| `drift` | Sources whose digest no longer matches the one recorded at build time |
| `serve` | The A2A server |

`ingest` refuses to finish if a canary probe fails to retrieve its expected
document — a silent embedding or chunking regression that only shows up in
production answers is the failure mode that gate exists to prevent.

## Architecture

```
corpus.yaml ─┬─> loaders ──> documents ──> chunking ──> embeddings ──> PolicyIndex (FAISS)
             │                (OKF frontmatter,          (BGE-small,     IndexFlatIP
             │                 handbook section split)    asymmetric)    in IndexIDMap2
             │
             └─> ACL map (entitlement per path prefix)
                                                              │
  A2A JSON-RPC ──> executor ──> PolicyRagService ──> retriever ┘
  (entitlements       │              │                 (dense + lexical, ACL filter)
   from header)       │              ├──> guards        (5 corpus-datasheet rules)
                      │              └──> answer        (extractive | Gemini, groundedness gate)
                      └──> artifact: text part + JSON data part
```

**Index.** `IndexFlatIP` wrapped in `IndexIDMap2`, over L2-normalised vectors —
so inner product *is* cosine, and it is exact rather than approximate. At 480
chunks an ANN structure buys nothing, and `IndexIDMap2` supports `remove_ids`,
which is what the SLA-04 stale-embedding eviction path needs. `IndexHNSWFlat` is
configured and selectable (`index.type: hnsw`) for when the corpus outgrows
exact search, somewhere north of ~100k chunks.

**Chunking** follows markdown heading boundaries first and only splits on size
when a single section exceeds `max_chars`. A policy answer that straddles a
heading is worse than a slightly long chunk.

**Retrieval** is hybrid: a dense bi-encoder score plus IDF-weighted lexical term
overlap. Over-fetch to `candidate_k: 60` happens *before* the ACL, corpus and
doc-type filters, because FAISS cannot express those predicates and they have to
be applied to the candidate list.

**Two scores, deliberately.** Hits are *ordered* by an uncalibrated fusion and
*gated* on the calibrated one. Calibration clips at `cosine_ceiling`, which is
what makes the score comparable to the SDD's fixed 0.80 threshold — but it also
flattens every strong hit to exactly 1.0, and sorting on a flattened score
discards precisely the resolution that decides which passage leads the answer.
Early on this pushed the best passage for a payout question to rank 8, outside
`top_k`, behind seven others tied at 1.000.

## The two gates

SDD §3.3 Path 1 requires both to pass:

| Gate | Threshold | Where |
| :--- | :--- | :--- |
| Retrieval relevance | ≥ 0.80 | `retrieval.relevance_gate` in `corpus.yaml` |
| Groundedness | ≥ 0.85 | `GROUNDEDNESS_GATE` in `answer.py` |

The extractive composer quotes retrieved text verbatim, so its groundedness is
1.0 by construction — it cannot hallucinate, only fail to answer. The Gemini
composer generates under a grounding instruction and then has its output
*measured* against the retrieved content words; below 0.85 the generated answer
is discarded and the caller gets a refusal, not a hedge.

Citations are resolved, not asserted: every cited URI is checked against the
chunk it came from before the answer goes out.

## Guards

Five rules, each traceable to a line in the corpus datasheet's *"What must not be
answered from this bundle"*:

| Reason code | Trigger | Outcome |
| :--- | :--- | :--- |
| `absent_section` | Query names a handbook section the source does not contain | escalate |
| `extended_workforce_leave` | Contractor/temp/vendor + a leave topic | escalate |
| `source_conflict` | The top-ranked passage *is* a `# Conflict` note | escalate |
| `no_hits` | Nothing cleared the relevance gate | refuse |
| `groundedness_gate` | Generated answer failed the groundedness measurement | refuse |

Plus advisory notices that ride along with an answer rather than blocking it:
gap sections, `stale_after` expiry, `draft` status, and conflicts that matched
below the top rank.

`absent_section` deserves a note. When a question names a section the handbook
skips, the honest response is not "there is no such rule" — the gap is not
evidence that the topic is unregulated, it is evidence that we do not know. The
guard says exactly that and routes to People Ops.

**Known limitation.** The `source_conflict` trigger is "the best-matching passage
is the Conflict note". Widening it to "any Conflict section of the answering
document matched" was tried and over-fires: a concept file can cover two rules
and be contested on only one, so a procedural question about the sound rule got
escalated on the strength of its neighbour. The residual risk is the reverse — a
question about a contested point, phrased so the policy text outranks the
Conflict note, is answered with a caveat instead of escalated. The durable fix is
to match the query against the source defect register rather than relying on
chunk ranking. It is not done.

## Entitlements (SDD §4.1 / §4.7)

The ACL filter runs at query time, on entitlements taken from **the verified
caller, never the payload**. `references/` — the defect register and executor
procedures — requires `hr_operational`; everything else is `general`.

Over A2A, entitlements arrive in the `X-Altostrat-Entitlements` header, set by
the gateway that authenticated the principal. A payload field claiming
entitlements is ignored and logged. This is the same reasoning SDD §4.1 applies
to `employee_id`: in an agent-to-agent chain the message body may have been
composed by an LLM acting on text an employee typed, so it cannot be the source
of an authorisation decision. `POLICY_RAG_TRUST_PAYLOAD_ENTITLEMENTS=1` relaxes
this for local development against a server with no gateway in front.

## A2A usage

```bash
python -m src.grounding.policy_rag.cli serve --port 8080 --public-url https://policy-rag.internal
```

| Endpoint | |
| :--- | :--- |
| `GET /.well-known/agent-card.json` | discovery |
| `POST /` | A2A JSON-RPC |
| `GET /healthz` | liveness, index-aware |

Three skills, named in `message.metadata.skill`:

| Skill | Returns |
| :--- | :--- |
| `policy_answer` | Composed answer, decision, citations, notices (default) |
| `policy_search` | Ranked chunks with scores and citations, no composed prose |
| `corpus_status` | Chunk counts, embedder fingerprint, build time, drift |

Every response is one artifact with two parts: a `text/plain` part for a human
or an LLM to read, and an `application/json` data part with the structured
result for a programmatic caller.

Both JSON-RPC method vocabularies are accepted — the spec names (`message/send`,
`tasks/get`) and the SDK's native gRPC-style ones (`SendMessage`, `GetTask`).
Consumers of this knowledge base are other teams' agents, and which A2A client
generation they are on is not ours to dictate.

Parameters may be sent in `message.metadata`, in `MessageSendParams.metadata`, or
as a JSON data part; all three are merged. Entitlements are the one exception —
header only.

```bash
python -m src.grounding.policy_rag.a2a_app.client_demo --url http://127.0.0.1:8080 \
    --skill policy_answer "How many vacation days after 8 years?"

python -m src.grounding.policy_rag.a2a_app.client_demo --url http://127.0.0.1:8080 \
    --skill policy_search --entitlement hr_operational --json "source defect register"
```

Raw JSON-RPC, for a client that is not using the a2a-sdk:

```bash
curl -s http://127.0.0.1:8080/ \
  -H 'content-type: application/json' \
  -H 'x-altostrat-entitlements: general' \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{
        "role":"user","messageId":"m1",
        "parts":[{"text":"How many vacation days after 8 years?"}],
        "metadata":{"skill":"policy_answer"}}}}'
```

## Evaluation

```bash
PYTHONPATH=. python eval/run_policy_rag_eval.py                  # score at the configured gate
PYTHONPATH=. python eval/run_policy_rag_eval.py --show-failures  # with per-question detail
PYTHONPATH=. python eval/run_policy_rag_eval.py --sweep          # gate 0.40 → 0.95
PYTHONPATH=. python eval/run_policy_rag_eval.py --min-pass-rate 0.85  # CI mode, non-zero exit
```

45 golden questions in [`eval/golden/policy_rag_golden.json`](../../../eval/golden/policy_rag_golden.json),
each declaring the *expected disposition* — `answer` (with the paths that must be
retrieved), `escalate`, or `refuse` — not just an expected string. Measuring
refusal and escalation as first-class outcomes is the only way the harness can
tell "correctly declined" apart from "failed to retrieve".

Current, at gate 0.80:

```
overall            41/45
recall@1           78.79%
recall@k           87.88%
MRR                0.828
answer accuracy    87.88%
escalate accuracy  100.00%
refusal accuracy   100.00%
```

All four failures (`g-ethics-02`, `g-workplace-04`, `g-workplace-07`,
`g-peopleops-04`) are over-conservative refusals: the corpus contains the answer
and retrieval did not clear the gate. There are no wrong answers and no missed
escalations, which is the direction the failures should point.

### Calibrating the relevance gate

The gate stays pinned at the SDD's 0.80. What moves is the calibration that maps
raw cosine onto the [0,1] relevance scale — `cosine_floor` and `cosine_ceiling`
in `corpus.yaml`. This is the right way round: moving the gate to fit whatever
the model happens to score would make the SDD's threshold a number that means
nothing.

`--sweep` is how the pair is derived, and it **must be re-run whenever
`embedding.model` changes** — the values are model-specific and silently wrong
across a swap.

The current `(0.55, 0.72)` was chosen over `(0.45, 0.72)`, which tied it on
overall pass rate. `(0.45, 0.72)` held refusal accuracy at only 66.7%; the looser
floor let genuinely-absent topics score high enough to be answered. NFR-3.1
settles that trade: a wrong answer costs more than a missed one.

### Choosing the embedding model

`BAAI/bge-small-en-v1.5`, over `all-MiniLM-L6-v2` — same 384 dimensions, roughly
the same CPU cost. Measured on the golden set, BGE held 84.8% answer accuracy
down to gate 0.75 where MiniLM had collapsed to 42.4%, and reached 100% escalate
accuracy.

The failure that prompted the switch is worth recording. Under MiniLM every
canary probe was rejected, best relevance 0.501–0.736 against a 0.80 gate — yet
the correct document was rank 1 in all six. The ranking was right and the *scale*
was wrong, and no amount of gate-tuning fixes that.

The other half of the fix was the fusion formula. Dense and lexical scores had
been combined as a weighted average, which *penalises* a passage for stating the
rule in words the question did not use — exactly what a well-written policy
document does. Lexical overlap is now a bounded corroboration bonus
(`dense + boost · lexical · (1 - dense)`): it can only raise a score, in
proportion to the headroom left, and saturates at 1.0. See `Retriever._fuse`.

BGE and E5 are asymmetric models and need a query-side instruction prefix; the
prefixes live in `embeddings.py`, keyed on model name. Getting this wrong
degrades retrieval quietly rather than loudly.

## Tests

```bash
python -m pytest tests/policy_rag        # 312 tests
python -m pytest --cov                   # 100% statement and branch, whole repo
```

The suite runs on the `hash` embedding provider — deterministic hashed n-grams,
no model download, no network. Retrieval *quality* is therefore not testable
there and is not tested there; that is what `eval/run_policy_rag_eval.py` is for.
These tests cover the plumbing, the ACL filter, the guards and the A2A surface,
all of which are model-independent. The A2A tests are real JSON-RPC round trips
over httpx's ASGI transport, with no port bound.

Fixtures live in `tests/policy_rag/conftest.py` rather than the suite-wide
`tests/conftest.py`, because names like `config`, `index` and `service` read
naturally here and ambiguously in a suite that also covers the HCM, ITSM and Saga
agents.

## Using it from the rest of the codebase

`src/grounding/faiss_pipeline.py` wraps the service in
[`BaseRAGPipeline`](../rag_boilerplate.py), the same interface
`VertexAISearchRAGBoilerplate` declares and defers. A caller written against that
interface can be pointed at either backend without changing:

```python
from src.grounding import faiss_policy_rag

if faiss_policy_rag.is_ready:
    chunks = await faiss_policy_rag.semantic_search(
        "How many vacation days after 8 years?",
        top_k=5,
        entitlements=["general"],      # from the verified caller, never the payload
    )
```

Two things a caller has to know, both of which are properties of *this* corpus
rather than of the interface:

* Results are already gated at `relevance_gate`, so `[]` means "nothing in the
  corpus is a good enough match" — a refusal signal (BRD FR-5.4), not an error.
* `index_documents` takes corpus **ids** from `corpus.yaml`, not GCS URIs, and an
  undeclared id raises rather than silently indexing nothing. Nothing may
  introduce a corpus at runtime.

`FaissPolicyRAG` is exported lazily from `src.grounding`, so importing the
package does not pull in faiss, numpy and sentence-transformers for callers that
only want the OKF store.

The richer surface — guards, composed answers, citation resolution, notices — is
on `PolicyRagService` and over A2A. `BaseRAGPipeline` is deliberately just
retrieval; a caller that needs a *decision* rather than passages should use one
of those two.

## Configuration

Everything is in [`config/corpus.yaml`](../../../config/corpus.yaml), which is the single
declaration of what is ingested, how it is chunked and embedded, and which
entitlement is required to retrieve it — the same discipline SDD §3.2 applies to
the agent/tool registry. Nothing may add a corpus at runtime.

Embedding providers: `local` (sentence-transformers, CPU, no credentials),
`vertex` (Vertex AI, for parity with the SDD target platform), `hash` (CI).
Override with `POLICY_RAG_EMBEDDING_PROVIDER`.

The index records the embedder fingerprint in its manifest and refuses to serve
if a different embedder is loaded against it, rather than returning quietly
meaningless neighbours.

## Requirement traceability

| Requirement | Where |
| :--- | :--- |
| BRD FR-1.5 (RBAC) | `retriever.py` ACL filter, `executor.py` header binding |
| BRD FR-5.1–5.3 (retrieve, cite, ground) | `retriever.py`, `answer.py` citations |
| BRD FR-5.4 (refuse rather than guess) | `guards.py`, both gates |
| BRD FR-5.5 (corpus provenance) | `corpus_status` skill, `manifest.json`, `drift` |
| BRD NFR-3.1 (0% hallucination) | extractive composer + groundedness gate + eval harness |
| SDD §3.3 Path 1 (dual gate) | `relevance_gate` 0.80 ∧ `GROUNDEDNESS_GATE` 0.85 |
| SDD §4.1 (subject from session) | `resolve_entitlements` — header, never payload |
| SDD §4.7 (query-time ACL) | `references/` → `hr_operational` |
| SLA-04 (stale embedding eviction) | `IndexIDMap2.remove_ids`, `drift` command |

## Known gaps

- `source_conflict` relies on chunk ranking rather than the defect register — see
  *Known limitation* above.
- Four golden questions retrieve below the gate. They fail safe, but they fail.
- A corpus republish needs a restart: the index is loaded once at startup as an
  immutable artefact. Rolling deploy or bust.
- The Gemini composer path is implemented but the measured numbers above are all
  from the extractive composer.
