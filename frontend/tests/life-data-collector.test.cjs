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
    '// @version      1.1.1',
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

test('collector panel reports learned api templates and full collection feedback', () => {
  const source = fs.readFileSync(scriptPath, 'utf8')
  assert.equal(source.includes('已登记模板'), true)
  assert.equal(source.includes('立即全量采集'), true)
  assert.equal(source.includes('采集中…'), true)
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
