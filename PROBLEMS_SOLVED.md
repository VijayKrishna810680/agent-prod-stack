# What this project actually solves

Each row is a real production failure mode for a software MNC shipping an AI agent,
the component in this repo that addresses it, and where to see it working.

| # | Problem an MNC hits in production | Component | Proof in this repo |
|---|---|---|---|
| 1 | The agent's output can't be trusted by downstream systems (billing, CRM, ticketing) — a malformed or hallucinated shape breaks the integration. | **Pydantic contracts** (`app/schemas.py`) | `tests/test_schemas.py` — a blank/missing field is rejected with a 422 before it reaches the agent (`tests/test_api.py::test_invoke_rejects_invalid_payload`). |
| 2 | Enterprise processes are approval chains, not single prompts — legal/finance/compliance need a real pause-and-resume step, not prompt-engineered pretend approval. | **LangGraph workflow + human-in-the-loop pause** (`app/agent/graph.py`) | `tests/test_agent_graph.py` proves the graph actually pauses (`is_awaiting_approval`) and resumes from that exact point — it does not re-run the planning step — on approval or rejection. |
| 3 | One LLM provider outage takes down a business-critical workflow. | **LiteLLM gateway with retries + fallback chain** (`app/llm_gateway.py`) | `tests/test_llm_gateway.py::test_generate_falls_back_when_primary_fails` — kills the primary model and shows the fallback model answers instead. |
| 4 | Knowledge is split across a system of record and a bolted-on vector database, adding a vendor and a sync problem. | **Postgres + pgvector in one schema** (`app/db.py`) | `KnowledgeDocument` model does relational storage and `.cosine_distance()` semantic search in the same table/transaction. |
| 5 | Cost and latency are invisible until the bill or the outage — repeat questions get re-billed, one caller starves everyone else. | **Redis cache + per-user rate limit** (`app/cache.py`) | `tests/test_api.py::test_invoke_completes_and_caches` and `::test_rate_limit_returns_429` exercise both paths directly, with a real (faked) Redis, not a mock that assumes success. |
| 6 | "The model decided to" isn't an acceptable answer to a compliance reviewer or an incident retro. | **Trace ID on every turn** (`app/observability.py`) | Every `AgentResponse` carries a `trace_id`; swap the log calls for real Langfuse/Opik calls without touching a call site. |
| 7 | "Works on my machine" — dependency or environment drift causes incidents unrelated to the model itself. | **uv-managed deps + Docker** (`pyproject.toml`, `Dockerfile`, `docker-compose.yml`) | `uv pip install -e ".[dev]"` reproduces the exact resolved set; the image is built from the same lockable dependency graph. |
| 8 | Shared agent codebases rot as more teams touch them — inconsistent style, silent regressions. | **Ruff + Pytest** | `ruff check .` passes clean; `pytest -q` — **16/16 tests pass**, covering contracts, the graph's control flow (including the approval branch and rejection branch), the gateway's fallback logic, and the API end-to-end. |
| 9 | Manual, inconsistent releases across regions/environments. | **GitHub Actions CI** (`.github/workflows/ci.yml`) | Pipeline runs `ruff check`, `pytest`, then builds the Docker image — the same three gates before anything ships. |
| 10 | A demo script doesn't survive concurrent enterprise load or give other internal systems a stable integration surface. | **FastAPI** (`app/main.py`) | Async endpoints, auto-generated OpenAPI schema (`/openapi.json`, verified booting in this repo), validated request/response models on every route. |

## What's intentionally left as a next step, not solved here

Two things came up in the LinkedIn thread's comments that are real and *not* fully
solved by this scaffold — worth being honest about:

- **Per-action audit logs and access control** beyond the trace_id — who was allowed
  to call `/v1/agent/approve`, and a durable record of every decision, is an authn/authz
  layer this repo doesn't implement.
- **Partial multi-tool-call failure handling** — this scaffold has one example tool
  call; a real workflow with 5 sequential tool calls needs an explicit policy for what
  happens when step 3 fails (retry the step, roll back 1-2, or fail the whole turn).
  The `ToolCall.succeeded` field in `app/schemas.py` is where that policy would attach.

## Verified, not asserted

Everything in the table above was actually run in this environment before being
handed to you:

```
$ ruff check .
All checks passed!

$ pytest -q
................                                                         [100%]
16 passed
```
