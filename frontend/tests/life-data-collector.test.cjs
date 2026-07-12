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
    '// @match        https://www.life-data.cn/*',
    '// @run-at       document-start',
    '// @grant        GM_xmlhttpRequest',
    '// @grant        GM_getValue',
    '// @grant        GM_setValue',
    '// @grant        GM_registerMenuCommand',
    '// @grant        unsafeWindow',
    '// @connect      hbreare.com',
  ]) {
    assert.equal(source.includes(line), true, `missing metadata: ${line}`)
  }
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
      'Root-Life-Account-ID': ACCOUNT_ID,
      'Life-Account-ID': LIFE_ACCOUNT_ID,
      'X-Ignored': 'ignored',
    }),
    {
      'x-tt-ls-session-id': 'session-value',
      'root-life-account-id': ACCOUNT_ID,
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
  })

  assert.deepEqual(Object.keys(payload).sort(), [
    'account_id',
    'captured_at',
    'endpoint',
    'event_id',
    'page_path',
    'request_payload',
    'response_payload',
    'schema_version',
  ])
  assert.equal(payload.account_id, ACCOUNT_ID)
  assert.equal(payload.endpoint, '/api/dito/query')
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