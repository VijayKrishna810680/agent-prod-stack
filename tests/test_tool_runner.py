from __future__ import annotations

from app.agent.tool_runner import ToolExecutionError, ToolStep, run_tool_sequence


def test_all_steps_succeed():
    steps = [
        ToolStep("a", lambda: {"ok": 1}),
        ToolStep("b", lambda: {"ok": 2}),
    ]
    records, all_ok = run_tool_sequence(steps)

    assert all_ok is True
    assert [r["succeeded"] for r in records] == [True, True]


def test_failure_stops_remaining_steps():
    calls = []

    def failing():
        calls.append("failing")
        raise ToolExecutionError("boom")

    def never_reached():
        calls.append("never_reached")
        return {"ok": True}

    steps = [
        ToolStep("first_ok", lambda: {"ok": True}),
        ToolStep("failing", failing),
        ToolStep("third", never_reached),
    ]
    records, all_ok = run_tool_sequence(steps, max_retries=1)

    assert all_ok is False
    assert [r["name"] for r in records] == ["first_ok", "failing"]
    assert records[-1]["succeeded"] is False
    assert "never_reached" not in calls
    # one initial attempt + one retry = 2 calls to the failing step
    assert calls.count("failing") == 2


def test_retry_recovers_transient_failure():
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ToolExecutionError("transient")
        return {"ok": True}

    records, all_ok = run_tool_sequence([ToolStep("flaky", flaky)], max_retries=1)

    assert all_ok is True
    assert records[0]["succeeded"] is True
    assert attempts["count"] == 2
