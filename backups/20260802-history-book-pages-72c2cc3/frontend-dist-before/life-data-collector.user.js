// ==UserScript==
// @name         华邦 LifeData 主动采集器
// @namespace    https://hbreare.com/
// @version      1.2.0
// @description  在已登录的生意经页面内采集白名单业务 JSON
// @updateURL     https://hbreare.com/life-data-collector.user.js
// @downloadURL   https://hbreare.com/life-data-collector.user.js
// @match        https://www.life-data.cn/*
// @run-at       document-start
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_deleteValue
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      hbreare.com
// ==/UserScript==

;(function () {
  'use strict'

  const ACCOUNT_ID = '1798826701211732'
  const LIFE_ACCOUNT_ID = '7319301636050913280'
  const LIFE_DATA_ORIGIN = 'https://www.life-data.cn'
  const ALLOWED_ENDPOINTS = new Set([
    '/api/dito/query',
    '/api/lowcode_api/query',
  ])
  const SESSION_HEADERS = new Set([
    'x-tt-ls-session-id',
    'root-life-account-id',
    'life-account-id',
  ])
  const SENSITIVE_JSON_KEYS = new Set([
    'cookie',
    'set-cookie',
    'set_cookie',
    'authorization',
    'x-tt-ls-session-id',
    'x_tt_ls_session_id',
    'root-life-account-id',
    'life-account-id',
  ])
  const CANONICAL_FIELD_ALIASES = Object.freeze({
    plays: ['plays', 'item_play_cnt', 'item_total_play_cnt', 'play_count'],
    spend_fen: ['spend_fen', 'total_ad_cost', 'current_ad_cost'],
    ad_orders: [
      'ad_orders',
      'order_cnt',
      'ad_order_cnt',
      'ad_pay_order_cnt',
      'total_ad_order_cnt',
      'current_ad_order_cnt',
    ],
    ad_pay_gmv_fen: [
      'ad_pay_gmv_fen',
      'ad_pay_gmv',
      'total_ad_pay_gmv',
      'current_ad_pay_gmv',
    ],
    pay_gmv_fen: ['pay_gmv_fen', 'pay_gmv'],
    verified_gmv_fen: ['verified_gmv_fen', 'verify_gmv', 'verified_gmv'],
    verified_count: ['verified_count', 'verify_cert_cnt'],
    refund_gmv_fen: ['refund_gmv_fen', 'refund_gmv'],
    audience_age: ['audience_age', 'age', 'age_range', 'age_name'],
    audience_gender: ['audience_gender', 'gender', 'gender_name', 'sex'],
    region: ['region', 'province', 'city', 'city_resident', 'province_resident'],
    hour: ['hour', 'stat_hour', 'hour_str'],
    video_id: ['video_id', 'item_id', 'aweme_id'],
    campaign_id: ['campaign_id'],
    plan_id: ['plan_id'],
    creative_id: ['creative_id'],
    store_id: ['store_id'],
    stat_date: ['stat_date', 'date_str'],
  })
  const CANONICAL_FIELD_BY_ALIAS = new Map(
    Object.entries(CANONICAL_FIELD_ALIASES).flatMap(([canonical, aliases]) =>
      aliases.map((alias) => [alias, canonical]),
    ),
  )
  const SCAN_MAX_DEPTH = 40
  const SCAN_MAX_NODES = 100_000
  const SCAN_MAX_SAMPLE_PATHS = 8
  const RETRY_DELAYS = [30_000, 120_000, 600_000, 1_800_000]
  const TRUSTED_PROMPT =
    typeof globalThis.prompt === 'function'
      ? globalThis.prompt.bind(globalThis)
      : null

  function deepCloneJson(value) {
    return JSON.parse(JSON.stringify(value))
  }

  function normalizeEndpoint(url) {
    try {
      const parsed = new URL(String(url), LIFE_DATA_ORIGIN)
      if (parsed.origin !== LIFE_DATA_ORIGIN) return null
      return ALLOWED_ENDPOINTS.has(parsed.pathname) ? parsed.pathname : null
    } catch (_error) {
      return null
    }
  }

  function isAllowedEndpoint(url) {
    return normalizeEndpoint(url) !== null
  }

  function findItemRankContainer(root) {
    const stack = [root]
    const seen = new Set()
    while (stack.length > 0) {
      const current = stack.pop()
      if (!current || typeof current !== 'object' || seen.has(current)) continue
      seen.add(current)
      for (const [key, value] of Object.entries(current)) {
        if (
          key.toLowerCase() === 'itemrank' &&
          value &&
          typeof value === 'object' &&
          Array.isArray(value.data) &&
          Number.isFinite(Number(value.total))
        ) {
          return value
        }
      }
      for (const value of Object.values(current)) {
        if (value && typeof value === 'object') stack.push(value)
      }
    }
    return null
  }

  function extractItemRank(response) {
    return findItemRankContainer(response)
  }

  function findMutableItemRank(root) {
    const stack = [root]
    const seen = new Set()
    while (stack.length > 0) {
      const current = stack.pop()
      if (!current || typeof current !== 'object' || seen.has(current)) continue
      seen.add(current)
      for (const [key, value] of Object.entries(current)) {
        if (
          key.toLowerCase() === 'itemrank' &&
          value &&
          typeof value === 'object' &&
          ('offset' in value || 'limit' in value)
        ) {
          return value
        }
      }
      for (const value of Object.values(current)) {
        if (value && typeof value === 'object') stack.push(value)
      }
    }
    return null
  }

  function hasPageableItemRank(request) {
    const rank = findMutableItemRank(request)
    return Boolean(
      rank &&
        Number.isFinite(Number(rank.offset)) &&
        Number.isFinite(Number(rank.limit)) &&
        Number(rank.limit) > 0,
    )
  }

  function getModuleIdentity(request) {
    const moduleParams = findNestedFieldValue(request, [
      'module_params',
      'moduleParams',
    ])
    if (!moduleParams || typeof moduleParams !== 'object') return 'unknown'
    const names = Object.keys(moduleParams).sort()
    return names.length > 0 ? names.join('+') : 'unknown'
  }
  function buildVideoRequest(template, offset, limit) {
    const request = deepCloneJson(template)
    const itemRank = findMutableItemRank(request)
    if (!itemRank) throw new Error('视频模板缺少 ItemRank 分页参数')
    itemRank.offset = Number(offset)
    itemRank.limit = Number(limit)
    return request
  }

  function buildPageOffsets(total, limit = 100) {
    const rowCount = Math.max(0, Math.floor(Number(total)))
    const pageSize = Math.floor(Number(limit))
    if (!Number.isFinite(rowCount) || !Number.isFinite(pageSize) || pageSize <= 0) {
      throw new Error('无效的分页参数')
    }
    const offsets = []
    for (let offset = 0; offset < rowCount; offset += pageSize) {
      offsets.push(offset)
    }
    return offsets
  }

  function pickLifeDataHeaders(headers) {
    const selected = {}
    if (!headers || typeof headers !== 'object') return selected
    for (const [name, value] of Object.entries(headers)) {
      const normalized = String(name).toLowerCase()
      if (SESSION_HEADERS.has(normalized) && value != null) {
        selected[normalized] = String(value)
      }
    }
    return selected
  }

  function sanitizeBusinessJson(value) {
    if (value === null || typeof value === 'string' || typeof value === 'boolean') {
      return value
    }
    if (typeof value === 'number') return Number.isFinite(value) ? value : null
    if (Array.isArray(value)) return value.map(sanitizeBusinessJson)
    if (!value || typeof value !== 'object') return null

    const clean = {}
    for (const [key, child] of Object.entries(value)) {
      if (
        isSensitiveJsonKey(key) ||
        ['__proto__', 'prototype', 'constructor'].includes(
          String(key).toLowerCase(),
        )
      ) {
        continue
      }
      clean[key] = sanitizeBusinessJson(child)
    }
    return clean
  }

  function isSensitiveJsonKey(key) {
    const normalized = String(key).toLowerCase()
    if (SENSITIVE_JSON_KEYS.has(normalized)) return true
    const compact = normalized.replace(/[^a-z0-9]/g, '')
    return (
      compact.includes('cookie') ||
      compact.includes('authorization') ||
      compact.includes('session') ||
      compact.includes('token') ||
      compact.includes('signature') ||
      compact === 'sign' ||
      compact.includes('signingsecret') ||
      compact === 'secret'
    )
  }

  function responsePath(parent, key, isArray) {
    if (isArray) return `${parent}[${key}]`
    return /^[A-Za-z_$][\w$]*$/.test(key)
      ? `${parent}.${key}`
      : `${parent}[${JSON.stringify(key)}]`
  }

  function *jsonEntries(value) {
    if (Array.isArray(value)) {
      for (let index = 0; index < value.length; index += 1) {
        yield [index, value[index]]
      }
      return
    }
    for (const key in value) {
      if (Object.prototype.hasOwnProperty.call(value, key)) {
        yield [key, value[key]]
      }
    }
  }

  function scanCanonicalFields(response) {
    const found = {}
    if (!response || typeof response !== 'object') return found
    const stack = [{
      iterator: jsonEntries(response),
      value: response,
      path: '$',
      depth: 0,
    }]
    const seen = new Set()
    seen.add(response)
    let visited = 1

    while (stack.length > 0 && visited < SCAN_MAX_NODES) {
      const current = stack[stack.length - 1]
      const next = current.iterator.next()
      if (next.done) {
        stack.pop()
        continue
      }
      visited += 1
      const [rawKey, child] = next.value
      const key = String(rawKey)
      const isArray = Array.isArray(current.value)
      const normalized = key.toLowerCase()
      const path = responsePath(current.path, key, isArray)
      if (!isArray && isSensitiveJsonKey(key)) continue
      const canonical = isArray
        ? null
        : CANONICAL_FIELD_BY_ALIAS.get(normalized)
      if (canonical) {
        if (!found[canonical]) found[canonical] = { paths: [], count: 0 }
        found[canonical].count += 1
        if (found[canonical].paths.length < SCAN_MAX_SAMPLE_PATHS) {
          found[canonical].paths.push(path)
        }
      }
      if (
        visited < SCAN_MAX_NODES &&
        child &&
        typeof child === 'object' &&
        current.depth < SCAN_MAX_DEPTH &&
        !seen.has(child)
      ) {
        seen.add(child)
        stack.push({
          iterator: jsonEntries(child),
          value: child,
          path,
          depth: current.depth + 1,
        })
      }
    }
    return found
  }

  function templateCapabilities(_template, response) {
    const scanned = scanCanonicalFields(response)
    const fields = Object.keys(scanned).sort()
    return {
      fields,
      samplePaths: Object.fromEntries(
        fields.map((field) => [field, [...scanned[field].paths]]),
      ),
    }
  }

  const FIELD_GUIDANCE = {
    plays: ['流量', '视频分析'],
    spend_fen: ['投放', '广告分析'],
    ad_orders: ['投放', '广告分析'],
    ad_pay_gmv_fen: ['投放', '广告分析'],
    pay_gmv_fen: ['经营', '经营概览'],
    verified_gmv_fen: ['经营', '经营概览'],
    verified_count: ['经营', '经营概览'],
    refund_gmv_fen: ['经营', '经营概览'],
    audience_age: ['人群分析', '人群分析'],
    audience_gender: ['人群分析', '人群分析'],
    region: ['地域分析', '地域分析'],
    hour: ['时间趋势', '时间趋势'],
    video_id: ['视频详情', '交易明细'],
    campaign_id: ['视频详情', '交易明细'],
    plan_id: ['视频详情', '交易明细'],
    creative_id: ['视频详情', '交易明细'],
    store_id: ['经营', '经营概览'],
    stat_date: ['经营', '经营概览'],
  }
  const MANDATORY_FIELDS = Object.freeze(['spend_fen', 'verified_gmv_fen', 'stat_date'])

  function missingFieldGuidance(registry) {
    const available = new Set()
    for (const template of Object.values(registry || {})) {
      for (const field of Array.isArray(template && template.canonicalFields)
        ? template.canonicalFields
        : []) available.add(field)
    }
    const orderedFields = [
      ...MANDATORY_FIELDS,
      ...Object.keys(FIELD_GUIDANCE).filter((field) => !MANDATORY_FIELDS.includes(field)),
    ]
    return orderedFields
      .filter((field) => !available.has(field))
      .map((field) => {
        const [page, module] = FIELD_GUIDANCE[field]
        return {
          field,
          page,
          module,
          message: `请打开${page} → ${module}并刷新页面`,
        }
      })
  }

  function nextLeaderLease(currentLease, tabId, now, ttl = 30_000) {
    const current =
      currentLease && typeof currentLease === 'object' ? currentLease : null
    const owned = current && current.tabId === tabId
    const expired = !current || Number(current.expiresAt) <= Number(now)
    if (!owned && !expired) return { isLeader: false, lease: currentLease }
    return {
      isLeader: true,
      lease: { tabId, expiresAt: Number(now) + Number(ttl) },
    }
  }

  function enqueueBounded(queue, event, limit = 100) {
    const max = Math.max(1, Math.floor(Number(limit)))
    const next = [...(Array.isArray(queue) ? queue : []), event]
    return next.slice(Math.max(0, next.length - max))
  }

  const QUEUE_HIGH_WATER_COUNT = 500
  const QUEUE_LOW_WATER_COUNT = 300
  const QUEUE_MAX_BYTES = 50 * 1024 * 1024

  function jsonByteLength(value) {
    const text = JSON.stringify(value)
    if (typeof TextEncoder === 'function') return new TextEncoder().encode(text).length
    return unescape(encodeURIComponent(text)).length
  }

  function queueStats(queue) {
    const records = Array.isArray(queue) ? queue : []
    return { count: records.length, bytes: records.reduce((total, record) => total +
      (Number(record && record.__bytes) || jsonByteLength(record)), 0) }
  }

  function shouldPauseAutoCollection(stats, paused = false) {
    const value = stats && typeof stats === 'object' ? stats : {}
    if (paused) return Number(value.count || 0) > QUEUE_LOW_WATER_COUNT || Number(value.bytes || 0) >= QUEUE_MAX_BYTES
    return Number(value.count || 0) >= QUEUE_HIGH_WATER_COUNT || Number(value.bytes || 0) >= QUEUE_MAX_BYTES
  }

  function enqueueQueueEntry(queue, entry, options = {}) {
    const records = Array.isArray(queue) ? queue : []
    const maxEntries = Number(options.maxEntries || QUEUE_HIGH_WATER_COUNT)
    const maxBytes = Number(options.maxBytes || QUEUE_MAX_BYTES)
    const appended = [...records, entry]
    const stats = queueStats(appended)
    if (stats.count <= maxEntries && stats.bytes <= maxBytes) {
      return { status: 'queued', queue: appended, stats }
    }
    if (options.passive && entry && entry.capabilityKey) {
      let mergeIndex = -1
      for (let index = records.length - 1; index >= 0; index -= 1) {
        const candidate = records[index]
        if (candidate && !candidate.claimedBy && candidate.capabilityKey === entry.capabilityKey) {
          mergeIndex = index
          break
        }
      }
      if (mergeIndex >= 0) {
        const merged = records.slice()
        merged[mergeIndex] = entry
        const mergedStats = queueStats(merged)
        if (mergedStats.count <= maxEntries && mergedStats.bytes <= maxBytes) {
          return { status: 'merged', queue: merged, stats: mergedStats }
        }
      }
    }
    return { status: 'queue_full', queue: records, stats: queueStats(records) }
  }

  function selectOldestDue(queue, now) {
    return (Array.isArray(queue) ? queue : [])
      .filter((item) => item && Number(item.nextAttemptAt || 0) <= Number(now) &&
        (!item.claimedBy || Number(item.claimExpiresAt || 0) <= Number(now)))
      .sort((a, b) => Number(a.nextAttemptAt || 0) - Number(b.nextAttemptAt || 0) ||
        String(a.payload && a.payload.captured_at || '').localeCompare(String(b.payload && b.payload.captured_at || '')))[0] || null
  }

  function cloneQueue(value) {
    return typeof structuredClone === 'function'
      ? structuredClone(value)
      : JSON.parse(JSON.stringify(value))
  }

  function stableCaptureValue(value) {
    if (Array.isArray(value)) return value.map(stableCaptureValue)
    if (!value || typeof value !== 'object') return value
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableCaptureValue(value[key])]))
  }

  async function captureDedupeKey(payload, cryptoApi = (typeof globalThis !== 'undefined' ? globalThis.crypto : null)) {
    const safe = sanitizeBusinessJson({
      endpoint: payload && payload.endpoint,
      request_payload: payload && payload.request_payload,
      response_payload: payload && payload.response_payload,
    })
    const text = JSON.stringify(stableCaptureValue(safe))
    const domainText = `huabang-life-data-capture-v1\u0000${text.length}\u0000${text}`
    try {
      if (!cryptoApi || !cryptoApi.subtle || typeof cryptoApi.subtle.digest !== 'function' || typeof TextEncoder !== 'function') return null
      const digest = await cryptoApi.subtle.digest('SHA-256', new TextEncoder().encode(domainText))
      const hex = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
      return /^[0-9a-f]{64}$/.test(hex) ? `${hex}:${text.length}` : null
    } catch (_error) {
      return null
    }
  }

  function createMemoryQueueStore(initial = [], onCommit = null) {
    let records = cloneQueue(Array.isArray(initial) ? initial : [])
    let permits = []
    let dedupe = []
    let pending = Promise.resolve()
    return {
      async snapshot() { return cloneQueue(records) },
      async transaction(mutator) {
        const run = async () => {
          const mutation = await mutator(cloneQueue(records), { permits: cloneQueue(permits), dedupe: cloneQueue(dedupe) })
          const next = mutation && mutation.records
          if (!Array.isArray(next)) throw new Error('invalid queue transaction')
          const committed = cloneQueue(next)
          if (typeof onCommit === 'function' && onCommit(cloneQueue(committed)) === false) {
            throw new Error('queue commit rejected')
          }
          records = committed
          permits = cloneQueue(Array.isArray(mutation.permits) ? mutation.permits : permits)
          dedupe = cloneQueue(Array.isArray(mutation.dedupe) ? mutation.dedupe : dedupe)
          return { records: cloneQueue(records), value: mutation.value }
        }
        const result = pending.then(run, run)
        pending = result.then(() => undefined, () => undefined)
        return result
      },
    }
  }

  function createGmQueueStore(gm, options = {}) {
    const prefix = options.prefix || 'lifeDataQueue'
    const metaKey = `${prefix}:meta`
    const pendingKey = `${prefix}:pending`
    const emptyMeta = () => ({ version: 1, count: 0, totalBytes: 0, entries: [], permits: [], dedupe: [] })
    const readMeta = () => {
      const value = gm.get(metaKey, emptyMeta())
      return value && Array.isArray(value.entries) ? value : emptyMeta()
    }
    let generation = 0
    const cryptoApi = typeof globalThis !== 'undefined' && globalThis.crypto
    const tabNonce = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
    const generateVersionToken = typeof options.generateVersionToken === 'function'
      ? options.generateVersionToken
      : () => cryptoApi && typeof cryptoApi.randomUUID === 'function'
        ? cryptoApi.randomUUID()
        : `${tabNonce}-${generation += 1}`
    const nextRecordKey = (id, oldKey = null) => {
      for (let attempt = 0; attempt < 16; attempt += 1) {
        const token = String(generateVersionToken())
        const key = `${prefix}:event:${encodeURIComponent(id)}:${token}`
        if (key !== oldKey && gm.get(key, undefined) === undefined) return key
      }
      throw new Error('unable to allocate unique queue record version')
    }
    const summary = (record, bytes, key) => ({
      id: String(record.payload.event_id), key, bytes,
      due: Number(record.nextAttemptAt || 0), attempt: Number(record.attempt || 0),
      claimedBy: record.claimedBy || null, claimExpiresAt: Number(record.claimExpiresAt || 0),
      capabilityKey: record.capabilityKey || null,
      capturedAt: String(record.payload.captured_at || ''), updatedAt: Date.now(),
    })
    const stub = (item) => ({
      payload: { event_id: item.id, captured_at: item.capturedAt },
      attempt: item.attempt, nextAttemptAt: item.due,
      claimedBy: item.claimedBy || undefined,
      claimExpiresAt: item.claimExpiresAt || undefined,
      capabilityKey: item.capabilityKey || null,
      __bytes: item.bytes,
    })
    const comparable = (record) => JSON.stringify({
      due: Number(record.nextAttemptAt || 0), attempt: Number(record.attempt || 0),
      claimedBy: record.claimedBy || null, claimExpiresAt: Number(record.claimExpiresAt || 0),
      capabilityKey: record.capabilityKey || null,
    })
    const sameMeta = (left, right) => JSON.stringify(left) === JSON.stringify(right)
    const cleanup = (keys) => {
      for (const key of keys) gm.delete(key)
    }
    const recover = async () => {
      const pending = gm.get(pendingKey, null)
      if (!pending || !pending.oldMeta || !pending.newMeta) return { status: 'clean' }
      const current = readMeta()
      if (sameMeta(current, pending.newMeta)) {
        cleanup(pending.oldKeys || [])
        gm.delete(pendingKey)
        return { status: 'completed' }
      }
      if (!sameMeta(current, pending.oldMeta)) gm.set(metaKey, pending.oldMeta)
      cleanup(pending.newKeys || [])
      gm.delete(pendingKey)
      return { status: 'rolled_back' }
    }
    return {
      recover,
      async snapshot() { return readMeta().entries.map(stub) },
      async transaction(mutator) {
        await recover()
        const beforeMeta = readMeta()
        const before = beforeMeta.entries.map(stub)
        const mutation = await mutator(cloneQueue(before), {
          permits: cloneQueue(Array.isArray(beforeMeta.permits) ? beforeMeta.permits : []),
          dedupe: cloneQueue(Array.isArray(beforeMeta.dedupe) ? beforeMeta.dedupe : []),
        })
        const next = mutation && mutation.records
        if (!Array.isArray(next)) throw new Error('invalid queue transaction')
        const oldById = new Map(beforeMeta.entries.map((item) => [item.id, item]))
        const nextById = new Map(next.map((record) => [String(record.payload.event_id), record]))
        const nextEntries = []
        const changed = []
        for (const record of next) {
          const id = String(record.payload.event_id)
          const old = oldById.get(id)
          const hasPayload = !record.__bytes
          if (!old || hasPayload || comparable(record) !== comparable(stub(old))) {
            const oldRecord = old && !hasPayload ? gm.get(old.key, {}) : null
            const persisted = old && !hasPayload
              ? { ...oldRecord, ...record, payload: oldRecord.payload }
              : record
            const bytes = jsonByteLength(persisted)
            const key = nextRecordKey(id, old && old.key)
            changed.push([key, persisted])
            nextEntries.push(summary(persisted, bytes, key))
          } else nextEntries.push(old)
        }
        const deleted = beforeMeta.entries.filter((item) => !nextById.has(item.id))
        const nextMeta = { version: 1, count: nextEntries.length,
          totalBytes: nextEntries.reduce((total, item) => total + item.bytes, 0), entries: nextEntries,
          permits: cloneQueue(Array.isArray(mutation.permits) ? mutation.permits : (beforeMeta.permits || [])),
          dedupe: cloneQueue(Array.isArray(mutation.dedupe) ? mutation.dedupe : (beforeMeta.dedupe || [])) }
        const changedIds = new Set(nextEntries.filter((item) =>
          !oldById.has(item.id) || oldById.get(item.id).key !== item.key).map((item) => item.id))
        const oldKeys = beforeMeta.entries.filter((item) =>
          deleted.some((entry) => entry.id === item.id) || changedIds.has(item.id)).map((item) => item.key)
        const newKeys = changed.map(([key]) => key)
        try {
          for (const [key, record] of changed) gm.set(key, record)
          gm.set(pendingKey, { version: 1, oldMeta: beforeMeta, newMeta: nextMeta, oldKeys, newKeys })
        } catch (error) {
          try { cleanup(newKeys) } catch (_cleanupError) { /* best effort before journal exists */ }
          throw error
        }
        gm.set(metaKey, nextMeta)
        cleanup(oldKeys)
        gm.delete(pendingKey)
        let value = mutation.value
        if (value && value.item && value.item.payload) {
          const id = String(value.item.payload.event_id)
          const item = nextEntries.find((entry) => entry.id === id)
          value = { ...value, item: item ? gm.get(item.key, value.item) : value.item }
        }
        return { records: nextEntries.map(stub), value }
      },
    }
  }

  async function migrateLegacyQueue(store, legacy) {
    const records = legacy.read()
    if (!Array.isArray(records) || records.length === 0) return { status: 'empty' }
    try {
      await store.transaction(async (current) => {
        const ids = new Set(current.map((entry) => entry && entry.payload && entry.payload.event_id))
        const additions = records.filter((entry) => entry && entry.payload && !ids.has(entry.payload.event_id))
        const next = [...current, ...additions]
        const stats = queueStats(next)
        if (stats.count > QUEUE_HIGH_WATER_COUNT || stats.bytes > QUEUE_MAX_BYTES) {
          throw new Error('legacy queue exceeds capacity')
        }
        return { records: next }
      })
      legacy.clear()
      return { status: 'migrated' }
    } catch (_error) {
      return { status: 'failed' }
    }
  }

  function retryDelayForAttempt(attempt) {
    const index = Math.max(0, Math.floor(Number(attempt) || 0))
    return RETRY_DELAYS[Math.min(index, RETRY_DELAYS.length - 1)]
  }

  function nextRateLimitDelay(timestamps, now, limit, windowMs) {
    const current = Number(now)
    const window = Math.max(1, Number(windowMs))
    const ceiling = Math.max(1, Math.floor(Number(limit)))
    const live = (Array.isArray(timestamps) ? timestamps : [])
      .map(Number)
      .filter((timestamp) => Number.isFinite(timestamp) && timestamp > current - window && timestamp <= current)
      .sort((a, b) => a - b)
    if (live.length < ceiling) return 0
    return Math.max(1, live[live.length - ceiling] + window - current)
  }

  function effectiveRateLimit(rateState, now, threshold = 2) {
    const state = rateState && typeof rateState === 'object' ? rateState : {}
    return state.reducedMode === true || (
      Number(state.consecutive429 || 0) >= Number(threshold) &&
      Number(state.reducedUntil || 0) > 0
    ) ? 20 : 40
  }

  function estimateQueueDrainMs(queueDepth, ratePerMinute) {
    const depth = Math.max(0, Math.floor(Number(queueDepth) || 0))
    const rate = Math.max(1, Number(ratePerMinute) || 0)
    return depth === 0 ? 0 : Math.ceil((depth / rate) * 60_000)
  }

  function sanitizeStatusError(message) {
    const source = String(message || '')
    const sensitiveKey = (key) => {
      const compact = String(key).toLowerCase().replace(/[^a-z0-9]/g, '')
      return compact.includes('cookie') || compact.includes('authorization') ||
        compact.includes('session') || compact.includes('token') ||
        compact.includes('signature') || compact === 'sign' ||
        compact.includes('secret') || compact.includes('password')
    }
    const containerKey = (key) => ['header', 'headers', 'requestbody', 'requestpayload', 'body']
      .includes(String(key).toLowerCase().replace(/[^a-z0-9]/g, ''))
    try {
      const parsed = JSON.parse(source)
      if (parsed && typeof parsed === 'object') {
        let visited = 0
        const sanitizeStructured = (value, depth = 0) => {
          visited += 1
          if (depth > 8 || visited > 200) return '[redacted]'
          if (Array.isArray(value)) {
            return value.slice(0, 100).map((item) => sanitizeStructured(item, depth + 1))
          }
          if (!value || typeof value !== 'object') return value
          return Object.fromEntries(Object.entries(value).slice(0, 100).map(([key, child]) => [
            key,
            containerKey(key) || sensitiveKey(key)
              ? '[redacted]'
              : sanitizeStructured(child, depth + 1),
          ]))
        }
        return JSON.stringify(sanitizeStructured(parsed)).slice(0, 500)
      }
    } catch (_error) {
      // Fall through to conservative text sanitization for malformed JSON.
    }
    const redacted = source
      .replace(/(["']?(?:headers?|request[_-]?(?:body|payload)|request\s+(?:body|payload)|body)["']?\s*[:=]\s*)[\s\S]*/gi, '$1[redacted]')
      .replace(/bearer\s+[^\s,;]+/gi, 'Bearer [redacted]')
      .replace(/(["'](?:cookie|authorization|x-tt-ls-session-id|root-life-account-id|life-account-id|access[_-]?token|refresh[_-]?token|token|signature|sign|secret|password)["']\s*:\s*)(?:"[^"]*"|'[^']*'|[^,}\s]+)/gi, '$1"[redacted]"')
      .replace(/(cookie|authorization|x-tt-ls-session-id|root-life-account-id|life-account-id|access[_-]?token|refresh[_-]?token|token|signature|sign|secret|password)\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi, '$1=[redacted]')
    return (redacted.trim() || '采集器错误').slice(0, 500)
  }

  function nextUploadRateState(rateState, outcome, now, threshold = 2, consecutiveWindowMs = 300_000) {
    const state = rateState && typeof rateState === 'object' ? rateState : {}
    const current = Number(now)
    const httpStatus = Number(outcome && outcome.httpStatus) || 0
    if (httpStatus === 429) {
      const last429At = Number(state.last429At || 0)
      const consecutive429 = last429At > 0 && current - last429At <= consecutiveWindowMs
        ? Number(state.consecutive429 || 0) + 1
        : 1
      return { ...state, consecutive429, last429At: current, cooldownUntil: current + 60_000,
        reducedMode: state.reducedMode === true || consecutive429 >= Number(threshold), reducedUntil: 0 }
    }
    if (outcome && outcome.ok === true) {
      const reduced = effectiveRateLimit(state, current, threshold) === 20
      const recovered = reduced && current >= Number(state.cooldownUntil || 0)
      return recovered
        ? { ...state, consecutive429: 0, last429At: 0, cooldownUntil: 0, reducedMode: false, reducedUntil: 0 }
        : { ...state, consecutive429: 0, last429At: 0 }
    }
    return { ...state, consecutive429: 0, last429At: 0 }
  }

  function findNestedFieldValue(root, names) {
    const wanted = new Set(names.map((name) => name.toLowerCase()))
    const stack = [root]
    const seen = new Set()
    while (stack.length > 0) {
      const current = stack.pop()
      if (!current || typeof current !== 'object' || seen.has(current)) continue
      seen.add(current)
      for (const [key, value] of Object.entries(current)) {
        if (wanted.has(key.toLowerCase()) && value != null && value !== '') {
          return value
        }
        if (value && typeof value === 'object') stack.push(value)
      }
    }
    return null
  }

  function resolveGroupId(requestPayload, currentUrl) {
    const fromRequest = findNestedFieldValue(requestPayload, ['groupid', 'group_id'])
    if (fromRequest != null) return String(fromRequest)
    try {
      const parsed = new URL(String(currentUrl), LIFE_DATA_ORIGIN)
      return parsed.origin === LIFE_DATA_ORIGIN
        ? parsed.searchParams.get('groupid')
        : null
    } catch (_error) {
      return null
    }
  }

  function shanghaiRelativeWindow(now) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(now)
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
    const today = Date.UTC(
      Number(values.year),
      Number(values.month) - 1,
      Number(values.day),
    )
    const end = new Date(today - 86_400_000)
    const start = new Date(today - 7 * 86_400_000)
    return {
      start: start.toISOString().slice(0, 10),
      end: end.toISOString().slice(0, 10),
    }
  }

  function refreshRelativeDateRange(request, now = new Date()) {
    const range = shanghaiRelativeWindow(now)

    function visit(value, inheritedRelative) {
      if (Array.isArray(value)) {
        return value.map((item) => visit(item, inheritedRelative))
      }
      if (!value || typeof value !== 'object') return value
      const ownDateType = Object.entries(value).find(
        ([key]) => key.toLowerCase().replace(/[_-]/g, '') === 'datetype',
      )
      const relative = ownDateType
        ? String(ownDateType[1]).toLowerCase() === 'last_seven_days'
        : inheritedRelative
      const result = {}
      for (const [key, child] of Object.entries(value)) {
        const normalized = key.toLowerCase().replace(/[_-]/g, '')
        if (relative && normalized === 'startdate') result[key] = range.start
        else if (relative && normalized === 'enddate') result[key] = range.end
        else result[key] = visit(child, relative)
      }
      return result
    }

    return visit(request, false)
  }
  function classifyUploadResponse(status, body) {
    const httpStatus = Number(status) || 0
    if (
      httpStatus >= 200 &&
      httpStatus < 300 &&
      body &&
      body.success === true &&
      Number(body.code) === 200
    ) {
      return { ok: true, retryable: false, reason: 'ok' }
    }
    const businessCode = body ? Number(body.code) : 0
    const permanentStatuses = new Set([400, 403, 413, 422])
    const permanent =
      permanentStatuses.has(httpStatus) ||
      (httpStatus >= 200 && httpStatus < 300 && businessCode === 400) ||
      (httpStatus >= 400 && httpStatus < 500 && ![401, 408, 429].includes(httpStatus))
    return {
      ok: false,
      retryable: !permanent,
      reason: permanent ? 'permanent' : 'retryable',
    }
  }

  function isInvalidReplayStatus(status) {
    return status === 401 || status === 403
  }

  function validateVideoPage(rank, total, offset, pageSize, seenIds) {
    if (!rank || !Array.isArray(rank.data)) {
      throw new Error(`offset ${offset} 缺少 itemRank`)
    }
    if (Number(rank.total) !== Number(total)) {
      throw new Error(`offset ${offset} 的 total 已变化`)
    }
    const expected = Math.max(
      0,
      Math.min(Number(pageSize), Number(total) - Number(offset)),
    )
    if (rank.data.length !== expected) {
      throw new Error(
        `offset ${offset} 预期 ${expected} 条，实际 ${rank.data.length} 条`,
      )
    }
    for (const row of rank.data) {
      const itemId = row && row.item_id != null ? String(row.item_id).trim() : ''
      if (!itemId) throw new Error(`offset ${offset} 存在无效 item_id`)
      if (seenIds.has(itemId)) throw new Error(`item_id 重复：${itemId}`)
      seenIds.add(itemId)
    }
    return rank.data
  }
  function buildIngestPayload(options) {
    if (!options || !isAllowedEndpoint(options.endpoint)) {
      throw new Error('不允许的 LifeData 接口')
    }
    return {
      schema_version: '1.0',
      event_id: String(options.eventId),
      account_id: ACCOUNT_ID,
      page_path: String(options.pagePath || '/'),
      queue_depth: Math.min(
        500,
        Math.max(0, Math.floor(Number(options.queueDepth) || 0)),
      ),
      endpoint: normalizeEndpoint(options.endpoint),
      request_payload: sanitizeBusinessJson(options.requestPayload),
      response_payload: sanitizeBusinessJson(options.responsePayload),
      captured_at: String(options.capturedAt),
    }
  }

  function isCapturePersistedSuccess(result) {
    return Boolean(result && [
      'uploaded', 'queued', 'merged', 'coalesced',
    ].includes(result.status))
  }

  function requiredCollectionGroupsHealthy(groups) {
    return ['video', 'business', 'advertising'].every(
      (group) => groups && groups[group] && groups[group].status === 'healthy',
    )
  }

  const VOLATILE_TEMPLATE_KEYS = new Set([
    'start_date', 'end_date', 'date_type', 'offset', 'limit', 'cursor',
    'page', 'page_no', 'page_num', 'page_size',
  ])

  function stableTemplateValue(value) {
    if (Array.isArray(value)) return value.map(stableTemplateValue)
    if (!value || typeof value !== 'object') return value
    return Object.keys(value)
      .sort()
      .reduce((result, key) => {
        if (!VOLATILE_TEMPLATE_KEYS.has(String(key).toLowerCase())) {
          result[key] = stableTemplateValue(value[key])
        }
        return result
      }, {})
  }

  function classifyTemplate(template) {
    const pagePath = String(template && (template.pagePath || template.path) || '')
      .split('?')[0]
      .replace(/\/$/, '')
    if (pagePath === '/flow/content/analysis/video') {
      const request = template && (template.requestPayload || template.request_payload)
      return request && hasPageableItemRank(request) ? 'video' : 'other'
    }
    if (pagePath === '/dito/pc/business/page' || pagePath === '/trade/overview' || pagePath === '/flow/my/overview') return 'business'
    if (pagePath === '/dito/pc/ad/analysis' || pagePath.startsWith('/ad/analysis')) return 'advertising'
    return 'other'
  }

  function templateFingerprint(template) {
    const normalized = {
      endpoint: normalizeEndpoint(template && template.endpoint) || String(template && template.endpoint || ''),
      pagePath: String(template && (template.pagePath || template.path) || '').split('?')[0],
      requestPayload: stableTemplateValue(template && (template.requestPayload || template.request_payload) || {}),
    }
    return JSON.stringify(normalized)
  }

  function normalizedCanonicalFields(template) {
    return [...new Set(
      (Array.isArray(template && template.canonicalFields)
        ? template.canonicalFields
        : [])
        .map((field) => String(field).trim())
        .filter(Boolean),
    )].sort()
  }

  function templateCapabilityIdentity(template) {
    return JSON.stringify({
      group: String(template && template.group || classifyTemplate(template)),
      moduleIdentity: String(template && template.moduleIdentity || ''),
      endpoint: normalizeEndpoint(template && template.endpoint) || String(template && template.endpoint || ''),
      canonicalFields: normalizedCanonicalFields(template),
    })
  }

  function templateTimestamp(template, key) {
    const value = template && template[key]
    const numeric = Number(value)
    if (Number.isFinite(numeric)) return numeric
    const parsed = Date.parse(value)
    return Number.isFinite(parsed) ? parsed : 0
  }

  function compareTemplatePriority(left, right) {
    return (
      templateTimestamp(right, 'lastSuccessfulAt') - templateTimestamp(left, 'lastSuccessfulAt') ||
      templateTimestamp(right, 'learnedAt') - templateTimestamp(left, 'learnedAt') ||
      templateCapabilityIdentity(left).localeCompare(templateCapabilityIdentity(right))
    )
  }

  function selectMinimalTemplates(templates, targetFields) {
    const targets = [...new Set(
      (Array.isArray(targetFields) ? targetFields : [])
        .map((field) => String(field).trim())
        .filter(Boolean),
    )]
    const targetSet = new Set(targets)
    const bestByIdentity = new Map()
    for (const template of Array.isArray(templates) ? templates : []) {
      if (!template || template.valid === false) continue
      const identity = templateCapabilityIdentity(template)
      const existing = bestByIdentity.get(identity)
      if (!existing || compareTemplatePriority(template, existing) < 0) {
        bestByIdentity.set(identity, template)
      }
    }

    const missing = new Set(targets)
    const selected = []
    const candidates = [...bestByIdentity.values()]
    while (missing.size > 0) {
      const ranked = candidates
        .map((template) => ({
          template,
          gain: normalizedCanonicalFields(template)
            .filter((field) => targetSet.has(field) && missing.has(field)).length,
        }))
        .filter((candidate) => candidate.gain > 0)
        .sort((left, right) =>
          right.gain - left.gain || compareTemplatePriority(left.template, right.template),
        )
      if (ranked.length === 0) break
      const winner = ranked[0].template
      selected.push(winner)
      for (const field of normalizedCanonicalFields(winner)) missing.delete(field)
      candidates.splice(candidates.indexOf(winner), 1)
    }

    const groupOrder = new Map(
      ['business', 'advertising', 'video', 'other'].map((group, index) => [group, index]),
    )
    selected.sort((left, right) =>
      (groupOrder.get(String(left.group || classifyTemplate(left))) ?? 3) -
        (groupOrder.get(String(right.group || classifyTemplate(right))) ?? 3) ||
      compareTemplatePriority(left, right),
    )
    return {
      selected,
      skipped: (Array.isArray(templates) ? templates.length : 0) - selected.length,
      covered: targets.filter((field) => !missing.has(field)),
      missing: targets.filter((field) => missing.has(field)),
    }
  }

  function hasMeaningfulBusinessData(response, group) {
    if (!response || Number(response.code) !== 0) return false
    if (group === 'video') return Boolean(extractItemRank(response))
    const keys = group === 'advertising'
      ? new Set(['total_ad_cost', 'current_ad_cost', 'ad_pay_gmv', 'total_ad_pay_gmv', 'current_ad_pay_gmv'])
      : group === 'business'
        ? new Set(['verify_gmv', 'pay_gmv', 'refund_gmv'])
        : null
    if (!keys) return true
    const stack = [response]
    while (stack.length) {
      const current = stack.pop()
      if (!current || typeof current !== 'object') continue
      for (const [key, value] of Object.entries(current)) {
        if (keys.has(String(key).toLowerCase()) && value !== null && value !== '' && Number.isFinite(Number(value))) return true
        if (value && typeof value === 'object') stack.push(value)
      }
    }
    return false
  }

  async function runWorkerPool(items, options) {
    const values = Array.isArray(items) ? items : []
    const concurrency = Math.max(1, Math.floor(Number(options.concurrency) || 1))
    const startGapMs = Math.max(0, Number(options.startGapMs) || 0)
    const now = options.now || Date.now
    const wait = options.wait || (
      (delay) => new Promise((resolve) => setTimeout(resolve, delay))
    )
    const results = new Array(values.length)
    const active = new Set()
    let lastStartedAt = null
    for (let index = 0; index < values.length; index += 1) {
      if (active.size >= concurrency) await Promise.race(active)
      if (lastStartedAt !== null) {
        const remaining = startGapMs - (now() - lastStartedAt)
        if (remaining > 0) await wait(remaining)
      }
      lastStartedAt = now()
      let work
      try {
        work = options.worker(values[index], index)
      } catch (error) {
        work = Promise.reject(error)
      }
      let task
      task = Promise.resolve(work)
        .then(
          (value) => { results[index] = { status: 'fulfilled', value } },
          (reason) => { results[index] = { status: 'rejected', reason } },
        )
        .finally(() => active.delete(task))
      active.add(task)
    }
    await Promise.all(active)
    return results
  }

  function mergeTemplateRegistry(current, learned) {
    const registry = current && typeof current === 'object' ? { ...current } : {}
    const template = { ...learned }
    template.group = classifyTemplate(template)
    template.kind = template.group === 'video' ? 'video' : template.group
    const key = templateFingerprint(template)
    const existing = registry[key]
    if (
      existing &&
      Array.isArray(template.canonicalFields) &&
      template.canonicalFields.length === 0 &&
      Array.isArray(existing.canonicalFields) &&
      existing.canonicalFields.length > 0
    ) {
      template.canonicalFields = [...existing.canonicalFields]
      template.fieldSamplePaths = Object.fromEntries(
        template.canonicalFields.map((field) => [
          field,
          [...((existing.fieldSamplePaths || {})[field] || [])]
            .slice(0, SCAN_MAX_SAMPLE_PATHS),
        ]),
      )
      template.lastSuccessfulAt = existing.lastSuccessfulAt
    }
    if (existing && template.canonicalFields && existing.canonicalFields) {
      const fields = [...new Set([
        ...existing.canonicalFields,
        ...template.canonicalFields,
      ])].sort()
      template.canonicalFields = fields
      template.fieldSamplePaths = Object.fromEntries(fields.map((field) => [
        field,
        [...new Set([
          ...((existing.fieldSamplePaths || {})[field] || []),
          ...((template.fieldSamplePaths || {})[field] || []),
        ])].slice(0, SCAN_MAX_SAMPLE_PATHS),
      ]))
    }
    if (!existing || Number(template.learnedAt || 0) >= Number(existing.learnedAt || 0)) {
      registry[key] = template
    }
    const entries = Object.entries(registry)
      .sort((a, b) => Number(b[1].learnedAt || 0) - Number(a[1].learnedAt || 0))
      .slice(0, 80)
    return Object.fromEntries(entries)
  }

  const core = {
    MANDATORY_FIELDS,
    ACCOUNT_ID,
    LIFE_ACCOUNT_ID,
    buildIngestPayload,
    buildPageOffsets,
    buildVideoRequest,
    classifyUploadResponse,
    captureDedupeKey,
    classifyTemplate,
    createGmQueueStore,
    createMemoryQueueStore,
    enqueueBounded,
    enqueueQueueEntry,
    extractItemRank,
    hasMeaningfulBusinessData,
    mergeTemplateRegistry,
    missingFieldGuidance,
    isAllowedEndpoint,
    isInvalidReplayStatus,
    nextLeaderLease,
    nextRateLimitDelay,
    effectiveRateLimit,
    estimateQueueDrainMs,
    nextUploadRateState,
    pickLifeDataHeaders,
    queueStats,
    jsonByteLength,
    refreshRelativeDateRange,
    resolveGroupId,
    retryDelayForAttempt,
    selectOldestDue,
    shouldPauseAutoCollection,
    migrateLegacyQueue,
    sanitizeStatusError,
    sanitizeBusinessJson,
    scanCanonicalFields,
    templateCapabilities,
    templateCapabilityIdentity,
    templateFingerprint,
    selectMinimalTemplates,
    runWorkerPool,
    validateVideoPage,
    isCapturePersistedSuccess,
    requiredCollectionGroupsHealthy,
  }

  if (typeof module === 'object' && module.exports) {
    module.exports = core
    return
  }

  main(core)

  function main() {
    const page = typeof unsafeWindow === 'undefined' ? window : unsafeWindow
    if (!page || page.__huabangLifeDataCollector) return
    Object.defineProperty(page, '__huabangLifeDataCollector', { value: true })
    const nativePageFetch =
      typeof page.fetch === 'function' ? page.fetch.bind(page) : null
    const observedXhrPrototypes = new WeakMap()
    let installedFetchWrapper = null

    const KEYS = {
      token: 'lifeDataCollectorToken',
      headers: 'lifeDataSessionHeaders',
      templates: 'lifeDataTemplates',
      queue: 'lifeDataQueue',
      rate: 'lifeDataRateState',
      leader: 'lifeDataLeader',
      minimized: 'lifeDataPanelMinimized',
    }
    const INGEST_URL = 'https://hbreare.com/api/v1/life-data/ingest'
    const STATUS_URL = 'https://hbreare.com/api/v1/life-data/status'
    const VIDEO_PATH = '/flow/content/analysis/video'
    const VIDEO_INTERVAL = 300_000
    const CORE_INTERVAL = 3_600_000
    const INITIAL_COLLECTION_DELAY = 30_000
    const LIFE_DATA_CONCURRENCY = 3
    const LIFE_DATA_START_GAP = 1_000
    const REPLAY_FETCH_TIMEOUT = 20_000
    const OBSERVED_LOCK_WAIT_TIMEOUT = 30_000
    const OBSERVED_LOCK_WAITER_LIMIT = 20
    const tabId =
      globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function'
        ? globalThis.crypto.randomUUID()
        : `tab-${Date.now()}-${Math.random().toString(16).slice(2)}`
    const state = {
      ready: false,
      isLeader: false,
      collecting: false,
      fullCollecting: false,
      activeWorkers: 0,
      autoCollectionPaused: false,
      leaderTimer: null,
      videoTimer: null,
      otherTimer: null,
      initialCollectionTimer: null,
      queueTimer: null,
      statusTimer: null,
      statusErrorTimer: null,
      observedLockWaiters: 0,
      triggeredTemplateAt: 0,
      startupReady: false,
      lastCapture: '',
      lastUpload: '',
      videoCount: null,
      lastFullResult: '',
      lastFullSuccessAt: null,
      nextVideoRunAt: null,
      nextCoreRunAt: null,
      selectedTemplateCount: 0,
      skippedTemplateCount: 0,
      groupHealth: {
        video: { status: 'missing', lastSuccessAt: null, lastError: null },
        business: { status: 'missing', lastSuccessAt: null, lastError: null },
        advertising: { status: 'missing', lastSuccessAt: null, lastError: null },
        other: { status: 'missing', lastSuccessAt: null, lastError: null },
      },
      error: '',
      panel: null,
    }
    const injectedQueueStore = page.__huabangLifeDataQueueStore || null
    let queueCache = injectedQueueStore
      ? (Array.isArray(getValue(KEYS.queue, [])) ? getValue(KEYS.queue, []) : [])
      : []
    const queueStore = injectedQueueStore || createGmQueueStore({
      get: (key, fallback) => getValue(key, fallback),
      set: (key, value) => { if (!setValue(key, value)) throw new Error('GM_setValue failed') },
      delete: (key) => GM_deleteValue(key),
    })

    function getValue(key, fallback) {
      try {
        const value = GM_getValue(key, fallback)
        return value === undefined ? fallback : value
      } catch (_error) {
        return fallback
      }
    }

    function setValue(key, value) {
      try {
        GM_setValue(key, value)
        return true
      } catch (_error) {
        return false
      }
    }

    function clearStatusErrorTimer() {
      if (state.statusErrorTimer !== null) {
        page.clearTimeout(state.statusErrorTimer)
        state.statusErrorTimer = null
      }
    }

    function setError(message) {
      state.error = message ? sanitizeStatusError(message) : ''
      updatePanel()
      if (state.error) {
        scheduleStatusError(state.error)
      } else {
        clearStatusErrorTimer()
        if (state.ready && state.isLeader) void postCollectorStatus('online')
      }
    }

    function setStatus(patch) {
      const next = { ...(patch || {}) }
      const hasError = Object.prototype.hasOwnProperty.call(next, 'error')
      const error = next.error
      delete next.error
      Object.assign(state, next)
      if (hasError) setError(error)
      else updatePanel()
    }

    function hasConfirmedLeaderLease(now = Date.now()) {
      const first = getValue(KEYS.leader, null)
      const second = getValue(KEYS.leader, null)
      return Boolean(
        first &&
          second &&
          first.tabId === tabId &&
          second.tabId === tabId &&
          Number(first.expiresAt) === Number(second.expiresAt) &&
          Number(first.expiresAt) > now,
      )
    }

    async function runExclusiveAction(action, actionType = 'scheduled') {
      const waitsForLock = actionType === 'observed'
      const unavailable = (reason, message) => ({
        status: 'lock_unavailable',
        reason,
        message,
      })
      if (!state.isLeader || !hasConfirmedLeaderLease()) {
        applyLeadership(false)
        return waitsForLock
          ? unavailable('leadership_lost', '主标签租约已失效')
          : false
      }
      const locks = page.navigator && page.navigator.locks
      if (!locks || typeof locks.request !== 'function') return action()
      if (
        waitsForLock &&
        state.observedLockWaiters >= OBSERVED_LOCK_WAITER_LIMIT
      ) {
        return unavailable('waiter_limit', '浏览器互斥锁等待数量已达上限')
      }

      const lockOptions = waitsForLock
        ? { mode: 'exclusive' }
        : { ifAvailable: true, mode: 'exclusive' }
      let actionStarted = false
      let waitingRegistered = false
      let waitController = null
      let waitTimer = null
      const stopWaiting = () => {
        if (waitTimer !== null) {
          page.clearTimeout(waitTimer)
          waitTimer = null
        }
        if (waitingRegistered) {
          state.observedLockWaiters = Math.max(
            0,
            state.observedLockWaiters - 1,
          )
          waitingRegistered = false
        }
      }

      if (waitsForLock) {
        const AbortControllerClass =
          page.AbortController || globalThis.AbortController
        if (typeof AbortControllerClass !== 'function') {
          return unavailable(
            'abort_unsupported',
            '浏览器不支持互斥锁等待中止',
          )
        }
        waitController = new AbortControllerClass()
        lockOptions.signal = waitController.signal
        state.observedLockWaiters += 1
        waitingRegistered = true
        waitTimer = page.setTimeout(
          () => waitController.abort(),
          OBSERVED_LOCK_WAIT_TIMEOUT,
        )
      }

      try {
        return await locks.request(
          'huabang-life-data-action',
          lockOptions,
          async (lock) => {
            if (!lock) {
              return waitsForLock
                ? unavailable('lock_missing', '浏览器互斥锁未获取')
                : false
            }
            if (waitsForLock) stopWaiting()
            else if (!hasConfirmedLeaderLease()) return false
            actionStarted = true
            return action()
          },
        )
      } catch (error) {
        if (actionStarted) throw error
        if (waitsForLock) {
          return waitController && waitController.signal.aborted
            ? unavailable('wait_timeout', '浏览器互斥锁等待超时（30 秒）')
            : unavailable('lock_rejected', '浏览器互斥锁获取失败')
        }
        setError('浏览器互斥锁获取失败，本次采集动作已取消')
        return false
      } finally {
        if (waitsForLock) stopWaiting()
      }
    }

    function findFieldValue(root, names) {
      const wanted = new Set(names.map((name) => name.toLowerCase()))
      const stack = [root]
      const seen = new Set()
      while (stack.length > 0) {
        const current = stack.pop()
        if (!current || typeof current !== 'object' || seen.has(current)) continue
        seen.add(current)
        for (const [key, value] of Object.entries(current)) {
          if (wanted.has(key.toLowerCase()) && value != null) return value
          if (value && typeof value === 'object') stack.push(value)
        }
      }
      return null
    }

    function requestPagePath(requestPayload, fallback) {
      const path = findFieldValue(requestPayload, ['path'])
      return typeof path === 'string' && path.startsWith('/')
        ? path.split('?')[0]
        : fallback || '/'
    }

    function isSuccessfulResponse(response) {
      return Boolean(response) && (response.code === 0 || response.code === '0')
    }

    function assertExpectedAccount(requestPayload, headers, currentUrl) {
      const groupId = resolveGroupId(requestPayload, currentUrl)
      if (String(groupId || '') !== ACCOUNT_ID) {
        throw new Error('LifeData 主体账号不匹配')
      }
      if (!headers['x-tt-ls-session-id']) {
        throw new Error('尚未捕获 LifeData 会话标识')
      }
      if (
        String(headers['root-life-account-id'] || '') !== LIFE_ACCOUNT_ID ||
        String(headers['life-account-id'] || '') !== LIFE_ACCOUNT_ID
      ) {
        throw new Error('LifeData 登录账号不匹配')
      }
    }
    function readTemplates() {
      const templates = getValue(KEYS.templates, {})
      return templates && typeof templates === 'object' ? templates : {}
    }

    function saveTemplate(template) {
      setValue(KEYS.templates, mergeTemplateRegistry(readTemplates(), template))
    }

    function latestVideoTemplate() {
      return Object.values(readTemplates())
        .filter(
          (template) =>
            template && template.valid !== false &&
            (template.kind === 'video' || template.isVideo === true),
        )
        .sort((a, b) => Number(b.learnedAt) - Number(a.learnedAt))[0] || null
    }

    function otherTemplates() {
      return Object.values(readTemplates()).filter(
        (template) =>
          template && template.valid !== false &&
          template.kind !== 'video' && template.isVideo !== true,
      )
    }

    function invalidateTemplate(template, status) {
      const key = templateFingerprint(template)
      const registry = readTemplates()
      if (!registry[key]) return
      registry[key] = {
        ...registry[key],
        valid: false,
        invalidAt: Date.now(),
        invalidReason: `LifeData HTTP ${status}`,
      }
      setValue(KEYS.templates, registry)
      updatePanel()
    }
    function parseRequestBody(body) {
      if (typeof body !== 'string') return null
      try {
        const parsed = JSON.parse(body)
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
          ? parsed
          : null
      } catch (_error) {
        return null
      }
    }

    function parseXhrResponse(xhr) {
      try {
        if (xhr.responseType === 'json' && xhr.response) return xhr.response
        return JSON.parse(xhr.responseText)
      } catch (_error) {
        return null
      }
    }

    function headersToObject(headers) {
      const result = {}
      if (!headers) return result
      if (typeof headers.forEach === 'function') {
        headers.forEach((value, name) => {
          result[String(name)] = String(value)
        })
        return result
      }
      if (Array.isArray(headers)) {
        for (const pair of headers) {
          if (Array.isArray(pair) && pair.length >= 2) {
            result[String(pair[0])] = String(pair[1])
          }
        }
        return result
      }
      if (typeof headers === 'object') {
        for (const [name, value] of Object.entries(headers)) {
          result[String(name)] = String(value)
        }
      }
      return result
    }

    function installXhrObserver() {
      const XHR = page.XMLHttpRequest
      if (!XHR || !XHR.prototype) return
      const prototype = XHR.prototype
      const installed = observedXhrPrototypes.get(prototype)
      if (
        installed &&
        prototype.open === installed.open &&
        prototype.setRequestHeader === installed.setRequestHeader &&
        prototype.send === installed.send
      ) {
        return
      }

      const records = new WeakMap()
      const loadListeners = new WeakMap()
      const originalOpen =
        installed && prototype.open === installed.open
          ? installed.originalOpen
          : prototype.open
      const originalSetHeader =
        installed && prototype.setRequestHeader === installed.setRequestHeader
          ? installed.originalSetHeader
          : prototype.setRequestHeader
      const originalSend =
        installed && prototype.send === installed.send
          ? installed.originalSend
          : prototype.send

      function clearTrackedRequest(xhr) {
        const oldListener = loadListeners.get(xhr)
        if (oldListener) xhr.removeEventListener('load', oldListener)
        loadListeners.delete(xhr)
        records.delete(xhr)
      }

      function observedOpen(method, url, ...rest) {
        clearTrackedRequest(this)
        const result = originalOpen.call(this, method, url, ...rest)
        if (String(method).toUpperCase() === 'POST' && isAllowedEndpoint(url)) {
          records.set(this, {
            endpoint: normalizeEndpoint(url),
            headers: {},
            requestPayload: null,
            browserPath: page.location.pathname,
            browserUrl: page.location.href,
          })
        }
        return result
      }

      function observedSetRequestHeader(name, value) {
        const record = records.get(this)
        const normalized = String(name).toLowerCase()
        if (record && SESSION_HEADERS.has(normalized)) {
          record.headers[normalized] = String(value)
        }
        return originalSetHeader.call(this, name, value)
      }

      function observedSend(body) {
        const record = records.get(this)
        if (record) {
          record.requestPayload = parseRequestBody(body)
          if (!record.requestPayload) {
            clearTrackedRequest(this)
          } else {
            const listener = () => {
              if (records.get(this) !== record) return
              const responseEndpoint = normalizeEndpoint(this.responseURL)
              this.removeEventListener('load', listener)
              loadListeners.delete(this)
              records.delete(this)
              if (!responseEndpoint || responseEndpoint !== record.endpoint) return
              if (this.status < 200 || this.status >= 300) return
              const response = parseXhrResponse(this)
              if (!response) return
              Promise.resolve(processObserved(record, response)).catch(() => {
                setError('处理 LifeData 响应失败，未上传')
              })
            }
            loadListeners.set(this, listener)
            this.addEventListener('load', listener)
          }
        }
        return originalSend.call(this, body)
      }

      prototype.open = observedOpen
      prototype.setRequestHeader = observedSetRequestHeader
      prototype.send = observedSend
      observedXhrPrototypes.set(prototype, {
        open: observedOpen,
        setRequestHeader: observedSetRequestHeader,
        send: observedSend,
        originalOpen,
        originalSetHeader,
        originalSend,
      })
    }

    function installFetchObserver() {
      const currentFetch = page.fetch
      if (typeof currentFetch !== 'function' || currentFetch === installedFetchWrapper) {
        return
      }
      const delegate = currentFetch
      const wrapper = function (input, init = {}) {
        const url =
          typeof input === 'string' || input instanceof URL
            ? String(input)
            : input && input.url
        const method = String(init.method || (input && input.method) || 'GET')
          .toUpperCase()
        const endpoint = normalizeEndpoint(url)
        const shouldObserve = method === 'POST' && Boolean(endpoint)
        let headers = {}
        let requestPayloadPromise = Promise.resolve(null)
        if (shouldObserve) {
          const sourceHeaders =
            init.headers || (input && input.headers) || {}
          headers = pickLifeDataHeaders(headersToObject(sourceHeaders))
          const body = init.body
          requestPayloadPromise = Promise.resolve(parseRequestBody(body))
          if (
            body == null &&
            input &&
            typeof input.clone === 'function'
          ) {
            try {
              requestPayloadPromise = input
                .clone()
                .text()
                .then((text) => parseRequestBody(text))
                .catch(() => null)
            } catch (_error) {
              requestPayloadPromise = Promise.resolve(null)
            }
          }
        }
        const record = shouldObserve
          ? {
              endpoint,
              headers,
              browserPath: page.location.pathname,
              browserUrl: page.location.href,
            }
          : null
        const result = delegate.call(this, input, init)
        if (record) {
          Promise.resolve(result)
            .then(async (response) => {
              const requestPayload = await requestPayloadPromise
              if (!requestPayload || !response || !response.ok) return
              const responseEndpoint = normalizeEndpoint(response.url)
              if (!responseEndpoint || responseEndpoint !== record.endpoint) return
              const cloned = response.clone()
              const businessJson = await cloned.json()
              await processObserved(
                { ...record, requestPayload },
                businessJson,
              )
            })
            .catch(() => {
              setError('处理 LifeData fetch 响应失败，未上传')
            })
        }
        return result
      }
      installedFetchWrapper = wrapper
      page.fetch = wrapper
    }

    function ensureObservers() {
      installXhrObserver()
      installFetchObserver()
    }

    function installSpaObserver() {
      if (page.__huabangLifeDataSpaObserved) return
      Object.defineProperty(page, '__huabangLifeDataSpaObserved', { value: true })
      for (const method of ['pushState', 'replaceState']) {
        if (!page.history || typeof page.history[method] !== 'function') continue
        const original = page.history[method]
        page.history[method] = function (...args) {
          const result = original.apply(this, args)
          page.setTimeout(ensureObservers, 0)
          return result
        }
      }
      page.addEventListener('popstate', ensureObservers)
      page.addEventListener('hashchange', ensureObservers)
    }
    async function processObserved(record, response) {
      if (!isSuccessfulResponse(response)) {
        setError(`LifeData API 返回非 0：${String(response.code)}`)
        return
      }
      const headers = pickLifeDataHeaders(record.headers)
      assertExpectedAccount(record.requestPayload, headers, record.browserUrl)
      setValue(KEYS.headers, headers)
      const pagePath = requestPagePath(record.requestPayload, record.browserPath)
      const isVideo = Boolean(
        pagePath === VIDEO_PATH &&
          hasPageableItemRank(record.requestPayload) &&
          extractItemRank(response),
      )
      const group = classifyTemplate({ pagePath, requestPayload: record.requestPayload })
      const template = {
        endpoint: record.endpoint,
        pagePath,
        requestPayload: sanitizeBusinessJson(record.requestPayload),
        kind: isVideo ? 'video' : group,
        group,
        moduleIdentity: getModuleIdentity(record.requestPayload),
        isVideo,
        learnedAt: Date.now(),
      }
      const capabilities = templateCapabilities(template, response)
      template.canonicalFields = capabilities.fields
      template.fieldSamplePaths = capabilities.samplePaths
      if (capabilities.fields.length > 0) {
        template.lastSuccessfulAt = new Date().toISOString()
      }
      if (
        hasMeaningfulBusinessData(response, group) &&
        responseHasBusinessContent(response)
      ) saveTemplate(template)
      if (template.isVideo) {
        setStatus({ lastCapture: new Date().toISOString(), error: '' })
        if (state.ready && synchronizeLeadership()) maybeCollectNewTemplate()
        return
      }

      const payload = buildCapturePayload(
        template,
        template.requestPayload,
        response,
      )
      setStatus({ lastCapture: payload.captured_at, error: '' })
      if (!state.ready) return
      if (!synchronizeLeadership()) {
        const queued = await queuePayload(payload, { passive: true, capabilityKey: templateCapabilityIdentity(template) })
        if (queued.status === 'queued' && !queued.dropped) {
          setError('当前为待命标签，事件已进入共享离线队列')
        }
        return
      }
      const result = await runExclusiveAction(
        async () => {
          if (!hasConfirmedLeaderLease()) {
            applyLeadership(false)
            const queued = await queuePayload(payload, { passive: true, capabilityKey: templateCapabilityIdentity(template) })
            if (queued.status === 'queued' && !queued.dropped) {
              setError('主标签已切换，事件已进入离线队列')
            }
            return queued
          }
          return uploadOrQueue(payload, { passive: true, capabilityKey: templateCapabilityIdentity(template) })
        },
        'observed',
      )
      if (result && result.status === 'lock_unavailable') {
        const queued = await queuePayload(payload, { passive: true, capabilityKey: templateCapabilityIdentity(template) })
        if (queued.status === 'queued' && !queued.dropped) {
          setError(`${result.message}，事件已进入离线队列`)
        }
      }
    }

    function responseHasBusinessContent(response) {
      const stack = [response && response.data]
      while (stack.length > 0) {
        const value = stack.pop()
        if (Array.isArray(value)) {
          if (value.length > 0) return true
          continue
        }
        if (value && typeof value === 'object') {
          const children = Object.values(value)
          if (children.length === 0) continue
          stack.push(...children)
          continue
        }
        if (value !== null && value !== undefined && value !== '') return true
      }
      return false
    }

    async function replayLifeData(template, requestPayload) {
      const headers = pickLifeDataHeaders(getValue(KEYS.headers, {}))
      assertExpectedAccount(requestPayload, headers, page.location.href)
      if (!nativePageFetch) throw new Error('LifeData 原生 fetch 不可用')
      const controller = new page.AbortController()
      const timeoutId = page.setTimeout(
        () => controller.abort(),
        REPLAY_FETCH_TIMEOUT,
      )
      try {
        const response = await nativePageFetch(
          `${LIFE_DATA_ORIGIN}${template.endpoint}`,
          {
            method: 'POST',
            credentials: 'include',
            headers: {
              'Content-Type': 'application/json;charset=UTF-8',
              ...headers,
            },
            body: JSON.stringify(sanitizeBusinessJson(requestPayload)),
            signal: controller.signal,
          },
        )
        if (!response.ok) {
          const error = new Error(`LifeData HTTP ${response.status}`)
          error.httpStatus = response.status
          if (isInvalidReplayStatus(response.status)) {
            invalidateTemplate(template, response.status)
          }
          throw error
        }
        const businessJson = await response.json()
        if (!isSuccessfulResponse(businessJson)) {
          throw new Error(
            `LifeData API 返回非 0：${String(businessJson.code)}`,
          )
        }
        return businessJson
      } catch (error) {
        if (controller.signal.aborted) {
          throw new Error('LifeData 请求超时（20 秒）')
        }
        throw error
      } finally {
        page.clearTimeout(timeoutId)
      }
    }

    function newEventId() {
      return globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function'
        ? globalThis.crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(16).slice(2)}-event`
    }

    function readQueue() {
      return queueCache
    }

    async function mutateQueueExclusive(mutator) {
      const mutate = async () => {
        let committed
        try {
          committed = await queueStore.transaction((before, metadata) => {
            const mutation = mutator(before, metadata || { permits: [] })
            const next = mutation && mutation.queue
            if (!Array.isArray(next)) throw new Error('invalid queue transaction')
            return { records: next, permits: mutation.permits, dedupe: mutation.dedupe, value: mutation.value }
          })
        } catch (_error) {
          setError('离线队列写入失败，事件状态未保存')
          return { status: 'queue_failed', queue: readQueue(), value: null }
        }
        queueCache = committed.records
        updatePanel()
        return {
          status: 'mutated',
          queue: queueCache,
          value: committed.value,
        }
      }

      const locks = page.navigator && page.navigator.locks
      if (!locks || typeof locks.request !== 'function') return mutate()
      try {
        return await locks.request(
          'huabang-life-data-queue',
          { mode: 'exclusive' },
          mutate,
        )
      } catch (_error) {
        setError('离线队列互斥锁获取失败，事件状态未保存')
        return { status: 'queue_failed', queue: readQueue(), value: null }
      }
    }

    function templateGroupCounts() {
      const counts = { video: 0, business: 0, advertising: 0, other: 0 }
      for (const template of Object.values(readTemplates())) {
        if (!template || template.valid === false) continue
        const group = classifyTemplate(template)
        counts[group] += 1
      }
      return counts
    }

    function setGroupHealth(group, status, error = null) {
      const current = state.groupHealth[group]
      if (!current) return
      current.status = status
      current.lastError = error ? sanitizeStatusError(error) : null
      if (status === 'healthy') current.lastSuccessAt = new Date().toISOString()
      updatePanel()
    }

    function serializedGroupHealth() {
      const counts = templateGroupCounts()
      return Object.fromEntries(
        Object.entries(state.groupHealth).map(([group, health]) => [
          group,
          {
            status: counts[group] === 0 ? 'missing' : health.status,
            template_count: counts[group],
            last_success_at: health.lastSuccessAt,
            last_error: health.lastError,
          },
        ]),
      )
    }

    function postCollectorStatus(status, lastError = null) {
      const token = String(getValue(KEYS.token, '') || '').trim()
      if (!token || !state.isLeader) return Promise.resolve(false)
      const body = {
        schema_version: '1.0',
        account_id: ACCOUNT_ID,
        status,
        queue_depth: Math.min(500, readQueue().length),
        last_error:
          status === 'error' ? sanitizeStatusError(lastError) : null,
        template_count: Object.keys(readTemplates()).length,
        last_full_success_at: state.lastFullSuccessAt,
        groups: serializedGroupHealth(),
      }
      return new Promise((resolve) => {
        GM_xmlhttpRequest({
          method: 'POST',
          url: STATUS_URL,
          timeout: 20_000,
          anonymous: true,
          headers: {
            'Content-Type': 'application/json',
            'X-Collector-Token': token,
          },
          data: JSON.stringify(body),
          onload(response) {
            let parsed = null
            try {
              parsed = JSON.parse(response.responseText)
            } catch (_error) {
              parsed = null
            }
            resolve(
              response.status >= 200 &&
                response.status < 300 &&
                parsed &&
                parsed.success === true &&
                Number(parsed.code) === 200,
            )
          },
          ontimeout() {
            resolve(false)
          },
          onerror() {
            resolve(false)
          },
        })
      })
    }

    function scheduleStatusError(message) {
      if (!state.ready || !state.isLeader || !message) return
      if (state.statusErrorTimer !== null) {
        page.clearTimeout(state.statusErrorTimer)
      }
      state.statusErrorTimer = page.setTimeout(() => {
        state.statusErrorTimer = null
        void postCollectorStatus('error', message)
      }, 30_000)
    }
    function uploadError(message, retryable) {
      const error = new Error(message)
      error.retryable = Boolean(retryable)
      return error
    }

    function postPayload(payload) {
      const token = String(getValue(KEYS.token, '') || '').trim()
      if (!token) {
        return Promise.reject(uploadError('采集令牌未配置', true))
      }
      const outgoingPayload = {
        ...payload,
        queue_depth: Math.min(500, readQueue().length),
      }
      return new Promise((resolve, reject) => {
        GM_xmlhttpRequest({
          method: 'POST',
          url: INGEST_URL,
          timeout: 20_000,
          anonymous: true,
          headers: {
            'Content-Type': 'application/json',
            'X-Collector-Token': token,
          },
          data: JSON.stringify(outgoingPayload),
          onload(response) {
            let body = null
            try {
              body = JSON.parse(response.responseText)
            } catch (_error) {
              body = null
            }
            const classification = classifyUploadResponse(response.status, body)
            if (classification.ok) {
              resolve(body)
              return
            }
            reject(
              Object.assign(uploadError(
                classification.retryable
                  ? `中台暂时不可用（HTTP ${response.status}）`
                  : `中台永久拒绝事件（HTTP ${response.status}）`,
                classification.retryable,
              ), { httpStatus: Number(response.status) }),
            )
          },
          ontimeout() {
            reject(uploadError('上传超时', true))
          },
          onerror() {
            reject(uploadError('上传网络错误', true))
          },
        })
      })
    }

    async function queuePayload(payload, options = {}) {
      const dedupeKey = options.passive ? await captureDedupeKey(payload, page.crypto) : null
      const mutation = await mutateQueueExclusive((before, metadata) => {
        const now = Date.now()
        const liveDedupe = (Array.isArray(metadata.dedupe) ? metadata.dedupe : [])
          .filter((item) => item && Number(item.expiresAt) > now)
        if (dedupeKey && liveDedupe.some((item) => item.key === dedupeKey)) {
          return { queue: before, dedupe: liveDedupe, value: { status: 'coalesced' } }
        }
        const result = enqueueQueueEntry(before, {
          payload,
          attempt: 0,
          nextAttemptAt: Date.now(),
          capabilityKey: options.capabilityKey || null,
        }, { passive: Boolean(options.passive) })
        return {
          queue: result.queue,
          dedupe: dedupeKey && ['queued', 'merged'].includes(result.status)
            ? [...liveDedupe, { key: dedupeKey, expiresAt: now + 60_000 }].slice(-500)
            : liveDedupe,
          value: { status: result.status },
        }
      })
      if (mutation.status === 'queue_failed') {
        return { status: 'queue_failed', dropped: false }
      }
      const status = mutation.value && mutation.value.status
      if (status === 'queue_full') {
        setError('离线队列已满，事件未保存')
        return { status: 'queue_full', dropped: false }
      }
      wakeUploadWorkers()
      return { status, dropped: false }
    }

    async function uploadOrQueue(payload, options) {
      return queuePayload(payload, options)
    }

    function buildCapturePayload(
      template,
      requestPayload,
      responsePayload,
    ) {
      return buildIngestPayload({
        eventId: newEventId(),
        endpoint: template.endpoint,
        pagePath: template.pagePath,
        requestPayload,
        responsePayload,
        capturedAt: new Date().toISOString(),
        queueDepth: readQueue().length,
      })
    }

    async function publishCapture(template, requestPayload, responsePayload) {
      const payload = buildCapturePayload(
        template,
        requestPayload,
        responsePayload,
      )
      setStatus({ lastCapture: payload.captured_at })
      return uploadOrQueue(payload, { capabilityKey: templateCapabilityIdentity(template) })
    }
    function readRateState() {
      const value = getValue(KEYS.rate, {})
      return value && typeof value === 'object' ? value : {}
    }

    async function claimNextUpload(workerId) {
      const now = Date.now()
      return mutateQueueExclusive((queue, metadata) => {
        const rate = readRateState()
        const timestamps = (Array.isArray(rate.timestamps) ? rate.timestamps : [])
          .map(Number).filter((timestamp) => timestamp > now - 60_000 && timestamp <= now)
        const cooldownDelay = Math.max(0, Number(rate.cooldownUntil || 0) - now)
        const limit = effectiveRateLimit(rate, now, 2)
        const rateDelay = nextRateLimitDelay(timestamps, now, limit, 60_000)
        const livePermits = (Array.isArray(metadata.permits) ? metadata.permits : [])
          .filter((permit) => permit && Number(permit.expiresAt) > now)
        if (cooldownDelay > 0 || rateDelay > 0) {
          return { queue, permits: livePermits, value: { item: null, delay: Math.max(cooldownDelay, rateDelay), blocked: true } }
        }
        if (livePermits.length >= 2) return { queue, permits: livePermits, value: { item: null, delay: 5_000, blocked: true } }
        const selectedItem = selectOldestDue(queue, now)
        if (!selectedItem) return { queue, permits: livePermits, value: { item: null, delay: 0 } }
        const selected = { item: selectedItem, index: queue.indexOf(selectedItem) }
        const claimed = { ...selectedItem, claimedBy: workerId, claimExpiresAt: now + 30_000 }
        const next = queue.slice()
        next[selected.index] = claimed
        if (!setValue(KEYS.rate, { ...rate, timestamps: [...timestamps, now] })) {
          return { queue, permits: livePermits, value: { item: null, delay: 5_000 } }
        }
        return { queue: next, permits: [...livePermits, {
          workerId, eventId: String(claimed.payload.event_id), expiresAt: claimed.claimExpiresAt,
        }], value: { item: claimed, delay: 0 } }
      })
    }

    function updateRateAfterUploadLocked(error) {
      const now = Date.now()
      const rate = readRateState()
      setValue(KEYS.rate, nextUploadRateState(rate,
        error ? { httpStatus: Number(error.httpStatus) || 0 } : { ok: true }, now))
    }

    function scheduleWorkerWake(delay) {
      page.setTimeout(() => wakeUploadWorkers(), Math.max(1, Math.min(Number(delay) || 5_000, 60_000)))
    }

    function wakeUploadWorkers() {
      if (!state.isLeader) return
      while (state.activeWorkers < 2) {
        state.activeWorkers += 1
        const workerId = `${tabId}:worker-${state.activeWorkers}:${Date.now()}`
        void uploadWorker(workerId).then((outcome) => {
          state.activeWorkers -= 1
          if (outcome !== 'blocked' && readQueue().some((item) => item && Number(item.nextAttemptAt || 0) <= Date.now() &&
            (!item.claimedBy || Number(item.claimExpiresAt || 0) <= Date.now()))) {
            queueMicrotask(() => wakeUploadWorkers())
          }
        }, () => {
          state.activeWorkers -= 1
        })
      }
    }

    async function uploadWorker(workerId) {
      const claimed = await claimNextUpload(workerId)
      if (claimed.status === 'queue_failed') return 'blocked'
      const item = claimed.value && claimed.value.item
      if (!item) {
        if (claimed.value && claimed.value.delay > 0) scheduleWorkerWake(claimed.value.delay)
        return claimed.value && claimed.value.blocked ? 'blocked' : 'empty'
      }
      try {
        await postPayload(item.payload)
        const mutation = await mutateQueueExclusive((latest, metadata) => {
          updateRateAfterUploadLocked(null)
          const ownsPermit = (metadata.permits || []).some((permit) =>
            permit.workerId === workerId && permit.eventId === String(item.payload.event_id))
          return { queue: ownsPermit ? latest.filter(
            (queued) => queued.payload.event_id !== item.payload.event_id || queued.claimedBy !== workerId,
          ) : latest, permits: (metadata.permits || []).filter((permit) =>
            permit.workerId !== workerId || permit.eventId !== String(item.payload.event_id)), value: null }
        })
        if (mutation.status === 'queue_failed') return
        setStatus({ lastUpload: new Date().toISOString() })
        if (mutation.queue.length === 0) setError('')
      } catch (error) {
        if (error.retryable === false) {
          const mutation = await mutateQueueExclusive((latest, metadata) => {
            updateRateAfterUploadLocked(error)
            const ownsPermit = (metadata.permits || []).some((permit) =>
              permit.workerId === workerId && permit.eventId === String(item.payload.event_id))
            return { queue: ownsPermit ? latest.filter(
              (queued) => queued.payload.event_id !== item.payload.event_id || queued.claimedBy !== workerId,
            ) : latest, permits: (metadata.permits || []).filter((permit) =>
              permit.workerId !== workerId || permit.eventId !== String(item.payload.event_id)), value: null }
          })
          if (mutation.status === 'queue_failed') return
          setError(`永久上传错误，事件已移出队列：${error.message}`)
        } else {
          const mutation = await mutateQueueExclusive((latest, metadata) => {
            updateRateAfterUploadLocked(error)
            return { queue: latest.map((queued) => {
              if (queued.payload.event_id !== item.payload.event_id) {
                return queued
              }
              if (queued.claimedBy !== workerId) return queued
              const attempt = Number(queued.attempt || 0) + 1
              return {
                ...queued,
                attempt,
                nextAttemptAt:
                  Date.now() + retryDelayForAttempt(attempt),
                claimedBy: undefined,
                claimExpiresAt: undefined,
              }
            }), permits: (metadata.permits || []).filter((permit) =>
              permit.workerId !== workerId || permit.eventId !== String(item.payload.event_id)), value: null }
          })
          if (mutation.status === 'queue_failed') return
          if (mutation.queue.length < 500) {
            setError('离线队列重试失败，将按退避时间继续')
          }
        }
      }
      return 'processed'
    }

    function flushQueue() {
      wakeUploadWorkers()
    }

    async function runScheduledCollection(action) {
      try {
        queueCache = await queueStore.snapshot()
      } catch (_error) {
        setError('离线队列读取失败，自动采集已暂停')
        return false
      }
      state.autoCollectionPaused = shouldPauseAutoCollection(
        queueStats(queueCache), state.autoCollectionPaused,
      )
      if (state.autoCollectionPaused) {
        setError('离线队列达到高水位，自动采集已暂停')
        return false
      }
      return action()
    }

    async function collectVideo() {
      if (!state.isLeader) {
        setError('其他标签正在负责定时采集')
        return
      }
      if (state.collecting) return
      const template = latestVideoTemplate()
      if (!template) {
        setError('尚未捕获视频分析成功模板')
        return
      }
      state.collecting = true
      try {
        const currentTemplate = refreshRelativeDateRange(
          template.requestPayload,
          new Date(),
        )
        const firstRequest = buildVideoRequest(currentTemplate, 0, 100)
        const firstResponse = await replayLifeData(template, firstRequest)
        const firstRank = extractItemRank(firstResponse)
        const total = firstRank ? Math.floor(Number(firstRank.total)) : 0
        if (!firstRank || total <= 0) {
          throw new Error('视频返回缺少 itemRank 或总数为 0，未上传')
        }

        const offsets = buildPageOffsets(total, 100)
        const seenIds = new Set()
        const captures = []
        validateVideoPage(firstRank, total, 0, 100, seenIds)
        captures.push({ request: firstRequest, response: firstResponse })

        for (const offset of offsets.slice(1)) {
          const request = buildVideoRequest(currentTemplate, offset, 100)
          const response = await replayLifeData(template, request)
          const rank = extractItemRank(response)
          validateVideoPage(rank, total, offset, 100, seenIds)
          captures.push({ request, response })
        }
        if (seenIds.size !== total) {
          throw new Error(`视频 item_id 总数不完整：预期 ${total}，实际 ${seenIds.size}`)
        }

        let allUploaded = true
        for (const capture of captures) {
          const result = await publishCapture(
            template,
            capture.request,
            capture.response,
          )
          if (!isCapturePersistedSuccess(result)) allUploaded = false
        }
        setStatus({ videoCount: total })
        if (allUploaded) {
          setGroupHealth('video', 'healthy')
          setError('')
        } else {
          setGroupHealth('video', 'error', '部分视频上传失败')
        }
      } catch (error) {
        setGroupHealth('video', 'error', error.message || '未知错误')
        setError(`视频采集失败：${error.message || '未知错误'}`)
      } finally {
        state.collecting = false
      }
    }
    async function collectCoreTemplates() {
      if (!state.isLeader) return
      const templates = otherTemplates()
      const optionalTargets = missingFieldGuidance(readTemplates())
        .map((item) => item.field)
        .filter((field) => !MANDATORY_FIELDS.includes(field))
      const selection = selectMinimalTemplates(
        templates,
        [...new Set([
          ...MANDATORY_FIELDS,
          'plays', 'pay_gmv_fen', 'refund_gmv_fen', 'verified_count',
          'ad_orders', 'ad_pay_gmv_fen',
          ...optionalTargets,
        ])],
      )
      state.selectedTemplateCount = selection.selected.length
      state.skippedTemplateCount = selection.skipped
      updatePanel()
      const attempted = new Set()
      const failed = new Map()
      const succeeded = new Set()
      const wait = (delay) => new Promise(
        (resolve) => page.setTimeout(resolve, delay),
      )
      const replayTemplate = async (template) => {
        const group = classifyTemplate(template)
        attempted.add(group)
        try {
          const request = refreshRelativeDateRange(
            template.requestPayload,
            new Date(),
          )
          const response = await replayLifeData(template, request)
          const result = await publishCapture(template, request, response)
          if (isCapturePersistedSuccess(result)) {
            succeeded.add(group)
            setError('')
          }
        } catch (error) {
          failed.set(group, error.message || '未知错误')
          if (isInvalidReplayStatus(error.httpStatus)) {
            setError(`模板已失效（HTTP ${error.httpStatus}），请重新登录并刷新对应生意经页面`)
          } else {
            setError(`业务模板重放失败：${error.message || '未知错误'}`)
          }
        }
      }
      const stages = ['business', 'advertising', 'other']
        .map((group) => selection.selected.filter(
          (template) => classifyTemplate(template) === group,
        ))
        .filter((stage) => stage.length > 0)
      for (let index = 0; index < stages.length; index += 1) {
        if (index > 0) await wait(LIFE_DATA_START_GAP)
        await runWorkerPool(stages[index], {
          concurrency: LIFE_DATA_CONCURRENCY,
          startGapMs: LIFE_DATA_START_GAP,
          now: () => Date.now(),
          wait,
          worker: replayTemplate,
        })
      }
      for (const group of attempted) {
        setGroupHealth(
          group,
          succeeded.has(group) || !failed.has(group) ? 'healthy' : 'error',
          succeeded.has(group) ? null : failed.get(group) || null,
        )
      }
    }

    const replayOtherTemplates = collectCoreTemplates

    async function runFullCollection() {
      if (state.fullCollecting) return
      state.fullCollecting = true
      state.lastFullResult = '采集中…'
      updatePanel()
      try {
        await collectVideo()
        await replayOtherTemplates()
        state.lastFullResult = `完成，共 ${Object.keys(readTemplates()).length} 个模板`
        const required = serializedGroupHealth()
        if (requiredCollectionGroupsHealthy(required)) {
          state.lastFullSuccessAt = new Date().toISOString()
        }
        void postCollectorStatus('online')
      } finally {
        state.fullCollecting = false
        updatePanel()
      }
    }

    function maybeCollectNewTemplate() {
      if (!state.isLeader || !state.startupReady) return
      const template = latestVideoTemplate()
      if (!template || Number(template.learnedAt) <= state.triggeredTemplateAt) return
      void runExclusiveAction(() => {
        const current = latestVideoTemplate()
        const learnedAt = Number(current && current.learnedAt)
        if (!current || learnedAt <= state.triggeredTemplateAt) return false
        state.triggeredTemplateAt = learnedAt
        return collectVideo()
      })
    }

    function startLeaderTimers() {
      if (state.videoTimer !== null) return
      state.startupReady = false
      state.videoTimer = page.setInterval(() => {
        if (synchronizeLeadership()) {
          state.nextVideoRunAt = Date.now() + VIDEO_INTERVAL
          updatePanel()
          void runExclusiveAction(() => runScheduledCollection(() => collectVideo()))
        }
      }, VIDEO_INTERVAL)
      state.otherTimer = page.setInterval(
        () => {
          if (synchronizeLeadership()) {
            state.nextCoreRunAt = Date.now() + CORE_INTERVAL
            updatePanel()
            void runExclusiveAction(() => runScheduledCollection(() => collectCoreTemplates()))
          }
        },
        CORE_INTERVAL,
      )
      state.nextVideoRunAt = Date.now() + VIDEO_INTERVAL
      state.nextCoreRunAt = Date.now() + CORE_INTERVAL
      updatePanel()
      state.initialCollectionTimer = page.setTimeout(function initialCollectionCallback() {
        state.initialCollectionTimer = null
        if (!synchronizeLeadership()) return
        state.startupReady = true
        state.triggeredTemplateAt = Math.max(
          state.triggeredTemplateAt,
          Number(latestVideoTemplate() && latestVideoTemplate().learnedAt) || 0,
        )
        void runExclusiveAction(() => runScheduledCollection(async () => {
          await collectVideo()
          await collectCoreTemplates()
        }))
      }, INITIAL_COLLECTION_DELAY)
      state.queueTimer = page.setInterval(() => {
        if (synchronizeLeadership()) {
          void runExclusiveAction(() => flushQueue())
        }
      }, 5_000)
      state.statusTimer = page.setInterval(
        () => {
          if (synchronizeLeadership()) void postCollectorStatus('online')
        },
        60_000,
      )
      void postCollectorStatus('online')
      maybeCollectNewTemplate()
      void runExclusiveAction(() => flushQueue())
    }

    function stopLeaderTimers() {
      state.startupReady = false
      for (const key of [
        'videoTimer',
        'otherTimer',
        'queueTimer',
        'statusTimer',
      ]) {
        if (state[key] !== null) page.clearInterval(state[key])
        state[key] = null
      }
      if (state.statusErrorTimer !== null) {
        page.clearTimeout(state.statusErrorTimer)
        state.statusErrorTimer = null
      }
      if (state.initialCollectionTimer !== null) {
        page.clearTimeout(state.initialCollectionTimer)
        state.initialCollectionTimer = null
      }
    }

    function applyLeadership(isLeader) {
      const changed = state.isLeader !== isLeader
      state.isLeader = isLeader
      if (isLeader) {
        startLeaderTimers()
        maybeCollectNewTemplate()
      } else {
        stopLeaderTimers()
      }
      if (changed) updatePanel()
      return isLeader
    }

    function synchronizeLeadership() {
      const now = Date.now()
      const decision = nextLeaderLease(getValue(KEYS.leader, null), tabId, now)
      const wroteLease = decision.isLeader && setValue(KEYS.leader, decision.lease)
      const isLeader = Boolean(wroteLease && hasConfirmedLeaderLease(now))
      return applyLeadership(isLeader)
    }

    function formatTime(value) {
      if (!value) return '—'
      try {
        return new Date(value).toLocaleString('zh-CN', { hour12: false })
      } catch (_error) {
        return String(value)
      }
    }

    function updatePanel() {
      const refs = state.panel
      if (!refs) return
      refs.account.textContent = ACCOUNT_ID
      refs.leader.textContent = state.isLeader ? '主标签' : '待命标签'
      refs.capture.textContent = formatTime(state.lastCapture)
      refs.upload.textContent = formatTime(state.lastUpload)
      refs.video.textContent = state.videoCount == null ? '—' : String(state.videoCount)
      refs.templates.textContent = String(Object.keys(readTemplates()).length)
      refs.nextVideo.textContent = formatTime(state.nextVideoRunAt)
      refs.nextCore.textContent = formatTime(state.nextCoreRunAt)
      refs.templateSelection.textContent = `${state.selectedTemplateCount}/${state.skippedTemplateCount}`
      refs.invalidTemplates.textContent = String(
        Object.values(readTemplates()).filter((template) => template && template.valid === false).length,
      )
      const groups = serializedGroupHealth()
      refs.groups.textContent = [
        ['视频', groups.video],
        ['经营', groups.business],
        ['广告', groups.advertising],
        ['其他', groups.other],
      ]
        .map(([label, health]) => `${label}${health.template_count}:${health.status === 'healthy' ? '正常' : health.status === 'error' ? '异常' : '缺失'}`)
        .join(' · ')
      const guidance = missingFieldGuidance(readTemplates())
      const mandatory = guidance.filter((item) => MANDATORY_FIELDS.includes(item.field))
      const optional = guidance.filter((item) => !MANDATORY_FIELDS.includes(item.field))
      const shown = [...mandatory, ...optional].slice(0, 5)
      const optionalShown = shown.filter((item) => !MANDATORY_FIELDS.includes(item.field))
      refs.missingFields.textContent = mandatory.length
        ? `缺少必需字段 ${mandatory.map((item) => item.field).join('、')}；${mandatory[0].message}${optionalShown.length ? `；可选维度待补 ${optionalShown.map((item) => item.field).join('、')}` : ''}`
        : optional.length
          ? `必需字段已覆盖；可选维度待补 ${optional.slice(0, 5).map((item) => item.field).join('、')}；${optional[0].message}`
          : '必需字段已覆盖；可选维度已覆盖'
      refs.fullResult.textContent = state.lastFullResult || '等待全量采集'
      const queueDepth = readQueue().length
      refs.queue.textContent = String(queueDepth)
      const drainMs = estimateQueueDrainMs(
        queueDepth,
        effectiveRateLimit(getValue(KEYS.rate, {}), Date.now()),
      )
      refs.queueDrain.textContent = drainMs === 0
        ? '已排空'
        : `约 ${Math.ceil(drainMs / 60_000)} 分钟`
      refs.error.textContent = state.error ? sanitizeStatusError(state.error) : '无'
      refs.collect.disabled = state.fullCollecting
      refs.collect.textContent = state.fullCollecting ? '采集中…' : '立即全量采集'
    }

    function createPanel() {
      if (state.panel || !document.documentElement) return
      const host = document.createElement('div')
      host.style.cssText =
        'position:fixed;right:16px;bottom:16px;z-index:2147483647;font-family:Arial,"Microsoft YaHei",sans-serif'
      const shadow = host.attachShadow({ mode: 'closed' })
      shadow.innerHTML = `
        <style>
          .panel{width:310px;background:#111827;color:#f9fafb;border:1px solid #374151;border-radius:12px;box-shadow:0 12px 30px rgba(0,0,0,.35);overflow:hidden;font-size:13px}
          .head{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:#1f2937;font-weight:700}
          .body{padding:10px 12px}.panel.min .body{display:none}
          .row{display:grid;grid-template-columns:84px 1fr;gap:8px;margin:6px 0}.value{overflow-wrap:anywhere;color:#d1d5db}
          .error{color:#fca5a5;max-height:54px;overflow:auto}
          button{border:0;border-radius:7px;padding:7px 10px;cursor:pointer}.toggle{background:transparent;color:#f9fafb;padding:2px 6px}.collect{width:100%;margin-top:8px;background:#2563eb;color:#fff;font-weight:700}.collect:disabled{opacity:.65;cursor:wait}
        </style>
        <section class="panel">
          <div class="head"><span>LifeData 采集器</span><button class="toggle" type="button">—</button></div>
          <div class="body">
            <div class="row"><span>主体账号</span><span class="value account"></span></div>
            <div class="row"><span>标签状态</span><span class="value leader"></span></div>
            <div class="row"><span>最近采集</span><span class="value capture"></span></div>
            <div class="row"><span>最近上传</span><span class="value upload"></span></div>
            <div class="row"><span>视频数</span><span class="value video"></span></div>
            <div class="row"><span>已登记模板</span><span class="value templates"></span></div>
            <div class="row"><span>下次视频采集</span><span class="value next-video"></span></div>
            <div class="row"><span>下次核心采集</span><span class="value next-core"></span></div>
            <div class="row"><span>本轮模板</span><span class="value template-selection"></span></div>
            <div class="row"><span>失效模板</span><span class="value invalid-templates"></span></div>
            <div class="row"><span>分组状态</span><span class="value groups"></span></div>
            <div class="row"><span>缺少字段</span><span class="value missing-fields"></span></div>
            <div class="row"><span>全量结果</span><span class="value full-result"></span></div>
            <div class="row"><span>队列数</span><span class="value queue"></span></div>
            <div class="row"><span>队列排空预计</span><span class="value queue-drain"></span></div>
            <div class="row"><span>错误</span><span class="value error"></span></div>
            <button class="collect" type="button">立即全量采集</button>
          </div>
        </section>`
      document.documentElement.appendChild(host)
      const panel = shadow.querySelector('.panel')
      const toggle = shadow.querySelector('.toggle')
      const minimized = Boolean(getValue(KEYS.minimized, false))
      panel.classList.toggle('min', minimized)
      toggle.textContent = minimized ? '+' : '—'
      toggle.addEventListener('click', () => {
        const next = !panel.classList.contains('min')
        panel.classList.toggle('min', next)
        toggle.textContent = next ? '+' : '—'
        setValue(KEYS.minimized, next)
      })
      shadow.querySelector('.collect').addEventListener('click', () => {
        if (!synchronizeLeadership()) {
          setError('其他标签持有主标签租约，请在主标签立即采集')
          return
        }
        void runExclusiveAction(() => runFullCollection())
      })
      state.panel = {
        account: shadow.querySelector('.account'),
        leader: shadow.querySelector('.leader'),
        capture: shadow.querySelector('.capture'),
        upload: shadow.querySelector('.upload'),
        video: shadow.querySelector('.video'),
        templates: shadow.querySelector('.templates'),
        nextVideo: shadow.querySelector('.next-video'),
        nextCore: shadow.querySelector('.next-core'),
        templateSelection: shadow.querySelector('.template-selection'),
        invalidTemplates: shadow.querySelector('.invalid-templates'),
        groups: shadow.querySelector('.groups'),
        missingFields: shadow.querySelector('.missing-fields'),
        fullResult: shadow.querySelector('.full-result'),
        queue: shadow.querySelector('.queue'),
        queueDrain: shadow.querySelector('.queue-drain'),
        error: shadow.querySelector('.error'),
        collect: shadow.querySelector('.collect'),
      }
      updatePanel()
    }

    function ensureToken(force = false) {
      const existing = String(getValue(KEYS.token, '') || '').trim()
      if (existing && !force) return true
      const entered = TRUSTED_PROMPT
        ? TRUSTED_PROMPT(
            force
              ? '请输入新的华邦 LifeData 采集令牌'
              : '首次使用：请输入华邦 LifeData 采集令牌',
            '',
          )
        : null
      if (typeof entered === 'string' && entered.trim()) {
        setValue(KEYS.token, entered.trim())
        setError('')
        if (state.isLeader) {
          void runExclusiveAction(() => flushQueue())
        }
        return true
      }
      setError('采集令牌未配置，采集结果只会保存在离线队列')
      return false
    }

    async function initializeQueueStorage() {
      await queueStore.recover()
      const migration = await migrateLegacyQueue(queueStore, {
        read: () => getValue(KEYS.queue, []),
        clear: () => GM_deleteValue(KEYS.queue),
      })
      if (migration.status === 'failed') {
        setError('旧版离线队列迁移失败，原数据已保留')
      }
      queueCache = await queueStore.snapshot()
    }

    function finishStartup() {
      state.ready = true
      ensureToken(false)
      maintenanceTick()
      state.leaderTimer = page.setInterval(maintenanceTick, 10_000)
    }

    function startAfterDomReady() {
      createPanel()
      if (injectedQueueStore) {
        finishStartup()
        return
      }
      void initializeQueueStorage().then(finishStartup, () => {
        setError('GM 离线队列初始化失败')
      })
    }

    function maintenanceTick() {
      ensureObservers()
      synchronizeLeadership()
    }

    ensureObservers()
    installSpaObserver()
    GM_registerMenuCommand('立即采集 LifeData 视频', () => {
      if (synchronizeLeadership()) {
        void runExclusiveAction(() => collectVideo())
      }
    })
    GM_registerMenuCommand('立即全量采集 LifeData', () => {
      if (synchronizeLeadership()) {
        void runExclusiveAction(() => runFullCollection())
      }
    })
    GM_registerMenuCommand('配置/更换采集令牌', () => ensureToken(true))

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', startAfterDomReady, {
        once: true,
      })
    } else {
      startAfterDomReady()
    }

    page.addEventListener('beforeunload', () => {
      if (state.leaderTimer !== null) page.clearInterval(state.leaderTimer)
      stopLeaderTimers()
      const lease = getValue(KEYS.leader, null)
      if (lease && lease.tabId === tabId) {
        setValue(KEYS.leader, { tabId, expiresAt: 0 })
      }
    })
  }
})()
