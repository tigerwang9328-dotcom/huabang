const test = require('node:test');
const assert = require('node:assert/strict');

const { GlobalScheduler } = require('../../tools/douyin-color-collector/globalScheduler');

class MemoryStore {
  constructor() { this.value = null; }
  async get() { return this.value; }
  async set(value) { this.value = structuredClone(value); }
}

test('two workers share a 1000ms start interval and at most two leases', async () => {
  let now = 10_000;
  const store = new MemoryStore();
  const first = new GlobalScheduler({ store, now: () => now, random: () => 0 });
  const second = new GlobalScheduler({ store, now: () => now, random: () => 0 });

  const one = await first.tryAcquire('primary');
  assert.equal(one.granted, true);
  const tooSoon = await second.tryAcquire('primary');
  assert.deepEqual(tooSoon, { granted: false, reason: 'rate_limited', waitMs: 1000 });

  now += 1000;
  const two = await second.tryAcquire('primary');
  assert.equal(two.granted, true);
  now += 1000;
  const capacity = await first.tryAcquire('primary');
  assert.deepEqual(capacity, { granted: false, reason: 'concurrency_limited', waitMs: 1000 });
  await first.release(one.leaseId);
  const three = await first.tryAcquire('primary');
  assert.equal(three.granted, true);
});

test('simultaneous workers cannot both acquire the same global start slot', async () => {
  const store = new MemoryStore();
  const first = new GlobalScheduler({ store, now: () => 10_000, random: () => 0 });
  const second = new GlobalScheduler({ store, now: () => 10_000, random: () => 0 });
  const results = await Promise.all([first.tryAcquire('primary'), second.tryAcquire('primary')]);
  assert.equal(results.filter((result) => result.granted).length, 1);
  assert.equal(results.filter((result) => result.reason === 'rate_limited').length, 1);
});

test('429 uses bounded backoff and auth or account switches stop collection', async () => {
  let now = 20_000;
  const store = new MemoryStore();
  const scheduler = new GlobalScheduler({ store, now: () => now, random: () => 0 });
  const lease = await scheduler.tryAcquire('primary');
  const retry = await scheduler.recordFailure(lease.leaseId, { status: 429, retryCount: 2 });
  assert.deepEqual(retry, { retryable: true, retryCount: 3, waitMs: 4000 });
  now += 4000;
  assert.equal((await scheduler.tryAcquire('primary')).granted, true);
  assert.deepEqual(await scheduler.classifyResponse(401), { stopped: true, reason: 'auth_required' });
  assert.deepEqual(await scheduler.switchAccount('secondary'), { stopped: true, reason: 'account_switched' });
  assert.deepEqual(await scheduler.tryAcquire('primary'), { granted: false, reason: 'account_switched', waitMs: 0 });
});

test('scheduler permits the full 0..500ms jitter budget for rate-limit retries', async () => {
  const store = new MemoryStore();
  const scheduler = new GlobalScheduler({ store, now: () => 20_000, random: () => 0.999999 });
  const lease = await scheduler.tryAcquire('primary');
  const retry = await scheduler.recordFailure(lease.leaseId, { status: 429, retryCount: 0 });
  assert.equal(retry.waitMs, 1500);
});
