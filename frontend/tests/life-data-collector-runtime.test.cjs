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
  const storage = new Map([
    ...(options.withToken === false
      ? []
      : [['lifeDataCollectorToken', 'collector-token']]),
    ...(options.storage || []),
  ])
  const gmRequests = []
  const menus = new Map()
  const intervals = []
  const timeouts = []
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
      timeouts.push({ callback, delay })
      return timeouts.length
    },
    clearTimeout() {},
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

test('HTTP 200 business code 400 is permanent and never enters the queue', async () => {
  const harness = createHarness({
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