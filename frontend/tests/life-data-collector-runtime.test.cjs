'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')

const scriptPath = path.join(__dirname, '..', 'public', 'life-data-collector.user.js')
const scriptSource = fs.readFileSync(scriptPath, 'utf8')
const ACCOUNT_ID = '1798826701211732'
const LIFE_ACCOUNT_ID = '7319301636050913280'
const DITO_URL = 'https://www.life-data.cn/api/dito/query'

class FakeEventTarget {
  constructor() {
    this.listeners = new Map()
  }

  addEventListener(type, listener, options = {}) {
    const entries = this.listeners.get(type) || []
    entries.push({ listener, once: Boolean(options && options.once) })
    this.listeners.set(type, entries)
  }

  removeEventListener(type, listener) {
    const entries = this.listeners.get(type) || []
    this.listeners.set(
      type,
      entries.filter((entry) => entry.listener !== listener),
    )
  }

  dispatch(type) {
    for (const entry of [...(this.listeners.get(type) || [])]) {
      entry.listener.call(this, { type, target: this })
      if (entry.once) this.removeEventListener(type, entry.listener)
    }
  }
}

class FakeClassList {
  constructor() {
    this.values = new Set()
  }

  toggle(name, force) {
    const enabled = force === undefined ? !this.values.has(name) : Boolean(force)
    if (enabled) this.values.add(name)
    else this.values.delete(name)
    return enabled
  }

  contains(name) {
    return this.values.has(name)
  }
}

class FakeNode extends FakeEventTarget {
  constructor() {
    super()
    this.style = { cssText: '' }
    this.textContent = ''
    this.classList = new FakeClassList()
    this.children = []
    this.shadowRoot = null
  }

  appendChild(child) {
    this.children.push(child)
    return child
  }

  attachShadow() {
    this.shadowRoot = new FakeShadowRoot()
    return this.shadowRoot
  }
}

class FakeShadowRoot {
  constructor() {
    this.nodes = new Map()
    this._innerHTML = ''
  }

  set innerHTML(value) {
    this._innerHTML = String(value)
  }

  get innerHTML() {
    return this._innerHTML
  }

  querySelector(selector) {
    if (!this.nodes.has(selector)) this.nodes.set(selector, new FakeNode())
    return this.nodes.get(selector)
  }
}
function jsonResponse(body, url = DITO_URL) {
  return {
    ok: true,
    status: 200,
    url,
    clone() {
      return jsonResponse(body, url)
    },
    async json() {
      return structuredClone(body)
    },
  }
}

function createHarness(options = {}) {
  const storage = options.sharedStorage || new Map()
  if (options.withToken !== false && !storage.has('lifeDataCollectorToken')) {
    storage.set('lifeDataCollectorToken', 'collector-token')
  }
  for (const [key, value] of options.storage || []) storage.set(key, value)
  const gmRequests = []
  const menus = new Map()
  const intervals = []
  const timeouts = []
  let timeoutId = 0
  const createdNodes = []
  let sandboxPromptCalls = 0
  let pagePromptCalls = 0
  let uuid = 0

  class FakeXHR extends FakeEventTarget {
    constructor() {
      super()
      this.status = 0
      this.responseType = ''
      this.responseText = ''
      this.response = null
      this.responseURL = ''
      this.headers = {}
    }

    open(method, url) {
      this.method = method
      this.url = String(url)
    }

    setRequestHeader(name, value) {
      this.headers[String(name).toLowerCase()] = String(value)
    }

    send(body) {
      this.body = body
    }

    respond(body, url = this.url, status = 200) {
      this.status = status
      this.responseURL = new URL(url, 'https://www.life-data.cn').href
      this.responseText = JSON.stringify(body)
      this.response = body
      this.dispatch('load')
    }
  }

  const pageEvents = new FakeEventTarget()
  const nativeFetchCalls = []
  const nativeFetch = async (url, init = {}) => {
    nativeFetchCalls.push({ url: String(url), init })
    return options.fetchResponse
      ? options.fetchResponse(url, init, nativeFetchCalls.length)
      : jsonResponse({ code: 0, data: {} }, String(url))
  }
  const page = {
    XMLHttpRequest: FakeXHR,
    fetch: nativeFetch,
    location: {
      href: `https://www.life-data.cn/flow/content/analysis/video?groupid=${ACCOUNT_ID}`,
      pathname: '/flow/content/analysis/video',
    },
    navigator: { locks: options.locks || null },
    AbortController: options.AbortController || AbortController,
    history: {
      pushState() {},
      replaceState() {},
    },
    prompt() {
      pagePromptCalls += 1
      throw new Error('unsafeWindow.prompt must not be used')
    },
    setInterval(callback, delay) {
      intervals.push({ callback, delay })
      return intervals.length
    },
    clearInterval() {},
    setTimeout(callback, delay) {
      timeoutId += 1
      timeouts.push({ id: timeoutId, callback, delay, canceled: false })
      return timeoutId
    },
    clearTimeout(id) {
      const timer = timeouts.find((entry) => entry.id === id)
      if (timer) timer.canceled = true
    },
    addEventListener: pageEvents.addEventListener.bind(pageEvents),
    removeEventListener: pageEvents.removeEventListener.bind(pageEvents),
  }

  const documentEvents = new FakeEventTarget()
  const documentElement = new FakeNode()
  const document = {
    readyState: options.ready ? 'complete' : 'loading',
    documentElement: options.ready ? documentElement : null,
    addEventListener: documentEvents.addEventListener.bind(documentEvents),
    createElement() {
      const node = new FakeNode()
      createdNodes.push(node)
      return node
    },
  }

  const context = {
    unsafeWindow: page,
    window: page,
    document,
    prompt: () => {
      sandboxPromptCalls += 1
      return options.promptValue || 'sandbox-token'
    },
    GM_getValue(key, fallback) {
      return storage.has(key) ? storage.get(key) : fallback
    },
    GM_setValue(key, value) {
      if (options.gmSetFailure && options.gmSetFailure(key, value)) {
        throw new Error(`GM_setValue failed for ${key}`)
      }
      storage.set(key, structuredClone(value))
    },
    GM_registerMenuCommand(label, callback) {
      menus.set(label, callback)
    },
    GM_xmlhttpRequest(request) {
      gmRequests.push(request)
      const response = options.gmResponder
        ? options.gmResponder(request, gmRequests.length)
        : { status: 200, body: { success: true, code: 200 } }
      queueMicrotask(() => {
        if (response && response.type === 'manual') return
        if (response && response.type === 'error') request.onerror({})
        else if (response && response.type === 'timeout') request.ontimeout({})
        else
          request.onload({
            status: response ? response.status : 0,
            responseText: JSON.stringify(response ? response.body : null),
          })
      })
    },
    crypto: {
      randomUUID() {
        uuid += 1
        if (uuid === 1 && options.tabId) return options.tabId
        return `00000000-0000-4000-8000-${String(uuid).padStart(12, '0')}`
      },
    },
    URL,
    Intl,
    Date,
    Promise,
    structuredClone,
    queueMicrotask,
    setTimeout,
    clearTimeout,
    console,
  }

  vm.runInNewContext(scriptSource, context, { filename: scriptPath })

  return {
    page,
    storage,
    gmRequests,
    menus,
    intervals,
    timeouts,
    nativeFetchCalls,
    get sandboxPromptCalls() {
      return sandboxPromptCalls
    },
    get pagePromptCalls() {
      return pagePromptCalls
    },
    panelText(selector) {
      const shadow = createdNodes[0] && createdNodes[0].shadowRoot
      const node = shadow && shadow.querySelector(selector)
      return node ? node.textContent : ''
    },
    flush: async () => {
      await new Promise((resolve) => setImmediate(resolve))
      await new Promise((resolve) => setImmediate(resolve))
    },
  }
}

function videoRequest(offset = 0, limit = 100) {
  return {
    path: '/flow/content/analysis/video',
    groupid: ACCOUNT_ID,
    biz_params: {
      module_params: {
        ItemRank: { offset, limit },
      },
    },
  }
}

function summaryRequest() {
  return {
    path: '/flow/content/analysis/video',
    groupid: ACCOUNT_ID,
    biz_params: {
      module_params: {
        ContentSummary: { metric: 'play' },
      },
    },
  }
}

function videoResponse(rows, total = rows.length) {
  return {
    code: 0,
    data: {
      rankings: {
        itemRank: { total, data: rows },
      },
    },
  }
}

function setBusinessHeaders(xhr) {
  xhr.setRequestHeader('X-TT-LS-Session-ID', 'session-secret')
  xhr.setRequestHeader('Root-Life-Account-ID', LIFE_ACCOUNT_ID)
  xhr.setRequestHeader('Life-Account-ID', LIFE_ACCOUNT_ID)
}

function observeXhr(harness, request, response, xhr = null) {
  const instance = xhr || new harness.page.XMLHttpRequest()
  instance.open('POST', DITO_URL)
  setBusinessHeaders(instance)
  instance.send(JSON.stringify(request))
  instance.respond(response, DITO_URL)
  return instance
}

test('reusing an XHR for a blocked endpoint cannot leak the old business record', async () => {
  const harness = createHarness()
  const xhr = new harness.page.XMLHttpRequest()

  xhr.open('POST', DITO_URL)
  setBusinessHeaders(xhr)
  xhr.send(JSON.stringify(videoRequest()))
  xhr.open('POST', 'https://www.life-data.cn/api/msg/query')
  xhr.send(JSON.stringify(summaryRequest()))
  xhr.respond({ code: 0, data: { summary: { total: 99 } } }, DITO_URL)
  await harness.flush()

  assert.equal(harness.storage.has('lifeDataTemplates'), false)
  assert.equal(harness.gmRequests.length, 0)
})

test('a summary response on the video page cannot overwrite the ItemRank template', async () => {
  const harness = createHarness()

  observeXhr(
    harness,
    videoRequest(),
    videoResponse([{ item_id: 'video-1', item_play_cnt: 10 }], 1),
  )
  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()

  const templates = Object.values(harness.storage.get('lifeDataTemplates') || {})
  assert.equal(templates.length, 2)
  const video = templates.find((template) => template.kind === 'video')
  const summary = templates.find((template) => template.kind === 'other')
  assert.ok(video)
  assert.ok(summary)
  assert.deepEqual(
    Object.keys(video.requestPayload.biz_params.module_params),
    ['ItemRank'],
  )
  assert.deepEqual(
    Object.keys(summary.requestPayload.biz_params.module_params),
    ['ContentSummary'],
  )
})
test('XHR responseURL must match the endpoint opened for the observed record', async () => {
  const harness = createHarness()
  const xhr = new harness.page.XMLHttpRequest()
  xhr.open('POST', DITO_URL)
  setBusinessHeaders(xhr)
  xhr.send(JSON.stringify(videoRequest()))
  xhr.respond(
    videoResponse([{ item_id: 'video-1', item_play_cnt: 10 }], 1),
    'https://www.life-data.cn/api/lowcode_api/query',
  )
  await harness.flush()

  assert.equal(harness.storage.has('lifeDataTemplates'), false)
})

test('both LifeData account headers must match the fixed life account', async () => {
  const harness = createHarness()
  const xhr = new harness.page.XMLHttpRequest()
  xhr.open('POST', DITO_URL)
  xhr.setRequestHeader('X-TT-LS-Session-ID', 'session-secret')
  xhr.setRequestHeader('Root-Life-Account-ID', ACCOUNT_ID)
  xhr.setRequestHeader('Life-Account-ID', LIFE_ACCOUNT_ID)
  xhr.send(JSON.stringify(videoRequest()))
  xhr.respond(videoResponse([{ item_id: 'video-1', item_play_cnt: 10 }], 1))
  await harness.flush()

  assert.equal(harness.storage.has('lifeDataTemplates'), false)
})
function ingestRequests(harness) {
  return harness.gmRequests.filter((request) => request.url.endsWith('/ingest'))
}

function makeRows(start, count) {
  return Array.from({ length: count }, (_, index) => ({
    item_id: `video-${start + index}`,
    item_play_cnt: start + index,
  }))
}

async function waitFor(predicate, message) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    if (predicate()) return
    await new Promise((resolve) => setImmediate(resolve))
  }
  assert.fail(message)
}

function createSharedLockManager() {
  const active = new Set()
  const pending = new Map()
  const calls = []
  const drain = (name) => {
    if (active.has(name)) return
    const queue = pending.get(name) || []
    const entry = queue.shift()
    if (!entry) return
    active.add(name)
    Promise.resolve()
      .then(() => entry.callback({ name }))
      .then(entry.resolve, entry.reject)
      .finally(() => {
        active.delete(name)
        drain(name)
      })
  }
  return {
    calls,
    locks: {
      request(name, options, callback) {
        calls.push({ name, options })
        return new Promise((resolve, reject) => {
          const queue = pending.get(name) || []
          queue.push({ callback, resolve, reject })
          pending.set(name, queue)
          drain(name)
        })
      },
    },
  }
}

function createBusyLockController() {
  let busy = true
  const pending = []
  const locks = {
    request(name, options, callback) {
      if (name === 'huabang-life-data-queue') {
        return Promise.resolve(callback({ name }))
      }
      if (options.ifAvailable) {
        return Promise.resolve(callback(busy ? null : { name }))
      }
      if (!busy) return Promise.resolve(callback({ name }))
      return new Promise((resolve, reject) => {
        const entry = {
          name,
          options,
          callback,
          resolve,
          reject,
          settled: false,
          onAbort: null,
        }
        entry.onAbort = () => {
          if (entry.settled) return
          entry.settled = true
          const error = new Error('Web Lock request aborted')
          error.name = 'AbortError'
          reject(error)
        }
        pending.push(entry)
        if (options.signal) {
          if (options.signal.aborted) entry.onAbort()
          else {
            options.signal.addEventListener('abort', entry.onAbort, {
              once: true,
            })
          }
        }
      })
    },
  }
  return {
    locks,
    pendingCount() {
      return pending.filter((entry) => !entry.settled).length
    },
    release() {
      busy = false
      for (const entry of pending.splice(0)) {
        if (entry.settled) continue
        entry.settled = true
        if (entry.options.signal) {
          entry.options.signal.removeEventListener('abort', entry.onAbort)
        }
        Promise.resolve(entry.callback({ name: entry.name })).then(
          entry.resolve,
          entry.reject,
        )
      }
    },
  }
}

test('HTTP 200 business code 400 is permanent and never enters the queue', async () => {
  const harness = createHarness({
    ready: true,
    gmResponder: () => ({
      status: 200,
      body: { success: false, code: 400 },
    }),
  })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()

  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 0)
})

test('HTTP 503 remains retryable and enters the bounded queue', async () => {
  const harness = createHarness({
    ready: true,
    gmResponder: () => ({ status: 503, body: { success: false, code: 503 } }),
  })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()

  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 1)
})

test('queue overflow warning is not overwritten by a generic upload error', async () => {
  const queue = Array.from({ length: 100 }, (_, index) => ({
    payload: { event_id: `queued-${index}` },
    attempt: 0,
    nextAttemptAt: Date.now() + 3_600_000,
  }))
  const harness = createHarness({
    ready: true,
    storage: [['lifeDataQueue', queue]],
    gmResponder: () => ({ status: 503, body: { success: false, code: 503 } }),
  })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()

  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 100)
  assert.match(harness.panelText('.error'), /队列已满|丢弃最旧/)
})

test('active video collection uploads exactly 100 plus 14 rows without session headers in payload', async () => {
  const harness = createHarness({
    fetchResponse(url, init) {
      const request = JSON.parse(init.body)
      const offset = request.biz_params.module_params.ItemRank.offset
      const count = offset === 0 ? 100 : 14
      return jsonResponse(videoResponse(makeRows(offset, count), 114), String(url))
    },
  })

  observeXhr(
    harness,
    videoRequest(),
    videoResponse([{ item_id: 'learn-template', item_play_cnt: 1 }], 1),
  )
  harness.menus.get('立即采集 LifeData 视频')()
  await waitFor(
    () => ingestRequests(harness).length === 2,
    'expected two completed ingest uploads',
  )

  const uploads = ingestRequests(harness).map((request) => JSON.parse(request.data))
  assert.deepEqual(
    uploads.map((payload) => payload.response_payload.data.rankings.itemRank.data.length),
    [100, 14],
  )
  assert.deepEqual(uploads.map((payload) => payload.queue_depth), [0, 0])
  for (const request of ingestRequests(harness)) {
    const serialized = request.data.toLowerCase()
    assert.equal(serialized.includes('session-secret'), false)
    assert.equal(serialized.includes('x-tt-ls-session-id'), false)
    assert.equal(serialized.includes('root-life-account-id'), false)
    assert.equal(serialized.includes('life-account-id'), false)
    assert.deepEqual(Object.keys(request.headers).sort(), [
      'Content-Type',
      'X-Collector-Token',
    ])
  }
  assert.equal(harness.nativeFetchCalls.length, 2)
  assert.equal(
    Object.values(harness.storage.get('lifeDataTemplates') || {}).filter(
      (template) => template.kind === 'video',
    ).length,
    1,
  )
})

test('a short second video page prevents every page from being published', async () => {
  const harness = createHarness({
    fetchResponse(url, init) {
      const request = JSON.parse(init.body)
      const offset = request.biz_params.module_params.ItemRank.offset
      const count = offset === 0 ? 100 : 13
      return jsonResponse(videoResponse(makeRows(offset, count), 114), String(url))
    },
  })

  observeXhr(
    harness,
    videoRequest(),
    videoResponse([{ item_id: 'learn-template', item_play_cnt: 1 }], 1),
  )
  harness.menus.get('立即采集 LifeData 视频')()
  await harness.flush()
  await harness.flush()

  assert.equal(ingestRequests(harness).length, 0)
})

test('page fetch is observed through a cloned response and learns a video template', async () => {
  const harness = createHarness({
    fetchResponse(url) {
      return jsonResponse(
        videoResponse([{ item_id: 'fetch-video', item_play_cnt: 5 }], 1),
        String(url),
      )
    },
  })

  await harness.page.fetch(DITO_URL, {
    method: 'POST',
    headers: {
      Cookie: 'never-capture',
      Authorization: 'never-capture',
      'X-TT-LS-Session-ID': 'session-secret',
      'Root-Life-Account-ID': LIFE_ACCOUNT_ID,
      'Life-Account-ID': LIFE_ACCOUNT_ID,
    },
    body: JSON.stringify(videoRequest()),
  })
  await harness.flush()

  const templates = Object.values(harness.storage.get('lifeDataTemplates') || {})
  assert.equal(templates.some((template) => template.kind === 'video'), true)
  const stored = JSON.stringify(harness.storage.get('lifeDataTemplates')).toLowerCase()
  assert.equal(stored.includes('never-capture'), false)
})

test('first token prompt uses the captured userscript sandbox prompt', () => {
  const harness = createHarness({
    ready: true,
    withToken: false,
    promptValue: 'trusted-sandbox-token',
  })

  assert.equal(harness.sandboxPromptCalls, 1)
  assert.equal(harness.pagePromptCalls, 0)
  assert.equal(
    harness.storage.get('lifeDataCollectorToken'),
    'trusted-sandbox-token',
  )
})
function statusRequests(harness) {
  return harness.gmRequests.filter((request) => request.url.endsWith('/status'))
}

test('observer maintenance rewraps replaced XHR and fetch implementations', async () => {
  const harness = createHarness({ ready: true })

  class ReplacementXHR extends FakeEventTarget {
    constructor() {
      super()
      this.status = 0
      this.responseType = ''
      this.responseText = ''
      this.response = null
      this.responseURL = ''
    }
    open(method, url) {
      this.method = method
      this.url = String(url)
    }
    setRequestHeader() {}
    send(body) {
      this.body = body
    }
    respond(body, url = this.url) {
      this.status = 200
      this.responseURL = String(url)
      this.responseText = JSON.stringify(body)
      this.dispatch('load')
    }
  }
  const rawOpen = ReplacementXHR.prototype.open
  const replacementFetch = async (url) => jsonResponse({ code: 0 }, String(url))
  harness.page.XMLHttpRequest = ReplacementXHR
  harness.page.fetch = replacementFetch

  const maintenance = harness.intervals.find((entry) => entry.delay === 10_000)
  assert.ok(maintenance)
  maintenance.callback()
  assert.notEqual(harness.page.XMLHttpRequest.prototype.open, rawOpen)
  assert.notEqual(harness.page.fetch, replacementFetch)

  const secondReplacementFetch = async (url) => jsonResponse({ code: 0 }, String(url))
  harness.page.fetch = secondReplacementFetch
  harness.page.history.pushState({}, '', '/next')
  const spaEnsure = harness.timeouts.find((entry) => entry.delay === 0)
  assert.ok(spaEnsure)
  spaEnsure.callback()
  assert.notEqual(harness.page.fetch, secondReplacementFetch)
})

test('leader posts a sanitized online status heartbeat every 60 seconds', async () => {
  const harness = createHarness({ ready: true })
  const heartbeat = harness.intervals.find((entry) => entry.delay === 60_000)
  assert.ok(heartbeat)

  heartbeat.callback()
  await harness.flush()

  const request = statusRequests(harness).at(-1)
  assert.ok(request)
  assert.deepEqual(JSON.parse(request.data), {
    schema_version: '1.0',
    account_id: ACCOUNT_ID,
    status: 'online',
    queue_depth: 0,
    last_error: null,
  })
  const serialized = request.data.toLowerCase()
  assert.equal(serialized.includes('collector-token'), false)
  assert.equal(serialized.includes('session-secret'), false)
  assert.deepEqual(Object.keys(request.headers).sort(), [
    'Content-Type',
    'X-Collector-Token',
  ])
})

test('permanent upload errors debounce a status error for 30 seconds without queue recursion', async () => {
  const harness = createHarness({
    ready: true,
    gmResponder(request) {
      if (request.url.endsWith('/ingest')) {
        return { status: 200, body: { success: false, code: 400 } }
      }
      return { status: 503, body: { success: false, code: 503 } }
    },
  })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()
  const debounced = harness.timeouts.filter((entry) => entry.delay === 30_000)
  assert.equal(debounced.length, 1)
  debounced[0].callback()
  await harness.flush()

  const request = statusRequests(harness).at(-1)
  assert.ok(request)
  const body = JSON.parse(request.data)
  assert.equal(body.status, 'error')
  assert.equal(body.queue_depth, 0)
  assert.equal(typeof body.last_error, 'string')
  assert.ok(body.last_error.length > 0 && body.last_error.length <= 500)
  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 0)
})
test('blocked fetch requests are not cloned or inspected', async () => {
  const harness = createHarness()
  let cloneCalls = 0
  const blockedRequest = {
    url: 'https://www.life-data.cn/api/msg/query',
    method: 'POST',
    headers: { Authorization: 'never-read' },
    clone() {
      cloneCalls += 1
      return {
        async text() {
          return JSON.stringify({ secret: 'never-read' })
        },
      }
    },
  }

  await harness.page.fetch(blockedRequest)
  await harness.flush()

  assert.equal(cloneCalls, 0)
  assert.equal(harness.storage.has('lifeDataTemplates'), false)
})

test('a permanently rejected queued event is removed instead of retried', async () => {
  const payload = {
    schema_version: '1.0',
    event_id: 'queued-permanent-event',
    account_id: ACCOUNT_ID,
    page_path: '/summary',
    endpoint: '/api/dito/query',
    queue_depth: 0,
    request_payload: {},
    response_payload: { code: 0 },
    captured_at: '2026-07-12T00:00:00.000Z',
  }
  const harness = createHarness({
    ready: true,
    storage: [[
      'lifeDataQueue',
      [{ payload, attempt: 0, nextAttemptAt: 0 }],
    ]],
    gmResponder: () => ({
      status: 200,
      body: { success: false, code: 400 },
    }),
  })
  await harness.flush()

  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 0)
  assert.equal(JSON.parse(ingestRequests(harness)[0].data).queue_depth, 1)
  assert.match(harness.panelText('.error'), /永久上传错误/)
})

test('queued video page uploads keep the collection error visible', async () => {
  const harness = createHarness({
    ready: true,
    fetchResponse(url, init) {
      const request = JSON.parse(init.body)
      const offset = request.biz_params.module_params.ItemRank.offset
      const count = offset === 0 ? 100 : 14
      return jsonResponse(videoResponse(makeRows(offset, count), 114), String(url))
    },
    gmResponder(request) {
      return request.url.endsWith('/ingest')
        ? { status: 503, body: { success: false, code: 503 } }
        : { status: 200, body: { success: true, code: 200 } }
    },
  })

  observeXhr(
    harness,
    videoRequest(),
    videoResponse([{ item_id: 'learn-template', item_play_cnt: 1 }], 1),
  )
  await waitFor(
    () => (harness.storage.get('lifeDataQueue') || []).length === 2,
    'expected both video pages in retry queue',
  )

  assert.match(harness.panelText('.error'), /队列|上传失败/)
})
test('active replay of one other template creates exactly one additional ingest', async () => {
  const harness = createHarness({
    ready: true,
    fetchResponse(url) {
      return jsonResponse(
        { code: 0, data: { contentSummary: { play_count: 11 } } },
        String(url),
      )
    },
  })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await waitFor(() => ingestRequests(harness).length === 1, 'initial ingest missing')
  const before = ingestRequests(harness).length
  const replayTimer = harness.intervals.find(
    (entry) => entry.delay === 1_800_000,
  )
  assert.ok(replayTimer)
  replayTimer.callback()
  await waitFor(
    () => ingestRequests(harness).length >= 2,
    'active other replay ingest missing',
  )
  await harness.flush()

  assert.equal(before, 1)
  assert.equal(ingestRequests(harness).length, 2)
  assert.equal(harness.nativeFetchCalls.length, 1)
})

test('full collection menu replays video and learned non-video api templates', async () => {
  const harness = createHarness({
    fetchResponse(url, init) {
      const body = JSON.parse(init.body)
      const modules = body.biz_params.module_params
      return jsonResponse(
        modules.ItemRank
          ? videoResponse([{ item_id: 'full-video', item_play_cnt: 2200 }], 1)
          : { code: 0, data: { contentSummary: { play_count: 20 } } },
        String(url),
      )
    },
  })
  observeXhr(harness, videoRequest(), videoResponse([{ item_id: 'learn-video', item_play_cnt: 1 }], 1))
  observeXhr(harness, summaryRequest(), { code: 0, data: { contentSummary: { play_count: 10 } } })
  await harness.flush()

  harness.menus.get('立即全量采集 LifeData')()
  await waitFor(() => harness.nativeFetchCalls.length === 2, 'full api replay missing')
  assert.equal(harness.nativeFetchCalls.length, 2)
})

test('successful recovery cancels a pending debounced status error', async () => {
  let permanent = true
  const harness = createHarness({
    ready: true,
    gmResponder(request) {
      if (request.url.endsWith('/status')) {
        return { status: 200, body: { success: true, code: 200 } }
      }
      return permanent
        ? { status: 200, body: { success: false, code: 400 } }
        : { status: 200, body: { success: true, code: 200 } }
    },
  })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()
  assert.equal(
    harness.timeouts.filter((entry) => entry.delay === 30_000).length,
    1,
  )

  permanent = false
  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 12 } } },
  )
  await harness.flush()
  for (const timer of harness.timeouts.filter(
    (entry) => entry.delay === 30_000 && !entry.canceled,
  )) {
    timer.callback()
  }
  await harness.flush()

  const errorStatuses = statusRequests(harness)
    .map((request) => JSON.parse(request.data))
    .filter((body) => body.status === 'error')
  assert.equal(errorStatuses.length, 0)
})

test('a failed GM leader write cannot retain leadership from an old lease', () => {
  const tabId = '00000000-0000-4000-8000-000000000001'
  const harness = createHarness({
    ready: true,
    storage: [[
      'lifeDataLeader',
      { tabId, expiresAt: Date.now() + 60_000 },
    ]],
    gmSetFailure(key) {
      return key === 'lifeDataLeader'
    },
  })

  assert.equal(
    harness.intervals.some((entry) => entry.delay === 300_000),
    false,
  )
  assert.equal(harness.panelText('.leader'), '待命标签')
})

test('a failed GM queue write is explicit and is never reported as queued', async () => {
  const harness = createHarness({
    ready: true,
    gmSetFailure(key) {
      return key === 'lifeDataQueue'
    },
    gmResponder(request) {
      return request.url.endsWith('/ingest')
        ? { status: 503, body: { success: false, code: 503 } }
        : { status: 200, body: { success: true, code: 200 } }
    },
  })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()

  assert.equal(harness.storage.has('lifeDataQueue'), false)
  assert.match(harness.panelText('.error'), /队列写入失败|未保存/)
})
test('nonleader only learns other templates while the leader replays once', async () => {
  const sharedStorage = new Map([
    ['lifeDataCollectorToken', 'collector-token'],
  ])
  const leader = createHarness({
    ready: true,
    sharedStorage,
    tabId: 'leader-tab',
    fetchResponse(url) {
      return jsonResponse(
        { code: 0, data: { contentSummary: { play_count: 20 } } },
        String(url),
      )
    },
  })
  const follower = createHarness({
    ready: true,
    sharedStorage,
    tabId: 'follower-tab',
  })

  observeXhr(
    follower,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await follower.flush()
  assert.equal(ingestRequests(follower).length, 0)
  assert.equal((sharedStorage.get('lifeDataQueue') || []).length, 0)

  const replayTimer = leader.intervals.find(
    (entry) => entry.delay === 1_800_000,
  )
  assert.ok(replayTimer)
  replayTimer.callback()
  await waitFor(
    () => ingestRequests(leader).length === 1,
    'leader did not replay the shared other template',
  )
  assert.equal(ingestRequests(leader).length, 1)
})

test('hanging native replay fetch aborts after 20 seconds with an explicit error', async () => {
  let fetchSignal = null
  const harness = createHarness({
    ready: true,
    fetchResponse(_url, init) {
      fetchSignal = init.signal
      return new Promise((_resolve, reject) => {
        init.signal.addEventListener(
          'abort',
          () => {
            const error = new Error('fetch aborted')
            error.name = 'AbortError'
            reject(error)
          },
          { once: true },
        )
      })
    },
  })

  observeXhr(
    harness,
    videoRequest(),
    videoResponse([{ item_id: 'learn-template', item_play_cnt: 1 }], 1),
  )
  await waitFor(() => fetchSignal !== null, 'native replay fetch did not start')
  const fetchTimeout = harness.timeouts.find(
    (entry) => entry.delay === 20_000 && !entry.canceled,
  )
  assert.ok(fetchTimeout)
  fetchTimeout.callback()
  await waitFor(
    () => /20.*秒|超时/.test(harness.panelText('.error')),
    'fetch timeout did not surface an explicit error',
  )

  assert.equal(fetchSignal.aborted, true)
  assert.equal(fetchTimeout.canceled, true)
  assert.equal(ingestRequests(harness).length, 0)
  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 0)
})

test('busy Web Lock queues an observed response and uploads it exactly once after release', async () => {
  let busy = true
  const pending = []
  const lockCalls = []
  const locks = {
    request(name, options, callback) {
      lockCalls.push({ name, options })
      if (options.ifAvailable) {
        return Promise.resolve(callback(busy ? null : { name }))
      }
      if (!busy) return Promise.resolve(callback({ name }))
      return new Promise((resolve, reject) => {
        pending.push(() => {
          Promise.resolve(callback({ name })).then(resolve, reject)
        })
      })
    },
  }
  const harness = createHarness({ ready: true, locks })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()

  assert.equal(ingestRequests(harness).length, 0)
  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 0)
  assert.equal(
    lockCalls.some(
      (call) =>
        call.options.mode === 'exclusive' &&
        !Object.prototype.hasOwnProperty.call(call.options, 'ifAvailable'),
    ),
    true,
  )

  busy = false
  for (const resume of pending.splice(0)) resume()
  await waitFor(
    () => ingestRequests(harness).length === 1,
    'observed response was lost while the Web Lock was busy',
  )
  await harness.flush()

  assert.equal(ingestRequests(harness).length, 1)
  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 0)
})

test('only 20 observed responses wait for a busy lock and the 21st is queued', async () => {
  const controller = createBusyLockController()
  const harness = createHarness({ ready: true, locks: controller.locks })

  for (let index = 0; index < 21; index += 1) {
    observeXhr(
      harness,
      summaryRequest(),
      { code: 0, data: { contentSummary: { play_count: index } } },
    )
  }
  await harness.flush()

  assert.equal(controller.pendingCount(), 20)
  assert.equal(ingestRequests(harness).length, 0)
  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 1)
  assert.match(harness.panelText('.error'), /等待|队列|上限/)
})

test('observed lock wait timeout queues the captured payload', async () => {
  const controller = createBusyLockController()
  const harness = createHarness({ ready: true, locks: controller.locks })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()
  assert.equal(controller.pendingCount(), 1)

  const lockTimeout = harness.timeouts.find(
    (entry) => entry.delay === 30_000 && !entry.canceled,
  )
  assert.ok(lockTimeout)
  lockTimeout.callback()
  await waitFor(
    () => (harness.storage.get('lifeDataQueue') || []).length === 1,
    'timed-out observed payload was not queued',
  )

  assert.equal(controller.pendingCount(), 0)
  assert.equal(ingestRequests(harness).length, 0)
  assert.match(harness.panelText('.error'), /超时.*队列|队列.*超时/)
})

test('leader transfer while waiting queues the capture without uploading', async () => {
  const controller = createBusyLockController()
  const harness = createHarness({ ready: true, locks: controller.locks })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()
  assert.equal(controller.pendingCount(), 1)

  harness.storage.set('lifeDataLeader', {
    tabId: 'another-tab',
    expiresAt: Date.now() + 60_000,
  })
  controller.release()
  await waitFor(
    () => (harness.storage.get('lifeDataQueue') || []).length === 1,
    'capture was not queued after leadership changed',
  )
  await harness.flush()

  assert.equal(ingestRequests(harness).length, 0)
  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 1)
})

test('busy scheduled lock leaves a new video template retryable on maintenance', async () => {
  let busy = true
  const lockCalls = []
  const locks = {
    request(name, options, callback) {
      lockCalls.push({ name, options })
      return Promise.resolve(callback(busy ? null : { name }))
    },
  }
  const harness = createHarness({
    ready: true,
    locks,
    fetchResponse(url) {
      return jsonResponse(
        videoResponse([{ item_id: 'video-1', item_play_cnt: 10 }], 1),
        String(url),
      )
    },
  })

  observeXhr(
    harness,
    videoRequest(),
    videoResponse([{ item_id: 'learn-template', item_play_cnt: 1 }], 1),
  )
  await harness.flush()
  assert.equal(ingestRequests(harness).length, 0)
  assert.equal(harness.nativeFetchCalls.length, 0)

  busy = false
  const beforeMaintenance = lockCalls.length
  const maintenance = harness.intervals.find((entry) => entry.delay === 10_000)
  assert.ok(maintenance)
  maintenance.callback()
  await waitFor(
    () => ingestRequests(harness).length === 1,
    'maintenance did not retry the untriggered video template',
  )
  maintenance.callback()
  await harness.flush()

  assert.equal(ingestRequests(harness).length, 1)
  assert.equal(harness.nativeFetchCalls.length, 1)
  assert.equal(
    lockCalls
      .slice(beforeMaintenance)
      .some((call) => call.options.ifAvailable === true),
    true,
  )
})

test('rejected waiting Web Lock reports an explicit collector error', async () => {
  const locks = {
    request(name, _options, callback) {
      if (name === 'huabang-life-data-action') {
        return Promise.reject(new Error('lock service unavailable'))
      }
      return Promise.resolve(callback({ name }))
    },
  }
  const harness = createHarness({ ready: true, locks })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()

  assert.equal(ingestRequests(harness).length, 0)
  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 1)
  assert.match(harness.panelText('.error'), /互斥锁|锁获取失败|队列/)
})

test('Chrome Web Locks wraps observed other upload as one exclusive action', async () => {
  const lockCalls = []
  const locks = {
    request(name, options, callback) {
      lockCalls.push({ name, options })
      return Promise.resolve(callback({ name }))
    },
  }
  const harness = createHarness({ ready: true, locks })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await waitFor(() => ingestRequests(harness).length === 1, 'ingest missing')

  assert.equal(
    lockCalls.some(
      (call) =>
        call.name === 'huabang-life-data-action' &&
        call.options.mode === 'exclusive' &&
        !Object.prototype.hasOwnProperty.call(call.options, 'ifAvailable'),
    ),
    true,
  )
})

test('shared queue lock preserves fallback while another tab flushes', async () => {
  const oldPayload = {
    schema_version: '1.0',
    event_id: 'old-event',
    account_id: ACCOUNT_ID,
    page_path: '/summary',
    endpoint: '/api/dito/query',
    queue_depth: 1,
    request_payload: {},
    response_payload: { code: 0 },
    captured_at: '2026-07-12T00:00:00.000Z',
  }
  const sharedStorage = new Map([
    ['lifeDataCollectorToken', 'collector-token'],
    [
      'lifeDataQueue',
      [{ payload: oldPayload, attempt: 0, nextAttemptAt: 0 }],
    ],
  ])
  const sharedQueueLock = createSharedLockManager()
  const leaderLocks = {
    request(name, options, callback) {
      if (name === 'huabang-life-data-queue') {
        return sharedQueueLock.locks.request(name, options, callback)
      }
      return Promise.resolve(callback({ name }))
    },
  }
  const fallbackLocks = {
    request(name, options, callback) {
      if (name === 'huabang-life-data-queue') {
        return sharedQueueLock.locks.request(name, options, callback)
      }
      return Promise.reject(new Error('force observed fallback'))
    },
  }
  const leader = createHarness({
    ready: true,
    sharedStorage,
    tabId: 'queue-leader',
    locks: leaderLocks,
    gmResponder(request) {
      return request.url.endsWith('/ingest')
        ? { type: 'manual' }
        : { status: 200, body: { success: true, code: 200 } }
    },
  })
  await waitFor(
    () => ingestRequests(leader).length === 1,
    'leader flush did not start',
  )

  const currentQueue = structuredClone(sharedStorage.get('lifeDataQueue'))
  currentQueue[0].nextAttemptAt = Date.now() + 60_000
  sharedStorage.set('lifeDataQueue', currentQueue)
  sharedStorage.set('lifeDataLeader', {
    tabId: 'fallback-tab',
    expiresAt: Date.now() + 60_000,
  })
  const fallback = createHarness({
    ready: true,
    sharedStorage,
    tabId: 'fallback-tab',
    locks: fallbackLocks,
  })
  observeXhr(
    fallback,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 99 } } },
  )
  await waitFor(
    () => (sharedStorage.get('lifeDataQueue') || []).length === 2,
    'fallback event was not queued while flush was pending',
  )

  ingestRequests(leader)[0].onload({
    status: 200,
    responseText: JSON.stringify({ success: true, code: 200 }),
  })
  await waitFor(
    () =>
      (sharedStorage.get('lifeDataQueue') || []).length === 1 &&
      sharedStorage.get('lifeDataQueue')[0].payload.event_id !== 'old-event',
    'flush lost fallback event or resurrected old event',
  )

  const finalQueue = sharedStorage.get('lifeDataQueue')
  assert.equal(finalQueue.length, 1)
  assert.equal(finalQueue[0].payload.event_id === 'old-event', false)
  assert.equal(
    finalQueue[0].payload.response_payload.data.contentSummary.play_count,
    99,
  )
  const queueLockCalls = sharedQueueLock.calls.filter(
    (call) => call.name === 'huabang-life-data-queue',
  )
  assert.equal(queueLockCalls.length >= 2, true)
  assert.equal(
    queueLockCalls.every(
      (call) =>
        call.options.mode === 'exclusive' &&
        !Object.prototype.hasOwnProperty.call(call.options, 'ifAvailable'),
    ),
    true,
  )
})

test('queue Web Lock rejection is explicit and never claims queued', async () => {
  const locks = {
    request(name, _options, callback) {
      if (name === 'huabang-life-data-queue') {
        return Promise.reject(new Error('queue lock unavailable'))
      }
      return Promise.resolve(callback({ name }))
    },
  }
  const harness = createHarness({
    ready: true,
    locks,
    gmResponder(request) {
      return request.url.endsWith('/ingest')
        ? { status: 503, body: { success: false, code: 503 } }
        : { status: 200, body: { success: true, code: 200 } }
    },
  })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()

  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 0)
  assert.match(harness.panelText('.error'), /队列.*锁.*失败|状态未保存/)
  assert.doesNotMatch(harness.panelText('.error'), /已进入离线队列/)
})

test('flush keeps an explicit error when removing an uploaded queue item cannot be stored', async () => {
  const payload = {
    schema_version: '1.0',
    event_id: 'queue-write-failure-after-upload',
    account_id: ACCOUNT_ID,
    page_path: '/summary',
    endpoint: '/api/dito/query',
    queue_depth: 1,
    request_payload: {},
    response_payload: { code: 0 },
    captured_at: '2026-07-12T00:00:00.000Z',
  }
  const harness = createHarness({
    ready: true,
    storage: [[
      'lifeDataQueue',
      [{ payload, attempt: 0, nextAttemptAt: 0 }],
    ]],
    gmSetFailure(key) {
      return key === 'lifeDataQueue'
    },
  })
  await harness.flush()

  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 1)
  assert.match(harness.panelText('.error'), /队列写入失败|未保存/)
})
