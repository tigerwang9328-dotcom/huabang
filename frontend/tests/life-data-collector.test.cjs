'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const scriptPath = path.join(__dirname, '..', 'public', 'life-data-collector.user.js')
const core = require(scriptPath)

const ACCOUNT_ID = '1798826701211732'
const LIFE_ACCOUNT_ID = '7319301636050913280'

function makeTemplate() {
  return {
    path: '/flow/content/analysis/video',
    groupid: ACCOUNT_ID,
    biz_params: {
      module_params: {
        ItemRank: {
          offset: 0,
          limit: 20,
          filters: { content_type: 'video' },
        },
      },
    },
  }
}

test('declares the required Tampermonkey metadata', () => {
  const source = fs.readFileSync(scriptPath, 'utf8')

  for (const line of [
    '// @version      1.2.0',
    '// @match        https://www.life-data.cn/*',
    '// @run-at       document-start',
    '// @grant        GM_xmlhttpRequest',
    '// @grant        GM_getValue',
    '// @grant        GM_setValue',
    '// @grant        GM_deleteValue',
    '// @grant        GM_registerMenuCommand',
    '// @grant        unsafeWindow',
    '// @connect      hbreare.com',
  ]) {
    assert.equal(source.includes(line), true, `missing metadata: ${line}`)
  }
})

test('collector panel reports learned api templates and full collection feedback', () => {
  const source = fs.readFileSync(scriptPath, 'utf8')
  assert.equal(source.includes('已登记模板'), true)
  assert.equal(source.includes('立即全量采集'), true)
  assert.equal(source.includes('采集中…'), true)
})

test('collector panel exposes scheduler, template selection, invalid count and drain estimate', () => {
  const source = fs.readFileSync(scriptPath, 'utf8')
  for (const label of ['下次视频采集', '下次核心采集', '本轮模板', '失效模板', '队列排空预计']) {
    assert.equal(source.includes(label), true, `missing panel field: ${label}`)
  }
})

test('estimates queue drain from the active 40/20 per-minute upload rate', () => {
  assert.equal(core.estimateQueueDrainMs(0, 40), 0)
  assert.equal(core.estimateQueueDrainMs(1, 40), 1_500)
  assert.equal(core.estimateQueueDrainMs(40, 40), 60_000)
  assert.equal(core.estimateQueueDrainMs(40, 20), 120_000)
})

test('sanitizes headers, tokens, request bodies and signatures from panel and status errors', () => {
  const raw = 'Authorization: Bearer top-secret Cookie=session=abc token=tok-123 signature=sig-456 request body={"password":"pw"}'
  const clean = core.sanitizeStatusError(raw)
  for (const secret of ['top-secret', 'session=abc', 'tok-123', 'sig-456', '"password":"pw"']) {
    assert.equal(clean.includes(secret), false, `leaked secret: ${secret}`)
  }
  assert.match(clean, /\[redacted\]/i)

  const jsonClean = core.sanitizeStatusError('{"token":"json-token","signature":"json-signature"}')
  assert.equal(jsonClean.includes('json-token'), false)
  assert.equal(jsonClean.includes('json-signature'), false)
})

test('redacts complete structured header and request-body containers with bounded nested traversal', () => {
  const raw = JSON.stringify({
    message: 'LifeData HTTP 503',
    headers: { 'x-api-key': 'header-secret', unknown: 'header-value' },
    nested: [{ request_body: { foo: 'body-secret', unknown: 'body-value' } }, {
      requestBody: [{ deeply: { token: 'nested-token', ordinary: 'keep-me' } }],
    }],
  })
  const clean = core.sanitizeStatusError(raw)
  for (const leaked of ['header-secret', 'header-value', 'body-secret', 'body-value', 'nested-token']) {
    assert.equal(clean.includes(leaked), false, `leaked structured value: ${leaked}`)
  }
  assert.match(clean, /\[redacted\]/i)
  assert.match(clean, /LifeData HTTP 503/)
  assert.ok(clean.length <= 500)

  let deep = { value: 'beyond-depth-secret' }
  for (let index = 0; index < 20; index += 1) deep = { nested: [deep] }
  const deepClean = core.sanitizeStatusError(JSON.stringify(deep))
  assert.equal(deepClean.includes('beyond-depth-secret'), false)
  assert.ok(deepClean.length <= 500)
})

test('malformed JSON fallback redacts snake, camel, hyphen and plain request body containers', () => {
  const samples = [
    'failed {"headers":{"x-api-key":"secret","unknown":"value"}',
    'failed {"request_body":{"foo":"snake-secret","unknown":"snake-value"}',
    'failed requestBody={"foo":"camel-secret","unknown":"camel-value"}',
    'failed request-body={"foo":"hyphen-secret","unknown":"hyphen-value"}',
    'failed request body={"foo":"plain-secret","unknown":"plain-value"}',
  ]
  for (const sample of samples) {
    const clean = core.sanitizeStatusError(sample)
    assert.doesNotMatch(clean, /secret|unknown|value/i)
    assert.match(clean, /\[redacted\]/i)
  }
  assert.equal(core.sanitizeStatusError('LifeData HTTP 403'), 'LifeData HTTP 403')
})

test('redacts nested structured request-payload variants without treating arbitrary payload as sensitive', () => {
  for (const key of ['request_payload', 'requestPayload', 'request-payload']) {
    const clean = core.sanitizeStatusError(JSON.stringify({ nested: [{ [key]: {
      unknown: 'payload-secret', ordinary: 'payload-value',
    } }] }))
    assert.equal(clean.includes('payload-secret'), false, `leaked ${key} secret`)
    assert.equal(clean.includes('payload-value'), false, `leaked ${key} value`)
    assert.match(clean, /\[redacted\]/i)
  }
  const ordinary = core.sanitizeStatusError('{"payload":{"ordinary":"kept"}}')
  assert.match(ordinary, /kept/)
})

test('malformed JSON fallback redacts quoted and unquoted request-payload variants', () => {
  const samples = [
    'failed {"request_payload":{"unknown":"snake-secret"}',
    'failed requestPayload={"unknown":"camel-secret"}',
    'failed request-payload={"unknown":"hyphen-secret"}',
    'failed request payload={"unknown":"plain-secret"}',
  ]
  for (const sample of samples) {
    const clean = core.sanitizeStatusError(sample)
    assert.doesNotMatch(clean, /unknown|secret/i)
    assert.match(clean, /\[redacted\]/i)
  }
  assert.equal(core.sanitizeStatusError('LifeData HTTP 500'), 'LifeData HTTP 500')
})

test('does not double every successful ingest with an immediate status request', () => {
  const source = fs.readFileSync(scriptPath, 'utf8')
  assert.equal(
    source.includes("if (state.isLeader) void postCollectorStatus('online')"),
    false,
  )
})

test('rolling upload limit waits only until the oldest live timestamp expires', () => {
  const now = 100_000
  assert.equal(core.nextRateLimitDelay(Array.from({ length: 39 }, (_, i) => now - i * 1000), now, 40, 60_000), 0)
  const forty = Array.from({ length: 40 }, (_, i) => now - 59_000 + i * 1000)
  assert.equal(core.nextRateLimitDelay(forty, now, 40, 60_000), 1_000)
  assert.equal(core.nextRateLimitDelay([now - 60_001, ...forty.slice(1, 40)], now, 40, 60_000), 0)
})

test('stale separated 429 responses do not count as consecutive', () => {
  const first = core.nextUploadRateState({}, { httpStatus: 429 }, 10_000)
  const separated = core.nextUploadRateState(first, { httpStatus: 429 }, 10_000 + 300_001)
  assert.equal(separated.consecutive429, 1)
  assert.equal(core.effectiveRateLimit(separated, 400_001, 2), 40)
})

test('reduced rate persists after time passes until a post-cooldown success', () => {
  const first = core.nextUploadRateState({}, { httpStatus: 429 }, 10_000)
  const reduced = core.nextUploadRateState(first, { httpStatus: 429 }, 70_000)
  assert.equal(core.effectiveRateLimit(reduced, 86_400_000, 2), 20)
  const recovered = core.nextUploadRateState(reduced, { ok: true }, 86_400_000)
  assert.equal(core.effectiveRateLimit(recovered, 86_400_000, 2), 40)
  assert.equal(recovered.consecutive429, 0)
  const legacyReduced = { consecutive429: 2, cooldownUntil: 70_000, reducedUntil: 70_000 }
  assert.equal(core.effectiveRateLimit(legacyReduced, 86_400_000, 2), 20)
  assert.equal(core.effectiveRateLimit(core.nextUploadRateState(legacyReduced, { ok: true }, 86_400_000), 86_400_000, 2), 40)
})

test('network and HTTP 5xx failures break the 429 sequence without entering recovery', () => {
  const first429 = core.nextUploadRateState({}, { httpStatus: 429 }, 10_000)
  for (const outcome of [{ httpStatus: 0 }, { httpStatus: 503 }]) {
    const interrupted = core.nextUploadRateState(first429, outcome, 20_000)
    assert.equal(interrupted.consecutive429, 0)
    assert.equal(interrupted.reducedMode, false)
    const later429 = core.nextUploadRateState(interrupted, { httpStatus: 429 }, 30_000)
    assert.equal(later429.consecutive429, 1)
  }
})

test('permanent HTTP 4xx breaks the 429 sequence and never counts toward reduction', () => {
  const first429 = core.nextUploadRateState({}, { httpStatus: 429 }, 10_000)
  const permanent = core.nextUploadRateState(first429, { httpStatus: 422 }, 20_000)
  assert.equal(permanent.consecutive429, 0)
  assert.equal(core.effectiveRateLimit(permanent, 20_000, 2), 40)
})

test('queue watermarks pause at 500 and resume only at 300', () => {
  assert.equal(core.shouldPauseAutoCollection({ count: 499, bytes: 1 }, false), false)
  assert.equal(core.shouldPauseAutoCollection({ count: 500, bytes: 1 }, false), true)
  assert.equal(core.shouldPauseAutoCollection({ count: 301, bytes: 1 }, true), true)
  assert.equal(core.shouldPauseAutoCollection({ count: 300, bytes: 1 }, true), false)
  assert.equal(core.shouldPauseAutoCollection({ count: 1, bytes: 50 * 1024 * 1024 }, false), true)
})

test('full queue merges only newest matching passive unclaimed capture', async () => {
  const make = (id, capabilityKey, claimedBy) => ({
    payload: { event_id: id, response_payload: { value: id } }, capabilityKey,
    attempt: 0, nextAttemptAt: 0, claimedBy,
  })
  const queue = Array.from({ length: 500 }, (_, index) => make(`e-${index}`, index > 497 ? 'same' : `c-${index}`, index === 499 ? 'worker' : undefined))
  const merged = core.enqueueQueueEntry(queue, make('replacement', 'same'), { passive: true, maxEntries: 500 })
  assert.equal(merged.status, 'merged')
  assert.equal(merged.queue.length, 500)
  assert.equal(merged.queue[498].payload.event_id, 'replacement')
  assert.equal(merged.queue[499].payload.event_id, 'e-499')
  const rejected = core.enqueueQueueEntry(queue, make('other', 'absent'), { passive: true, maxEntries: 500 })
  assert.equal(rejected.status, 'queue_full')
  assert.deepEqual(rejected.queue, queue)
})

test('queue capacity and byte ceiling never evict claimed or retryable old entries', () => {
  const old = { payload: { event_id: 'old', body: 'x'.repeat(100) }, attempt: 4, nextAttemptAt: 99 }
  const result = core.enqueueQueueEntry([old], { payload: { event_id: 'new', body: 'y'.repeat(100) }, attempt: 0, nextAttemptAt: 0 }, { maxEntries: 500, maxBytes: 150 })
  assert.equal(result.status, 'queue_full')
  assert.equal(result.queue[0].payload.event_id, 'old')
})

test('memory queue transactions persist before callers can upload and claim oldest due first', async () => {
  const store = core.createMemoryQueueStore()
  await store.transaction(() => ({ records: [
    { payload: { event_id: 'new' }, nextAttemptAt: 20 },
    { payload: { event_id: 'old' }, nextAttemptAt: 10 },
  ] }))
  assert.deepEqual((await store.snapshot()).map((entry) => entry.payload.event_id), ['new', 'old'])
  const selected = core.selectOldestDue(await store.snapshot(), 20)
  assert.equal(selected.payload.event_id, 'old')
})

function fakeGm(initial = [], fail = () => false) {
  const values = new Map(initial)
  const calls = []
  return {
    values, calls,
    get(key, fallback) { calls.push(['get', key]); return values.has(key) ? structuredClone(values.get(key)) : fallback },
    set(key, value) { calls.push(['set', key]); if (fail('set', key, value)) throw new Error('set failed'); values.set(key, structuredClone(value)) },
    delete(key) { calls.push(['delete', key]); if (fail('delete', key)) throw new Error('delete failed'); values.delete(key) },
  }
}

test('GM adapter stores payloads per event and meta contains no response payload', async () => {
  const gm = fakeGm()
  const store = core.createGmQueueStore(gm)
  const one = { payload: { event_id: 'one', response_payload: { large: 'x'.repeat(1000) } }, nextAttemptAt: 5 }
  await store.transaction(() => ({ records: [one] }))
  const meta = gm.values.get('lifeDataQueue:meta')
  assert.deepEqual(gm.values.get(meta.entries[0].key), one)
  assert.equal(JSON.stringify(meta).includes('response_payload'), false)
  assert.equal(meta.count, 1)
  assert.equal(meta.totalBytes, core.jsonByteLength(one))
})

test('GM hot update reads and rewrites only target payload plus small meta', async () => {
  const gm = fakeGm()
  const store = core.createGmQueueStore(gm)
  await store.transaction(() => ({ records: [
    { payload: { event_id: 'one', response_payload: { v: 1 } }, nextAttemptAt: 1 },
    { payload: { event_id: 'two', response_payload: { v: 2 } }, nextAttemptAt: 2 },
  ] }))
  gm.calls.length = 0
  await store.transaction((records) => ({ records: records.map((record) => record.payload.event_id === 'one' ? { ...record, claimedBy: 'w' } : record) }))
  const touchedPayloadKeys = gm.calls.filter((call) => /:event:/.test(call[1])).map((call) => call[1])
  assert.equal(touchedPayloadKeys.some((key) => key.includes(':two:')), false)
  assert.equal(new Set(touchedPayloadKeys).size, 2)
  assert.equal(gm.calls.some((call) => call[1] === 'lifeDataQueue:pending'), true)
})

test('restart rolls back new enqueue when version write succeeded but meta switch failed', async () => {
  let failMeta = true
  const gm = fakeGm([], (op, key) => failMeta && op === 'set' && key.endsWith(':meta'))
  const store = core.createGmQueueStore(gm)
  await assert.rejects(store.transaction(() => ({ records: [{ payload: { event_id: 'one' }, nextAttemptAt: 0 }] })))
  assert.equal(gm.values.has('lifeDataQueue:pending'), true)
  failMeta = false
  const restarted = core.createGmQueueStore(gm)
  assert.equal((await restarted.recover()).status, 'rolled_back')
  assert.deepEqual(await restarted.snapshot(), [])
  assert.equal(gm.values.has('lifeDataQueue:pending'), false)
  assert.equal([...gm.values.keys()].some((key) => key.includes(':event:one:')), false)
})

test('restart preserves old claim retry semantics when updated version meta switch failed', async () => {
  let failMeta = false
  const gm = fakeGm([], (op, key) => failMeta && op === 'set' && key.endsWith(':meta'))
  const store = core.createGmQueueStore(gm)
  await store.transaction(() => ({ records: [{ payload: { event_id: 'one' }, attempt: 2, nextAttemptAt: 55 }] }))
  failMeta = true
  await assert.rejects(store.transaction((records) => ({ records: records.map((record) => ({
    ...record, attempt: 3, nextAttemptAt: 99, claimedBy: 'worker', claimExpiresAt: 123,
  })) })))
  failMeta = false
  const restarted = core.createGmQueueStore(gm)
  assert.equal((await restarted.recover()).status, 'rolled_back')
  const [record] = await restarted.snapshot()
  assert.equal(record.attempt, 2)
  assert.equal(record.nextAttemptAt, 55)
  assert.equal(record.claimedBy, undefined)
})

test('cleanup failure leaves journal and restart removes old version without losing indexed record', async () => {
  let oldKey = null
  let failDelete = false
  const gm = fakeGm([], (op, key) => failDelete && op === 'delete' && key === oldKey)
  const store = core.createGmQueueStore(gm)
  await store.transaction(() => ({ records: [{ payload: { event_id: 'one' }, attempt: 0, nextAttemptAt: 1 }] }))
  oldKey = gm.values.get('lifeDataQueue:meta').entries[0].key
  failDelete = true
  await assert.rejects(store.transaction((records) => ({ records: records.map((record) => ({ ...record, attempt: 1 })) })))
  assert.equal(gm.values.has('lifeDataQueue:pending'), true)
  failDelete = false
  const restarted = core.createGmQueueStore(gm)
  assert.equal((await restarted.recover()).status, 'completed')
  assert.equal(gm.values.has(oldKey), false)
  assert.equal((await restarted.snapshot())[0].attempt, 1)
  assert.equal(gm.values.has('lifeDataQueue:pending'), false)
})

test('independent stores at the same clock tick never reuse a cleaned version key', async () => {
  const gm = fakeGm()
  const realNow = Date.now
  Date.now = () => 12345
  try {
    const first = core.createGmQueueStore(gm)
    const second = core.createGmQueueStore(gm)
    await first.transaction(() => ({ records: [{ payload: { event_id: 'one' }, attempt: 0, nextAttemptAt: 1 }] }))
    const firstKey = gm.values.get('lifeDataQueue:meta').entries[0].key
    await second.transaction((records) => ({ records: records.map((record) => ({ ...record, attempt: 1 })) }))
    const secondKey = gm.values.get('lifeDataQueue:meta').entries[0].key
    assert.notEqual(secondKey, firstKey)
    assert.equal(gm.values.has(secondKey), true)
    assert.equal(gm.values.has(firstKey), false)
  } finally {
    Date.now = realNow
  }
})

test('injected version generator collision with old key retries before commit', async () => {
  const gm = fakeGm()
  const tokens = ['initial', 'initial', 'replacement']
  const store = core.createGmQueueStore(gm, { generateVersionToken: () => tokens.shift() })
  await store.transaction(() => ({ records: [{ payload: { event_id: 'one' }, attempt: 0 }] }))
  const oldKey = gm.values.get('lifeDataQueue:meta').entries[0].key
  await store.transaction((records) => ({ records: records.map((record) => ({ ...record, attempt: 1 })) }))
  const newKey = gm.values.get('lifeDataQueue:meta').entries[0].key
  assert.notEqual(newKey, oldKey)
  assert.match(newKey, /replacement$/)
  assert.equal(gm.values.has(newKey), true)
})

test('legacy GM array migration is reentrant after a partial per-record write', async () => {
  let failures = 1
  const gm = fakeGm([['lifeDataQueue', [
    { payload: { event_id: 'one' }, nextAttemptAt: 1 },
    { payload: { event_id: 'two' }, nextAttemptAt: 2 },
  ]]], (op, key) => op === 'set' && key.includes(':event:two:') && failures-- > 0)
  const store = core.createGmQueueStore(gm)
  const legacy = {
    read: () => gm.get('lifeDataQueue', []),
    clear: () => gm.delete('lifeDataQueue'),
  }
  assert.equal((await core.migrateLegacyQueue(store, legacy)).status, 'failed')
  assert.equal(gm.values.has('lifeDataQueue'), true)
  assert.equal((await core.migrateLegacyQueue(store, legacy)).status, 'migrated')
  assert.equal(gm.values.has('lifeDataQueue'), false)
  assert.equal(gm.values.get('lifeDataQueue:meta').count, 2)
})

test('legacy migration is idempotent and clears GM only after committed storage', async () => {
  let legacy = [{ payload: { event_id: 'legacy' }, attempt: 1, nextAttemptAt: 5 }]
  let clears = 0
  const store = core.createMemoryQueueStore()
  const gm = { read: () => legacy, clear: () => { clears += 1; legacy = [] } }
  assert.equal((await core.migrateLegacyQueue(store, gm)).status, 'migrated')
  assert.equal(clears, 1)
  assert.equal((await store.snapshot()).length, 1)
  assert.equal((await core.migrateLegacyQueue(store, gm)).status, 'empty')
  assert.equal(clears, 1)
  const failing = { transaction: async () => { throw new Error('disk') } }
  legacy = [{ payload: { event_id: 'keep' } }]
  assert.equal((await core.migrateLegacyQueue(failing, gm)).status, 'failed')
  assert.equal(legacy.length, 1)
  legacy = Array.from({ length: 501 }, (_, index) => ({ payload: { event_id: `overflow-${index}` } }))
  const emptyStore = core.createMemoryQueueStore()
  assert.equal((await core.migrateLegacyQueue(emptyStore, gm)).status, 'failed')
  assert.equal(legacy.length, 501)
})

test('recognizes only authentication failures as invalid replay templates', () => {
  assert.equal(core.isInvalidReplayStatus(401), true)
  assert.equal(core.isInvalidReplayStatus(403), true)
  assert.equal(core.isInvalidReplayStatus(429), false)
  assert.equal(core.isInvalidReplayStatus(500), false)
})

test('classifies the learned LifeData business paths into collection groups', () => {
  assert.equal(core.classifyTemplate({ pagePath: '/flow/content/analysis/video', requestPayload: { biz_params: { module_params: { ItemRank: { offset: 0, limit: 100 } } } } }), 'video')
  assert.equal(core.classifyTemplate({ pagePath: '/flow/content/analysis/video', requestPayload: { biz_params: { module_params: { ContentSummary: {} } } } }), 'other')
  assert.equal(core.classifyTemplate({ pagePath: '/dito/pc/business/page' }), 'business')
  assert.equal(core.classifyTemplate({ pagePath: '/dito/pc/ad/analysis' }), 'advertising')
  assert.equal(core.classifyTemplate({ pagePath: '/store/my/rank' }), 'other')
})

test('template fingerprint ignores dates and pagination but keeps module identity', () => {
  const make = (startDate, offset, moduleName = 'BudgetCardInfo') => ({
    endpoint: '/api/dito/query',
    pagePath: '/dito/pc/ad/analysis',
    requestPayload: {
      biz_params: {
        common_params: { start_date: startDate, end_date: '2026-07-12' },
        module_params: { [moduleName]: { offset, limit: 100 } },
      },
    },
  })
  assert.equal(core.templateFingerprint(make('2026-07-01', 0)), core.templateFingerprint(make('2026-07-06', 100)))
  assert.notEqual(core.templateFingerprint(make('2026-07-01', 0)), core.templateFingerprint(make('2026-07-01', 0, 'TargetAreaDistribute')))
})

test('capability identity ignores dates and canonical field order', () => {
  const make = (startDate, canonicalFields) => ({
    group: 'advertising',
    moduleIdentity: 'BudgetCardInfo',
    endpoint: '/api/dito/query',
    canonicalFields,
    requestPayload: { biz_params: { common_params: { start_date: startDate } } },
  })

  assert.equal(
    core.templateCapabilityIdentity(make('2026-07-01', ['stat_date', 'spend_fen'])),
    core.templateCapabilityIdentity(make('2026-07-15', ['spend_fen', 'stat_date'])),
  )
  assert.notEqual(
    core.templateCapabilityIdentity(make('2026-07-01', ['spend_fen'])),
    core.templateCapabilityIdentity(make('2026-07-01', ['spend_fen', 'stat_date'])),
  )
})

test('selects a deterministic minimal greedy cover from 48 overlapping templates', () => {
  const fields = ['spend_fen', 'verified_gmv_fen', 'stat_date', 'plays']
  const templates = Array.from({ length: 43 }, (_, index) => ({
    id: `noise-${index}`,
    group: ['other', 'video', 'advertising', 'business'][index % 4],
    moduleIdentity: `Noise${index}`,
    endpoint: '/api/dito/query',
    canonicalFields: [fields[index % fields.length]],
    learnedAt: index,
    lastSuccessfulAt: index,
    valid: index === 42 ? false : true,
  }))
  templates.push(
    { id: 'business-cover', group: 'business', moduleIdentity: 'BusinessCover', endpoint: '/api/dito/query', canonicalFields: ['verified_gmv_fen', 'stat_date'], lastSuccessfulAt: 10, learnedAt: 10 },
    { id: 'ad-old', group: 'advertising', moduleIdentity: 'AdCoverOld', endpoint: '/api/dito/query', canonicalFields: ['spend_fen', 'plays'], lastSuccessfulAt: 10, learnedAt: 100 },
    { id: 'ad-new', group: 'advertising', moduleIdentity: 'AdCoverNew', endpoint: '/api/dito/query', canonicalFields: ['spend_fen', 'plays'], lastSuccessfulAt: 20, learnedAt: 1 },
    { id: 'no-gain', group: 'video', moduleIdentity: 'NoGain', endpoint: '/api/dito/query', canonicalFields: ['campaign_id'], lastSuccessfulAt: 999, learnedAt: 999 },
    { id: 'invalid-all', group: 'business', moduleIdentity: 'InvalidAll', endpoint: '/api/dito/query', canonicalFields: fields, valid: false, lastSuccessfulAt: 999, learnedAt: 999 },
  )

  const result = core.selectMinimalTemplates(templates, fields)

  assert.deepEqual(result.selected.map((template) => template.id), ['business-cover', 'ad-new'])
  assert.equal(result.skipped, templates.length - 2)
  assert.deepEqual(result.covered, fields)
  assert.deepEqual(result.missing, [])
  assert.equal(result.selected.some((template) => template.id === 'no-gain'), false)
})

test('uses learnedAt after lastSuccessfulAt and reports missing target fields', () => {
  const templates = [
    { id: 'older-learned', group: 'advertising', moduleIdentity: 'A', endpoint: '/api/dito/query', canonicalFields: ['spend_fen'], lastSuccessfulAt: 10, learnedAt: 10 },
    { id: 'newer-learned', group: 'advertising', moduleIdentity: 'B', endpoint: '/api/dito/query', canonicalFields: ['spend_fen'], lastSuccessfulAt: 10, learnedAt: 20 },
  ]
  const result = core.selectMinimalTemplates(templates, ['spend_fen', 'stat_date'])

  assert.deepEqual(result.selected.map((template) => template.id), ['newer-learned'])
  assert.deepEqual(result.covered, ['spend_fen'])
  assert.deepEqual(result.missing, ['stat_date'])
})

test('only accepts responses containing meaningful metrics for their group', () => {
  assert.equal(core.hasMeaningfulBusinessData({ code: 0, data: { explain: [{ current_ad_cost: null }] } }, 'advertising'), false)
  assert.equal(core.hasMeaningfulBusinessData({ code: 0, data: { indicator: [{ total_ad_cost: 132717 }] } }, 'advertising'), true)
  assert.equal(core.hasMeaningfulBusinessData({ code: 0, data: { overview: [{ verify_gmv: 116000 }] } }, 'business'), true)
})

test('merges structurally equivalent templates by keeping the newest valid request', () => {
  const oldTemplate = { endpoint: '/api/dito/query', pagePath: '/dito/pc/ad/analysis', requestPayload: { biz_params: { module_params: { BudgetCardInfo: {} }, common_params: { start_date: '2026-07-01' } } }, learnedAt: 1 }
  const newTemplate = { ...oldTemplate, requestPayload: { biz_params: { module_params: { BudgetCardInfo: {} }, common_params: { start_date: '2026-07-06' } } }, learnedAt: 2 }
  const registry = core.mergeTemplateRegistry({}, oldTemplate)
  const merged = core.mergeTemplateRegistry(registry, newTemplate)
  assert.equal(Object.keys(merged).length, 1)
  assert.equal(Object.values(merged)[0].learnedAt, 2)
  assert.equal(Object.values(merged)[0].group, 'advertising')
})

test('builds 100-row video pages without mutating template', () => {
  const template = makeTemplate()

  const result = core.buildVideoRequest(template, 100, 100)

  assert.equal(result.biz_params.module_params.ItemRank.offset, 100)
  assert.equal(result.biz_params.module_params.ItemRank.limit, 100)
  assert.deepEqual(result.biz_params.module_params.ItemRank.filters, {
    content_type: 'video',
  })
  assert.equal(template.biz_params.module_params.ItemRank.offset, 0)
  assert.equal(template.biz_params.module_params.ItemRank.limit, 20)
})

test('builds offsets that fetch a 114-row result in two 100-row pages', () => {
  assert.deepEqual(core.buildPageOffsets(114, 100), [0, 100])
  assert.deepEqual(core.buildPageOffsets(100, 100), [0])
  assert.deepEqual(core.buildPageOffsets(0, 100), [])
})

test('extracts a nested itemRank result without inventing zero values', () => {
  const itemRank = {
    total: 114,
    data: [{ item_id: 'video-1', item_play_cnt: 34310 }],
  }
  const response = {
    code: 0,
    data: {
      result: {
        modules: { itemRank },
      },
    },
  }

  assert.equal(core.extractItemRank(response), itemRank)
  assert.equal(core.extractItemRank({ code: 0, data: {} }), null)
})

test('accepts ItemRank casing used by some LifeData responses', () => {
  const itemRank = {
    total: 1,
    data: [{ item_id: 'video-1', item_play_cnt: 2 }],
  }

  assert.equal(
    core.extractItemRank({ code: 0, data: { modules: { ItemRank: itemRank } } }),
    itemRank,
  )
})

test('allows business endpoints and blocks messages, logs, and foreign hosts', () => {
  assert.equal(
    core.isAllowedEndpoint('https://www.life-data.cn/api/dito/query'),
    true,
  )
  assert.equal(
    core.isAllowedEndpoint('https://www.life-data.cn/api/lowcode_api/query?x=1'),
    true,
  )
  assert.equal(core.isAllowedEndpoint('/api/dito/query'), true)
  assert.equal(
    core.isAllowedEndpoint('https://www.life-data.cn/api/msg/query'),
    false,
  )
  assert.equal(
    core.isAllowedEndpoint(
      'https://dypay.douyin.com/addone/alert/api/log_info/batch',
    ),
    false,
  )
  assert.equal(
    core.isAllowedEndpoint('https://evil.example/api/dito/query'),
    false,
  )
  assert.equal(
    core.isAllowedEndpoint('https://www.life-data.cn/api/dito/query/extra'),
    false,
  )
})

test('keeps only the three LifeData session headers for in-browser replay', () => {
  assert.deepEqual(
    core.pickLifeDataHeaders({
      Cookie: 'never-leave-browser',
      Authorization: 'Bearer never-upload',
      'X-TT-LS-Session-ID': 'session-value',
      'Root-Life-Account-ID': LIFE_ACCOUNT_ID,
      'Life-Account-ID': LIFE_ACCOUNT_ID,
      'X-Ignored': 'ignored',
    }),
    {
      'x-tt-ls-session-id': 'session-value',
      'root-life-account-id': LIFE_ACCOUNT_ID,
      'life-account-id': LIFE_ACCOUNT_ID,
    },
  )
})

test('renews a 30-second leader lease only for its owner or after expiry', () => {
  const now = 1_000_000
  const activeOther = { tabId: 'tab-b', expiresAt: now + 1 }

  assert.deepEqual(core.nextLeaderLease(activeOther, 'tab-a', now), {
    isLeader: false,
    lease: activeOther,
  })
  assert.deepEqual(
    core.nextLeaderLease({ tabId: 'tab-a', expiresAt: now + 1 }, 'tab-a', now),
    {
      isLeader: true,
      lease: { tabId: 'tab-a', expiresAt: now + 30_000 },
    },
  )
  assert.deepEqual(
    core.nextLeaderLease({ tabId: 'tab-b', expiresAt: now }, 'tab-a', now),
    {
      isLeader: true,
      lease: { tabId: 'tab-a', expiresAt: now + 30_000 },
    },
  )
})

test('bounds the offline queue at 100 events by dropping the oldest', () => {
  let queue = []
  for (let index = 0; index < 101; index += 1) {
    queue = core.enqueueBounded(queue, { event_id: `event-${index}` }, 100)
  }

  assert.equal(queue.length, 100)
  assert.equal(queue[0].event_id, 'event-1')
  assert.equal(queue[99].event_id, 'event-100')
})

test('uses the documented retry backoff and caps later attempts', () => {
  assert.deepEqual(
    [0, 1, 2, 3, 4, 99].map(core.retryDelayForAttempt),
    [30_000, 120_000, 600_000, 1_800_000, 1_800_000, 1_800_000],
  )
})

test('ingest payload reports the full bounded 500-event queue depth', () => {
  const options = {
    eventId: '00000000-0000-4000-8000-000000000001',
    endpoint: '/api/dito/query',
    pagePath: '/summary',
    requestPayload: {},
    responsePayload: { code: 0 },
    capturedAt: '2026-07-17T00:00:00Z',
  }
  assert.equal(core.buildIngestPayload({ ...options, queueDepth: 499 }).queue_depth, 499)
  assert.equal(core.buildIngestPayload({ ...options, queueDepth: 900 }).queue_depth, 500)
})

test('only durable queue-first outcomes count as capture success', () => {
  for (const status of ['uploaded', 'queued', 'merged', 'coalesced']) {
    assert.equal(core.isCapturePersistedSuccess({ status }), true, status)
  }
  for (const status of ['queue_full', 'queue_failed', 'discarded', undefined]) {
    assert.equal(core.isCapturePersistedSuccess({ status }), false, String(status))
  }
})

test('full success timestamp requires every required collection group healthy', () => {
  const healthy = {
    video: { status: 'healthy' },
    business: { status: 'healthy' },
    advertising: { status: 'healthy' },
  }
  assert.equal(core.requiredCollectionGroupsHealthy(healthy), true)
  assert.equal(core.requiredCollectionGroupsHealthy({ ...healthy, video: { status: 'error' } }), false)
  assert.equal(core.requiredCollectionGroupsHealthy({ ...healthy, business: { status: 'missing' } }), false)
})

test('builds a whitelisted ingest payload without headers or sensitive keys', () => {
  const payload = core.buildIngestPayload({
    eventId: '018f0f7f-1234-7890-abcd-123456789abc',
    endpoint: 'https://www.life-data.cn/api/dito/query',
    pagePath: '/flow/content/analysis/video',
    requestPayload: {
      groupid: ACCOUNT_ID,
      cookie: 'drop-me',
      nested: {
        Authorization: 'drop-me-too',
        'X-TT-LS-Session-ID': 'drop-session',
      },
    },
    responsePayload: {
      code: 0,
      data: {
        ok: true,
        'root-life-account-id': 'drop-account-header',
        'life-account-id': 'drop-life-header',
      },
    },
    capturedAt: '2026-07-12T08:00:00.000Z',
    queueDepth: 7,
  })

  assert.deepEqual(Object.keys(payload).sort(), [
    'account_id',
    'captured_at',
    'endpoint',
    'event_id',
    'page_path',
    'queue_depth',
    'request_payload',
    'response_payload',
    'schema_version',
  ])
  assert.equal(payload.account_id, ACCOUNT_ID)
  assert.equal(payload.endpoint, '/api/dito/query')
  assert.equal(payload.queue_depth, 7)
  assert.deepEqual(payload.request_payload, {
    groupid: ACCOUNT_ID,
    nested: {},
  })
  assert.deepEqual(payload.response_payload, {
    code: 0,
    data: { ok: true },
  })

  const serialized = JSON.stringify(payload).toLowerCase()
  for (const forbidden of [
    'cookie',
    'authorization',
    'x-tt-ls-session-id',
    'root-life-account-id',
    'life-account-id',
    'drop-me',
  ]) {
    assert.equal(serialized.includes(forbidden), false)
  }
})

test('rejects ingest payloads for non-business endpoints', () => {
  assert.throws(
    () =>
      core.buildIngestPayload({
        eventId: '018f0f7f-1234-7890-abcd-123456789abc',
        endpoint: 'https://www.life-data.cn/api/msg/query',
        pagePath: '/messages',
        requestPayload: {},
        responsePayload: { code: 0 },
        capturedAt: '2026-07-12T08:00:00.000Z',
      }),
    /不允许的 LifeData 接口/,
  )
})

test('falls back to the current LifeData URL when request JSON has no groupid', () => {
  assert.equal(
    core.resolveGroupId(
      { biz_params: { module_params: {} } },
      `https://www.life-data.cn/flow/content/analysis/video?groupid=${ACCOUNT_ID}`,
    ),
    ACCOUNT_ID,
  )
  assert.equal(
    core.resolveGroupId(
      { groupid: 'wrong-account' },
      `https://www.life-data.cn/?groupid=${ACCOUNT_ID}`,
    ),
    'wrong-account',
  )
})

test('refreshes last_seven_days to Shanghai yesterday without mutating custom dates', () => {
  const relative = {
    biz_params: {
      date_type: 'last_seven_days',
      start_date: '2026-01-01',
      end_date: '2026-01-07',
    },
  }
  const refreshed = core.refreshRelativeDateRange(
    relative,
    new Date('2026-07-12T16:30:00.000Z'),
  )
  assert.equal(refreshed.biz_params.start_date, '2026-07-06')
  assert.equal(refreshed.biz_params.end_date, '2026-07-12')
  assert.equal(relative.biz_params.start_date, '2026-01-01')

  const custom = {
    date_type: 'custom',
    start_date: '2026-02-01',
    end_date: '2026-02-28',
  }
  assert.deepEqual(
    core.refreshRelativeDateRange(custom, new Date('2026-07-12T16:30:00.000Z')),
    custom,
  )
})
test('classifies permanent and retryable collector upload responses', () => {
  assert.deepEqual(core.classifyUploadResponse(200, { success: true, code: 200 }), {
    ok: true,
    retryable: false,
    reason: 'ok',
  })
  for (const status of [400, 403, 413, 422]) {
    assert.equal(core.classifyUploadResponse(status, null).retryable, false)
  }
  assert.equal(
    core.classifyUploadResponse(200, { success: false, code: 400 }).retryable,
    false,
  )
  for (const status of [0, 401, 429, 503, 500]) {
    assert.equal(core.classifyUploadResponse(status, null).retryable, true)
  }
})

test('validates exact page sizes and unique item ids before publishing', () => {
  const seen = new Set()
  const first = {
    total: 114,
    data: Array.from({ length: 100 }, (_, index) => ({
      item_id: `video-${index}`,
    })),
  }
  const second = {
    total: 114,
    data: Array.from({ length: 14 }, (_, index) => ({
      item_id: `video-${index + 100}`,
    })),
  }
  assert.equal(core.validateVideoPage(first, 114, 0, 100, seen).length, 100)
  assert.equal(core.validateVideoPage(second, 114, 100, 100, seen).length, 14)
  assert.equal(seen.size, 114)
  assert.throws(
    () => core.validateVideoPage({ total: 114, data: second.data.slice(0, 13) }, 114, 100, 100, new Set()),
    /预期 14 条，实际 13 条/,
  )
  assert.throws(
    () =>
      core.validateVideoPage(
        { total: 2, data: [{ item_id: 'same' }, { item_id: 'same' }] },
        2,
        0,
        100,
        new Set(),
      ),
    /item_id 重复/,
  )
})

test('scans canonical fields through arbitrary nested LifeData response structures', () => {
  const response = {
    data: {
      result: {
        list: [{ itemRank: { summary: { metrics: { item_play_cnt: 12 } } } }],
        dimension: {
          extra: {
            total_ad_cost: 345,
            ad_orders: 4,
            total_ad_pay_gmv: 678,
            pay_gmv: 901,
            verify_gmv: 234,
            verify_cert_cnt: 5,
            refund_gmv: 67,
            age: '18-23',
            gender: 'female',
            province: '贵州',
            hour: 13,
            item_id: 'video-1',
            campaign_id: 'campaign-1',
            plan_id: 'plan-1',
            creative_id: 'creative-1',
            store_id: 'store-1',
            date_str: '2026-07-13',
          },
        },
      },
    },
  }

  assert.deepEqual(Object.keys(core.scanCanonicalFields(response)).sort(), [
    'ad_orders', 'ad_pay_gmv_fen', 'audience_age', 'audience_gender', 'campaign_id',
    'creative_id', 'hour', 'pay_gmv_fen', 'plan_id', 'plays', 'refund_gmv_fen',
    'region', 'spend_fen', 'stat_date', 'store_id', 'verified_count',
    'verified_gmv_fen', 'video_id',
  ])
  assert.deepEqual(core.scanCanonicalFields(response).plays, {
    paths: ['$.data.result.list[0].itemRank.summary.metrics.item_play_cnt'],
    count: 1,
  })
})

test('maps aliases, counts duplicates, ignores unknown and sensitive keys', () => {
  const response = {
    data: [
      { item_total_play_cnt: 1, current_ad_cost: 2, current_ad_pay_gmv: 3 },
      { video_id: 'v2', item_play_cnt: 4, totally_unknown_metric: 5 },
    ],
    cookie: { item_play_cnt: 999 },
    Authorization: { total_ad_cost: 999 },
    nested: { 'x-tt-ls-session-id': { pay_gmv: 999 } },
  }
  const found = core.scanCanonicalFields(response)

  assert.equal(found.plays.count, 2)
  assert.equal(found.plays.paths.length, 2)
  assert.equal(found.spend_fen.count, 1)
  assert.equal(found.ad_pay_gmv_fen.count, 1)
  assert.equal(found.video_id.count, 1)
  assert.equal('totally_unknown_metric' in found, false)
  assert.equal('pay_gmv_fen' in found, false)
  assert.equal(JSON.stringify(found).toLowerCase().includes('authorization'), false)
})

test('maps every canonical field including real ad order and ad pay GMV aliases', () => {
  const aliases = {
    item_play_cnt: 'plays',
    total_ad_cost: 'spend_fen',
    order_cnt: 'ad_orders',
    ad_pay_gmv: 'ad_pay_gmv_fen',
    pay_gmv: 'pay_gmv_fen',
    verify_gmv: 'verified_gmv_fen',
    verify_cert_cnt: 'verified_count',
    refund_gmv: 'refund_gmv_fen',
    age: 'audience_age',
    gender: 'audience_gender',
    province: 'region',
    hour: 'hour',
    item_id: 'video_id',
    campaign_id: 'campaign_id',
    plan_id: 'plan_id',
    creative_id: 'creative_id',
    store_id: 'store_id',
    date_str: 'stat_date',
  }
  const response = Object.fromEntries(
    Object.keys(aliases).map((alias, index) => [alias, index + 1]),
  )

  assert.deepEqual(
    Object.keys(core.scanCanonicalFields(response)).sort(),
    Object.values(aliases).sort(),
  )
})

test('keeps browser aliases aligned with backend real-response aliases', () => {
  const aliases = {
    play_count: 'plays',
    verified_gmv: 'verified_gmv_fen',
    age_name: 'audience_age',
    gender_name: 'audience_gender',
    sex: 'audience_gender',
    city_resident: 'region',
    province_resident: 'region',
    hour_str: 'hour',
    aweme_id: 'video_id',
  }

  for (const [alias, canonical] of Object.entries(aliases)) {
    assert.deepEqual(Object.keys(core.scanCanonicalFields({ [alias]: 1 })), [canonical])
  }
})

test('prioritizes every mandatory field before optional guidance', () => {
  assert.deepEqual(core.MANDATORY_FIELDS, ['spend_fen', 'verified_gmv_fen', 'stat_date'])
  const guidance = core.missingFieldGuidance({})
  assert.deepEqual(guidance.slice(0, 3).map((item) => item.field), core.MANDATORY_FIELDS)
})

test('excludes nested credential, token, session, signature, and secret subtrees', () => {
  const response = {
    safe: { item_play_cnt: 1 },
    sessionToken: { total_ad_cost: 2 },
    access_token: { ad_pay_gmv: 3 },
    refreshToken: { pay_gmv: 4 },
    request_signature: { verify_gmv: 5 },
    sign: { refund_gmv: 6 },
    signing_secret: { order_cnt: 7 },
    nested: {
      token: { video_id: 8 },
      'Bearer private-token': { campaign_id: 9 },
    },
  }
  const found = core.scanCanonicalFields(response)

  assert.deepEqual(found, { plays: { paths: ['$.safe.item_play_cnt'], count: 1 } })
  assert.equal(JSON.stringify(found).includes('private-token'), false)
})

test('bounds scanner depth, visited nodes, and sample paths', () => {
  let tooDeep = { item_play_cnt: 1 }
  for (let index = 0; index < 41; index += 1) tooDeep = { next: tooDeep }
  const many = Array.from({ length: 100_001 }, (_, index) => ({
    item_play_cnt: index,
  }))
  const duplicates = Array.from({ length: 12 }, (_, index) => ({
    total_ad_cost: index,
  }))

  assert.equal('plays' in core.scanCanonicalFields(tooDeep), false)
  assert.ok(core.scanCanonicalFields(many).plays.count <= 100_000)
  assert.equal(core.scanCanonicalFields(duplicates).spend_fen.count, 12)
  assert.equal(core.scanCanonicalFields(duplicates).spend_fen.paths.length, 8)
})

test('stops a wide object before a canonical field beyond the node budget', () => {
  const response = {}
  for (let index = 0; index < 100_000; index += 1) {
    response[`filler_${index}`] = index
  }
  response.item_play_cnt = 1

  assert.deepEqual(core.scanCanonicalFields(response), {})
})

test('derives bounded template capabilities without retaining response bodies', () => {
  const template = { endpoint: '/api/dito/query', pagePath: '/dito/pc/ad/analysis' }
  const capability = core.templateCapabilities(template, {
    data: { metrics: { total_ad_cost: 123, stat_date: '2026-07-13' } },
    authorization: 'secret',
  })

  assert.deepEqual(capability.fields, ['spend_fen', 'stat_date'])
  assert.deepEqual(capability.samplePaths, {
    spend_fen: ['$.data.metrics.total_ad_cost'],
    stat_date: ['$.data.metrics.stat_date'],
  })
  assert.equal(JSON.stringify(capability).includes('secret'), false)
  assert.equal('response' in capability, false)
})
