"""Integration tests for SessionMemory (T190) using fakeredis.

Covers:
- Turn 2 sees Turn 1's context (memory is cross-turn)
- Tenant/conversation keys are isolated (Tenant A can't see Tenant B)
- History cap (session_max_messages) is respected
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
import fakeredis.aioredis as fakeredis

from app.adapters.session.redis_session import RedisSession
from app.use_cases.session_memory import SessionMemory


@pytest_asyncio.fixture
async def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest_asyncio.fixture
async def session_store(redis_client):
    s = RedisSession.__new__(RedisSession)
    s._redis = redis_client
    return s


@pytest_asyncio.fixture
async def memory(session_store):
    return SessionMemory(session_store, ttl=3600, max_messages=20)


# ---------------------------------------------------------------------------
# Cross-turn continuity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_2_sees_turn_1(memory):
    tenant = uuid4()
    conv = uuid4()

    # First turn
    await memory.append_turn(tenant, conv, "Hello", "Hi there!")

    # Second turn: load should contain the first turn
    history = await memory.load(tenant, conv)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Hello"}
    assert history[1] == {"role": "assistant", "content": "Hi there!"}


@pytest.mark.asyncio
async def test_accumulates_multiple_turns(memory):
    tenant = uuid4()
    conv = uuid4()

    await memory.append_turn(tenant, conv, "Q1", "A1")
    await memory.append_turn(tenant, conv, "Q2", "A2")

    history = await memory.load(tenant, conv)
    assert len(history) == 4
    assert history[2] == {"role": "user", "content": "Q2"}
    assert history[3] == {"role": "assistant", "content": "A2"}


# ---------------------------------------------------------------------------
# Tenant/conversation isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_a_and_b_keys_isolated(memory):
    tenant_a = uuid4()
    tenant_b = uuid4()
    conv = uuid4()

    await memory.append_turn(tenant_a, conv, "A asks", "A gets answer")

    # Tenant B with same conv_id sees nothing
    history_b = await memory.load(tenant_b, conv)
    assert history_b == []


@pytest.mark.asyncio
async def test_different_conversations_isolated(memory):
    tenant = uuid4()
    conv_a = uuid4()
    conv_b = uuid4()

    await memory.append_turn(tenant, conv_a, "Conv A message", "Conv A reply")

    history_b = await memory.load(tenant, conv_b)
    assert history_b == []


# ---------------------------------------------------------------------------
# Cap enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_cap_drops_oldest_turns():
    # Use cap of 4 messages (2 turns)
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    store = RedisSession.__new__(RedisSession)
    store._redis = redis_client
    mem = SessionMemory(store, ttl=3600, max_messages=4)

    tenant = uuid4()
    conv = uuid4()

    await mem.append_turn(tenant, conv, "Q1", "A1")  # messages 1-2
    await mem.append_turn(tenant, conv, "Q2", "A2")  # messages 3-4
    await mem.append_turn(tenant, conv, "Q3", "A3")  # would be 5-6 → cap at 4

    history = await mem.load(tenant, conv)
    assert len(history) == 4
    # Oldest (Q1/A1) must be dropped
    assert history[0] == {"role": "user", "content": "Q2"}
    assert history[-1] == {"role": "assistant", "content": "A3"}


@pytest.mark.asyncio
async def test_load_returns_empty_list_for_new_conversation(memory):
    history = await memory.load(uuid4(), uuid4())
    assert history == []
