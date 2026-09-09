from __future__ import annotations

from app import llm_gateway

REVIEWER_HEADERS = {"Authorization": "Bearer dev-reviewer-token"}


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_invoke_completes_and_caches(client, monkeypatch):
    monkeypatch.setattr(llm_gateway, "generate", lambda messages: "mocked reply")

    payload = {"session_id": "api-session-1", "user_id": "user-1", "message": "hi there"}
    resp = client.post("/v1/agent/invoke", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["reply"] == "mocked reply"
    assert body["tool_calls"][0]["name"] == "classify_intent"


def test_invoke_rejects_invalid_payload(client):
    resp = client.post("/v1/agent/invoke", json={"session_id": "s", "user_id": "u", "message": ""})
    assert resp.status_code == 422


def test_invoke_then_approve_flow(client, monkeypatch):
    monkeypatch.setattr(llm_gateway, "generate", lambda messages: "mocked reply")

    payload = {
        "session_id": "api-session-2",
        "user_id": "user-1",
        "message": "please refund my order",
        "require_human_approval": True,
    }
    first = client.post("/v1/agent/invoke", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "awaiting_human_approval"

    approval = client.post(
        "/v1/agent/approve",
        json={"session_id": "api-session-2", "approved": True},
        headers=REVIEWER_HEADERS,
    )
    assert approval.status_code == 200
    body = approval.json()
    assert body["status"] == "completed"
    assert body["reply"] == "mocked reply"


def test_approve_without_token_is_rejected(client, monkeypatch):
    monkeypatch.setattr(llm_gateway, "generate", lambda messages: "mocked reply")
    client.post(
        "/v1/agent/invoke",
        json={
            "session_id": "api-session-noauth",
            "user_id": "user-1",
            "message": "cancel my plan",
            "require_human_approval": True,
        },
    )

    resp = client.post(
        "/v1/agent/approve", json={"session_id": "api-session-noauth", "approved": True}
    )
    assert resp.status_code == 401


def test_approve_with_wrong_token_is_forbidden(client, monkeypatch):
    monkeypatch.setattr(llm_gateway, "generate", lambda messages: "mocked reply")
    client.post(
        "/v1/agent/invoke",
        json={
            "session_id": "api-session-badtoken",
            "user_id": "user-1",
            "message": "cancel my plan",
            "require_human_approval": True,
        },
    )

    resp = client.post(
        "/v1/agent/approve",
        json={"session_id": "api-session-badtoken", "approved": True},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 403


def test_approval_is_recorded_in_audit_log(client, monkeypatch):
    monkeypatch.setattr(llm_gateway, "generate", lambda messages: "mocked reply")
    session_id = "api-session-audit"
    client.post(
        "/v1/agent/invoke",
        json={
            "session_id": session_id,
            "user_id": "user-1",
            "message": "please refund my order",
            "require_human_approval": True,
        },
    )
    client.post(
        "/v1/agent/approve",
        json={"session_id": session_id, "approved": True, "note": "checked, looks fine"},
        headers=REVIEWER_HEADERS,
    )

    audit_resp = client.get(f"/v1/agent/audit/{session_id}", headers=REVIEWER_HEADERS)
    assert audit_resp.status_code == 200
    entries = audit_resp.json()
    assert len(entries) == 1
    assert entries[0]["reviewer_id"] == "reviewer-1"
    assert entries[0]["approved"] is True
    assert entries[0]["note"] == "checked, looks fine"


def test_audit_log_requires_auth(client):
    resp = client.get("/v1/agent/audit/some-session")
    assert resp.status_code == 401


def test_failed_tool_call_auto_escalates_and_can_be_overridden(client, monkeypatch):
    monkeypatch.setattr(llm_gateway, "generate", lambda messages: "mocked reply")

    payload = {
        "session_id": "api-session-toolfail",
        "user_id": "user-1",
        "message": "please check balance for ACC-DOWN",
    }
    first = client.post("/v1/agent/invoke", json=payload)
    assert first.status_code == 200
    # Escalated even though require_human_approval was never set to true.
    assert first.json()["status"] == "awaiting_human_approval"

    approval = client.post(
        "/v1/agent/approve",
        json={"session_id": "api-session-toolfail", "approved": True, "note": "manually verified"},
        headers=REVIEWER_HEADERS,
    )
    assert approval.status_code == 200
    body = approval.json()
    assert body["status"] == "completed"
    assert body["tool_calls"][-1]["name"] == "check_downstream_billing_system"
    assert body["tool_calls"][-1]["succeeded"] is False


def test_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setenv("APP_RATE_LIMIT_PER_MINUTE", "1")
    from app.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(llm_gateway, "generate", lambda messages: "mocked reply")

    payload = {"session_id": "rl-session", "user_id": "rate-limited-user", "message": "hi"}
    first = client.post("/v1/agent/invoke", json=payload)
    second = client.post("/v1/agent/invoke", json={**payload, "session_id": "rl-session-2"})

    assert first.status_code == 200
    assert second.status_code == 429
    get_settings.cache_clear()
