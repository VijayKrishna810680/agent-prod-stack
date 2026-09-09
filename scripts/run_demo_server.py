"""Runs the real app over real HTTP for a local demo.

Only the outbound call to a third-party LLM provider is stubbed — this sandbox has
no OPENAI_API_KEY / ANTHROPIC_API_KEY configured. Every other path (FastAPI routing,
Pydantic validation, the LangGraph pause/resume, the real Redis cache and rate
limiter, bearer-token auth, the audit log) runs unmodified, against a real
redis-server process, over real HTTP.
"""

import uvicorn

from app import llm_gateway


def _stub_generate(messages: list[dict]) -> str:
    return (
        "[stubbed LLM reply — no provider key configured in this sandbox; "
        "set OPENAI_API_KEY/ANTHROPIC_API_KEY to hit a real model]"
    )


llm_gateway.generate = _stub_generate

from app.main import app  # noqa: E402  (import after the stub is installed)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
