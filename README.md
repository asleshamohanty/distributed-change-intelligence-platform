# Distributed Change Intelligence Platform

A developer-facing investigation tool for distributed systems. It answers
the question every backend/platform engineer eventually has to answer
during an incident: **"Something broke — what changed, what could it have
affected, and what evidence do we actually have?"**

It correlates five signal types — code changes, service dependencies,
deployment events, runtime telemetry, and historical incidents — into a
structured, evidence-backed investigation, instead of a black-box "root
cause" guess. See [Responsible Framing](#responsible-framing) below for
exactly what it does and does not claim.

This is Phase 1 of a two-phase build. Phase 1 (this repo, fully working) is
a complete local system running via Docker Compose — no Kubernetes.
Kubernetes manifests, a full React investigation UI, GitHub Actions CI/CD,
and OpenTelemetry tracing are deliberately out of scope here and are Phase
2 work.

## Architecture

```
                          +-------------------+
                          |   Static UI        |  http://localhost:8000/
                          | (backend/app/static)|
                          +---------+-----------+
                                    |
                                    v
                          +-------------------+
                          |   FastAPI backend   |  http://localhost:8000
                          |  (orchestration)     |
                          +---------+-----------+
                                    |
        +----------------+---------+---------+----------------+
        v                v                   v                v
  Change Service    Graph Service     Telemetry Service   Incident Service
        |                |                   |                |
        v                v                   v                v
  Postgres          NetworkX graph      Prometheus        Postgres +
  (changes,         (in-memory, loaded  (scraped from      pgvector
  deployments)       from `dependencies` the demo mesh)    (Gemini
                      edge-list table)        |             embeddings)
                                               v
                                        Isolation Forest
                                        (scikit-learn,
                                         trained at build
                                         time on synthetic
                                         baseline telemetry)
                                               |
                                               v
                                      Investigation Layer
                                     (aggregates all of the
                                      above into one object)
                                               |
                                               v
                                          MCP Server        <-- own container,
                                     (Streamable HTTP,      Streamable HTTP
                                      6 typed tools)             (:8100)
                                               ^
                                               | MCP client
                                               |
                                       Gemini (tool-calling
                                        loop -> structured
                                        InvestigationResult)


  Demo microservice mesh (what gets investigated):

  gateway -> order-service -> inventory-service -> "database" (edge only)
                            -> payment-service    -> "external-api" (edge only)

  Each demo service exposes /api/metrics (Prometheus format); Prometheus
  scrapes all four every 5s. A background load-generator container keeps a
  steady ~3 req/s trickle of checkout traffic flowing so the anomaly
  model's baseline reflects real steady-state numbers, not an idle
  container.
```

The React UI, Kubernetes, and real GitHub webhook ingestion from the
original design are Phase 2 — see [Phase 2](#phase-2-not-yet-built) below
for exactly what's deferred and why.

## Setup & run

**Prerequisites:** Docker + Docker Compose, and a [Gemini API
key](https://aistudio.google.com/apikey) (free tier works, but see the
[quota caveat](#gemini-free-tier-quota) below).

```bash
cp .env.example .env
# edit .env and set GEMINI_API_KEY to a real key
docker compose up --build
```

Once everything is up:

| URL                          | What it is                                   |
| ----------------------------- | --------------------------------------------- |
| http://localhost:8000         | The dashboard / investigation workspace       |
| http://localhost:8000/docs    | FastAPI's auto-generated API docs             |
| http://localhost:9090         | Prometheus (raw metrics, PromQL)              |
| http://localhost:8100/mcp     | MCP server (Streamable HTTP)                  |
| http://localhost:8080         | Gateway (demo mesh entrypoint)                |

### Running the demo

1. Open http://localhost:8000. The load generator is already producing
   background traffic, so telemetry/anomaly numbers are live from the
   start.
2. Click **Generate Demo Deploy (order-service)** to record a change event
   (mirrors the design doc's own worked example: a commit touching
   `payment_client.py` and `order_service.py`).
3. Toggle one of the **Failure injection** checkboxes (latency, errors, or
   load) to make inventory-service (or order-service's call volume to it)
   misbehave.
4. Wait ~30–60s for the change to show up in Prometheus's 2-minute rate
   window, then click **Run Investigation**. The dependency graph, evidence
   timeline, and a Gemini-synthesized, schema-constrained hypothesis (with
   citations and limitations) render below.

### Gemini free-tier quota

Gemini's free tier caps each **model** at a low daily request quota (20/day
per model at time of writing) — an investigation makes several
`generate_content` calls (tool-calling turns + one structured-synthesis
call), so this is easy to exhaust during a demo session. `GEMINI_MODEL` is
configurable via `.env` if you need a fresh quota bucket
(`gemini-3.6-flash`, `gemini-3.1-flash-lite`, and `gemini-flash-lite-latest`
all worked during development). This is a real constraint worth mentioning
if you're demoing live rather than screen-recording ahead of time.

### Running tests

```bash
docker compose exec backend pytest tests -v
```

19 tests cover dependency-graph traversal, blast-radius enrichment, and
anomaly-scoring logic specifically — the pieces most worth being able to
defend in an interview.

## Repository structure

```
change-platform/
├── docker-compose.yml
├── backend/            # FastAPI orchestration API + static UI
│   └── app/
│       ├── api/         # HTTP routes
│       ├── services/    # change/graph/telemetry/anomaly/incident/investigation logic
│       ├── models/      # SQLAlchemy models (7 tables)
│       ├── schemas/     # Pydantic request/response + InvestigationResult
│       └── static/      # index.html / app.js / style.css (Phase 1 UI)
├── services/            # demo mesh: gateway, order, inventory, payment, load-generator
├── mcp-server/          # MCP server exposing the 6 investigation tools
├── ml/                  # Isolation Forest: features, training, inference
├── scripts/             # incident seeding, MCP smoke test
├── prometheus/          # scrape config
└── tests/               # pytest: graph, blast radius, anomaly scoring
```

## Key design decisions

- **Graph**: NetworkX `DiGraph`, rebuilt in-memory from a plain Postgres
  edge-list table (`dependencies`) — no graph database. Blast radius is
  `nx.descendants()`, enriched with BFS dependency distance.
- **Telemetry**: a real Prometheus container scrapes each demo service's
  `/api/metrics`; the backend queries Prometheus's HTTP API rather than
  scraping directly.
- **Anomaly detection**: one `IsolationForest(contamination=0.05,
  random_state=42)` per investigation, trained **only** on synthetic
  baseline ("normal") telemetry at Docker build time. An earlier version of
  this trained on a synthetic *anomalous* cluster too — which is wrong for
  an unsupervised method: it teaches the model that cluster is just another
  legitimate mode of the data instead of an outlier. See `ml/train.py`'s
  docstring for the full explanation.
- **pgvector**: incident embeddings (Gemini's `gemini-embedding-001`,
  truncated to 768 dims) live in a `vector` column in the same Postgres
  instance — no separate vector database.
- **MCP**: a real MCP server (official `mcp` Python SDK, Streamable HTTP
  transport) in its own container. Its six tools are thin wrappers around
  the backend's own REST API — no logic is duplicated, and the LLM never
  touches Postgres/Prometheus/Gemini's embedding endpoint directly.
- **LLM tool-calling loop is manual, not the SDK's "automatic function
  calling"**: the MCP client is inherently async, and the SDK's automatic
  path only supports plain sync callables. The manual loop requires
  `google-genai>=2.20` — Gemini 3 models attach an opaque
  `thought_signature` to function-call turns that must round-trip
  unmodified, and older SDK versions don't model that field at all (this
  project hit exactly that bug during development).
- **Structured output**: `InvestigationResult` (Pydantic) has no
  `root_cause` field, structurally. Every hypothesis must carry
  `supporting_evidence` and `limitations`.
- **UI**: a single static HTML/CSS/vanilla-JS page, served via Starlette's
  built-in `StaticFiles` — no new dependency, no build step. Not a resume
  claim; React is optional Phase 2 polish.

## Responsible Framing

This is the difference between a mature engineering project and something
that falls apart under one follow-up question in an interview. From the
design doc's own "Responsible Framing" section — this wording is used
verbatim in the LLM's system prompt and the UI copy:

| Do not say                                   | Say instead                                                                                  |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Automatically identifies root causes.         | Supports failure investigation by connecting changes, dependencies, runtime telemetry, and historical incident evidence. |
| Predicts production failures.                 | Identifies potentially impacted services and detects unusual runtime behavior.                |
| The LLM determines the root cause.            | The LLM synthesizes retrieved evidence into structured investigation hypotheses.              |
| The deployment caused the incident.           | The deployment preceded the observed anomalies.                                               |
| These services are broken.                    | These services are potentially impacted / worth investigating first.                          |

Concretely, this system:

- **Does not** claim to identify a root cause. `InvestigationResult` has no
  field for one.
- **Does not** predict future failures — the anomaly model only answers
  "is this service's current behavior unusual relative to its own
  baseline?", nothing more.
- **Does not** claim the deployment caused anything downstream — only that
  it preceded observed signals (correlation, not causation).
- **Does not** claim a historical-incident match confirms the same root
  cause — only that it's semantically similar.
- Graph reachability ("blast radius") is a hypothesis space of what
  *could* be affected, never a diagnosis of what *was*.

## Tech stack

Python, FastAPI, PostgreSQL + pgvector, Docker, MCP, scikit-learn — the
hard constraints for Phase 1. Also: SQLAlchemy, NetworkX, Prometheus,
Gemini (`google-genai`), pytest. No Kubernetes, no Neo4j, no separate
vector database, no message queue — see the design doc's Technology Stack
section for why each of those is deliberately unnecessary at this scale.

## Phase 2 (not yet built)

- Kubernetes manifests (Deployment/Service/ConfigMap/Secret) for the demo
  mesh, deployable to a local kind/minikube cluster.
- Full React + TypeScript investigation UI (dependency graph via React Flow
  / Cytoscape, evidence timeline, investigation workspace) replacing the
  static dashboard.
- GitHub Actions CI/CD.
- OpenTelemetry tracing, as a natural extension alongside Prometheus
  metrics.
