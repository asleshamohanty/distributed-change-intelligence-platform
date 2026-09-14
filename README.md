# Distributed Change Intelligence Platform

**A developer-facing investigation system that correlates code changes, service
dependencies, runtime telemetry, and historical incidents into evidence-backed
failure investigations — without ever claiming to know the root cause.**

`Python` · `FastAPI` · `PostgreSQL + pgvector` · `Docker` · `MCP` · `scikit-learn` · `NetworkX` · `Gemini`

---

## Table of contents

1. [What this is](#what-this-is)
2. [The problem](#the-problem)
3. [What this demonstrates](#what-this-demonstrates)
4. [Architecture](#architecture)
5. [The complete data pipeline](#the-complete-data-pipeline)
6. [Tech stack](#tech-stack)
7. [Deep dive: dependency graph & blast radius](#deep-dive-dependency-graph--blast-radius)
8. [Deep dive: observability & telemetry](#deep-dive-observability--telemetry)
9. [Deep dive: machine learning — anomaly detection](#deep-dive-machine-learning--anomaly-detection)
10. [Deep dive: historical incident retrieval](#deep-dive-historical-incident-retrieval)
11. [Deep dive: MCP tool layer](#deep-dive-mcp-tool-layer)
12. [Deep dive: LLM reasoning & structured outputs](#deep-dive-llm-reasoning--structured-outputs)
13. [Database schema](#database-schema)
14. [Repository structure](#repository-structure)
15. [Setup & running](#setup--running)
16. [Demo scenarios](#demo-scenarios)
17. [Testing](#testing)
18. [Responsible framing](#responsible-framing)
19. [Engineering decisions & tradeoffs](#engineering-decisions--tradeoffs)
20. [Known limitations](#known-limitations)
21. [Phase 2 roadmap](#phase-2-roadmap)
22. [Glossary](#glossary)

---

## What this is

Every backend/platform engineer eventually has to answer the same expensive
question during an incident: **"Something broke — what changed, what could
it have affected, and what evidence do we actually have?"**

Today that answer lives scattered across GitHub, CI/CD, Kubernetes,
Prometheus, raw logs, and old incident tickets. Correlating them by hand,
under time pressure, is exactly the kind of toil an observability tool
should remove.

This system automatically correlates five signal types — **code changes,
service dependencies, deployment events, runtime telemetry, and historical
incidents** — and hands an engineer a structured investigation view instead
of a black-box guess. Each layer has one deterministic job (graph traversal,
anomaly scoring, similarity search); a thin LLM layer on top only
*synthesizes* evidence those deterministic layers already produced. **The
LLM never invents facts — it only reasons over facts it retrieved through
typed MCP tool calls**, and its output is structurally incapable of stating
a bare "root cause."

This is Phase 1: a complete, working system running locally via a single
`docker compose up --build` — no Kubernetes required. See
[Phase 2](#phase-2-roadmap) for what's deliberately deferred.

## The problem

```
Frontend → API Gateway → Order Service → Inventory Service → Database
                                        → Payment Service   → External API
```

A developer changes the Order Service and deploys it. Twenty minutes later,
API latency rises, Inventory requests begin failing, downstream error rates
climb, and an incident is opened. The on-call engineer has to manually
answer six questions:

1. What actually changed?
2. Which services depend on the changed service?
3. Which downstream services could realistically be affected?
4. Did the failure begin after the deployment, or was it already happening?
5. Which telemetry signals actually moved?
6. Has something like this happened before?

This system answers all six automatically, and hands an engineer a
prioritized, evidence-backed starting point rather than eleven browser tabs.

## What this demonstrates

One project, six separable competency areas — each backed by a real,
running component, not a slide:

| Competency             | Demonstrated by |
| ----------------------- | ---------------- |
| Software engineering    | FastAPI REST APIs, layered service architecture, inter-service HTTP communication, relational + vector data modeling |
| Distributed systems     | 4-service mesh with explicit dependencies, cascading failure propagation, deployment-event correlation |
| DevOps                  | Docker, Docker Compose, real Prometheus, multi-container orchestration |
| Machine learning        | Feature engineering over time-series telemetry, unsupervised anomaly detection, a real training-methodology bug found and fixed |
| Applied AI               | Real MCP server/client, Gemini tool-calling, schema-constrained structured outputs |
| Databases                | PostgreSQL relational modeling *and* pgvector similarity search in the same store |


## Architecture

Every layer has exactly one job. The UI never talks to Prometheus or
Postgres directly — everything goes through the FastAPI orchestration
layer.

```
                          +---------------------+
                          |     Static UI         |  http://localhost:8000/
                          +----------+------------+
                                     |  fetch()
                                     v
                          +---------------------+
                          |   FastAPI backend      |  orchestration — the only
                          |   (:8000)               |  thing the UI talks to
                          +----------+------------+
                                     |
      +---------------+-------------+-------------+----------------+
      v               v                            v                v
Change Service   Graph Service              Telemetry Service   Incident Service
      |               |                            |                |
      v               v                            v                v
  Postgres      NetworkX DiGraph              Prometheus       Postgres + pgvector
 (changes,      (rebuilt in-memory              (scrapes the        (incidents +
 deployments)    from `dependencies`             demo mesh's         Gemini embeddings,
                 edge-list table)                /api/metrics)       cosine similarity)
                                                       |
                                                       v
                                              Isolation Forest
                                            (scikit-learn, trained
                                             at Docker build time on
                                             synthetic baseline data)
                                                       |
                                                       v
                                             Investigation Layer
                                          (aggregates change + graph +
                                           telemetry + anomaly + history
                                                into one object)
                                                       |
                                                       v
                                               +---------------+
                                               |  MCP Server    |  own container,
                                               |  (:8100)        |  Streamable HTTP,
                                               +-------+-------+  6 typed tools
                                                       ^
                                                       | MCP client (async)
                                                       |
                                              Gemini tool-calling loop
                                           -> InvestigationResult (Pydantic,
                                              schema-enforced, no root_cause
                                              field)


 Demo microservice mesh — the thing actually being investigated:

   gateway --> order-service --+--> inventory-service --> "database"   (edge only,
                                |                                        not a live
                                +--> payment-service    --> "external-api" service)

 Each demo service exposes /api/metrics (Prometheus text format); Prometheus
 scrapes all four every 5s. A background load-generator container keeps a
 steady ~3 req/s trickle of checkout traffic flowing, so the anomaly model's
 baseline reflects real steady-state behavior instead of an idle container.
```

| Layer | Responsibility |
| ------- | ---------------- |
| Static UI | Renders the overview, dependency graph, evidence timeline, and investigation summary |
| FastAPI backend | Orchestrates every request; the only layer the UI talks to |
| Change Service | Ingests commit/deploy events, stores change metadata |
| Graph Service | Maintains the directed service-dependency graph; computes blast radius |
| Telemetry Service | Queries Prometheus and normalizes metrics into the anomaly model's feature vector |
| Anomaly Model | Isolation Forest scoring each service's current metrics vs. baseline |
| Incident Service | Embeds + stores incidents, runs pgvector similarity search |
| Investigation Layer | Aggregates change + graph + telemetry + anomaly + history into one object |
| MCP Server | Exposes the above as six callable, typed tools instead of raw data access |
| LLM Reasoning | Synthesizes retrieved evidence into a structured, schema-constrained hypothesis |

## The complete data pipeline

This is the single most important thing to be able to walk through in an
interview — the entire project, one stage at a time, with real output from
an actual run of this system.

**1. Commit + deploy** — `POST /api/events/generate-demo-deploy` records a
change to `order-service`:

```json
{"change_id": "62eb3136-...", "service": "order-service",
 "commit_sha": "15fc133", "files_changed": ["payment_client.py", "order_service.py"]}
```

**2. Graph lookup + blast radius** — `graph_service` resolves
`order-service`'s downstream dependencies via `nx.descendants()`, enriched
with BFS distance:

```json
{"changed_service": "order-service",
 "potentially_impacted": [
   {"service": "inventory-service", "dependency_distance": 1},
   {"service": "payment-service", "dependency_distance": 1},
   {"service": "database", "dependency_distance": 2},
   {"service": "external-api", "dependency_distance": 2}
 ]}
```

**3. Telemetry** — `telemetry_service` pulls live latency/error-rate/CPU/memory
for each impacted service from Prometheus.

**4. Anomaly scoring** — the Isolation Forest scores each service's current
feature vector against its baseline. With latency injection active on
inventory-service, real output from this system:

```json
{"service": "inventory-service", "is_anomalous": true, "driving_metric": "latency_ms",
 "telemetry": {"latency_ms": 1932.6, "error_rate": 0.0, "request_rate": 0.42,
               "cpu_percent": 0.39, "memory_mb": 49.7}}
```

**5. Incident retrieval** — the evidence gathered so far is embedded and
matched against stored incidents via pgvector cosine similarity; the seeded
"Order Service deploy caused Inventory Service latency spike" incident comes
back at ~0.89 similarity.

**6. Aggregation** — the Investigation Layer merges all of the above into
one object.

**7. MCP + LLM** — Gemini calls the six MCP tools, then produces a
structured hypothesis. Real output from this system, captured mid-latency-injection:

```json
{
  "summary": "Deployment 62eb3136 of order-service, modifying payment_client.py and order_service.py, preceded an increase in latency in order-service, inventory-service, and the gateway. Anomalies were detected in these services while payment-service remained within normal operational parameters.",
  "hypotheses": [
    {
      "statement": "The latency observed in order-service and downstream dependencies may be related to the recent code changes in payment_client.py or order_service.py.",
      "supporting_evidence": [
        {"source": "get_change_details", "detail": "Deployment 62eb3136 modified order_service.py and payment_client.py immediately prior to the observed anomalies."},
        {"source": "get_anomalies", "detail": "order-service and inventory-service are identified as anomalous with high latency readings."}
      ],
      "limitations": [
        "The current evidence establishes a temporal relationship but does not confirm causation.",
        "The anomaly in inventory-service may be a reflection of order-service latency or an independent issue."
      ]
    },
    {
      "statement": "The system may be experiencing a cascade effect triggered by the order-service deployment.",
      "supporting_evidence": [
        {"source": "get_dependency_graph", "detail": "The gateway depends on order-service, and order-service depends on inventory-service."},
        {"source": "get_anomalies", "detail": "gateway, order-service, and inventory-service all show anomalous latency simultaneously."}
      ],
      "limitations": [
        "This data does not rule out a common infrastructure issue affecting multiple services simultaneously.",
        "The evidence does not explain why payment-service remains stable despite being a primary dependency of order-service."
      ]
    }
  ]
}
```

Note what's *absent*: no field, anywhere, states a single confirmed root
cause. Every claim is hedged, cited, and paired with its own limitations —
by construction, not by the model's discretion.

**8. UI** — the dashboard renders the dependency graph, evidence timeline,
and this synthesized summary side by side.

## Tech stack

| Category | Technology | Why |
| ---------- | ------------ | ----- |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy | Async-friendly, typed, fast to build REST APIs and schemas |
| Database | PostgreSQL + pgvector | One database for relational data *and* vector similarity search — no second system |
| Graph | NetworkX | In-memory directed graph + traversal; simpler to build and explain than a dedicated graph DB at this scale |
| ML | scikit-learn (Isolation Forest) | Unsupervised, explainable, no labeled incident data required |
| AI / Orchestration | Gemini API, MCP, Pydantic structured outputs | Standardized tool access; forces evidence-grounded, schema-validated responses |
| Observability | Prometheus | Industry-standard metrics scraping and query API |
| Infrastructure | Docker, Docker Compose | Local-first development that mirrors a real deployment path |

**Deliberately not used:** Neo4j or any graph database (Postgres +
NetworkX answers every query this project needs, at far lower operational
cost); a second vector database (pgvector lives in the same Postgres
instance); a message queue (nothing here is async-workload-shaped enough to
need one); Kubernetes in Phase 1 (see [Phase 2](#phase-2-roadmap)).

## Deep dive: dependency graph & blast radius

The dependency graph is a directed graph where an edge `order-service →
inventory-service` means *Order calls Inventory*. It's persisted as a plain
Postgres edge-list table (`dependencies`) and rebuilt into an in-memory
`networkx.DiGraph` on every request that needs it:

```python
def load_graph(db: Session) -> nx.DiGraph:
    graph = nx.DiGraph()
    for edge in db.query(Dependency).all():
        graph.add_edge(edge.source_service_id, edge.target_service_id)
    return graph
```

**Blast radius** is the set of nodes reachable by following directed edges
forward from a changed node — everything that *could* be affected, not
everything that *definitely was*:

```python
def get_blast_radius(graph, changed_service):
    return nx.descendants(graph, changed_service)
```

Rebuilding on every call (rather than caching) is a deliberate choice at
this scale (single-digit node count, sub-millisecond query): it avoids an
entire class of "the graph went stale after an edge changed" bugs, and
Postgres stays the unambiguous source of truth.

Blast radius alone returns a flat set. It's enriched with **BFS dependency
distance** (`nx.shortest_path_length`) so an engineer can prioritize instead
of investigating every downstream service at once — verified against the
mesh's actual topology:

```
order-service's blast radius:
  inventory-service   — distance 1
  payment-service     — distance 1
  database            — distance 2
  external-api        — distance 2
```

**Wording discipline, enforced throughout the codebase and the LLM's system
prompt:** always "potentially impacted," never "affected" or "broken."
Graph reachability is a hypothesis space, not a diagnosis.

## Deep dive: observability & telemetry

A real Prometheus container (not a mock) scrapes all four demo mesh
services every 5 seconds on `/api/metrics`. Each service instruments itself
with `prometheus_client`:

- `http_requests_total{method, path, status}` — a `Counter`, labeled per
  request
- `http_request_duration_seconds{method, path}` — a `Histogram`
- `process_cpu_usage` / `process_memory_usage` — custom `Gauge`s, sampled
  from Python's stdlib only (`resource.getrusage()` for a CPU-time delta
  between scrapes, `/proc/self/status`'s `VmRSS` for resident memory) — no
  `psutil` dependency needed for a demo at this scale

The backend's `telemetry_service` queries Prometheus's **HTTP query API**
rather than scraping the mesh directly — the same separation of concerns a
real production Investigation API would have from its metrics store. Each
mesh service's scrape job is named after the service itself, so Prometheus's
built-in `job` label is all that's needed to select one service's series;
no extra relabeling required. The five features fed to the anomaly model
are computed with PromQL, e.g.:

```promql
# average latency in ms over a 2-minute window
1000 * sum(rate(http_request_duration_seconds_sum{job="order-service"}[2m]))
     / sum(rate(http_request_duration_seconds_count{job="order-service"}[2m]))

# error rate
sum(rate(http_requests_total{job="order-service",status=~"5.."}[2m]))
     / sum(rate(http_requests_total{job="order-service"}[2m]))
```

A 2-minute rate window balances two things: long enough to smooth over
Prometheus's 5s scrape jitter, short enough that toggling a failure
injection shows up within a demo session (~30–60s).

A background **load generator** container (`services/load-generator`) keeps
a steady ~3 req/s of checkout traffic flowing through the gateway at all
times. This matters more than it sounds: without it, `request_rate` reads
near-zero between manual test bursts, which is itself indistinguishable
from "unusual" to the anomaly model. The load generator gives the system a
stable, realistic steady state to actually deviate *from*.

## Deep dive: machine learning — anomaly detection

**What it detects.** For each service, a single question: *is this
service's current behavior unusual relative to its own baseline?* — across
five features pulled directly from the telemetry pipeline above:

```
[latency_ms, error_rate, request_rate, cpu_percent, memory_mb]
```

Nothing more. The model does not attempt to explain *why* — that's the LLM
layer's job downstream, and only once it's been handed this model's output
as one piece of evidence among several.

**Why Isolation Forest.** It's unsupervised — no labeled "this was an
incident" data required, which is the normal case for any real system (you
never have enough labeled incidents to train a classifier). It isolates
points by recursively splitting on random features and thresholds;
anomalies need fewer splits to isolate — a shorter average path length
across many random trees — so they get a higher anomaly score. It's cheap
to train, and easy to explain end-to-end in an interview, which matters
more than a marginally "more impressive"-sounding model that's harder to
justify.

```python
model = IsolationForest(contamination=0.05, random_state=42)
model.fit(training_data)
prediction = model.predict(current_metrics)  # 1 = normal, -1 = anomalous
```

`contamination=0.05` tells the model what fraction of the *training* data
to treat as the natural outlier tail when picking its internal score
threshold — it's a prior on "how often should even normal data look a
little unusual," not a label on which training points are anomalies.

**A real bug, and why it matters.** The first version of the training
pipeline generated two synthetic clusters — "normal" samples and
"anomalous" samples — and trained on both, mirroring how you might build
training data for a *supervised* classifier. Under that setup, an obvious
latency spike (1500ms against a ~60ms baseline) scored as **normal**.

The reason: Isolation Forest is unsupervised — it never sees the cluster
labels. Injecting a second, internally-consistent "anomalous" cluster
doesn't teach the model what an anomaly looks like; it teaches the model
that cluster is just another legitimate, non-isolated mode of the data,
since those points are no longer isolated from *each other*. The fix was to
train on baseline ("normal") data only, and let `contamination` set the
tail threshold within that single distribution — the textbook-correct
setup, and a materially different (and more defensible) design than the
first draft. This is documented in full in `ml/train.py`'s module
docstring, and is a genuinely good interview story: it demonstrates
actually understanding the algorithm rather than pattern-matching "call
`IsolationForest.fit()`."

**Baseline calibration.** The (mean, std) baseline for each feature is
calibrated against *this specific demo mesh's* actual steady-state
behavior under the load generator (`ml/features.py`'s `BASELINE_STATS`) —
not generic textbook production numbers. A lightweight FastAPI container
handling ~3 req/s runs cool (low single-digit CPU%) and fast (tens of ms);
a generic "50 req/s, 15% CPU" baseline would misfire on every request here.
This is itself a useful lesson: an anomaly model is only as good as how
faithfully its baseline matches the system it's actually watching.

**Per-metric attribution.** Isolation Forest gives one score for the whole
feature vector, not a per-feature breakdown — but the UI and MCP tool
output label a `driving_metric` for each flagged service. That label comes
from a separate, much simpler calculation layered *on top of* the model's
binary verdict: a plain z-score against each feature's baseline, reporting
whichever deviated furthest. This is descriptive statistics for display
purposes, not a second model — it never influences the anomalous/normal
decision itself, keeping the "one and only ML component, kept intentionally
small" framing intact.

**Verified results** from real failure-injection runs (see
[Demo scenarios](#demo-scenarios)):

| Scenario | Flagged services | `driving_metric` | Observed value vs. baseline |
| ---------- | ------------------- | ------------------- | ------------------------------ |
| Latency injection (2s sleep) | inventory-service, order-service, gateway | `latency_ms` | ~2000ms vs. ~60ms |
| Error injection (30% 500s) | inventory-service, order-service, gateway | `error_rate` | ~26% vs. ~1% |
| Dependency load increase (×6 calls) | inventory-service only | `request_rate` | ~14 req/s vs. ~3 req/s |

Notice the pattern: the three scenarios correctly propagate (or don't)
through the graph exactly as the topology predicts. payment-service never
gets flagged in the first two scenarios because order-service short-circuits
before calling it on a failed/slow inventory reservation; only
inventory-service is flagged in the third, because it's the only service
that actually received extra traffic.

## Deep dive: historical incident retrieval

Every incident is stored with a free-text description and a **Gemini
embedding** (`gemini-embedding-001`, truncated via Matryoshka
representation learning to 768 dimensions to match the pgvector column) in
the same Postgres instance — no separate vector database.

```
Current evidence → embed (RETRIEVAL_QUERY) → pgvector cosine similarity
                                            → ranked historical incidents
```

Incidents are embedded with `task_type="RETRIEVAL_DOCUMENT"` at seed time
and queries with `task_type="RETRIEVAL_QUERY"` — Gemini's asymmetric
retrieval hint, which tunes the embedding space slightly differently for
"this is a thing to be found" vs. "this is what I'm looking for."

Five incidents are seeded (`scripts/seed_incidents.py`), including one that
deliberately mirrors this system's own demo scenario (an order-service
deploy causing a downstream inventory-service latency/error spike) — a real
similarity search against it returns that incident at ~0.89 cosine
similarity, with a second, genuinely-also-relevant incident close behind at
~0.89 — a good illustration that semantic search surfaces *plausible*
matches, not a single unambiguous answer.

**A high-similarity match means "semantically similar," never "confirmed
same root cause."** This wording is enforced in the code comments, the
LLM's system prompt, and the UI copy.

## Deep dive: MCP tool layer

Instead of giving the LLM open-ended access to Postgres, Prometheus, and
the embedding API, exactly six narrow, typed tools are exposed via a real
**MCP server** (the official `mcp` Python SDK, Streamable HTTP transport,
running in its own container):

| Tool | Returns |
| ------ | --------- |
| `get_change_details(service)` | Commit SHA, author, changed files for the service's most recent deployment |
| `get_dependency_graph(service?)` | Direct dependencies/dependents of a service, or the full graph |
| `get_blast_radius(service)` | Potentially impacted downstream services, ranked by dependency distance |
| `get_service_telemetry(service)` | Live latency, error rate, request rate, CPU, memory |
| `get_anomalies()` | Which mesh services are currently anomalous, and on which metric |
| `search_historical_incidents(query, limit)` | Semantically similar past incidents |

Each tool is a thin wrapper — the MCP server calls the backend's *own REST
API* rather than touching Postgres/Prometheus directly, so there's a single
source of truth and a single audit trail regardless of whether a request
came from the UI or from the LLM's tool calls. **MCP adds no new logic,
only a safe, auditable interface to logic that already exists.**

Verified independently with a real MCP client (not just "the server process
started") — `scripts/mcp_smoke_test.py` connects over Streamable HTTP,
lists all six registered tools, and calls each one, confirming real,
correctly-typed responses come back.

## Deep dive: LLM reasoning & structured outputs

**What the LLM is *not* responsible for:** detecting anomalies, calculating
blast radius, embedding text, or querying raw infrastructure. Those are all
deterministic, upstream of this layer.

**What it *is* responsible for:** calling the six MCP tools to gather
evidence, then synthesizing that evidence into a structured hypothesis with
explicit limitations attached.

```python
class Evidence(BaseModel):
    source: str
    detail: str

class Hypothesis(BaseModel):
    statement: str
    supporting_evidence: list[Evidence]
    limitations: list[str]

class InvestigationResult(BaseModel):
    summary: str
    hypotheses: list[Hypothesis]
```

There is no `root_cause` field, anywhere in this schema. The model
structurally cannot claim to have found one — it can only ever produce
hypotheses, each carrying its own evidence *and* its own limitations. A
malformed model response fails validation loudly instead of rendering
garbage in the UI.

**The tool-calling loop is manual**, not the `google-genai` SDK's
"automatic function calling" convenience path — a deliberate choice, and
one that surfaced two real engineering problems worth knowing how to debug:

1. **`thought_signature` and SDK version skew.** Gemini 3-generation models
   attach an opaque `thought_signature` to each function-call turn that
   must be echoed back unmodified on the next turn — a token representing
   the model's internal reasoning continuity. A byte-perfect round-trip of
   the model's own response object still failed with "missing
   thought_signature," because the installed `google-genai==1.30.0` client
   didn't model that field on `Part` at all — it silently dropped it during
   deserialization regardless of what the API actually sent. Diagnosed by
   inspecting the raw response object directly (`getattr(part,
   "thought_signature", "MISSING_ATTR")` returned `"MISSING_ATTR"`, not
   `None` — confirming the attribute didn't exist on the SDK's model, not
   just that it was empty); fixed by pinning `google-genai>=2.20`.
2. **Automatic function calling doesn't support async tools.** The MCP
   client is inherently async; the SDK's automatic-calling convenience path
   only supports plain synchronous Python callables. This project's tools
   need to `await` an MCP session, so the loop is hand-rolled: send
   `contents` with `tools` attached → if the response contains
   `function_call` parts, execute them via the MCP client and append
   `function_response` parts → repeat → once the model stops calling
   tools, make one final call with **no tools attached** and
   `response_schema=InvestigationResult` to force the synthesis.

**Model quota is a real constraint worth knowing about.** Gemini's free
tier caps each *model* (not the account) at a low daily request quota (20
requests/day at time of writing), and one investigation makes several
`generate_content` calls. `GEMINI_MODEL` is a configurable env var so a
fresh quota bucket is one config change away rather than a code change —
directly informed by hitting this limit during development.

## Database schema

Seven tables, all in one PostgreSQL instance:

| Table | Columns |
| ------- | --------- |
| `services` | `id` (the service name itself, e.g. `"order-service"`), `description` |
| `dependencies` | `source_service_id`, `target_service_id` — the graph's edge list |
| `changes` | `id`, `service_id`, `commit_sha`, `author`, `files_changed` (JSON), `timestamp` |
| `deployments` | `id`, `service_id`, `change_id`, `status`, `timestamp` |
| `telemetry_events` | `id`, `service_id`, `metric_name`, `metric_value`, `timestamp` |
| `anomalies` | `id`, `service_id`, `metric`, `score`, `timestamp` |
| `incidents` | `id`, `title`, `description`, `resolution`, `timestamp`, `embedding` (`vector(768)`) |

`Service.id` is the service *name* rather than a synthetic UUID — the
graph, telemetry, and anomaly layers all key off service names throughout,
so this avoids a name↔id lookup at every join. `"database"` and
`"external-api"` are seeded as `Service` rows too (infra/external graph
nodes, not live containers) — mirroring how the design's own dependency
graph examples treat them as plain nodes.

`dependencies` is what NetworkX loads at request time to reconstruct the
in-memory graph; `incidents.embedding` is what powers the pgvector
similarity search.

## Repository structure

```
change-platform/
├── docker-compose.yml
├── backend/                    # FastAPI orchestration API + static UI
│   └── app/
│       ├── api/                 # HTTP routes (events, graph, telemetry, incidents, investigation, failure_injection)
│       ├── services/             # change/graph/telemetry/anomaly/incident/investigation logic
│       ├── models/               # SQLAlchemy models (7 tables)
│       ├── schemas/              # Pydantic: DeployEventIn/Out, InvestigationResult
│       └── static/               # index.html / app.js / style.css — the Phase 1 UI
├── services/                    # demo mesh
│   ├── gateway/ order-service/ inventory-service/ payment-service/
│   └── load-generator/           # background synthetic traffic
├── mcp-server/                  # MCP server exposing the 6 investigation tools
│   └── tools/                    # change/graph/telemetry/incident tool wrappers
├── ml/                          # Isolation Forest: features, training, inference
├── scripts/                      # incident seeding, MCP smoke test
├── prometheus/                   # scrape config
└── tests/                        # pytest: graph, blast radius, anomaly scoring
```

## Setup & running

**Prerequisites:** Docker + Docker Compose, and a [Gemini API
key](https://aistudio.google.com/apikey) (free tier works — see the
[quota note](#deep-dive-llm-reasoning--structured-outputs) above).

```bash
cp .env.example .env
# edit .env and set GEMINI_API_KEY to a real key
docker compose up --build
```

| URL | What it is |
| ----- | ------------ |
| http://localhost:8000 | The dashboard / investigation workspace |
| http://localhost:8000/docs | FastAPI's auto-generated API docs |
| http://localhost:9090 | Prometheus (raw metrics, PromQL) |
| http://localhost:8100/mcp | MCP server (Streamable HTTP) |
| http://localhost:8080 | Gateway (demo mesh entrypoint) |

## Demo scenarios

The dashboard exposes all of this as UI controls; the same actions can be
driven via `curl` for scripting:

**1. Latency injection** — simulates a blocking call added to
inventory-service:

```bash
curl -X POST "localhost:8000/api/failure-injection/latency?enabled=true&seconds=2.0"
# wait ~40s for the 2-minute Prometheus rate window to pick it up
curl "localhost:8000/api/telemetry/anomalies"
# -> inventory-service, order-service, and gateway all flagged, driving_metric: latency_ms
```

**2. Error injection** — simulates an intermittent downstream failure:

```bash
curl -X POST "localhost:8000/api/failure-injection/errors?enabled=true&rate=0.3"
# -> same three services flagged, driving_metric: error_rate; payment-service stays clean
#    (order-service short-circuits before ever calling it on a failed reservation)
```

**3. Dependency load increase** — simulates order-service calling
inventory-service more often:

```bash
curl -X POST "localhost:8000/api/failure-injection/load?enabled=true&multiplier=6"
# -> inventory-service alone flagged, driving_metric: request_rate (~14 req/s vs ~3 baseline)
```

Turn any scenario off with `enabled=false`, then trigger a demo deploy and
run a full investigation to see the LLM reason about the active anomaly:

```bash
curl -X POST "localhost:8000/api/events/generate-demo-deploy"
curl -X POST "localhost:8000/api/investigate?service=order-service"
```

## Testing

```bash
docker compose exec backend pytest tests -v
```

19 tests, focused specifically on the logic worth being able to defend in
an interview:

- **`tests/test_graph_service.py`** — direct dependency/dependent lookups,
  including edge cases (unknown service, root/leaf nodes)
- **`tests/test_blast_radius.py`** — descendant traversal matches the
  design's own worked example exactly; dependency-distance enrichment is
  correct and nearest-first sorted; a diamond-shaped dependency graph
  (`A→B→D`, `A→C→D`) resolves to the *shortest* path distance
- **`tests/test_anomaly_scoring.py`** — feature vector construction,
  z-score attribution, training-data determinism (same seed → identical
  data), and — critically — that a point at the exact baseline mean scores
  as normal while a correlated multi-feature extreme (the shape a real
  cascading failure actually produces) scores as anomalous

Tests run inside the same container image the app itself runs in,
guaranteeing environment parity between "it passed in CI" and "it runs in
prod."

## Responsible framing

This is the difference between a mature engineering project and something
that falls apart under one follow-up question in an interview.

| Do not say | Say instead |
| ------------ | ------------- |
| Automatically identifies root causes. | Supports failure investigation by connecting changes, dependencies, runtime telemetry, and historical incident evidence. |
| Predicts production failures. | Identifies potentially impacted services and detects unusual runtime behavior. |
| The LLM determines the root cause. | The LLM synthesizes retrieved evidence into structured investigation hypotheses. |
| The deployment caused the incident. | The deployment preceded the observed anomalies. |
| These services are broken. | These services are potentially impacted / worth investigating first. |

### Why this matters, not just as a wording rule

The system doesn't say *"I know exactly what broke your system."* It says:
*"Here is what changed, here is what could have been affected, here is what
became abnormal, and here are similar past incidents. Based on this
evidence, these are the most likely explanations."*

Worked example — the exact chain this system actually produces:

```
Developer changes Order Service
        |
Order Service deployed
        |
Inventory Service latency increases
        |
Inventory errors increase
        |
Anomaly detector flags inventory-service
        |
Investigation Layer finds:
   "Inventory is downstream of Order"
        +
   "Latency increased after deployment"
        +
   "A similar incident happened before"
        |
Result -> "This change may have contributed
           to the Inventory anomaly."
```

But it deliberately never says: *"The Order Service change caused the
Inventory failure."* Because there could be another explanation the
evidence gathered so far doesn't rule out:

- another deployment happened at the same time
- the database was overloaded independently
- an external API failed
- traffic suddenly increased for unrelated reasons
- the telemetry itself is incomplete or delayed

So the engineer makes the final call, not the system. That's a deliberate
design choice, not a limitation to apologize for: the algorithms and the
LLM are used to *collect, connect, and explain* evidence — not to pretend a
statistical model or an LLM can know ground truth it was never given.

**In one sentence:** this system narrows down *where* and *why* an incident
might have happened; the engineer decides whether that explanation is
actually correct.

Concretely, this system:

- **Does not** claim to identify a root cause — `InvestigationResult` has
  no field for one, structurally.
- **Does not** predict future failures — the anomaly model only answers
  "is this unusual right now?", nothing about what happens next.
- **Does not** claim a deployment caused anything downstream — only that it
  preceded observed signals. Correlation, not causation.
- **Does not** claim a historical-incident match confirms the same root
  cause — only that it's semantically similar.
- Blast radius is a hypothesis space of what *could* be affected, never a
  diagnosis of what *was*.

## Engineering decisions & tradeoffs

A consolidated list of the non-obvious calls made throughout the codebase,
and why:

- **Sync SQLAlchemy in an async framework.** The genuinely I/O-bound work
  here (calls to other microservices, Prometheus, Gemini) is already async
  via `httpx`/the async Gemini client; local Postgres queries are fast and
  simple enough that a sync session — run in FastAPI's threadpool for sync
  routes — keeps the ORM layer easy to reason about without
  asyncpg/async-session boilerplate.
- **Model trained at Docker build time, not lazily at runtime or via a
  separate offline job.** The training data is fully synthetic and
  generation is seeded (`random_state=42`), so this is 100% reproducible —
  there's no external data dependency to bootstrap from, and no benefit to
  a separate training pipeline at this scale.
- **`Service.id` is the service name**, not a UUID — every layer
  (graph, telemetry, anomalies) already keys off names; adding a synthetic
  id would only add an unnecessary lookup.
- **The MCP server calls the backend's REST API, not Postgres/Prometheus
  directly.** One source of truth, one audit trail, regardless of whether
  a request originated from the UI or an LLM tool call.
- **`driving_metric` is a z-score, not a second model.** Keeps the "one and
  only ML component, kept intentionally small" framing honest — it's
  descriptive statistics layered on top of, never inside, the anomaly
  decision.
- **The static UI has zero build step and zero new dependencies** —
  Starlette's built-in `StaticFiles`, vanilla JS, `fetch()`. React is
  explicitly Phase 2 polish, not a resume claim for Phase 1.

## Known limitations

- **Isolation Forest is multivariate but per-feature-independent at split
  time.** A synthetic outlier that's extreme on exactly one feature while
  sitting exactly at the baseline mean on the other four is a genuinely
  hard case for tree-based isolation — see the unit test docstring in
  `tests/test_anomaly_scoring.py`. Real injected failures are not this
  case: they naturally shift several correlated metrics at once (verified
  against the live system in [Demo scenarios](#demo-scenarios)), which is
  exactly the shape this model is good at catching.
- **`telemetry_events` and `anomalies` grow unbounded** — fine for a demo
  session, would need a retention policy in a long-running deployment.
- **Gemini's free-tier daily quota is per-model and low** (see the LLM
  section above) — a live demo can exhaust it; `GEMINI_MODEL` is
  configurable as a mitigation, not a fix.
- **Stock quantities in inventory-service are in-memory and reset on
  container restart** — a deliberate demo-scale simplification, not
  production inventory logic.

## Phase 2 roadmap

Everything below is deliberately out of scope for Phase 1 and left for a
second pass, once Phase 1 is confirmed solid:

- **Kubernetes manifests** (Deployment/Service/ConfigMap/Secret) for the
  demo mesh, deployable to a local `kind`/`minikube` cluster — this becomes
  the infrastructure layer the resume bullet's "distributed applications"
  framing can point to beyond Docker Compose.
- **Full React + TypeScript investigation UI** — dependency graph via React
  Flow or Cytoscape.js, a proper evidence timeline component, and the full
  investigation workspace from the original design — replacing the static
  dashboard. The backend's API surface is already UI-framework-agnostic, so
  this is additive, not a rewrite.
- **GitHub Actions CI/CD** — running the existing pytest suite and a
  Docker build on every push.
- **OpenTelemetry tracing**, as a natural extension alongside the existing
  Prometheus metrics pipeline — the doc's own framing for where distributed
  tracing fits once metrics-only observability is solid.

## Glossary

Interview-ready one-paragraph explanations for the core concepts, in case
a single word off the resume gets picked apart:

- **Directed graph** — a graph where edges have direction (`A → B` does not
  imply `B → A`). Here, `order-service → inventory-service` means Order
  calls Inventory. NetworkX represents this as a `DiGraph`; traversal (BFS)
  from a node follows edges forward only.
- **Blast radius** — the set of nodes reachable by following directed
  edges forward from a changed node: everything that *could* be affected,
  not everything that definitely *was*. Computed via graph descendant
  traversal (`nx.descendants`).
- **Isolation Forest** — an unsupervised anomaly-detection algorithm that
  isolates points via random recursive splits; outliers need fewer splits
  to isolate (a shorter average path length across many random trees), so
  they get a higher anomaly score. Ideal when there's no labeled "this was
  an incident" data — the normal case.
- **Embedding** — a numeric vector representation of text such that
  semantically similar inputs produce vectors close together in vector
  space. Used here to turn an incident's free-text description into
  something a similarity search can operate over.
- **Vector similarity search / pgvector** — given a query embedding, find
  the stored embeddings closest to it by a distance metric (cosine
  distance, here). pgvector is a PostgreSQL extension adding a vector
  column type and nearest-neighbor search operators directly inside
  Postgres, avoiding a separate vector database.
- **MCP (Model Context Protocol)** — a standardized protocol for exposing
  external tools/data sources to an LLM in a structured, typed way, instead
  of giving the model raw, unconstrained access to a system. The model
  calls a named tool with typed arguments and gets a typed result back.
- **Structured outputs** — constraining an LLM's response to a predefined
  schema (here, a Pydantic model) so the output is machine-parseable and
  validated, rather than unconstrained free text that might omit required
  fields or hallucinate a different shape each time.
- **Correlation vs. causation** — two events being related in time or
  co-occurring does not prove one caused the other. This entire platform is
  built to surface correlation (temporal ordering, graph reachability,
  semantic similarity) while explicitly refusing to assert causation.
- **Contamination parameter (Isolation Forest)** — a hyperparameter
  specifying the expected proportion of outliers in the *training* data
  (e.g. `0.05` = expect ~5% tail noise); it sets the model's internal
  decision threshold.
