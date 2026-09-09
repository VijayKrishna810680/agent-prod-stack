"""Example tools the agent can call.

Kept intentionally simple (no external calls) so the scaffold runs offline. In a real
deployment `check_downstream_billing_system` is where you'd call an internal API or
another service — it's written to actually fail for a specific input, so the
fail-fast policy in `app/agent/tool_runner.py` has something real to demonstrate
rather than being tested against a tool that can never fail.
"""

from __future__ import annotations

import re

from app.agent.tool_runner import ToolExecutionError

_ACCOUNT_REF_PATTERN = re.compile(r"ACC-[A-Z0-9]+")


def classify_intent(message: str) -> dict:
    """A stand-in for a real classification/tool call.

    Returns a structured result rather than raw text, so it fits directly into the
    ToolCall contract in app/schemas.py.
    """
    lowered = message.lower()
    if any(word in lowered for word in ("refund", "cancel", "charge")):
        intent = "billing"
    elif any(word in lowered for word in ("error", "bug", "broken", "down")):
        intent = "technical_support"
    else:
        intent = "general"
    return {"intent": intent, "confidence": 0.82}


def extract_account_ref(message: str) -> str | None:
    match = _ACCOUNT_REF_PATTERN.search(message)
    return match.group(0) if match else None


def check_downstream_billing_system(account_ref: str) -> dict:
    """A second tool call in the chain — deliberately able to fail.

    `ACC-DOWN` simulates the downstream system being unreachable, so tests can
    exercise the real failure path instead of only the happy path.
    """
    if account_ref == "ACC-DOWN":
        raise ToolExecutionError(f"billing system unreachable while looking up {account_ref}")
    return {"account_ref": account_ref, "balance_cents": 4200}
