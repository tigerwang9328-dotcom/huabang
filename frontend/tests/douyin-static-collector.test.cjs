"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

const script = fs.readFileSync(
  path.resolve(__dirname, "..", "..", "tools", "douyin-color-analytics-collector.user.js"),
  "utf8",
);

test("collector has fixed catalog and semantic curve endpoints", () => {
  assert.ok(script.includes("const CATALOG_ENDPOINT = '/web/api/creator/item/list';"));
  assert.ok(script.includes("const CURVE_ENDPOINT = '/janus/douyin/creator/data/realtime/analysis/data_center';"));
  assert.ok(script.includes("function fixedCatalogUrl()"));
  assert.ok(script.includes("function fixedCurveUrl(videoId, creatorId, analysisType)"));
  assert.ok(script.includes("url.searchParams.set('item_id', String(videoId));"));
  assert.ok(script.includes("url.searchParams.set('user_id', String(creatorId));"));
  assert.ok(script.includes("url.searchParams.set('analysis_type', String(analysisType));"));
  assert.ok(script.includes("for (const analysisType of [1, 7])"));
});

test("fixed collection does not require learned requests or relabel metrics trend data", () => {
  assert.ok(!script.includes("if (!learnedCurveRequest) return;"));
  assert.ok(!script.includes("if (!learnedCatalogRequest) return;"));
  assert.ok(!script.includes("trend_map"));
  assert.ok(!script.includes("learnedCurveRequest = rawUrl"));
  assert.ok(!script.includes("learnedCatalogRequest"));
  assert.ok(script.includes("let url = fixedCatalogUrl();"));
  assert.ok(script.includes("const url = fixedCurveUrl(item.video_id, creatorId, analysisType);"));
  assert.ok(script.includes("const record = recordFromAnalysis(await response.clone().json(), analysisType, item.video_id);"));
  assert.match(script, /if \(record\) \{ await enqueue\(record\); continue; \}/);
  assert.ok(script.includes("async function startFixedCollection()"));
  assert.ok(script.includes("void startFixedCollection();"));
});

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, clone: () => response(body, status), json: async () => structuredClone(body) };
}

function createHarness(options = {}) {
  const storage = new Map();
  const gmStorage = new Map();
  const intervals = [];
  let catalogFailures = options.catalogFailures || 0;
  const page = {
    __huabangDouyinColorV31TestApi: true,
    fetch: async (rawUrl) => {
      const url = new URL(rawUrl);
      if (url.pathname === "/web/api/creator/item/list") {
        if (catalogFailures > 0) { catalogFailures -= 1; return response({}, 503); }
        return response({ items: [{ item_id: "video", author_user_id: "creator", statistics: { play_count: 2000 }, type: 0 }], has_more: false });
      }
      if (url.pathname === "/janus/douyin/creator/data/realtime/analysis/data_center") {
        return response({ status_code: 0, analysis_trend: { current_item: [{ key: "00:00", value: 1 }] } });
      }
      throw new Error(`unexpected path ${url.pathname}`);
    },
    XMLHttpRequest: class { open() {} addEventListener() {} },
  };
  const indexedDB = {
    open() {
      const request = {};
      const db = { transaction: () => ({ objectStore: () => ({
        get: (key) => {
          const result = {};
          queueMicrotask(() => { result.result = storage.get(key); result.onsuccess(); });
          return result;
        },
        put: (value, key) => {
          const result = {};
          queueMicrotask(() => { storage.set(key, structuredClone(value)); result.onsuccess(); });
          return result;
        },
      }) }) };
      queueMicrotask(() => { request.result = db; request.onsuccess(); });
      return request;
    },
  };
  const listeners = new Map();
  const sandbox = {
    unsafeWindow: page,
    fetch: page.fetch,
    document: { visibilityState: "visible", addEventListener: (name, fn) => listeners.set(name, fn) },
    window: { addEventListener: (name, fn) => listeners.set(name, fn) },
    navigator: { locks: { request: async (_name, fn) => fn() } },
    location: { origin: "https://creator.douyin.com", pathname: "/creator-micro/data-center/content" },
    indexedDB,
    crypto: webcrypto,
    GM_getValue: (key) => gmStorage.get(key),
    GM_setValue: (key, value) => gmStorage.set(key, value),
    GM_registerMenuCommand: () => undefined,
    GM_xmlhttpRequest: () => undefined,
    setInterval: (callback, delay) => { intervals.push({ callback, delay }); return intervals.length; },
    setTimeout,
    console,
    URL,
    Response,
    Blob,
    TextEncoder,
    structuredClone,
    queueMicrotask,
  };
  const marker = "  observePageRequests(); registerMenus(); void loadSavedConfig();";
  const testScript = script.replace(marker, `
    PAGE_WINDOW.__huabangDouyinColorV31TestApi = {
      fixedCatalogUrl, fixedCurveUrl, recordFromAnalysis, collectCatalogPages,
      collectCatalogCurves, startFixedCollection, runScheduledCollection, queueState, captureCatalog,
      setRuntimeConfig: (value) => { runtimeConfig = value; },
      getRuntimeConfig: () => structuredClone(runtimeConfig),
      getSavedRuntimeConfig: () => GM_getValue(CONFIG_STORAGE_KEY),
    };
    uploadPending = async () => {};
  `);
  assert.notEqual(testScript, script, "test injection marker must remain in the userscript");
  vm.runInNewContext(testScript, sandbox, { filename: "collector.user.js" });
  return { api: page.__huabangDouyinColorV31TestApi, intervals };
}

test("automatic fixed collection enqueues retention and bounce without observed page requests", async () => {
  const { api } = createHarness();
  api.setRuntimeConfig({ uploadToken: "test", observedCreatorId: "creator", max_local_bytes: 1024 * 1024, max_local_batches: 10 });
  await api.startFixedCollection();
  const queue = await api.queueState();
  const records = queue.batches.flatMap((batch) => batch.records.map((item) => item.record));
  assert.deepEqual(records.map((item) => item.analysis_type).sort(), [1, 7]);
  assert.ok(records.every((item) => item.analysis_trend.current_item.length === 1));
});

test("catalog-based creator discovery persists the id before collection retries", async () => {
  const { api } = createHarness();
  api.setRuntimeConfig({ uploadToken: "test", observedCreatorId: "", observedAccountName: "", max_local_bytes: 1024 * 1024, max_local_batches: 10 });

  await api.captureCatalog({
    items: [{ item_id: "video", author_user_id: "creator", author: { nickname: "华邦" }, statistics: { play_count: 2000 }, type: 0 }],
    has_more: false,
  });

  assert.equal(api.getRuntimeConfig().observedCreatorId, "creator");
  assert.equal(JSON.parse(api.getSavedRuntimeConfig()).observedCreatorId, "creator");
});

test("trend map data is never relabeled as a curve", () => {
  const { api } = createHarness();
  assert.equal(api.recordFromAnalysis({ trend_map: { metric: { 0: [{ date_time: "00:00", value: 1 }] } } }, 1, "video"), null);
});

test("periodic collector retry recovers after initial catalog failures", async () => {
  const { api, intervals } = createHarness({ catalogFailures: 1 });
  api.setRuntimeConfig({ uploadToken: "test", observedCreatorId: "creator", max_local_bytes: 1024 * 1024, max_local_batches: 10 });
  await api.startFixedCollection();
  assert.equal((await api.queueState()).batches.length, 0);
  assert.ok(intervals.some((entry) => entry.delay === 5 * 60 * 1000), "collector retry interval must be registered");
  await api.runScheduledCollection();
  const records = (await api.queueState()).batches.flatMap((batch) => batch.records.map((item) => item.record));
  assert.deepEqual(records.map((item) => item.analysis_type).sort(), [1, 7]);
});
