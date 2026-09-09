"""The agent workflow: nodes, edges, shared state, and a real human-in-the-loop pause.

Problem this solves: a single call to an LLM API can't model "do this, but pause for
a human reviewer before taking the action, then continue." LangGraph makes that pause
a first-class part of the graph — the workflow can be paused, inspected, and resumed
by a separate approval call, instead of being simulated with fragile prompt logic.
"""

from __future__ import annotations

from collections.abc import Callable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agent.state import AgentState
from app.agent.tool_runner import ToolStep, run_tool_sequence
from app.agent.tools import check_downstream_billing_system, classify_intent, extract_account_ref


def _default_llm(message: str) -> str:
    from app import llm_gateway

    return llm_gateway.generate([{"role": "user", "content": message}])


def make_plan_node(llm_call: Callable[[str], str]):
    def plan_node(state: AgentState) -> AgentState:
        steps = [ToolStep("classify_intent", classify_intent, {"message": state["message"]})]

        account_ref = extract_account_ref(state["message"])
        if account_ref:
            steps.append(
                ToolStep(
                    "check_downstream_billing_system",
                    check_downstream_billing_system,
                    {"account_ref": account_ref},
                )
            )

        tool_calls, tool_chain_ok = run_tool_sequence(steps)
        reply = llm_call(state["message"])
        return {
            **state,
            "reply": reply,
            "tool_calls": tool_calls,
            "tool_chain_ok": tool_chain_ok,
        }

    return plan_node


def route_after_plan(state: AgentState) -> str:
    if not state.get("tool_chain_ok", True):
        # A tool call failed mid-chain: always escalate to a human, regardless of
        # whether the caller asked for approval. This is the auto-escalation half of
        # the partial-failure policy in app/agent/tool_runner.py.
        return "human_review"
    if state.get("require_human_approval"):
        return "human_review"
    return "finalize"


def human_review_node(state: AgentState) -> AgentState:
    # No-op: execution only reaches here after the caller has resumed the graph with
    # `approved` set via update_state(). The interrupt happens *before* this node runs.
    return state


def finalize_node(state: AgentState) -> AgentState:
    if state.get("approved") is False:
        return {
            **state,
            "status": "failed",
            "reply": "Request was reviewed and rejected by a human approver.",
        }

    tool_chain_ok = state.get("tool_chain_ok", True)
    if not tool_chain_ok and state.get("approved") is not True:
        # Reached finalize with a failed tool chain and no recorded approval to
        # proceed anyway. Routing guarantees this shouldn't happen — fail safe
        # instead of silently completing on an inconsistent state.
        return {
            **state,
            "status": "failed",
            "reply": "One or more required steps failed and no human approval was recorded.",
        }

    return {**state, "status": "completed"}


def build_graph(llm_call: Callable[[str], str] | None = None):
    """Build and compile the graph.

    `llm_call` is injectable so tests never need a real model provider or network
    access — this is what keeps the workflow's control flow unit-testable.
    """
    graph = StateGraph(AgentState)
    graph.add_node("plan", make_plan_node(llm_call or _default_llm))
    graph.add_node("human_review", human_review_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("plan")
    graph.add_conditional_edges(
        "plan", route_after_plan, {"human_review": "human_review", "finalize": "finalize"}
    )
    graph.add_edge("human_review", "finalize")
    graph.add_edge("finalize", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer, interrupt_before=["human_review"])


def is_awaiting_approval(compiled_graph, config: dict) -> bool:
    snapshot = compiled_graph.get_state(config)
    return "human_review" in snapshot.next


def resume_after_approval(
    compiled_graph, config: dict, *, approved: bool, reviewer_id: str, note: str | None = None
) -> AgentState:
    compiled_graph.update_state(
        config, {"approved": approved, "reviewer_id": reviewer_id, "reviewer_note": note}
    )
    result = compiled_graph.invoke(None, config)
    return result
