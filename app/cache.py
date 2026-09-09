"""Redis-backed cache and rate limiter.

Problem this solves: without caching, the same question gets re-sent to the LLM (and
re-billed) repeatedly; without rate limiting, one noisy internal caller can starve
throughput for everyone else. Both failure modes are usually discovered from a cost
report or an incident, not from a design review — this makes them explicit.
"""

from __future__ import annotations

import hashlib
import time

import redis

from app.settings import get_settings


def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def cache_key(session_id: str, message: str) -> str:
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()[:16]
    return f"agent:cache:{session_id}:{digest}"


def get_cached_reply(client: redis.Redis, session_id: str, message: str) -> str | None:
    return client.get(cache_key(session_id, message))


def set_cached_reply(client: redis.Redis, session_id: str, message: str, reply: str) -> None:
    settings = get_settings()
    client.set(cache_key(session_id, message), reply, ex=settings.cache_ttl_seconds)


class RateLimitExceededError(Exception):
    pass


def check_rate_limit(client: redis.Redis, user_id: str) -> None:
    """Fixed-window limiter: N requests per calendar minute per user."""
    settings = get_settings()
    window = int(time.time() // 60)
    key = f"agent:ratelimit:{user_id}:{window}"

    count = client.incr(key)
    if count == 1:
        client.expire(key, 60)
    if count > settings.rate_limit_per_minute:
        raise RateLimitExceededError(
            f"user {user_id} exceeded {settings.rate_limit_per_minute} requests/minute"
        )
