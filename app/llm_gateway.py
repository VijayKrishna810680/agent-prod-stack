"""Provider-agnostic LLM gateway.

Problem this solves: a business-critical workflow (support triage, internal copilot,
fraud review) cannot go down because one model provider had an incident. This wraps
LiteLLM with retries and an explicit fallback chain, so a provider outage degrades
to a backup model instead of a customer-facing failure.
"""

from __future__ import annotations

import logging

import litellm
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.settings import get_settings

logger = logging.getLogger(__name__)


class AllProvidersFailedError(RuntimeError):
    """Raised when the primary model and every fallback model failed."""


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type(litellm.exceptions.APIConnectionError),
)
def _call_model(model: str, messages: list[dict], timeout: float) -> str:
    response = litellm.completion(model=model, messages=messages, timeout=timeout)
    return response["choices"][0]["message"]["content"]


def generate(messages: list[dict]) -> str:
    """Call the primary model; on failure, walk the fallback chain in order."""
    settings = get_settings()
    models_to_try = [settings.primary_model, *settings.fallback_models]

    last_error: Exception | None = None
    for model in models_to_try:
        try:
            return _call_model(model, messages, settings.llm_request_timeout_s)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: any provider can fail
            logger.warning("model %s failed, trying next fallback: %s", model, exc)
            last_error = exc
            continue

    raise AllProvidersFailedError(
        f"All {len(models_to_try)} configured models failed"
    ) from last_error
