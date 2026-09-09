"""Explicit policy for what happens when a tool call fails mid-chain.

Problem this solves (flagged as an open gap in PROBLEMS_SOLVED.md): most agent code
either lets a failed tool call silently vanish, or crashes the whole request. Neither
is acceptable once the agent is touching real business systems: the caller (and a
human reviewer) needs to know exactly which step failed, that later steps were
deliberately *not* run against a possibly-inconsistent state, and the case has to be
escalated rather than guessed at.

Policy implemented here: retry a failing step once, then stop the chain (fail-fast)
and report every step's outcome — never continue past a failed step.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


class ToolExecutionError(Exception):
    """A tool call failed in a way that must not be silently swallowed."""


@dataclass
class ToolStep:
    name: str
    func: Callable[..., dict]
    kwargs: dict = field(default_factory=dict)


def run_tool_sequence(
    steps: list[ToolStep], *, max_retries: int = 1
) -> tuple[list[dict], bool]:
    """Runs `steps` in order. Returns (tool_call_records, all_succeeded).

    On a step's failure it retries up to `max_retries` times, then stops executing
    any remaining steps — so a downstream step never runs against state left
    inconsistent by an earlier failure.
    """
    records: list[dict] = []

    for step in steps:
        attempts = 0
        succeeded = False
        result_value = None
        last_error: Exception | None = None

        while attempts <= max_retries and not succeeded:
            attempts += 1
            try:
                result_value = step.func(**step.kwargs)
                succeeded = True
            except ToolExecutionError as exc:
                last_error = exc

        records.append(
            {
                "name": step.name,
                "arguments": step.kwargs,
                "result": (
                    str(result_value)
                    if succeeded
                    else f"failed after {attempts} attempt(s): {last_error}"
                ),
                "succeeded": succeeded,
            }
        )

        if not succeeded:
            return records, False

    return records, True
