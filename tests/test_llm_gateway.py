from __future__ import annotations

import litellm
import pytest

from app import llm_gateway


def test_generate_uses_primary_model(monkeypatch):
    monkeypatch.setattr(
        llm_gateway.litellm,
        "completion",
        lambda model, messages, timeout: {"choices": [{"message": {"content": f"ok:{model}"}}]},
    )
    result = llm_gateway.generate([{"role": "user", "content": "hi"}])
    assert result == "ok:gpt-4o-mini"


def test_generate_falls_back_when_primary_fails(monkeypatch):
    calls = []

    def fake_completion(model, messages, timeout):
        calls.append(model)
        if model == "gpt-4o-mini":
            raise RuntimeError("primary provider is down")
        return {"choices": [{"message": {"content": f"ok:{model}"}}]}

    monkeypatch.setattr(llm_gateway.litellm, "completion", fake_completion)
    result = llm_gateway.generate([{"role": "user", "content": "hi"}])

    assert result == "ok:claude-3-5-haiku-20241022"
    assert calls[0] == "gpt-4o-mini"


def test_generate_raises_when_every_model_fails(monkeypatch):
    def always_fails(model, messages, timeout):
        raise RuntimeError(f"{model} is down")

    monkeypatch.setattr(llm_gateway.litellm, "completion", always_fails)

    with pytest.raises(llm_gateway.AllProvidersFailedError):
        llm_gateway.generate([{"role": "user", "content": "hi"}])


def test_retries_on_connection_error(monkeypatch):
    attempts = []

    def flaky(model, messages, timeout):
        attempts.append(model)
        if len(attempts) < 2:
            raise litellm.exceptions.APIConnectionError(
                message="transient", llm_provider="openai", model=model
            )
        return {"choices": [{"message": {"content": "recovered"}}]}

    monkeypatch.setattr(llm_gateway.litellm, "completion", flaky)
    result = llm_gateway.generate([{"role": "user", "content": "hi"}])

    assert result == "recovered"
    assert attempts[0] == "gpt-4o-mini"
    assert len(attempts) == 2
