from __future__ import annotations

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.main import app, redis_dependency


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def client(fake_redis):
    app.dependency_overrides[redis_dependency] = lambda: fake_redis
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
