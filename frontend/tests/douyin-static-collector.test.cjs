"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

const localCollector = path.resolve(__dirname, "douyin-color-analytics-collector.user.js");
const canonicalCollector = path.resolve(__dirname, "..", "..", "tools", "douyin-color-analytics-collector.user.js");
const script = fs.readFileSync(fs.existsSync(localCollector) ? localCollector : canonicalCollector, "utf8");

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
  assert.match(script, /if \(record\) \{ analyses\[analysisType\] = record; continue; \}/);
  assert.match(script, /retention: analyses\[1\],/);
  assert.match(script, /platform_bounce: analyses\[7\],/);
  assert.ok(script.includes("async function startFixedCollection()"));
  assert.ok(script.includes("void startFixedCollection();"));
});

test("saved collector configuration reports and flushes pending work before a long backfill", () => {
  const start = script.indexOf("async function startFixedCollection()");
  const end = script.indexOf("async function runScheduledCollection()", start);
  const body = script.slice(start, end);
  assert.match(body, /await heartbeat\('online_active'\);/);
  assert.match(body, /await uploadPending\(\);/);
  assert.ok(
    body.indexOf("await uploadPending();") < body.indexOf("await collectCatalogPages();"),
    "existing queued batches must upload before the catalog/curve backfill begins",
  );
});

test("scheduled collection uploads first and starts a single collection when an hourly window is claimed", () => {
  const heartbeatStart = script.indexOf("async function heartbeat(status)");
  const recovery = script.slice(script.indexOf("async function recoverPending()"), heartbeatStart);
  const scheduled = script.slice(script.indexOf("async function runScheduledCollection()"), heartbeatStart);
  assert.match(recovery, /await heartbeat\('online_active'\);/);
  assert.match(recovery, /await uploadPending\(\);/);
  assert.doesNotMatch(recovery, /collectCatalogPages|collectCatalogCurves/);
  assert.match(scheduled, /await recoverPending\(\);/);
  assert.match(scheduled, /claimCollectionHour\(now\(\)\)/);
  assert.match(scheduled, /await startFixedCollection\(\);/);
});

test("saved configuration collects once for every page load, independent of script version", () => {
  const start = script.indexOf("async function loadSavedConfig()");
  const end = script.indexOf("function openQueueDb()", start);
  const body = script.slice(start, end);
  assert.match(body, /void startFixedCollection\(\);/);
  assert.doesNotMatch(body, /fullBackfillVersion/);
});

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, clone: () => response(body, status), json: async () => structuredClone(body) };
}

function createHarness(options = {}) {
  const storage = new Map();
  const gmStorage = new Map();
  const gmRequests = [];
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
  const document = { visibilityState: "visible", addEventListener: (name, fn) => listeners.set(name, fn) };
  const sandbox = {
    unsafeWindow: page,
    fetch: page.fetch,
    document,
    window: { addEventListener: (name, fn) => listeners.set(name, fn) },
    navigator: { locks: { request: async (_name, fn) => fn() } },
    location: { origin: "https://creator.douyin.com", pathname: "/creator-micro/data-center/content" },
    indexedDB,
    crypto: webcrypto,
    GM_getValue: (key) => gmStorage.get(key),
    GM_setValue: (key, value) => gmStorage.set(key, value),
    GM_registerMenuCommand: () => undefined,
    GM_xmlhttpRequest: (details) => {
      gmRequests.push(details);
      queueMicrotask(() => details.onload?.({ status: 200, responseText: "{}" }));
    },
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
      collectCatalogCurves, startFixedCollection, runScheduledCollection, recoverPending, queueState, captureCatalog, enqueueObservedAnalysis,
      claimCollectionHour: typeof claimCollectionHour === 'function' ? claimCollectionHour : null,
      setRuntimeConfig: (value) => { runtimeConfig = value; },
      setQueueState: async (value) => queueWrite(value),
      setPaused: (value) => { paused = value; },
      setPageVisibility: (value) => { document.visibilityState = value; },
      recoveryCalls: [],
      getRuntimeConfig: () => structuredClone(runtimeConfig),
      getSavedRuntimeConfig: () => GM_getValue(CONFIG_STORAGE_KEY),
    };
    // 启动路径会先发送心跳；该单元测试不连接管理后台，因此两种
    // 网络副作用都由桩替代，保留目录与曲线采集行为供断言。
    const realHeartbeat = heartbeat;
    PAGE_WINDOW.__huabangDouyinColorV31TestApi.heartbeat = realHeartbeat;
    heartbeat = async (status) => { PAGE_WINDOW.__huabangDouyinColorV31TestApi.recoveryCalls.push(['heartbeat', status]); };
    uploadPending = async () => { PAGE_WINDOW.__huabangDouyinColorV31TestApi.recoveryCalls.push(['upload']); };
  `);
  assert.notEqual(testScript, script, "test injection marker must remain in the userscript");
  vm.runInNewContext(testScript, sandbox, { filename: "collector.user.js" });
  return { api: page.__huabangDouyinColorV31TestApi, intervals, gmRequests };
}

test("heartbeat reports only unfinished local batches as pending", async () => {
  const { api, gmRequests } = createHarness();
  api.setRuntimeConfig({ uploadToken: "test", observedCreatorId: "creator", max_local_bytes: 1024 * 1024, max_local_batches: 10 });
  const completed = { id: "done", uploaded: true, status: "completed", records: [{ record: { video_id: "old" } }] };
  const pending = { id: "pending", uploaded: false, status: "receiving", records: [{ record: { video_id: "new" } }] };
  await api.setQueueState({ batches: [completed, pending] });
  await api.heartbeat("online_active");
  const request = gmRequests.find((entry) => entry.url.endsWith("/collector-heartbeats"));
  const payload = JSON.parse(request.data);
  assert.equal(payload.queued_batch_count, 1);
  assert.equal(payload.queued_bytes, new TextEncoder().encode(JSON.stringify({ batches: [pending] })).byteLength);
});

test("background recovery keeps heartbeat and uploads queued work without collecting catalog curves", async () => {
  const { api } = createHarness();
  api.setRuntimeConfig({ uploadToken: "test", observedCreatorId: "creator", max_local_bytes: 1024 * 1024, max_local_batches: 10 });
  api.setPageVisibility("hidden");

  await api.recoverPending();

  assert.equal(JSON.stringify(api.recoveryCalls), JSON.stringify([["heartbeat", "online_active"], ["upload"]]));
});

test("background collection is allowed and enqueues retention plus bounce", async () => {
  const { api } = createHarness();
  api.setRuntimeConfig({ uploadToken: "test", observedCreatorId: "creator", max_local_bytes: 1024 * 1024, max_local_batches: 10 });
  api.setPageVisibility("hidden");

  await api.startFixedCollection();

  const records = (await api.queueState()).batches.flatMap((batch) => batch.records.map((item) => item.record));
  assert.equal(records.length, 1);
  assert.equal(records[0].retention.analysis_type, 1);
  assert.equal(records[0].platform_bounce.analysis_type, 7);
});

test("hourly collection claim accepts the first run in an hour and rejects duplicates", () => {
  const { api } = createHarness();
  assert.equal(typeof api.claimCollectionHour, "function");
  assert.equal(api.claimCollectionHour(Date.UTC(2026, 7, 2, 14, 0, 0)), true);
  assert.equal(api.claimCollectionHour(Date.UTC(2026, 7, 2, 14, 59, 59)), false);
  assert.equal(api.claimCollectionHour(Date.UTC(2026, 7, 2, 15, 0, 0)), true);
});

test("automatic fixed collection enqueues retention and bounce without observed page requests", async () => {
  const { api } = createHarness();
  api.setRuntimeConfig({ uploadToken: "test", observedCreatorId: "creator", max_local_bytes: 1024 * 1024, max_local_batches: 10 });
  await api.startFixedCollection();
  const queue = await api.queueState();
  const records = queue.batches.flatMap((batch) => batch.records.map((item) => item.record));
  assert.equal(records.length, 1);
  assert.equal(records[0].source_type, "video");
  assert.equal(records[0].retention.analysis_type, 1);
  assert.equal(records[0].platform_bounce.analysis_type, 7);
  assert.ok(records.every((item) => item.retention.response_data.analysis_trend.current_item.length === 1));
  assert.ok(records.every((item) => item.platform_bounce.response_data.analysis_trend.current_item.length === 1));
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

test("catalog refresh backfills metadata missing from a previously cached video", async () => {
  const { api } = createHarness();
  api.setRuntimeConfig({ uploadToken: "test", observedCreatorId: "creator", observedAccountName: "华邦", max_local_bytes: 1024 * 1024, max_local_batches: 10 });
  await api.setQueueState({
    batches: [],
    catalogItems: [{ video_id: "video", item_status: "pending" }],
  });

  await api.captureCatalog({
    items: [{
      item_id: "video", author_user_id: "creator", desc: "补全后的标题", create_time: 1_700_000_000,
      duration: 12_345, statistics: { play_count: 2_000 }, type: 0,
    }],
    has_more: false,
  });

  const item = (await api.queueState()).catalogItems.find((entry) => entry.video_id === "video");
  assert.equal(item.sanitized_title, "补全后的标题");
  assert.equal(item.published_at_epoch_seconds, 1_700_000_000);
  assert.equal(item.duration_ms, 12_345);
});

test("observed retention and bounce responses are paired before upload", async () => {
  const { api } = createHarness();
  api.setRuntimeConfig({ uploadToken: "test", observedCreatorId: "creator", max_local_bytes: 1024 * 1024, max_local_batches: 10 });
  const retention = api.recordFromAnalysis({ status_code: 0, analysis_trend: { current_item: [{ key: "00:00", value: 1 }] } }, 1, "video");
  const bounce = api.recordFromAnalysis({ status_code: 0, analysis_trend: { current_item: [{ key: "00:00", value: 1 }] } }, 7, "video");
  await api.enqueueObservedAnalysis(retention);
  assert.equal((await api.queueState()).batches.length, 0);
  await api.enqueueObservedAnalysis(bounce);
  const records = (await api.queueState()).batches.flatMap((batch) => batch.records.map((item) => item.record));
  assert.equal(records.length, 1);
  assert.equal(records[0].retention.analysis_type, 1);
  assert.equal(records[0].platform_bounce.analysis_type, 7);
});

test("trend map data is never relabeled as a curve", () => {
  const { api } = createHarness();
  assert.equal(api.recordFromAnalysis({ trend_map: { metric: { 0: [{ date_time: "00:00", value: 1 }] } } }, 1, "video"), null);
});
