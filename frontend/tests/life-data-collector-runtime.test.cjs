'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const vm = require('node:vm')
const { webcrypto } = require('node:crypto')

const scriptPath = path.join(__dirname, '..', 'public', 'life-data-collector.user.js')
const scriptSource = fs.readFileSync(scriptPath, 'utf8')
const core = require(scriptPath)
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
  const cryptoApi = {
    subtle: options.subtle || webcrypto.subtle,
    randomUUID() {
      uuid += 1
      if (uuid === 1 && options.tabId) return options.tabId
      if (options.tabId) return `${options.tabId}:event-${uuid}`
      return `00000000-0000-4000-8000-${String(uuid).padStart(12, '0')}`
    },
  }

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
    __huabangLifeDataQueueStore: options.queueStore || core.createMemoryQueueStore(
      storage.get('lifeDataQueue') || [],
      (records) => {
        if (options.gmSetFailure && options.gmSetFailure('lifeDataQueue', records)) return false
        storage.set('lifeDataQueue', structuredClone(records))
        return true
      },
    ),
    XMLHttpRequest: FakeXHR,
    fetch: nativeFetch,
    location: {
      href: `https://www.life-data.cn/flow/content/analysis/video?groupid=${ACCOUNT_ID}`,
      pathname: '/flow/content/analysis/video',
    },
    navigator: { locks: options.locks || null },
    crypto: cryptoApi,
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
      const id = intervals.length + 1
      intervals.push({ id, callback, delay, canceled: false })
      return id
    },
    clearInterval(id) {
      const timer = intervals.find((entry) => entry.id === id)
      if (timer) timer.canceled = true
    },
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
    GM_deleteValue(key) {
      storage.delete(key)
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
    crypto: cryptoApi,
    TextEncoder,
    URL,
    Intl,
    Date: options.Date || Date,
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
    peekNextUuid() {
      if (options.tabId) return `${options.tabId}:event-${uuid + 1}`
      return `00000000-0000-4000-8000-${String(uuid + 1).padStart(12, '0')}`
    },
    panelText(selector) {
      const shadow = createdNodes[0] && createdNodes[0].shadowRoot
      const node = shadow && shadow.querySelector(selector)
      return node ? node.textContent : ''
    },
    flush: async () => {
      for (let turn = 0; turn < 8; turn += 1) {
        await new Promise((resolve) => setImmediate(resolve))
      }
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
  for (let attempt = 0; attempt < 200; attempt += 1) {
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

function createSharedGmRuntime(records) {
  const storage = new Map([['lifeDataCollectorToken', 'collector-token']])
  const gm = {
    get: (key, fallback) => storage.has(key) ? structuredClone(storage.get(key)) : fallback,
    set: (key, value) => storage.set(key, structuredClone(value)),
    delete: (key) => storage.delete(key),
  }
  const store = core.createGmQueueStore(gm)
  return store.transaction(() => ({ records })).then(() => ({
    storage, gm, store, locks: createSharedLockManager().locks,
  }))
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

test('queue full warning preserves all old retryable events', async () => {
  const queue = Array.from({ length: 500 }, (_, index) => ({
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

  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 500)
  assert.match(harness.panelText('.error'), /队列已满/)
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
  assert.equal(uploads.every((payload) => payload.queue_depth >= 1 && payload.queue_depth <= 2), true)
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
    template_count: 0,
    last_full_success_at: null,
    groups: {
      video: { status: 'missing', template_count: 0, last_success_at: null, last_error: null },
      business: { status: 'missing', template_count: 0, last_success_at: null, last_error: null },
      advertising: { status: 'missing', template_count: 0, last_success_at: null, last_error: null },
      other: { status: 'missing', template_count: 0, last_success_at: null, last_error: null },
    },
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
  const debounced = harness.timeouts.filter(
    (entry) => entry.delay === 30_000 &&
      entry.callback.name !== 'initialCollectionCallback',
  )
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

test('queue starts exactly two uploads and atomically claims oldest due entries', async () => {
  const payload = (id, capturedAt) => ({ schema_version: '1.0', event_id: id, account_id: ACCOUNT_ID, page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {}, response_payload: { code: 0 }, captured_at: capturedAt })
  const harness = createHarness({
    ready: true,
    storage: [['lifeDataQueue', [
      { payload: payload('oldest', '2026-07-12T00:00:00Z'), attempt: 0, nextAttemptAt: 0 },
      { payload: payload('middle', '2026-07-12T00:00:01Z'), attempt: 0, nextAttemptAt: 0 },
      { payload: payload('third', '2026-07-12T00:00:02Z'), attempt: 0, nextAttemptAt: 0 },
    ]]],
    gmResponder(request) { return request.url.endsWith('/ingest') ? { type: 'manual' } : { status: 200, body: { success: true, code: 200 } } },
  })
  await waitFor(() => ingestRequests(harness).length === 2, 'two workers did not start')
  assert.deepEqual(ingestRequests(harness).map((r) => JSON.parse(r.data).event_id), ['oldest', 'middle'])
  const queue = harness.storage.get('lifeDataQueue')
  assert.equal(queue.filter((item) => item.claimedBy && item.claimExpiresAt > Date.now()).length, 2)
  assert.equal(queue.find((item) => item.payload.event_id === 'third').claimedBy, undefined)
})

test('two tabs sharing GM metadata allow only two global upload permits and block leader transfer', async () => {
  const payload = (id, capturedAt) => ({ schema_version: '1.0', event_id: id, account_id: ACCOUNT_ID, page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {}, response_payload: { code: 0 }, captured_at: capturedAt })
  const sharedStorage = new Map([['lifeDataCollectorToken', 'collector-token']])
  const gm = {
    get: (key, fallback) => sharedStorage.has(key) ? structuredClone(sharedStorage.get(key)) : fallback,
    set: (key, value) => sharedStorage.set(key, structuredClone(value)),
    delete: (key) => sharedStorage.delete(key),
  }
  const firstStore = core.createGmQueueStore(gm)
  const secondStore = core.createGmQueueStore(gm)
  await firstStore.transaction(() => ({ records: [
    { payload: payload('global-1', '2026-07-12T00:00:00Z'), attempt: 0, nextAttemptAt: 0 },
    { payload: payload('global-2', '2026-07-12T00:00:01Z'), attempt: 0, nextAttemptAt: 0 },
    { payload: payload('global-3', '2026-07-12T00:00:02Z'), attempt: 0, nextAttemptAt: 0 },
  ] }))
  const lock = createSharedLockManager()
  const first = createHarness({ ready: true, sharedStorage, queueStore: firstStore, tabId: 'permit-a', locks: lock.locks,
    gmResponder(request) { return request.url.endsWith('/ingest') ? { type: 'manual' } : { status: 200, body: { success: true, code: 200 } } } })
  await waitFor(() => ingestRequests(first).length === 2, 'first leader did not fill permits')
  sharedStorage.set('lifeDataLeader', { tabId: 'permit-b', expiresAt: Date.now() + 60_000 })
  const second = createHarness({ ready: true, sharedStorage, queueStore: secondStore, tabId: 'permit-b', locks: lock.locks,
    gmResponder(request) { return request.url.endsWith('/ingest') ? { type: 'manual' } : { status: 200, body: { success: true, code: 200 } } } })
  await second.flush()
  assert.equal(ingestRequests(second).length, 0)
  assert.equal((sharedStorage.get('lifeDataQueue:meta').permits || []).length, 2)
})

test('expired permit recovery fences a late old success from the new owner event', async () => {
  const payload = { schema_version: '1.0', event_id: 'fenced-event', account_id: ACCOUNT_ID, page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {}, response_payload: { code: 0 }, captured_at: '2026-07-12T00:00:00Z' }
  const sharedStorage = new Map([['lifeDataCollectorToken', 'collector-token']])
  const gm = { get: (key, fallback) => sharedStorage.has(key) ? structuredClone(sharedStorage.get(key)) : fallback,
    set: (key, value) => sharedStorage.set(key, structuredClone(value)), delete: (key) => sharedStorage.delete(key) }
  const sharedStore = core.createGmQueueStore(gm)
  await sharedStore.transaction(() => ({ records: [{ payload, attempt: 0, nextAttemptAt: 0 }] }))
  const lock = createSharedLockManager()
  const old = createHarness({ ready: true, sharedStorage, queueStore: sharedStore, tabId: 'old-owner', locks: lock.locks,
    gmResponder(request) { return request.url.endsWith('/ingest') ? { type: 'manual' } : { status: 200, body: { success: true, code: 200 } } } })
  await waitFor(() => ingestRequests(old).length === 1, 'old owner did not upload')
  const meta = structuredClone(sharedStorage.get('lifeDataQueue:meta'))
  meta.permits[0].expiresAt = Date.now() - 1
  meta.entries[0].claimExpiresAt = Date.now() - 1
  sharedStorage.set('lifeDataQueue:meta', meta)
  sharedStorage.set('lifeDataLeader', { tabId: 'new-owner', expiresAt: Date.now() + 60_000 })
  const fresh = createHarness({ ready: true, sharedStorage, queueStore: sharedStore, tabId: 'new-owner', locks: lock.locks,
    gmResponder(request) { return request.url.endsWith('/ingest') ? { type: 'manual' } : { status: 200, body: { success: true, code: 200 } } } })
  await waitFor(() => ingestRequests(fresh).length === 1, 'new owner did not reclaim expired permit')
  ingestRequests(old)[0].onload({ status: 200, responseText: JSON.stringify({ success: true, code: 200 }) })
  await old.flush()
  const afterLate = await sharedStore.snapshot()
  assert.equal(afterLate.length, 1)
  assert.match(afterLate[0].claimedBy, /^new-owner:/)
  ingestRequests(fresh)[0].onload({ status: 200, responseText: JSON.stringify({ success: true, code: 200 }) })
  await fresh.flush()
  assert.equal((await sharedStore.snapshot()).length, 0)
})

test('high-watermark scheduled video pauses and resumes below the low watermark', async () => {
  const payload = (index) => ({ schema_version: '1.0', event_id: `water-${index}`, account_id: ACCOUNT_ID, page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {}, response_payload: { code: 0 }, captured_at: '2026-07-12T00:00:00Z' })
  const records = Array.from({ length: 500 }, (_, index) => ({ payload: payload(index), attempt: 0, nextAttemptAt: Date.now() + 60_000 }))
  const store = core.createMemoryQueueStore(records)
  const harness = createHarness({ ready: true, queueStore: store, storage: [['lifeDataQueue', records]] })
  observeXhr(harness, videoRequest(), videoResponse([{ item_id: 'scheduler-template', item_play_cnt: 1 }], 1))
  await harness.flush()
  harness.nativeFetchCalls.length = 0
  const videoTimer = harness.intervals.find((entry) => entry.delay === 300_000)
  videoTimer.callback()
  await harness.flush()
  assert.equal(harness.nativeFetchCalls.length, 0)
  assert.match(harness.panelText('.error'), /高水位|暂停/)
  await store.transaction((current, metadata) => ({ records: current.slice(0, 300), permits: metadata.permits }))
  videoTimer.callback()
  await waitFor(() => harness.nativeFetchCalls.length > 0, 'scheduled video did not resume below low watermark')
})

test('completion releases only the permit matching both worker and event', async () => {
  const payload = { schema_version: '1.0', event_id: 'permit-target', account_id: ACCOUNT_ID, page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {}, response_payload: { code: 0 }, captured_at: '2026-07-12T00:00:00Z' }
  const shared = await createSharedGmRuntime([{ payload, attempt: 0, nextAttemptAt: 0 }])
  const harness = createHarness({ ready: true, sharedStorage: shared.storage, queueStore: shared.store,
    tabId: 'duplicate-worker', locks: shared.locks,
    gmResponder(request) { return request.url.endsWith('/ingest') ? { type: 'manual' } : { status: 200, body: { success: true, code: 200 } } } })
  await waitFor(() => ingestRequests(harness).length === 1, 'target upload missing')
  const meta = structuredClone(shared.storage.get('lifeDataQueue:meta'))
  const owned = meta.permits[0]
  meta.permits.push({ workerId: owned.workerId, eventId: 'anomalous-other-event', expiresAt: owned.expiresAt })
  shared.storage.set('lifeDataQueue:meta', meta)
  ingestRequests(harness)[0].onload({ status: 200, responseText: JSON.stringify({ success: true, code: 200 }) })
  await harness.flush()
  assert.deepEqual(shared.storage.get('lifeDataQueue:meta').permits, [
    { workerId: owned.workerId, eventId: 'anomalous-other-event', expiresAt: owned.expiresAt },
  ])
})

test('20-second timeout releases its matching 30-second permit and preserves retry', async () => {
  const payload = { schema_version: '1.0', event_id: 'gm-timeout', account_id: ACCOUNT_ID, page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {}, response_payload: { code: 0 }, captured_at: '2026-07-12T00:00:00Z' }
  const shared = await createSharedGmRuntime([{ payload, attempt: 0, nextAttemptAt: 0 }])
  const harness = createHarness({ ready: true, sharedStorage: shared.storage, queueStore: shared.store,
    tabId: 'timeout-owner', locks: shared.locks,
    gmResponder(request) { return request.url.endsWith('/ingest') ? { type: 'manual' } : { status: 200, body: { success: true, code: 200 } } } })
  await waitFor(() => ingestRequests(harness).length === 1, 'timeout upload missing')
  const request = ingestRequests(harness)[0]
  const permit = shared.storage.get('lifeDataQueue:meta').permits[0]
  assert.equal(request.timeout, 20_000)
  assert.equal(permit.expiresAt - Date.now() <= 30_000, true)
  assert.equal(permit.expiresAt - Date.now() >= 29_900, true)
  request.ontimeout({})
  await harness.flush()
  const meta = shared.storage.get('lifeDataQueue:meta')
  const queue = await shared.store.snapshot()
  assert.equal(meta.permits.length, 0)
  assert.equal(queue.length, 1)
  assert.equal(queue[0].attempt, 1)
  assert.equal(queue[0].claimedBy, undefined)
})

test('fake clock 31-second expiry recovers claim and permit in another tab and fences late success', async () => {
  let now = 1_800_000_000_000
  class FakeDate extends Date { static now() { return now } }
  const payload = { schema_version: '1.0', event_id: 'clock-recovery', account_id: ACCOUNT_ID, page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {}, response_payload: { code: 0 }, captured_at: '2026-07-12T00:00:00Z' }
  const shared = await createSharedGmRuntime([{ payload, attempt: 0, nextAttemptAt: 0 }])
  const oldStore = core.createGmQueueStore(shared.gm)
  const newStore = core.createGmQueueStore(shared.gm)
  const responder = (request) => request.url.endsWith('/ingest') ? { type: 'manual' } : { status: 200, body: { success: true, code: 200 } }
  const old = createHarness({ ready: true, sharedStorage: shared.storage, queueStore: oldStore, Date: FakeDate,
    tabId: 'clock-old', locks: shared.locks, gmResponder: responder })
  await waitFor(() => ingestRequests(old).length === 1, 'old clock owner missing')
  now += 31_000
  shared.storage.set('lifeDataLeader', { tabId: 'clock-new', expiresAt: now + 30_000 })
  const fresh = createHarness({ ready: true, sharedStorage: shared.storage, queueStore: newStore, Date: FakeDate,
    tabId: 'clock-new', locks: shared.locks, gmResponder: responder })
  await waitFor(() => ingestRequests(fresh).length === 1, 'expired claim was not recovered')
  assert.equal(shared.storage.get('lifeDataQueue:meta').permits.length, 1)
  assert.match(shared.storage.get('lifeDataQueue:meta').permits[0].workerId, /^clock-new:/)
  ingestRequests(old)[0].onload({ status: 200, responseText: JSON.stringify({ success: true, code: 200 }) })
  await old.flush()
  assert.equal((await newStore.snapshot()).length, 1)
  assert.match((await newStore.snapshot())[0].claimedBy, /^clock-new:/)
})

test('retryable and permanent responses release matching permits with correct queue outcomes', async () => {
  const payload = (id) => ({ schema_version: '1.0', event_id: id, account_id: ACCOUNT_ID, page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {}, response_payload: { code: 0 }, captured_at: '2026-07-12T00:00:00Z' })
  const retryShared = await createSharedGmRuntime([{ payload: payload('gm-retry'), attempt: 0, nextAttemptAt: 0 }])
  const retry = createHarness({ ready: true, sharedStorage: retryShared.storage, queueStore: retryShared.store,
    tabId: 'retry-owner', locks: retryShared.locks,
    gmResponder(request) { return request.url.endsWith('/ingest') ? { type: 'manual' } : { status: 200, body: { success: true, code: 200 } } } })
  await waitFor(() => ingestRequests(retry).length === 1, 'retry upload missing')
  ingestRequests(retry)[0].onload({ status: 503, responseText: JSON.stringify({ success: false, code: 503 }) })
  await retry.flush()
  const retryQueue = await retryShared.store.snapshot()
  assert.equal(retryShared.storage.get('lifeDataQueue:meta').permits.length, 0)
  assert.equal(retryQueue[0].attempt, 1)
  assert.equal(retryQueue[0].nextAttemptAt > Date.now(), true)

  const permanentShared = await createSharedGmRuntime([
    { payload: payload('gm-permanent'), attempt: 0, nextAttemptAt: 0 },
    { payload: payload('gm-permanent-survivor'), attempt: 0, nextAttemptAt: Date.now() + 60_000 },
  ])
  const permanent = createHarness({ ready: true, sharedStorage: permanentShared.storage, queueStore: permanentShared.store,
    tabId: 'permanent-owner', locks: permanentShared.locks,
    gmResponder(request) { return request.url.endsWith('/ingest') ? { type: 'manual' } : { status: 200, body: { success: true, code: 200 } } } })
  await waitFor(() => ingestRequests(permanent).length === 1, 'permanent upload missing')
  ingestRequests(permanent)[0].onload({ status: 200, responseText: JSON.stringify({ success: false, code: 400 }) })
  await permanent.flush()
  assert.equal(permanentShared.storage.get('lifeDataQueue:meta').permits.length, 0)
  assert.deepEqual((await permanentShared.store.snapshot()).map((item) => item.payload.event_id), ['gm-permanent-survivor'])
})

test('429 pauses both workers and retries the same queue entry without duplication', async () => {
  const payload = { schema_version: '1.0', event_id: 'rate-limited', account_id: ACCOUNT_ID, page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {}, response_payload: { code: 0 }, captured_at: '2026-07-12T00:00:00Z' }
  const harness = createHarness({ ready: true, storage: [['lifeDataQueue', [{ payload, attempt: 0, nextAttemptAt: 0 }]]], gmResponder(request) { return request.url.endsWith('/ingest') ? { status: 429, body: { success: false, code: 429 } } : { status: 200, body: { success: true, code: 200 } } } })
  await waitFor(() => ingestRequests(harness).length === 1, '429 upload missing')
  await harness.flush()
  const queue = harness.storage.get('lifeDataQueue')
  assert.equal(queue.length, 1)
  assert.equal(queue[0].payload.event_id, 'rate-limited')
  assert.equal(queue[0].claimedBy, undefined)
  assert.equal(harness.storage.get('lifeDataRateState').cooldownUntil > Date.now(), true)
})

test('production workers enforce exact 40 and 20 rolling boundaries and recover only after success', async () => {
  let now = 1_800_000_000_000
  class FakeDate extends Date { static now() { return now } }
  const payload = (prefix, index) => ({ schema_version: '1.0', event_id: `${prefix}-${index}`, account_id: ACCOUNT_ID,
    page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {},
    response_payload: { code: 0 }, captured_at: new FakeDate(now).toISOString() })
  const manual = (request) => request.url.endsWith('/ingest') ? { type: 'manual' } : { status: 200, body: { success: true, code: 200 } }
  const completeUntil = async (harness, target, response) => {
    const completed = new Set()
    for (let turn = 0; turn < 300 && ingestRequests(harness).length < target; turn += 1) {
      await harness.flush()
      for (const request of ingestRequests(harness)) {
        if (completed.has(request)) continue
        completed.add(request)
        request.onload(response)
      }
    }
    await harness.flush()
    return completed
  }

  const normal = await createSharedGmRuntime(Array.from({ length: 41 }, (_, index) => ({ payload: payload('normal', index), attempt: 0, nextAttemptAt: now })))
  const normalHarness = createHarness({ ready: true, sharedStorage: normal.storage, queueStore: core.createGmQueueStore(normal.gm),
    locks: normal.locks, Date: FakeDate, tabId: 'rate-normal', gmResponder: manual })
  const normalCompleted = await completeUntil(normalHarness, 40, { status: 200, responseText: JSON.stringify({ success: true, code: 200 }) })
  assert.equal(ingestRequests(normalHarness).length, 40)
  assert.equal(normalCompleted.size, 40)
  await normalHarness.flush()
  assert.equal(ingestRequests(normalHarness).length, 40)
  now += 60_001
  normalHarness.intervals.find((entry) => entry.delay === 5_000 && !entry.canceled).callback()
  for (const timer of normalHarness.timeouts.filter((entry) => !entry.canceled)) timer.callback()
  await waitFor(() => ingestRequests(normalHarness).length === 41, 'normal 41st did not resume after oldest slot expired')

  now += 60_001
  const reduced = await createSharedGmRuntime(Array.from({ length: 41 }, (_, index) => ({ payload: payload('reduced', index), attempt: 0, nextAttemptAt: now })))
  reduced.storage.set('lifeDataRateState', { reducedMode: true, consecutive429: 2, cooldownUntil: now - 1, timestamps: [] })
  const reducedHarness = createHarness({ ready: true, sharedStorage: reduced.storage, queueStore: core.createGmQueueStore(reduced.gm),
    locks: reduced.locks, Date: FakeDate, tabId: 'rate-reduced', gmResponder: manual })
  const removed = await completeUntil(reducedHarness, 20, { status: 422, responseText: JSON.stringify({ success: false, code: 422 }) })
  assert.equal(removed.size, 20)
  assert.equal(ingestRequests(reducedHarness).length, 20)
  now += 30_000
  await reducedHarness.flush()
  assert.equal(ingestRequests(reducedHarness).length, 20)
  assert.equal(core.effectiveRateLimit(reduced.storage.get('lifeDataRateState'), now, 2), 20)
  now += 30_001
  assert.equal(core.nextRateLimitDelay(reduced.storage.get('lifeDataRateState').timestamps, now, 20, 60_000), 0)
  for (const timer of reducedHarness.timeouts.filter((entry) => !entry.canceled && entry.delay === 60_000)) timer.callback()
  await waitFor(() => ingestRequests(reducedHarness).length >= 21, 'blocked reduced 21st did not resume after its rolling slot expired')
  const recoveryRequest = ingestRequests(reducedHarness)[20]
  recoveryRequest.onload({ status: 200, responseText: JSON.stringify({ success: true, code: 200 }) })
  await reducedHarness.flush()
  const recoveredRate = reduced.storage.get('lifeDataRateState')
  assert.equal(recoveredRate.reducedMode, false)
  assert.equal(core.effectiveRateLimit(recoveredRate, now, 2), 40)
  const completedAfterRecovery = new Set([recoveryRequest])
  for (let turn = 0; turn < 100 && ingestRequests(reducedHarness).length < 25; turn += 1) {
    for (const request of ingestRequests(reducedHarness).slice(20)) {
      if (completedAfterRecovery.has(request)) continue
      completedAfterRecovery.add(request)
      request.onload({ status: 200, responseText: JSON.stringify({ success: true, code: 200 }) })
    }
    await reducedHarness.flush()
  }
  assert.ok(ingestRequests(reducedHarness).length >= 25)
})

test('network, HTTP 5xx, and permanent 4xx outcomes break consecutive 429 with correct queue disposition', async () => {
  const makePayload = (id) => ({ schema_version: '1.0', event_id: id, account_id: ACCOUNT_ID,
    page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {},
    response_payload: { code: 0 }, captured_at: '2026-07-12T00:00:00Z' })
  const cases = [
    { id: 'network-break', response: { type: 'error' }, retained: true },
    { id: 'five-x-break', response: { status: 503, body: { success: false, code: 503 } }, retained: true },
    { id: 'permanent-break', response: { status: 422, body: { success: false, code: 422 } }, retained: false },
  ]
  for (const scenario of cases) {
    const harness = createHarness({ ready: true, storage: [
      ['lifeDataRateState', { consecutive429: 1, last429At: Date.now(), cooldownUntil: 0 }],
      ['lifeDataQueue', [{ payload: makePayload(scenario.id), attempt: 0, nextAttemptAt: 0 }]],
    ], gmResponder(request) { return request.url.endsWith('/ingest') ? scenario.response : { status: 200, body: { success: true, code: 200 } } } })
    await waitFor(() => ingestRequests(harness).length === 1, `${scenario.id} upload missing`)
    await harness.flush()
    assert.equal((harness.storage.get('lifeDataRateState') || {}).consecutive429, 0)
    assert.equal((harness.storage.get('lifeDataQueue') || []).some((entry) => entry.payload.event_id === scenario.id), scenario.retained)
  }
})

test('independent nonleader tabs coalesce identical sanitized captures but retain distinct responses', async () => {
  let now = 1_800_000_000_000
  class FakeDate extends Date { static now() { return now } }
  const sharedStorage = new Map([
    ['lifeDataCollectorToken', 'collector-token'],
    ['lifeDataLeader', { tabId: 'dedupe-blocker', expiresAt: now + 10 * 60_000 }],
  ])
  const gm = { get: (key, fallback) => sharedStorage.has(key) ? structuredClone(sharedStorage.get(key)) : fallback,
    set: (key, value) => sharedStorage.set(key, structuredClone(value)), delete: (key) => sharedStorage.delete(key) }
  const locks = createSharedLockManager().locks
  const waitDepth = async (store, depth, harnesses) => {
    for (let turn = 0; turn < 100 && (await store.snapshot()).length < depth; turn += 1) {
      for (const harness of harnesses) await harness.flush()
    }
  }
  const first = createHarness({ ready: true, sharedStorage, queueStore: core.createGmQueueStore(gm), locks, Date: FakeDate, tabId: 'dedupe-a' })
  const second = createHarness({ ready: true, sharedStorage, queueStore: core.createGmQueueStore(gm), locks, Date: FakeDate, tabId: 'dedupe-b' })
  const response = { code: 0, data: { contentSummary: { play_count: 88, token: 'must-not-index' } } }
  observeXhr(first, summaryRequest(), response)
  observeXhr(second, summaryRequest(), response)
  await first.flush()
  await second.flush()
  const firstStore = core.createGmQueueStore(gm)
  assert.equal((await firstStore.snapshot()).length, 1)
  const metaText = JSON.stringify(sharedStorage.get('lifeDataQueue:meta'))
  assert.equal(metaText.includes('must-not-index'), false)
  assert.equal(metaText.includes('response_payload'), false)
  observeXhr(second, summaryRequest(), { code: 0, data: { contentSummary: { play_count: 89 } } })
  await waitDepth(firstStore, 2, [second])
  assert.equal((await firstStore.snapshot()).length, 2)
  const dedupeMeta = sharedStorage.get('lifeDataQueue:meta').dedupe
  assert.ok(dedupeMeta.every((item) => /^[0-9a-f]{64}:\d+$/.test(item.key)))
  now += 60_001
  observeXhr(first, summaryRequest(), response)
  await waitDepth(firstStore, 3, [first])
  assert.equal((await firstStore.snapshot()).length, 3)

  const failedStorage = new Map([
    ['lifeDataCollectorToken', 'collector-token'],
    ['lifeDataLeader', { tabId: 'dedupe-fail-blocker', expiresAt: now + 60_000 }],
  ])
  const failedGm = { get: (key, fallback) => failedStorage.has(key) ? structuredClone(failedStorage.get(key)) : fallback,
    set: (key, value) => failedStorage.set(key, structuredClone(value)), delete: (key) => failedStorage.delete(key) }
  const rejectedSubtle = { digest: async () => { throw new Error('digest unavailable') } }
  const failedLocks = createSharedLockManager().locks
  const failA = createHarness({ ready: true, sharedStorage: failedStorage, queueStore: core.createGmQueueStore(failedGm),
    locks: failedLocks, Date: FakeDate, tabId: 'dedupe-fail-a', subtle: rejectedSubtle })
  const failB = createHarness({ ready: true, sharedStorage: failedStorage, queueStore: core.createGmQueueStore(failedGm),
    locks: failedLocks, Date: FakeDate, tabId: 'dedupe-fail-b', subtle: rejectedSubtle })
  observeXhr(failA, summaryRequest(), response)
  observeXhr(failB, summaryRequest(), response)
  const failedStore = core.createGmQueueStore(failedGm)
  await waitDepth(failedStore, 2, [failA, failB])
  assert.equal((await failedStore.snapshot()).length, 2)
})

test('24-hour fake clock drives real dual-tab GM queue through limits, failures, watermarks and leader transfer', async () => {
  let now = 1_800_000_000_000
  class FakeDate extends Date { static now() { return now } }
  const sharedStorage = new Map([
    ['lifeDataCollectorToken', 'collector-token'],
    ['lifeDataLeader', { tabId: 'soak-blocker', expiresAt: now + 60 * 60_000 }],
  ])
  const gm = {
    get: (key, fallback) => sharedStorage.has(key) ? structuredClone(sharedStorage.get(key)) : fallback,
    set: (key, value) => sharedStorage.set(key, structuredClone(value)),
    delete: (key) => sharedStorage.delete(key),
  }
  const firstStore = core.createGmQueueStore(gm)
  const secondStore = core.createGmQueueStore(gm)
  const lock = createSharedLockManager()
  const manual = (request) => request.url.endsWith('/ingest')
    ? { type: 'manual' }
    : { status: 200, body: { success: true, code: 200 } }
  const scheduledFetch = (url) => jsonResponse(videoResponse([{ item_id: 'scheduled-soak', item_play_cnt: 1 }], 1), String(url))
  const first = createHarness({ ready: true, sharedStorage, queueStore: firstStore, tabId: 'soak-a', locks: lock.locks, Date: FakeDate, gmResponder: manual, fetchResponse: scheduledFetch })
  let second = null
  const offered = new Set()
  const attempted = new Set()
  const succeeded = new Set()
  const activeOwners = new Map()
  const handled = new Set()
  const starts = []
  let maxPermits = 0
  let sawReduced = false
  let sawHighWater = false
  let sawLowWaterRecovery = false

  const runTimers = async (harness) => {
    if (!harness) return
    for (const timer of [...harness.timeouts]) {
      if (!timer.canceled && !timer.ran) {
        timer.ran = true
        timer.callback()
      }
    }
    await harness.flush()
  }
  const settleStarts = async () => {
    for (let pass = 0; pass < 300; pass += 1) {
      await first.flush()
      if (second) await second.flush()
      const pending = [first, second].filter(Boolean).flatMap(ingestRequests).filter((request) => !handled.has(request))
      if (pending.length === 0) break
      const batchOwners = []
      for (const request of pending) {
        handled.add(request)
        const eventId = JSON.parse(request.data).event_id
        assert.equal(activeOwners.has(eventId), false, `concurrent duplicate owner for ${eventId}`)
        activeOwners.set(eventId, request)
        const rate = sharedStorage.get('lifeDataRateState') || {}
        const limit = core.effectiveRateLimit(rate, now, 2)
        const liveStarts = starts.filter((candidate) => candidate.at > now - 60_000 && candidate.at <= now)
        assert.ok(liveStarts.length < limit, `${limit}/min rolling reservation exceeded`)
        starts.push({ at: now, limit, eventId })
        batchOwners.push({ request, eventId, startNumber: starts.length })
        const livePermits = (sharedStorage.get('lifeDataQueue:meta').permits || []).filter((permit) => permit.expiresAt > now)
        maxPermits = Math.max(maxPermits, livePermits.length)
        assert.ok(livePermits.length <= 2)
      }
      assert.equal(activeOwners.size, batchOwners.length)
      assert.ok(activeOwners.size <= 2)
      now += 10_000
      assert.equal((sharedStorage.get('lifeDataQueue:meta').permits || []).filter((permit) => permit.expiresAt > now).length, batchOwners.length)
      if (batchOwners.some((owner) => owner.startNumber === 55)) {
        now += 10_000
        assert.equal((sharedStorage.get('lifeDataQueue:meta').permits || []).filter((permit) => permit.expiresAt > now).length, batchOwners.length)
      }
      for (const { request, eventId, startNumber } of batchOwners) {
        if (startNumber === 10 || startNumber === 11) {
          request.onload({ status: 429, responseText: JSON.stringify({ success: false, code: 429 }) })
        } else if (startNumber === 55) {
          assert.equal(request.timeout, 20_000)
          request.ontimeout({})
        } else {
          request.onload({ status: 200, responseText: JSON.stringify({ success: true, code: 200 }) })
          succeeded.add(eventId)
        }
        activeOwners.delete(eventId)
      }
      await first.flush()
      if (second) await second.flush()
    }
  }

  const offeredBatches = [38, 38, 38, 100, 100, 100, 87]
  for (let minute = 0; minute < offeredBatches.length; minute += 1) {
    for (let index = 0; index < offeredBatches[minute]; index += 1) {
      if (minute === 0 && index === 0) {
        observeXhr(first, videoRequest(), videoResponse([{ item_id: 'soak-template', item_play_cnt: 1 }], 1))
      } else {
        attempted.add(first.peekNextUuid())
        observeXhr(first, summaryRequest(), { code: 0, data: { contentSummary: { play_count: minute * 1000 + index + 1 } } })
      }
    }
    const expectedDepth = offeredBatches.slice(0, minute + 1).reduce((total, count) => total + count, 0) - 1
    for (let wait = 0; wait < 600 && (await firstStore.snapshot()).length < expectedDepth; wait += 1) {
      await first.flush()
    }
    for (const record of await firstStore.snapshot()) offered.add(record.payload.event_id)
    now += 60_000
  }
  assert.equal((await firstStore.snapshot()).length, 500)
  assert.equal(offered.size, 500)
  sawHighWater = true
  sharedStorage.set('lifeDataLeader', { tabId: 'soak-blocker', expiresAt: now - 1 })
  first.intervals.find((entry) => entry.delay === 10_000).callback()
  await first.flush()
  assert.equal(first.panelText('.leader'), '主标签')
  const firstVideoTimer = first.intervals.find((entry) => entry.delay === 300_000 && !entry.canceled)
  first.nativeFetchCalls.length = 0
  firstVideoTimer.callback()
  await first.flush()
  assert.equal(first.nativeFetchCalls.length, 0)
  for (const timer of first.timeouts.filter((entry) => entry.delay === 30_000)) timer.canceled = true

  let resumedScheduledCollection = false
  for (let minute = offeredBatches.length; minute < 24 * 60; minute += 1) {
    if (minute === 12 * 60) {
      sharedStorage.set('lifeDataLeader', { tabId: 'soak-b', expiresAt: now + 30_000 })
      const beforeA = ingestRequests(first).length
      first.intervals.find((entry) => entry.delay === 10_000).callback()
      await first.flush()
      assert.equal(first.panelText('.leader'), '待命标签')
      assert.equal(first.intervals.find((entry) => entry.delay === 5_000).canceled, true)
      const takeoverSchedulerEventId = 'soak-b:event-2'
      attempted.add(takeoverSchedulerEventId)
      for (const eventId of ['soak-b:event-3', 'soak-b:event-5', 'soak-b:event-6']) {
        attempted.add(eventId)
      }
      second = createHarness({ ready: true, sharedStorage, queueStore: secondStore, tabId: 'soak-b', locks: lock.locks, Date: FakeDate, gmResponder: manual, fetchResponse: scheduledFetch })
      await second.flush()
      assert.equal(second.panelText('.leader'), '主标签')
      assert.equal((await secondStore.snapshot()).some((record) => record.payload.event_id === takeoverSchedulerEventId), false)
      const takeoverStartup = second.timeouts.find((entry) => entry.callback.name === 'initialCollectionCallback')
      takeoverStartup.callback()
      for (let wait = 0; wait < 100 && !(await secondStore.snapshot()).some(
        (record) => record.payload.event_id === takeoverSchedulerEventId
      ); wait += 1) await second.flush()
      assert.equal((await secondStore.snapshot()).some((record) => record.payload.event_id === takeoverSchedulerEventId), true)
      assert.equal(ingestRequests(first).length, beforeA)
      const handoffEventId = second.peekNextUuid()
      attempted.add(handoffEventId)
      observeXhr(second, summaryRequest(), { code: 0, data: { contentSummary: { play_count: 12_000_001 } } })
      for (let wait = 0; wait < 100 && !(await secondStore.snapshot()).some(
        (record) => record.payload.event_id === handoffEventId
      ); wait += 1) await second.flush()
      for (const record of await secondStore.snapshot()) offered.add(record.payload.event_id)
      assert.equal((await secondStore.snapshot()).some((record) => record.payload.event_id === handoffEventId), true)
    }
    const depth = Number((sharedStorage.get('lifeDataQueue:meta') || {}).count || 0)
    assert.ok(depth <= 500)
    if (sawHighWater && depth <= 300) sawLowWaterRecovery = true
    if (sawLowWaterRecovery && !resumedScheduledCollection) {
      const leader = second || first
      const timer = leader.intervals.find((entry) => entry.delay === 300_000 && !entry.canceled)
      leader.nativeFetchCalls.length = 0
      const schedulerEventId = leader.peekNextUuid()
      attempted.add(schedulerEventId)
      timer.callback()
      await leader.flush()
      resumedScheduledCollection = leader.nativeFetchCalls.length > 0
      for (const record of await (second ? secondStore : firstStore).snapshot()) offered.add(record.payload.event_id)
      assert.equal(offered.has(schedulerEventId), true)
    }
    await settleStarts()
    sawReduced ||= core.effectiveRateLimit(sharedStorage.get('lifeDataRateState') || {}, now, 2) === 20
    now += 60_000
    await runTimers(first)
    await runTimers(second)
  }
  for (let drain = 0; drain < 24 && Number((sharedStorage.get('lifeDataQueue:meta') || {}).count || 0) > 0; drain += 1) {
    await settleStarts()
    now += 60 * 60_000
    await runTimers(first)
    await runTimers(second)
  }
  await settleStarts()

  assert.ok(starts.some((start) => start.limit === 20))
  assert.ok(starts.some((start) => start.limit === 40))
  assert.equal(activeOwners.size, 0)
  assert.equal(maxPermits, 2)
  assert.equal(sawReduced, true)
  assert.equal(sawHighWater, true)
  assert.equal(sawLowWaterRecovery, true)
  assert.equal(resumedScheduledCollection, true)
  assert.equal((sharedStorage.get('lifeDataQueue:meta') || {}).count, 0)
  assert.ok((sharedStorage.get('lifeDataQueue:meta').dedupe || []).length <= 500)
  assert.deepEqual([...succeeded].sort(), [...attempted].sort())
  assert.equal([...offered].every((eventId) => attempted.has(eventId)), true)
  assert.equal(sharedStorage.get('lifeDataRateState').reducedMode, false)
})

test('worker timeout clears its 30-second claim and retains one retry entry', async () => {
  const payload = { schema_version: '1.0', event_id: 'timeout-event', account_id: ACCOUNT_ID, page_path: '/summary', endpoint: '/api/dito/query', queue_depth: 0, request_payload: {}, response_payload: { code: 0 }, captured_at: '2026-07-12T00:00:00Z' }
  const harness = createHarness({ ready: true, storage: [['lifeDataQueue', [{ payload, attempt: 0, nextAttemptAt: 0 }]]], gmResponder(request) { return request.url.endsWith('/ingest') ? { type: 'timeout' } : { status: 200, body: { success: true, code: 200 } } } })
  await waitFor(() => ingestRequests(harness).length === 1, 'timeout upload missing')
  await harness.flush()
  const queue = harness.storage.get('lifeDataQueue')
  assert.equal(queue.length, 1)
  assert.equal(queue[0].attempt, 1)
  assert.equal(queue[0].claimedBy, undefined)
  assert.equal(queue[0].claimExpiresAt, undefined)
})

test('durably queued video pages keep collection healthy while upload health remains visible', async () => {
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
  harness.timeouts.find((entry) => entry.callback.name === 'initialCollectionCallback').callback()
  await waitFor(
    () => (harness.storage.get('lifeDataQueue') || []).length === 2,
    'expected both video pages in retry queue',
  )

  const statusTimer = harness.intervals.find((entry) => entry.delay === 60_000)
  statusTimer.callback()
  await harness.flush()
  const latest = JSON.parse(statusRequests(harness).at(-1).data)
  assert.equal(latest.groups.video.status, 'healthy')
  assert.match(harness.panelText('.error'), /队列|重试/)
})

test('persisted video template cannot replay before the 30-second startup gate', async () => {
  const learner = createHarness({
    ready: true,
    storage: [['lifeDataLeader', { tabId: 'other-tab', expiresAt: Date.now() + 60_000 }]],
  })
  observeXhr(learner, videoRequest(), videoResponse([{ item_id: 'persisted', item_play_cnt: 1 }], 1))
  await learner.flush()
  const templates = structuredClone(learner.storage.get('lifeDataTemplates'))
  const headers = structuredClone(learner.storage.get('lifeDataSessionHeaders'))
  const harness = createHarness({
    ready: true,
    storage: [
      ['lifeDataTemplates', templates],
      ['lifeDataSessionHeaders', headers],
    ],
    fetchResponse(url) { return jsonResponse(videoResponse([{ item_id: 'replayed', item_play_cnt: 2 }], 1), String(url)) },
  })
  await harness.flush()
  assert.equal(harness.nativeFetchCalls.length, 0)
  const startup = harness.timeouts.find((entry) => entry.callback.name === 'initialCollectionCallback')
  assert.ok(startup)
  startup.callback()
  await waitFor(() => harness.nativeFetchCalls.length >= 1, 'startup-gated persisted template did not replay')
})

test('a newly observed video template triggers only after startup gate is ready', async () => {
  const harness = createHarness({
    ready: true,
    fetchResponse(url) { return jsonResponse(videoResponse([{ item_id: 'fresh-replay', item_play_cnt: 2 }], 1), String(url)) },
  })
  const startup = harness.timeouts.find((entry) => entry.callback.name === 'initialCollectionCallback')
  startup.callback()
  await harness.flush()
  assert.equal(harness.nativeFetchCalls.length, 0)
  observeXhr(harness, videoRequest(), videoResponse([{ item_id: 'fresh-template', item_play_cnt: 1 }], 1))
  await waitFor(() => harness.nativeFetchCalls.length >= 1, 'post-gate fresh template did not trigger')
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
    (entry) => entry.delay === 3_600_000,
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

test('a 403 replay invalidates the template and later runs skip it', async () => {
  const harness = createHarness({
    ready: true,
    fetchResponse(url) {
      return {
        ...jsonResponse({ code: 403 }, String(url)),
        ok: false,
        status: 403,
      }
    },
  })

  observeXhr(
    harness,
    summaryRequest(),
    { code: 0, data: { contentSummary: { play_count: 10 } } },
  )
  await harness.flush()
  const replayTimer = harness.intervals.find(
    (entry) => entry.delay === 3_600_000,
  )
  assert.ok(replayTimer)

  replayTimer.callback()
  await waitFor(
    () => Object.values(harness.storage.get('lifeDataTemplates') || {})[0]?.valid === false,
    '403 template was not invalidated',
  )
  replayTimer.callback()
  await harness.flush()

  assert.equal(harness.nativeFetchCalls.length, 1)
  assert.match(harness.panelText('.error'), /模板已失效|403/)
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
  await waitFor(() => harness.timeouts.some(
    (entry) => entry.delay === 30_000 && entry.callback.name !== 'initialCollectionCallback',
  ), 'debounced status error was not scheduled after async digest')
  assert.equal(
    harness.timeouts.filter((entry) => entry.delay === 30_000 && entry.callback.name !== 'initialCollectionCallback').length,
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
    (entry) => entry.delay === 30_000 && !entry.canceled && entry.callback.name !== 'initialCollectionCallback',
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
test('nonleader learns and queues other captures while the leader replays once', async () => {
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
  await waitFor(() => (sharedStorage.get('lifeDataQueue') || []).length === 1,
    'nonleader capture was not queued after async digest')
  assert.equal(ingestRequests(follower).length, 0)
  assert.equal((sharedStorage.get('lifeDataQueue') || []).length, 1)

  const replayTimer = leader.intervals.find(
    (entry) => entry.delay === 3_600_000,
  )
  assert.ok(replayTimer)
  replayTimer.callback()
  await waitFor(
    () => ingestRequests(leader).length === 1,
    'leader did not replay the shared other template',
  )
  assert.equal(ingestRequests(leader).length, 1)
})

test('worker pool bounds concurrency, spaces starts, and does not let one hanging item block others', async () => {
  let now = 0
  let active = 0
  let maximumActive = 0
  const starts = []
  const releases = new Map()
  const wait = async (delay) => { now += delay }
  const worker = (item) => {
    starts.push(now)
    active += 1
    maximumActive = Math.max(maximumActive, active)
    return new Promise((resolve) => releases.set(item, () => {
      active -= 1
      resolve(item)
    }))
  }

  const pending = core.runWorkerPool([0, 1, 2, 3], {
    concurrency: 3,
    startGapMs: 1_000,
    worker,
    now: () => now,
    wait,
  })
  await new Promise((resolve) => setImmediate(resolve))
  assert.deepEqual(starts, [0, 1_000, 2_000])
  assert.equal(maximumActive, 3)
  releases.get(1)()
  await new Promise((resolve) => setImmediate(resolve))
  assert.deepEqual(starts, [0, 1_000, 2_000, 3_000])
  releases.get(2)()
  releases.get(3)()
  releases.get(0)()
  assert.deepEqual((await pending).map((result) => result.value), [0, 1, 2, 3])
  assert.ok(starts.slice(1).every((value, index) => value - starts[index] >= 1_000))
})

test('only the leader schedules delayed dual-frequency automatic collection', () => {
  const sharedStorage = new Map([['lifeDataCollectorToken', 'collector-token']])
  const leader = createHarness({ ready: true, sharedStorage, tabId: 'timer-leader' })
  const follower = createHarness({ ready: true, sharedStorage, tabId: 'timer-follower' })

  assert.ok(leader.timeouts.some((entry) => entry.delay === 30_000))
  assert.ok(leader.intervals.some((entry) => entry.delay === 300_000))
  assert.ok(leader.intervals.some((entry) => entry.delay === 3_600_000))
  assert.equal(follower.timeouts.some((entry) => entry.delay === 30_000), false)
  assert.equal(follower.intervals.some((entry) => entry.delay === 300_000), false)
  assert.equal(follower.intervals.some((entry) => entry.delay === 3_600_000), false)
})

test('panel renders next runs, selected/skipped, invalid templates and reduced-rate drain estimate', () => {
  const queue = Array.from({ length: 40 }, (_, index) => ({
    payload: { event_id: `panel-${index}` }, attempt: 0, nextAttemptAt: Date.now() + 60_000,
  }))
  const harness = createHarness({
    ready: true,
    storage: [
      ['lifeDataTemplates', {
        valid: { valid: true },
        invalid: { valid: false },
      }],
      ['lifeDataRateState', { reducedMode: true }],
      ['lifeDataQueue', queue],
    ],
    queueStore: core.createMemoryQueueStore(queue),
  })

  assert.notEqual(harness.panelText('.next-video'), '—')
  assert.notEqual(harness.panelText('.next-core'), '—')
  assert.equal(harness.panelText('.template-selection'), '0/0')
  assert.equal(harness.panelText('.invalid-templates'), '1')
  assert.match(harness.panelText('.queue-drain'), /2.*分钟/)
})

test('core scheduler settles business before advertising and advertising before other', async () => {
  const starts = []
  const releases = new Map()
  const template = (name, group, canonicalFields) => ({
    endpoint: '/api/dito/query',
    pagePath: group === 'business'
      ? '/dito/pc/business/page'
      : group === 'advertising'
        ? '/dito/pc/ad/analysis'
        : `/test/${name}`,
    group,
    valid: true,
    learnedAt: Date.now(),
    canonicalFields,
    requestPayload: {
      path: `/test/${name}`,
      groupid: ACCOUNT_ID,
      name,
    },
    headers: {
      'x-tt-ls-session-id': 'session-secret',
      'root-life-account-id': LIFE_ACCOUNT_ID,
      'life-account-id': LIFE_ACCOUNT_ID,
    },
  })
  const templates = {
    businessPay: template('business-pay', 'business', ['pay_gmv_fen']),
    businessVerified: template('business-verified', 'business', ['verified_gmv_fen', 'stat_date']),
    advertisingSpend: template('advertising-spend', 'advertising', ['spend_fen']),
    advertisingOrders: template('advertising-orders', 'advertising', ['ad_orders', 'ad_pay_gmv_fen']),
    otherPlays: template('other-plays', 'other', ['plays']),
  }
  const harness = createHarness({
    ready: true,
    storage: [
      ['lifeDataTemplates', templates],
      ['lifeDataSessionHeaders', {
        'x-tt-ls-session-id': 'session-secret',
        'root-life-account-id': LIFE_ACCOUNT_ID,
        'life-account-id': LIFE_ACCOUNT_ID,
      }],
    ],
    fetchResponse(_url, init) {
      const name = JSON.parse(init.body).name
      starts.push(name)
      return new Promise((resolve) => releases.set(name, () => resolve(jsonResponse({
        code: 0,
        data: name.startsWith('business')
          ? { pay_gmv: 1, verify_gmv: 1 }
          : name.startsWith('advertising')
            ? { total_ad_cost: 1, order_cnt: 1, ad_pay_gmv: 1 }
            : { play_count: 1 },
      }, DITO_URL))))
    },
  })
  const replayTimer = harness.intervals.find((entry) => entry.delay === 3_600_000)
  replayTimer.callback()
  await waitFor(() => starts.length > 0, 'core collection did not start')
  assert.equal(starts.length, 1)
  assert.ok(starts[0].startsWith('business'))
  const firstGap = harness.timeouts.find(
    (entry) => entry.delay > 0 && entry.delay <= 1_000 && !entry.canceled,
  )
  firstGap.canceled = true
  firstGap.callback()
  await harness.flush()
  assert.equal(starts.length, 2)
  assert.ok(starts.every((name) => name.startsWith('business')))
  const secondGap = harness.timeouts.find(
    (entry) => entry.delay > 0 && entry.delay <= 1_000 && !entry.canceled,
  )
  if (secondGap) {
    secondGap.canceled = true
    secondGap.callback()
    await harness.flush()
  }
  assert.equal(starts.some((name) => name.startsWith('advertising')), false)
  releases.get('business-pay')()
  releases.get('business-verified')()
  await harness.flush()
  const advertisingStageGap = harness.timeouts.find(
    (entry) => entry.delay > 0 && entry.delay <= 1_000 && !entry.canceled,
  )
  advertisingStageGap.canceled = true
  advertisingStageGap.callback()
  await harness.flush()
  assert.ok(starts.some((name) => name.startsWith('advertising')))
  assert.equal(starts.includes('other-plays'), false)
  const advertisingStartGap = harness.timeouts.find(
    (entry) => entry.delay > 0 && entry.delay <= 1_000 && !entry.canceled,
  )
  advertisingStartGap.canceled = true
  advertisingStartGap.callback()
  await harness.flush()
  assert.equal(starts.filter((name) => name.startsWith('advertising')).length, 2)
  releases.get('advertising-spend')()
  releases.get('advertising-orders')()
  await harness.flush()
  assert.equal(starts.includes('other-plays'), false)
  const otherStageGap = harness.timeouts.find(
    (entry) => entry.delay > 0 && entry.delay <= 1_000 && !entry.canceled,
  )
  otherStageGap.canceled = true
  otherStageGap.callback()
  await waitFor(() => starts.includes('other-plays'), 'other stage did not start')
  releases.get('other-plays')()
  await harness.flush()
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
  harness.timeouts.find((entry) => entry.callback.name === 'initialCollectionCallback').callback()
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
  await waitFor(() => controller.pendingCount() === 20 && ingestRequests(harness).length === 1,
    'observed responses did not settle after async digest')

  assert.equal(controller.pendingCount(), 20)
  assert.equal(ingestRequests(harness).length, 1)
  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 0)
  assert.equal(JSON.parse(ingestRequests(harness)[0].data).event_id.length > 0, true)
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
    (entry) => entry.delay === 30_000 && !entry.canceled && entry.callback.name !== 'initialCollectionCallback',
  )
  assert.ok(lockTimeout)
  lockTimeout.callback()
  await waitFor(() => ingestRequests(harness).length === 1, 'timed-out observed payload was not uploaded from the queue')

  assert.equal(controller.pendingCount(), 0)
  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 0)
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

test('busy startup lock leaves a new video template retryable after the startup gate', async () => {
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
  const startup = harness.timeouts.find((entry) => entry.callback.name === 'initialCollectionCallback')
  assert.ok(startup)
  startup.callback()
  await waitFor(
    () => ingestRequests(harness).length === 1,
    'startup gate did not retry the untriggered video template',
  )
  const maintenance = harness.intervals.find((entry) => entry.delay === 10_000)
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

  assert.equal(ingestRequests(harness).length, 1)
  assert.equal((harness.storage.get('lifeDataQueue') || []).length, 0)
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
  await waitFor(() => ingestRequests(fallback).length === 1, 'fallback event was not uploaded through the shared queue')

  ingestRequests(leader)[0].onload({
    status: 200,
    responseText: JSON.stringify({ success: true, code: 200 }),
  })
  await waitFor(
    () =>
      (sharedStorage.get('lifeDataQueue') || []).length === 0,
    'flush lost fallback event or resurrected old event',
  )

  const finalQueue = sharedStorage.get('lifeDataQueue')
  assert.equal(finalQueue.length, 0)
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

test('successful XHR learns bounded canonical capability metadata', async () => {
  const harness = createHarness()
  observeXhr(harness, summaryRequest(), {
    code: 0,
    data: { summary: { verify_gmv: 123, refund_gmv: 4, stat_date: '2026-07-13' } },
  })
  await harness.flush()

  const [template] = Object.values(harness.storage.get('lifeDataTemplates') || {})
  assert.deepEqual(template.canonicalFields, ['refund_gmv_fen', 'stat_date', 'verified_gmv_fen'])
  assert.deepEqual(Object.keys(template.fieldSamplePaths), template.canonicalFields)
  assert.match(template.lastSuccessfulAt, /^\d{4}-\d{2}-\d{2}T/)
})

test('successful fetch learns capabilities without persisting body or sensitive headers', async () => {
  const secret = 'do-not-store-this-secret'
  const harness = createHarness({
    fetchResponse(url) {
      return jsonResponse({ code: 0, data: { metrics: { total_ad_cost: 88, order_cnt: 2 } } }, String(url))
    },
  })
  await harness.page.fetch(DITO_URL, {
    method: 'POST',
    headers: {
      Authorization: secret,
      Cookie: secret,
      'X-TT-LS-Session-ID': secret,
      'Root-Life-Account-ID': LIFE_ACCOUNT_ID,
      'Life-Account-ID': LIFE_ACCOUNT_ID,
    },
    body: JSON.stringify(summaryRequest()),
  })
  await harness.flush()

  const serialized = JSON.stringify(harness.storage.get('lifeDataTemplates')).toLowerCase()
  assert.match(serialized, /canonicalfields/)
  assert.match(serialized, /spend_fen/)
  assert.doesNotMatch(serialized, /do-not-store-this-secret|authorization|cookie|response_payload|responsebody/)
})

test('equivalent successful templates union capability metadata and sample paths', async () => {
  const harness = createHarness()
  observeXhr(harness, summaryRequest(), { code: 0, data: { pay_gmv: 10 } })
  await harness.flush()
  observeXhr(harness, summaryRequest(), {
    code: 0,
    data: { nested: { pay_gmv: 12 }, refund_gmv: 3 },
  })
  await harness.flush()
  const templates = Object.values(harness.storage.get('lifeDataTemplates') || {})
  assert.equal(templates.length, 1)
  assert.deepEqual(templates[0].canonicalFields, ['pay_gmv_fen', 'refund_gmv_fen'])
  assert.deepEqual(templates[0].fieldSamplePaths.pay_gmv_fen, [
    '$.data.pay_gmv',
    '$.data.nested.pay_gmv',
  ])
  assert.deepEqual(templates[0].fieldSamplePaths.refund_gmv_fen, [
    '$.data.refund_gmv',
  ])
})

test('failed and empty responses do not erase the last valid template', async () => {
  const harness = createHarness()
  observeXhr(harness, summaryRequest(), { code: 0, data: { pay_gmv: 10 } })
  await harness.flush()
  const before = structuredClone(harness.storage.get('lifeDataTemplates'))
  observeXhr(harness, summaryRequest(), { code: 1, data: { refund_gmv: 3 } })
  observeXhr(harness, summaryRequest(), { code: 0, data: {} })
  await harness.flush()
  assert.deepEqual(harness.storage.get('lifeDataTemplates'), before)
})

test('successful other response without canonical fields preserves capability timestamp', async () => {
  const harness = createHarness()
  observeXhr(harness, summaryRequest(), { code: 0, data: { pay_gmv: 10 } })
  await harness.flush()
  const before = structuredClone(harness.storage.get('lifeDataTemplates'))
  observeXhr(harness, summaryRequest(), {
    code: 0,
    data: { contentSummary: { unknown_business_value: 99 } },
  })
  await harness.flush()
  const [beforeTemplate] = Object.values(before)
  const [afterTemplate] = Object.values(harness.storage.get('lifeDataTemplates'))
  assert.deepEqual(afterTemplate.canonicalFields, beforeTemplate.canonicalFields)
  assert.deepEqual(afterTemplate.fieldSamplePaths, beforeTemplate.fieldSamplePaths)
  assert.equal(afterTemplate.lastSuccessfulAt, beforeTemplate.lastSuccessfulAt)
})

test('first capability-less other template may persist without claiming field success', async () => {
  const harness = createHarness()
  observeXhr(harness, summaryRequest(), {
    code: 0,
    data: { contentSummary: { unknown_business_value: 99 } },
  })
  await harness.flush()
  const [template] = Object.values(harness.storage.get('lifeDataTemplates') || {})
  assert.ok(template)
  assert.deepEqual(template.canonicalFields, [])
  assert.deepEqual(template.fieldSamplePaths, {})
  assert.equal(Object.hasOwn(template, 'lastSuccessfulAt'), false)
})

test('missing field guidance maps every planned page and module', () => {
  const registry = {
    one: { canonicalFields: ['plays'] },
  }
  const guidance = core.missingFieldGuidance(registry)
  const byField = Object.fromEntries(guidance.map((item) => [item.field, item]))
  assert.match(`${byField.video_id.page} ${byField.video_id.module}`, /视频详情.*交易明细|交易明细.*视频详情/)
  assert.match(`${byField.spend_fen.page} ${byField.spend_fen.module}`, /投放.*广告分析/)
  assert.match(`${byField.ad_orders.page} ${byField.ad_orders.module}`, /投放.*广告分析/)
  assert.match(`${byField.pay_gmv_fen.page} ${byField.pay_gmv_fen.module}`, /经营.*经营概览/)
  assert.match(`${byField.verified_gmv_fen.page} ${byField.verified_gmv_fen.module}`, /经营.*经营概览/)
  assert.match(`${byField.refund_gmv_fen.page} ${byField.refund_gmv_fen.module}`, /经营.*经营概览/)
  assert.match(`${byField.audience_age.page} ${byField.audience_age.module}`, /人群分析/)
  assert.match(`${byField.audience_gender.page} ${byField.audience_gender.module}`, /人群分析/)
  assert.match(`${byField.region.page} ${byField.region.module}`, /地域分析/)
  assert.match(`${byField.hour.page} ${byField.hour.module}`, /时间趋势/)
  for (const field of ['campaign_id', 'plan_id', 'creative_id', 'store_id', 'stat_date']) {
    assert.ok(byField[field], `missing guidance for ${field}`)
  }
  assert.equal(byField.plays, undefined)
})

test('panel shows no more than five missing fields without navigation or server replay', () => {
  const harness = createHarness({ ready: true })
  const text = harness.panelText('.missing-fields')
  assert.match(text, /缺少|请打开|刷新/)
  assert.equal((text.match(/、/g) || []).length <= 4, true)
  assert.equal(harness.page.location.pathname, '/flow/content/analysis/video')
  assert.equal(harness.gmRequests.some((request) => /replay/i.test(request.url)), false)
  assert.equal(harness.nativeFetchCalls.length, 0)
})

test('panel five-item cap never hides mandatory fields behind optional gaps', () => {
  const harness = createHarness({ ready: true })
  const text = harness.panelText('.missing-fields')

  for (const field of ['spend_fen', 'verified_gmv_fen', 'stat_date']) {
    assert.match(text, new RegExp(field))
  }
  assert.equal((text.match(/、/g) || []).length <= 4, true)
})

test('panel marks optional gaps separately after mandatory fields are covered', () => {
  const harness = createHarness({
    ready: true,
    storage: [[
      'lifeDataTemplates',
      { mandatory: { canonicalFields: ['spend_fen', 'verified_gmv_fen', 'stat_date'] } },
    ]],
  })
  const text = harness.panelText('.missing-fields')

  assert.match(text, /必需字段已覆盖/)
  assert.match(text, /可选维度待补/)
  assert.doesNotMatch(text, /必需字段.*缺|缺少必需/)
})
