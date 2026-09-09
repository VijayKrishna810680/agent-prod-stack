"""Centralized, typed configuration.

Problem this solves: enterprise deployments run the same code across dev/staging/prod
and multiple regions. Reading env vars ad-hoc across the codebase is how you end up
with a config value that's wrong in exactly one environment. Pydantic-settings gives
one validated source of truth, and fails fast at startup instead of at 2am in prod.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    environment: str = "development"

    # LLM gateway (LiteLLM) — provider-agnostic, with fallback model list.
    primary_model: str = "gpt-4o-mini"
    fallback_models: list[str] = ["claude-3-5-haiku-20241022"]
    llm_request_timeout_s: float = 30.0
    llm_max_retries: int = 2

    # Data layer
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/agent_db"
    embedding_dim: int = 1536

    # Redis (cache, rate limiting, short-term session state)
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_per_minute: int = 60
    cache_ttl_seconds: int = 300

    # Observability
    tracing_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Access control for the approval endpoint: token -> reviewer id.
    # Dev-only default below; set APP_REVIEWER_API_KEYS as a JSON object to override.
    reviewer_api_keys: dict[str, str] = {"dev-reviewer-token": "reviewer-1"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
