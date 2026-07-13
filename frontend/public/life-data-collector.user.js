// ==UserScript==
// @name         华邦 LifeData 主动采集器
// @namespace    https://hbreare.com/
// @version      1.0.4
// @description  在已登录的生意经页面内采集白名单业务 JSON
// @match        https://www.life-data.cn/*
// @run-at       document-start
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
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
      const normalized = String(key).toLowerCase()
      if (
        SENSITIVE_JSON_KEYS.has(normalized) ||
        normalized === '__proto__' ||
        normalized === 'prototype' ||
        normalized === 'constructor'
      ) {
        continue
      }
      clean[key] = sanitizeBusinessJson(child)
    }
    return clean
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

  function retryDelayForAttempt(attempt) {
    const index = Math.max(0, Math.floor(Number(attempt) || 0))
    return RETRY_DELAYS[Math.min(index, RETRY_DELAYS.length - 1)]
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
        100,
        Math.max(0, Math.floor(Number(options.queueDepth) || 0)),
      ),
      endpoint: normalizeEndpoint(options.endpoint),
      request_payload: sanitizeBusinessJson(options.requestPayload),
      response_payload: sanitizeBusinessJson(options.responsePayload),
      captured_at: String(options.capturedAt),
    }
  }

  const core = {
    ACCOUNT_ID,
    LIFE_ACCOUNT_ID,
    buildIngestPayload,
    buildPageOffsets,
    buildVideoRequest,
    classifyUploadResponse,
    enqueueBounded,
    extractItemRank,
    isAllowedEndpoint,
    nextLeaderLease,
    pickLifeDataHeaders,
    refreshRelativeDateRange,
    resolveGroupId,
    retryDelayForAttempt,
    sanitizeBusinessJson,
    validateVideoPage,
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
      leader: 'lifeDataLeader',
      minimized: 'lifeDataPanelMinimized',
    }
    const INGEST_URL = 'https://hbreare.com/api/v1/life-data/ingest'
    const STATUS_URL = 'https://hbreare.com/api/v1/life-data/status'
    const VIDEO_PATH = '/flow/content/analysis/video'
    const VIDEO_INTERVAL = 300_000
    const OTHER_INTERVAL = 1_800_000
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
      flushing: false,
      leaderTimer: null,
      videoTimer: null,
      otherTimer: null,
      queueTimer: null,
      statusTimer: null,
      statusErrorTimer: null,
      observedLockWaiters: 0,
      triggeredTemplateAt: 0,
      lastCapture: '',
      lastUpload: '',
      videoCount: null,
      error: '',
      panel: null,
    }

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
      state.error = String(message || '')
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
      const templates = readTemplates()
      const key = [
        template.kind,
        template.endpoint,
        template.pagePath,
        template.moduleIdentity,
      ].join('|')
      templates[key] = template
      setValue(KEYS.templates, templates)
    }

    function latestVideoTemplate() {
      return Object.values(readTemplates())
        .filter(
          (template) =>
            template && (template.kind === 'video' || template.isVideo === true),
        )
        .sort((a, b) => Number(b.learnedAt) - Number(a.learnedAt))[0] || null
    }

    function otherTemplates() {
      return Object.values(readTemplates()).filter(
        (template) =>
          template && template.kind !== 'video' && template.isVideo !== true,
      )
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
      const template = {
        endpoint: record.endpoint,
        pagePath,
        requestPayload: sanitizeBusinessJson(record.requestPayload),
        kind: isVideo ? 'video' : 'other',
        moduleIdentity: getModuleIdentity(record.requestPayload),
        isVideo,
        learnedAt: Date.now(),
      }
      saveTemplate(template)
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
      if (!state.ready || !synchronizeLeadership()) return
      const result = await runExclusiveAction(
        () => {
          if (!hasConfirmedLeaderLease()) {
            applyLeadership(false)
            const queued = queuePayload(payload)
            if (queued.status === 'queued' && !queued.dropped) {
              setError('主标签已切换，事件已进入离线队列')
            }
            return queued
          }
          return uploadOrQueue(payload)
        },
        'observed',
      )
      if (result && result.status === 'lock_unavailable') {
        const queued = queuePayload(payload)
        if (queued.status === 'queued' && !queued.dropped) {
          setError(`${result.message}，事件已进入离线队列`)
        }
      }
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
        if (!response.ok) throw new Error(`LifeData HTTP ${response.status}`)
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
      const queue = getValue(KEYS.queue, [])
      return Array.isArray(queue) ? queue : []
    }

    function writeQueue(queue) {
      if (!setValue(KEYS.queue, queue)) {
        setError('离线队列写入失败，事件状态未保存')
        return false
      }
      updatePanel()
      return true
    }

    function sanitizeStatusError(message) {
      const redacted = String(message || '')
        .replace(/bearer\s+[^\s]+/gi, 'Bearer [redacted]')
        .replace(/(cookie|authorization|x-tt-ls-session-id|root-life-account-id|life-account-id)\s*[:=]\s*[^\s,;]+/gi, '$1=[redacted]')
      return (redacted.trim() || '采集器错误').slice(0, 500)
    }

    function postCollectorStatus(status, lastError = null) {
      const token = String(getValue(KEYS.token, '') || '').trim()
      if (!token || !state.isLeader) return Promise.resolve(false)
      const body = {
        schema_version: '1.0',
        account_id: ACCOUNT_ID,
        status,
        queue_depth: Math.min(100, readQueue().length),
        last_error:
          status === 'error' ? sanitizeStatusError(lastError) : null,
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
        queue_depth: Math.min(100, readQueue().length),
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
              uploadError(
                classification.retryable
                  ? `中台暂时不可用（HTTP ${response.status}）`
                  : `中台永久拒绝事件（HTTP ${response.status}）`,
                classification.retryable,
              ),
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

    function queuePayload(payload) {
      const before = readQueue()
      const dropped = before.length >= 100
      const next = enqueueBounded(
        before,
        {
          payload,
          attempt: 0,
          nextAttemptAt: Date.now() + retryDelayForAttempt(0),
        },
        100,
      )
      if (!writeQueue(next)) {
        return { status: 'queue_failed', dropped: false }
      }
      if (dropped) setError('离线队列已满，已丢弃最旧事件')
      return { status: 'queued', dropped }
    }

    async function uploadOrQueue(payload) {
      try {
        await postPayload(payload)
        setStatus({ lastUpload: new Date().toISOString() })
        if (state.isLeader) void postCollectorStatus('online')
        return { status: 'uploaded', dropped: false }
      } catch (error) {
        if (error.retryable === false) {
          setError(`永久上传错误：${error.message}`)
          return { status: 'discarded', dropped: false }
        }
        const result = queuePayload(payload)
        if (result.status === 'queued' && !result.dropped) {
          setError('上传失败，事件已进入离线队列')
        }
        return result
      }
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
      return uploadOrQueue(payload)
    }
    async function flushQueue() {
      if (!state.isLeader || state.flushing) return
      const queue = readQueue()
      const index = queue.findIndex(
        (item) => item && Number(item.nextAttemptAt) <= Date.now(),
      )
      if (index < 0) return
      state.flushing = true
      const item = queue[index]
      try {
        await postPayload(item.payload)
        const latest = readQueue().filter(
          (queued) => queued.payload.event_id !== item.payload.event_id,
        )
        if (!writeQueue(latest)) return
        setStatus({ lastUpload: new Date().toISOString() })
        if (latest.length === 0) setError('')
      } catch (error) {
        const latest = readQueue()
        const failedIndex = latest.findIndex(
          (queued) => queued.payload.event_id === item.payload.event_id,
        )
        if (error.retryable === false) {
          if (failedIndex >= 0) latest.splice(failedIndex, 1)
          if (!writeQueue(latest)) return
          setError(`永久上传错误，事件已移出队列：${error.message}`)
        } else {
          const failed = failedIndex >= 0 ? latest[failedIndex] : null
          if (failed) {
            failed.attempt = Number(failed.attempt || 0) + 1
            failed.nextAttemptAt =
              Date.now() + retryDelayForAttempt(failed.attempt)
            if (!writeQueue(latest)) return
          }
          setError('离线队列重试失败，将按退避时间继续')
        }
      } finally {
        state.flushing = false
      }
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
          if (result.status !== 'uploaded') allUploaded = false
        }
        setStatus({ videoCount: total })
        if (allUploaded) setError('')
      } catch (error) {
        setError(`视频采集失败：${error.message || '未知错误'}`)
      } finally {
        state.collecting = false
      }
    }
    async function replayOtherTemplates() {
      if (!state.isLeader) return
      for (const template of otherTemplates()) {
        try {
          const request = refreshRelativeDateRange(
            template.requestPayload,
            new Date(),
          )
          const response = await replayLifeData(template, request)
          const result = await publishCapture(template, request, response)
          if (result.status === 'uploaded') setError('')
        } catch (error) {
          setError(`业务模板重放失败：${error.message || '未知错误'}`)
        }
      }
    }

    function maybeCollectNewTemplate() {
      if (!state.isLeader) return
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
      state.videoTimer = page.setInterval(() => {
        if (synchronizeLeadership()) {
          void runExclusiveAction(() => collectVideo())
        }
      }, VIDEO_INTERVAL)
      state.otherTimer = page.setInterval(
        () => {
          if (synchronizeLeadership()) {
            void runExclusiveAction(() => replayOtherTemplates())
          }
        },
        OTHER_INTERVAL,
      )
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
      refs.queue.textContent = String(readQueue().length)
      refs.error.textContent = state.error || '无'
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
          button{border:0;border-radius:7px;padding:7px 10px;cursor:pointer}.toggle{background:transparent;color:#f9fafb;padding:2px 6px}.collect{width:100%;margin-top:8px;background:#2563eb;color:#fff;font-weight:700}
        </style>
        <section class="panel">
          <div class="head"><span>LifeData 采集器</span><button class="toggle" type="button">—</button></div>
          <div class="body">
            <div class="row"><span>主体账号</span><span class="value account"></span></div>
            <div class="row"><span>标签状态</span><span class="value leader"></span></div>
            <div class="row"><span>最近采集</span><span class="value capture"></span></div>
            <div class="row"><span>最近上传</span><span class="value upload"></span></div>
            <div class="row"><span>视频数</span><span class="value video"></span></div>
            <div class="row"><span>队列数</span><span class="value queue"></span></div>
            <div class="row"><span>错误</span><span class="value error"></span></div>
            <button class="collect" type="button">立即采集</button>
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
        void runExclusiveAction(() => collectVideo())
      })
      state.panel = {
        account: shadow.querySelector('.account'),
        leader: shadow.querySelector('.leader'),
        capture: shadow.querySelector('.capture'),
        upload: shadow.querySelector('.upload'),
        video: shadow.querySelector('.video'),
        queue: shadow.querySelector('.queue'),
        error: shadow.querySelector('.error'),
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

    function startAfterDomReady() {
      createPanel()
      state.ready = true
      ensureToken(false)
      maintenanceTick()
      state.leaderTimer = page.setInterval(maintenanceTick, 10_000)
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