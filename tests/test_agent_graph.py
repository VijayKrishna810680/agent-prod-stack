from __future__ import annotations

from app.agent.graph import build_graph, is_awaiting_approval, resume_after_approval


def _base_state(session_id: str, **overrides) -> dict:
    state = {
        "session_id": session_id,
        "user_id": "u1",
        "message": "my payment was charged twice",
        "require_human_approval": False,
        "approved": None,
    }
    state.update(overrides)
    return state


def test_completes_immediately_without_approval():
    graph = build_graph(llm_call=lambda msg: "mock reply")
    config = {"configurable": {"thread_id": "session-a"}}

    result = graph.invoke(_base_state("session-a"), config)

    assert result["status"] == "completed"
    assert result["reply"] == "mock reply"
    assert result["tool_calls"][0]["name"] == "classify_intent"
    assert not is_awaiting_approval(graph, config)


def test_pauses_for_human_review_when_required():
    graph = build_graph(llm_call=lambda msg: "mock reply")
    config = {"configurable": {"thread_id": "session-b"}}

    graph.invoke(_base_state("session-b", require_human_approval=True), config)

    assert is_awaiting_approval(graph, config)


def test_resumes_and_completes_on_approval():
    graph = build_graph(llm_call=lambda msg: "mock reply")
    config = {"configurable": {"thread_id": "session-c"}}
    graph.invoke(_base_state("session-c", require_human_approval=True), config)

    result = resume_after_approval(graph, config, approved=True, reviewer_id="reviewer-1")

    assert result["status"] == "completed"
    assert result["reply"] == "mock reply"
    assert not is_awaiting_approval(graph, config)


def test_resumes_and_fails_on_rejection():
    graph = build_graph(llm_call=lambda msg: "mock reply")
    config = {"configurable": {"thread_id": "session-d"}}
    graph.invoke(_base_state("session-d", require_human_approval=True), config)

    result = resume_after_approval(
        graph, config, approved=False, reviewer_id="reviewer-1", note="not compliant"
    )

    assert result["status"] == "failed"
    assert "rejected" in result["reply"].lower()


def test_failed_tool_call_auto_escalates_even_without_approval_flag():
    graph = build_graph(llm_call=lambda msg: "mock reply")
    config = {"configurable": {"thread_id": "session-e"}}

    graph.invoke(
        _base_state(
            "session-e",
            message="check balance for ACC-DOWN",
            require_human_approval=False,
        ),
        config,
    )

    # Auto-escalated purely because a tool call failed mid-chain.
    assert is_awaiting_approval(graph, config)


def test_reviewer_can_override_a_failed_tool_call():
    graph = build_graph(llm_call=lambda msg: "mock reply")
    config = {"configurable": {"thread_id": "session-f"}}
    graph.invoke(
        _base_state("session-f", message="check balance for ACC-DOWN"), config
    )

    result = resume_after_approval(
        graph, config, approved=True, reviewer_id="reviewer-1", note="verified manually"
    )

    assert result["status"] == "completed"
    failed_call = next(
        tc for tc in result["tool_calls"] if tc["name"] == "check_downstream_billing_system"
    )
    assert failed_call["succeeded"] is False
