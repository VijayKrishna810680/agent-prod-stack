# Enterprise Agent Service — production scaffold

A runnable starter for taking an AI agent past the demo stage inside a large
organization. Every piece exists to close one specific gap that shows up when an
agent has to survive real enterprise usage — not to look impressive on a slide.

Stack: **FastAPI · Pydantic · LangGraph · PostgreSQL/pgvector · Redis · LiteLLM ·
tracing hook (Langfuse/Opik-shaped) · uv · Ruff · Pytest · Docker · GitHub Actions**

See [`PROBLEMS_SOLVED.md`](./PROBLEMS_SOLVED.md) for the full problem → component map.

## Quickstart

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"

ruff check .
pytest -q
```

The test suite runs fully offline: the LLM calls are dependency-injected/mocked and
Redis is faked with `fakeredis`, so `pytest` never needs a real provider key, a real
Postgres instance, or a real Redis instance.

## Running the full stack locally

```bash
cp .env.example .env   # fill in a real provider key for OPENAI_API_KEY etc.
docker compose up --build
```

This brings up the API, a Postgres instance with the `pgvector` extension enabled,
and Redis, wired together the way `app/settings.py` expects.

## Project layout

```
app/
  main.py         FastAPI app: /health, /v1/agent/invoke, /v1/agent/approve
  schemas.py      Pydantic request/response contracts
  settings.py     Typed, validated configuration (pydantic-settings)
  llm_gateway.py  LiteLLM wrapper: retries + provider fallback chain
  cache.py        Redis-backed response cache + per-user rate limiting
  db.py           SQLAlchemy models over Postgres + pgvector (relational + vector)
  observability.py  Trace-id + structured logging hook (swap in Langfuse/Opik)
  agent/
    state.py      Typed LangGraph state
    graph.py      Nodes, edges, and the human-in-the-loop approval pause
    tools.py      Example tool call (intent classification)
tests/            Pytest suite covering contracts, the graph, the gateway, the API
.github/workflows/ci.yml   Lint + test + build-image pipeline
Dockerfile, docker-compose.yml
```

## The one workflow worth tracing end-to-end

`POST /v1/agent/invoke` with `"require_human_approval": true` runs the agent's
planning step, then **pauses the graph** before taking any further action and
returns `status: "awaiting_human_approval"` plus a `trace_id`. A reviewer calls
`POST /v1/agent/approve` with `approved: true|false`; the graph resumes from
exactly where it paused — it does not re-run the planning step — and finalizes.
This is the human-in-the-loop pattern enterprise approval chains actually need,
implemented with LangGraph's checkpointing rather than simulated in prompt text.
