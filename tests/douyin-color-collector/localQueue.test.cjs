const test = require('node:test');
const assert = require('node:assert/strict');

const { LocalQueue, QueueCapacityError } = require('../../tools/douyin-color-collector/localQueue');

class MemoryStore {
  constructor() { this.value = { batches: [] }; }
  async load() { return structuredClone(this.value); }
  async save(value) { this.value = structuredClone(value); }
}

test('queue persists fixed parts, resumes missing parts, and removes completed data after seven days', async () => {
  let now = 1000;
  const store = new MemoryStore();
  const queue = new LocalQueue({ store, now: () => now, capacityBytes: 10_000 });
  await queue.enqueueBatch({ id: 'batch-1', parts: [{ number: 1, body: 'one' }, { number: 2, body: 'two' }] });
  await queue.markPartUploaded('batch-1', 1);
  assert.deepEqual(await queue.missingParts('batch-1'), [2]);
  const reloaded = new LocalQueue({ store, now: () => now, capacityBytes: 10_000 });
  assert.deepEqual(await reloaded.missingParts('batch-1'), [2]);
  await reloaded.markPartUploaded('batch-1', 2);
  now += 7 * 24 * 60 * 60 * 1000 + 1;
  assert.equal(await reloaded.cleanupCompleted(), 1);
  assert.deepEqual((await store.load()).batches, []);
});
test('queue refuses new collection at 80 percent and exports unfinished data without signed fields', async () => {
  const store = new MemoryStore();
  const queue = new LocalQueue({ store, capacityBytes: 100 });
  await queue.enqueueBatch({ id: 'safe', parts: [{ number: 1, body: 'x'.repeat(80), signature: 'drop-me' }] });
  await assert.rejects(() => queue.enqueueBatch({ id: 'blocked', parts: [{ number: 1, body: 'x' }] }), QueueCapacityError);
  const exported = await queue.exportUnuploaded();
  assert.equal(JSON.stringify(exported).includes('drop-me'), false);
  assert.equal(JSON.stringify(exported).includes('signature'), false);
});
