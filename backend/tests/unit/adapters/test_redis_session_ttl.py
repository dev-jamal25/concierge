"""Unit tests for RedisSession fixed-TTL behaviour (T184) and delete_by_tenant (T191).

Uses fakeredis so no live Redis is needed.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis

from app.adapters.session.redis_session import RedisSession


@pytest_asyncio.fixture
async def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest_asyncio.fixture
async def store(redis_client):
    s = RedisSession.__new__(RedisSession)
    s._redis = redis_client
    return s


# ---------------------------------------------------------------------------
# T184: Fixed TTL — second write must NOT reset the expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_write_sets_ttl(store, redis_client):
    key = "tid1:cid1"
    await store.store(key, {"turn": 1}, ttl=3600)
    ttl = await redis_client.ttl(store._key(key))
    assert 0 < ttl <= 3600


@pytest.mark.asyncio
async def test_second_write_does_not_reset_ttl(store, redis_client):
    key = "tid1:cid2"
    await store.store(key, {"turn": 1}, ttl=3600)
    ttl_after_first = await redis_client.ttl(store._key(key))

    # Simulate a 1-second gap by manually reducing TTL on the fake key
    await redis_client.expire(store._key(key), ttl_after_first - 1)

    await store.store(key, {"turn": 2}, ttl=3600)
    ttl_after_second = await redis_client.ttl(store._key(key))

    # TTL after 2nd write must be strictly less than the original 3600
    assert ttl_after_second < 3600
    # And the value must have been updated
    retrieved = await store.retrieve(key)
    assert retrieved == {"turn": 2}


@pytest.mark.asyncio
async def test_retrieve_returns_none_for_missing_key(store):
    result = await store.retrieve("nonexistent:key")
    assert result is None


# ---------------------------------------------------------------------------
# T191: delete_by_tenant scopes deletion to one tenant only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_by_tenant_removes_only_target_tenant(store, redis_client):
    tenant_a = uuid4()
    tenant_b = uuid4()
    conv1 = uuid4()
    conv2 = uuid4()
    conv3 = uuid4()

    await store.store(f"{tenant_a}:{conv1}", ["turn_a1"], ttl=3600)
    await store.store(f"{tenant_a}:{conv2}", ["turn_a2"], ttl=3600)
    await store.store(f"{tenant_b}:{conv3}", ["turn_b1"], ttl=3600)

    await store.delete_by_tenant(tenant_a)

    assert await store.retrieve(f"{tenant_a}:{conv1}") is None
    assert await store.retrieve(f"{tenant_a}:{conv2}") is None
    # Tenant B key must survive
    assert await store.retrieve(f"{tenant_b}:{conv3}") == ["turn_b1"]


@pytest.mark.asyncio
async def test_delete_by_tenant_no_keys_does_not_raise(store):
    # Should be a no-op
    await store.delete_by_tenant(uuid4())
