// ==UserScript==
// @name         华邦 LifeData 主动采集器
// @namespace    https://hbreare.com/
// @version      1.0.0
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
  function buildIngestPayload(options) {
    if (!options || !isAllowedEndpoint(options.endpoint)) {
      throw new Error('不允许的 LifeData 接口')
    }
    return {
      schema_version: '1.0',
      event_id: String(options.eventId),
      account_id: ACCOUNT_ID,
      page_path: String(options.pagePath || '/'),
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
    enqueueBounded,
    extractItemRank,
    isAllowedEndpoint,
    nextLeaderLease,
    pickLifeDataHeaders,
    refreshRelativeDateRange,
    resolveGroupId,
    retryDelayForAttempt,
    sanitizeBusinessJson,
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

    const KEYS = {
      token: 'lifeDataCollectorToken',
      headers: 'lifeDataSessionHeaders',
      templates: 'lifeDataTemplates',
      queue: 'lifeDataQueue',
      leader: 'lifeDataLeader',
      minimized: 'lifeDataPanelMinimized',
    }
    const INGEST_URL = 'https://hbreare.com/api/v1/life-data/ingest'
    const VIDEO_PATH = '/flow/content/analysis/video'
    const VIDEO_INTERVAL = 300_000
    const OTHER_INTERVAL = 1_800_000
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

    function setError(message) {
      state.error = String(message || '')
      updatePanel()
    }

    function setStatus(patch) {
      Object.assign(state, patch)
      updatePanel()
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
      if (!headers['x-tt-ls-session-id'] || !headers['root-life-account-id']) {
        throw new Error('尚未捕获完整 LifeData 会话头')
      }
      if (String(headers['life-account-id'] || '') !== LIFE_ACCOUNT_ID) {
        throw new Error('LifeData 登录账号不匹配')
      }
    }

    function readTemplates() {
      const templates = getValue(KEYS.templates, {})
      return templates && typeof templates === 'object' ? templates : {}
    }

    function saveTemplate(template) {
      const templates = readTemplates()
      templates[`${template.endpoint}|${template.pagePath}`] = template
      setValue(KEYS.templates, templates)
    }

    function latestVideoTemplate() {
      return Object.values(readTemplates())
        .filter((template) => template && template.isVideo)
        .sort((a, b) => Number(b.learnedAt) - Number(a.learnedAt))[0] || null
    }

    function otherTemplates() {
      return Object.values(readTemplates()).filter(
        (template) => template && !template.isVideo,
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

    function installXhrObserver() {
      const XHR = page.XMLHttpRequest
      if (!XHR || XHR.prototype.__huabangLifeDataObserved) return
      const records = new WeakMap()
      const originalOpen = XHR.prototype.open
      const originalSetHeader = XHR.prototype.setRequestHeader
      const originalSend = XHR.prototype.send
      Object.defineProperty(XHR.prototype, '__huabangLifeDataObserved', {
        value: true,
      })

      XHR.prototype.open = function (method, url, ...rest) {
        if (String(method).toUpperCase() === 'POST' && isAllowedEndpoint(url)) {
          records.set(this, {
            endpoint: normalizeEndpoint(url),
            headers: {},
            requestPayload: null,
            browserPath: page.location.pathname,
            browserUrl: page.location.href,
          })
        }
        return originalOpen.call(this, method, url, ...rest)
      }

      XHR.prototype.setRequestHeader = function (name, value) {
        const record = records.get(this)
        const normalized = String(name).toLowerCase()
        if (record && SESSION_HEADERS.has(normalized)) {
          record.headers[normalized] = String(value)
        }
        return originalSetHeader.call(this, name, value)
      }

      XHR.prototype.send = function (body) {
        const record = records.get(this)
        if (record) {
          record.requestPayload = parseRequestBody(body)
          if (record.requestPayload) {
            this.addEventListener(
              'load',
              () => {
                if (this.status < 200 || this.status >= 300) return
                const response = parseXhrResponse(this)
                if (!response) return
                Promise.resolve(processObserved(record, response)).catch(() => {
                  setError('处理 LifeData 响应失败，未上传')
                })
              },
              { once: true },
            )
          }
        }
        return originalSend.call(this, body)
      }
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
      const template = {
        endpoint: record.endpoint,
        pagePath,
        requestPayload: sanitizeBusinessJson(record.requestPayload),
        isVideo: pagePath === VIDEO_PATH,
        learnedAt: Date.now(),
      }
      saveTemplate(template)
      setStatus({ lastCapture: new Date().toISOString(), error: '' })
      if (template.isVideo) {
        if (state.ready && synchronizeLeadership()) maybeCollectNewTemplate()
        return
      }
      await publishCapture(template, template.requestPayload, response)
    }

    async function replayLifeData(template, requestPayload) {
      const headers = pickLifeDataHeaders(getValue(KEYS.headers, {}))
      assertExpectedAccount(requestPayload, headers, page.location.href)
      const response = await page.fetch.call(
        page,
        `${LIFE_DATA_ORIGIN}${template.endpoint}`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json;charset=UTF-8',
            ...headers,
          },
          body: JSON.stringify(sanitizeBusinessJson(requestPayload)),
        },
      )
      if (!response.ok) throw new Error(`LifeData HTTP ${response.status}`)
      const businessJson = await response.json()
      if (!isSuccessfulResponse(businessJson)) {
        throw new Error(`LifeData API 返回非 0：${String(businessJson.code)}`)
      }
      return businessJson
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
      setValue(KEYS.queue, queue)
      updatePanel()
    }

    function postPayload(payload) {
      const token = String(getValue(KEYS.token, '') || '').trim()
      if (!token) return Promise.reject(new Error('采集令牌未配置'))
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
          data: JSON.stringify(payload),
          onload(response) {
            let body = null
            try {
              body = JSON.parse(response.responseText)
            } catch (_error) {
              body = null
            }
            if (
              response.status >= 200 &&
              response.status < 300 &&
              body &&
              body.success === true &&
              Number(body.code) === 200
            ) {
              resolve(body)
              return
            }
            reject(new Error(`中台拒绝采集事件（HTTP ${response.status}）`))
          },
          ontimeout() {
            reject(new Error('上传超时'))
          },
          onerror() {
            reject(new Error('上传网络错误'))
          },
        })
      })
    }

    function queuePayload(payload) {
      const before = readQueue()
      const next = enqueueBounded(
        before,
        {
          payload,
          attempt: 0,
          nextAttemptAt: Date.now() + retryDelayForAttempt(0),
        },
        100,
      )
      writeQueue(next)
      if (before.length >= 100) {
        setError('离线队列已满，已丢弃最旧事件')
      }
    }

    async function uploadOrQueue(payload) {
      try {
        await postPayload(payload)
        setStatus({ lastUpload: new Date().toISOString(), error: '' })
      } catch (_error) {
        queuePayload(payload)
        setError('上传失败，事件已进入离线队列')
      }
    }

    async function publishCapture(template, requestPayload, responsePayload) {
      const capturedAt = new Date().toISOString()
      const payload = buildIngestPayload({
        eventId: newEventId(),
        endpoint: template.endpoint,
        pagePath: template.pagePath,
        requestPayload,
        responsePayload,
        capturedAt,
      })
      setStatus({ lastCapture: capturedAt })
      await uploadOrQueue(payload)
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
        writeQueue(latest)
        setStatus({ lastUpload: new Date().toISOString(), error: '' })
      } catch (_error) {
        const latest = readQueue()
        const failed = latest.find(
          (queued) => queued.payload.event_id === item.payload.event_id,
        )
        if (failed) {
          failed.attempt = Number(failed.attempt || 0) + 1
          failed.nextAttemptAt =
            Date.now() + retryDelayForAttempt(failed.attempt)
          writeQueue(latest)
        }
        setError('离线队列重试失败，将按退避时间继续')
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
        await publishCapture(template, firstRequest, firstResponse)
        for (const offset of offsets.slice(1)) {
          const request = buildVideoRequest(currentTemplate, offset, 100)
          const response = await replayLifeData(template, request)
          const rank = extractItemRank(response)
          if (!rank) throw new Error(`offset ${offset} 缺少 itemRank，未上传`)
          await publishCapture(template, request, response)
        }
        setStatus({ videoCount: total, error: '' })
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
          await publishCapture(template, request, response)
        } catch (error) {
          setError(`业务模板重放失败：${error.message || '未知错误'}`)
        }
      }
    }

    function maybeCollectNewTemplate() {
      if (!state.isLeader) return
      const template = latestVideoTemplate()
      if (!template || Number(template.learnedAt) <= state.triggeredTemplateAt) return
      state.triggeredTemplateAt = Number(template.learnedAt)
      void collectVideo()
    }

    function startLeaderTimers() {
      if (state.videoTimer !== null) return
      state.videoTimer = page.setInterval(() => void collectVideo(), VIDEO_INTERVAL)
      state.otherTimer = page.setInterval(
        () => void replayOtherTemplates(),
        OTHER_INTERVAL,
      )
      state.queueTimer = page.setInterval(() => void flushQueue(), 5_000)
      maybeCollectNewTemplate()
      void flushQueue()
    }

    function stopLeaderTimers() {
      for (const key of ['videoTimer', 'otherTimer', 'queueTimer']) {
        if (state[key] !== null) page.clearInterval(state[key])
        state[key] = null
      }
    }

    function synchronizeLeadership() {
      const now = Date.now()
      const decision = nextLeaderLease(getValue(KEYS.leader, null), tabId, now)
      if (decision.isLeader) setValue(KEYS.leader, decision.lease)
      const confirmed = getValue(KEYS.leader, null)
      const isLeader = Boolean(
        decision.isLeader &&
          confirmed &&
          confirmed.tabId === tabId &&
          Number(confirmed.expiresAt) > now,
      )
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
        void collectVideo()
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
      const entered = page.prompt(
        force ? '请输入新的华邦 LifeData 采集令牌' : '首次使用：请输入华邦 LifeData 采集令牌',
        '',
      )
      if (typeof entered === 'string' && entered.trim()) {
        setValue(KEYS.token, entered.trim())
        setError('')
        if (state.isLeader) void flushQueue()
        return true
      }
      setError('采集令牌未配置，采集结果只会保存在离线队列')
      return false
    }

    function startAfterDomReady() {
      createPanel()
      state.ready = true
      ensureToken(false)
      synchronizeLeadership()
      state.leaderTimer = page.setInterval(synchronizeLeadership, 10_000)
    }

    installXhrObserver()
    GM_registerMenuCommand('立即采集 LifeData 视频', () => {
      if (synchronizeLeadership()) void collectVideo()
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