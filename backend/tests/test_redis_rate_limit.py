import asyncio

import pytest

import app.core.redis as redis_module


class FakeRedis:
    def __init__(self):
        self.counts = {}
        self.lock = asyncio.Lock()

    async def eval(self, script, key_count, key, max_count, window_seconds):
        assert key_count == 1
        assert "INCR" in script and "EXPIRE" in script
        async with self.lock:
            count = self.counts.get(key, 0) + 1
            self.counts[key] = count
            return 1 if count <= int(max_count) else 0


@pytest.mark.asyncio
async def test_rate_limit_decision_is_atomic_for_concurrent_notification_keys(monkeypatch):
    fake = FakeRedis()

    async def get_fake_redis():
        return fake

    monkeypatch.setattr(redis_module, "get_redis", get_fake_redis)
    results = await asyncio.gather(*(
        redis_module.rate_limit_check("task:event:recipient", 1, 300)
        for _ in range(20)
    ))
    assert sum(results) == 1
