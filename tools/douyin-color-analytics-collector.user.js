// ==UserScript==
// @name         华邦抖音颜色分析采集器 v3.1
// @namespace    https://hbreare.com/
// @version      3.1.12
// @description  仅采集目录和留存/平台跳出曲线的白名单字段；不保存浏览器会话或签名参数。
// @match        https://creator.douyin.com/creator-micro/*
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        unsafeWindow
// @connect      hbreare.com
// @run-at       document-start
// ==/UserScript==

(function () {
  'use strict';
  const API_ORIGIN = 'https://hbreare.com';
  const API_PREFIX = '/api/v1/douyin-color-analytics';
  const SCRIPT_VERSION = '3.1.12';
  const SCHEMA_VERSION = 1;
  const DEFAULT_MAX_QUEUE_BYTES = 500 * 1024 * 1024;
  const DEFAULT_MAX_LOCAL_BATCHES = 100;
  const SENSITIVE_KEY = /(?:token|cookie|authorization|signature|captcha|query|url|hash)/i;
  const now = () => Date.now();
  let installationId = null;
  const PAGE_WINDOW = unsafeWindow;

  let runtimeConfig = null;
  let learnedCurveRequest = null;
  let learnedCatalogRequest = null;
  let paused = document.visibilityState !== 'visible';
  let lastWakeCheckAt = now();
  function openQueueDb() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('huabang_douyin_color_v31', 1);
      request.onupgradeneeded = () => request.result.createObjectStore('state');
      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);
    });
  }
  async function queueRead() {
    const db = await openQueueDb();
    return new Promise((resolve, reject) => { const request = db.transaction('state', 'readonly').objectStore('state').get('queue'); request.onsuccess = () => resolve(request.result || { batches: [] }); request.onerror = () => reject(request.error); });
  }
  async function queueWrite(value) {
    const db = await openQueueDb();
    return new Promise((resolve, reject) => { const request = db.transaction('state', 'readwrite').objectStore('state').put(value, 'queue'); request.onsuccess = () => resolve(); request.onerror = () => reject(request.error); });
  }
  async function ensureInstallationId() {
    if (installationId) return installationId;
    installationId = await navigator.locks.request('huabang-douyin-color-v31-queue-state', async () => {
      const state = await queueRead();
      const value = state.installationId || (crypto.randomUUID ? crypto.randomUUID().replaceAll('-', '') : String(now()));
      if (!state.installationId) { state.installationId = value; await queueWrite(state); }
      return value;
    });
    return installationId;
  }
  function safeClone(value) {
    if (Array.isArray(value)) return value.map(safeClone);
    if (!value || typeof value !== 'object') return value;
    return Object.fromEntries(Object.entries(value)
      .filter(([key]) => !SENSITIVE_KEY.test(key))
      .map(([key, item]) => [key, safeClone(item)]));
  }
  function hasSensitive(value) {
    if (Array.isArray(value)) return value.some(hasSensitive);
    return value && typeof value === 'object' && Object.entries(value).some(([key, item]) => SENSITIVE_KEY.test(key) || hasSensitive(item));
  }
  function bytes(value) { return new TextEncoder().encode(JSON.stringify(value)).byteLength; }
  function canonicalJson(value) {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  async function sha256(value) {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
    return [...new Uint8Array(digest)].map((item) => item.toString(16).padStart(2, '0')).join('');
  }
  async function gzip(value) {
    const stream = new Blob([JSON.stringify(value)]).stream().pipeThrough(new CompressionStream('gzip'));
    return new Response(stream).arrayBuffer();
  }
  function currentVideoId() {
    const match = location.pathname.match(/work-detail\/(\d+)/);
    return match ? match[1] : null;
  }
  function curve(points) {
    return Array.isArray(points) ? points.filter((item) => item && typeof item.key === 'string' && Number.isFinite(item.value))
      .map((item) => ({ key: item.key, value: item.value })) : [];
  }
  function guardObservedCreator(response) {
    const observed = response?.user_id || response?.data?.user_id || response?.data?.author?.user_id;
    if (!observed || !runtimeConfig?.observedCreatorId || String(observed) === runtimeConfig.observedCreatorId) return true;
    paused = true;
    runtimeConfig = null;
    console.warn('douyin-color-v31-status', 'account_switched');
    return false;
  }
  function stopForAuth() {
    paused = true;
    runtimeConfig = null;
    console.warn('douyin-color-v31-status', 'auth_required');
  }
  function recordFromAnalysis(response, analysisType, requestedVideoId) {
    if (hasSensitive(response) || !guardObservedCreator(response)) return null;
    const videoId = requestedVideoId || currentVideoId();
    const currentItem = curve(response?.analysis_trend?.current_item);
    if (!videoId || !currentItem.length || ![1, 7].includes(analysisType)) return null;
    const trend = { current_item: currentItem };
    const similar = curve(response?.analysis_trend?.similar_author);
    if (similar.length) trend.similar_author = similar;
    return {
      video_id: videoId, analysis_type: analysisType, http_status: 200,
      business_status_code: Number.isInteger(response.status_code) ? response.status_code : undefined,
      analysis_trend: trend,
    };
  }
  function catalogItemsFromResponse(response) {
    return Array.isArray(response?.items) ? response.items.map((item) => ({
      video_id: String(item.id), sanitized_title: typeof item.description === 'string' ? item.description.slice(0, 500) : undefined,
      published_at_epoch_seconds: Number.isInteger(item.create_time) ? item.create_time : undefined,
      duration_ms: Number.isInteger(item.video_info?.duration) ? item.video_info.duration : undefined,
      item_status: item.type === 4 ? 'pending' : 'skipped_non_video',
    })).map((item) => Object.fromEntries(Object.entries(item).filter(([, value]) => value !== undefined))) : [];
  }
  function observationWindow(publishedAtEpochSeconds) {
    if (!Number.isInteger(publishedAtEpochSeconds)) return null;
    const ageHours = (now() - publishedAtEpochSeconds * 1000) / 3600000;
    if (ageHours >= 36 && ageHours < 72) return 't2';
    if (ageHours >= 144 && ageHours < 216) return 't7';
    if (ageHours >= 672 && ageHours < 792) return 't30';
    return null;
  }
  async function queueState() { return queueRead(); }
  async function mutateQueue(mutator) {
    return navigator.locks.request('huabang-douyin-color-v31-queue-state', async () => {
      const state = await queueRead(); const result = await mutator(state);
      await queueWrite(state); return result;
    });
  }
  async function saveQueue(state) { await queueWrite(state); }
  async function enqueue(record) {
    await ensureInstallationId();
    const accepted = await mutateQueue((state) => {
      const maxQueueBytes = runtimeConfig?.max_local_bytes || DEFAULT_MAX_QUEUE_BYTES;
      const maxLocalBatches = runtimeConfig?.max_local_batches || DEFAULT_MAX_LOCAL_BATCHES;
      const incompleteBatches = state.batches.filter((item) => !item.uploaded);
      const receiving = incompleteBatches.find((item) => item.status === 'receiving');
      if (bytes(state) >= maxQueueBytes * 0.8 || (!receiving && incompleteBatches.length >= maxLocalBatches)) return false;
      const batch = receiving || {
        id: `v31-${now()}-${Math.random().toString(16).slice(2)}`, createdAt: now(), status: 'receiving', records: [], uploaded: false,
      };
      if (!state.batches.includes(batch)) state.batches.push(batch);
      const serializedRecord = JSON.stringify(record);
      if (!batch.records.some((item) => JSON.stringify(item.record) === serializedRecord)) batch.records.push({ record });
      return true;
    });
    if (!accepted) await heartbeat('upload_blocked');
  }
  async function captureCatalog(response, rawUrl) {
    if (rawUrl) learnedCatalogRequest = rawUrl;
    const catalogCreatorId = Array.isArray(response?.items) ? response.items.find((item) => item?.user_id)?.user_id : null;
    if (catalogCreatorId && !guardObservedCreator({ user_id: catalogCreatorId })) return;
    const items = catalogItemsFromResponse(response); if (!items.length) return;
    await mutateQueue((state) => {
      state.catalogItems = state.catalogItems || [];
      for (const item of items) if (!state.catalogItems.some((saved) => saved.video_id === item.video_id)) state.catalogItems.push(item);
    });
  }
  async function config() { return runtimeConfig; }
  function request(details) {
    return new Promise((resolve) => GM_xmlhttpRequest({ ...details, onload: resolve, onerror: () => resolve({ status: 0 }) }));
  }
  function versionAtLeast(actual, minimum) {
    const left = String(actual).split('.').map(Number); const right = String(minimum).split('.').map(Number);
    for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
      const delta = (left[index] || 0) - (right[index] || 0); if (delta) return delta > 0;
    }
    return true;
  }
  async function loadCollectorConfig(uploadToken) {
    const response = await scheduledRequest({ method: 'GET', url: `${API_ORIGIN}${API_PREFIX}/collector-config`, headers: { Authorization: `Bearer ${uploadToken}` } });
    if (response.status === 401 || response.status === 403) { stopForAuth(); return null; }
    if (!(response.status >= 200 && response.status < 300)) return null;
    try {
      const control = JSON.parse(response.responseText || '{}').data;
      if (control?.schema_version !== SCHEMA_VERSION || control?.collection_enabled !== true || !versionAtLeast(SCRIPT_VERSION, control?.minimum_script_version)) return null;
      if (!Number.isInteger(control?.max_part_uncompressed_bytes) || !Number.isInteger(control?.max_part_records) || !Number.isInteger(control?.max_local_batches) || !Number.isInteger(control?.max_local_bytes)) return null;
      return control;
    } catch (_) { return null; }
  }
  function splitUploadParts(records, maxBytes, maxRecords) {
    const parts = [[]];
    for (const record of records) {
      const candidate = [...parts.at(-1), record];
      if (parts.at(-1).length && (candidate.length > maxRecords || bytes({ records: candidate }) > maxBytes)) parts.push([record]); else parts[parts.length - 1] = candidate;
    }
    return parts;
  }
  async function serverMissingParts(clientBatchId, uploadToken) {
    const response = await scheduledRequest({ method: 'GET', url: `${API_ORIGIN}${API_PREFIX}/collection-batches/${encodeURIComponent(clientBatchId)}/missing-parts`, headers: { Authorization: `Bearer ${uploadToken}` } });
    if (response.status === 404) return null;
    if (!(response.status >= 200 && response.status < 300)) return undefined;
    try {
      const payload = JSON.parse(response.responseText || '{}');
      return Array.isArray(payload?.data?.missing_parts) ? payload.data.missing_parts.filter(Number.isInteger) : undefined;
    } catch (_) { return undefined; }
  }
  async function finalizeBatch(clientBatchId, uploadToken) {
    const response = await scheduledRequest({ method: 'POST', url: `${API_ORIGIN}${API_PREFIX}/collection-batches/${encodeURIComponent(clientBatchId)}/finalize`, headers: { Authorization: `Bearer ${uploadToken}` } });
    return response.status >= 200 && response.status < 300;
  }
  async function scheduledRequest(details) {
    if (paused || document.visibilityState !== 'visible') return { status: 0, paused: true };
    return navigator.locks.request('huabang-douyin-color-v31-network', async () => {
      const delay = await mutateQueue((state) => {
        const startAt = Math.max(now(), Number(state.nextRequestStartAt || 0));
        state.nextRequestStartAt = startAt + 1000; return startAt - now();
      });
      if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
      if (paused || document.visibilityState !== 'visible') return { status: 0, paused: true };
      return request(details);
    });
  }
  async function scheduledPageFetch(url) {
    if (paused || document.visibilityState !== 'visible') return null;
    return navigator.locks.request('huabang-douyin-color-v31-network', async () => {
      const delay = await mutateQueue((state) => {
        const startAt = Math.max(now(), Number(state.nextRequestStartAt || 0));
        state.nextRequestStartAt = startAt + 1000; return startAt - now();
      });
      if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
      if (paused || document.visibilityState !== 'visible') return null;
      return fetch(url);
    });
  }
  async function collectCatalogCurves({ onlyDueObservationWindows = false } = {}) {
    if (!learnedCurveRequest) return;
    const state = await queueState();
    for (const item of state.catalogItems || []) {
      if (onlyDueObservationWindows && !observationWindow(item.published_at_epoch_seconds)) continue;
      for (const analysisType of [1, 7]) {
      if (paused) return;
      const url = new URL(learnedCurveRequest, location.origin);
      url.searchParams.set('item_id', item.video_id); url.searchParams.set('analysis_type', String(analysisType));
      let response;
      for (let attempt = 0; attempt < 5; attempt += 1) {
        try { response = await scheduledPageFetch(url.toString()); } catch (_) { response = null; }
        if (response?.ok) break;
        if (response?.status === 401 || response?.status === 403) { paused = true; return; }
        if (attempt < 4) await new Promise((resolve) => setTimeout(resolve, Math.min(60000, 1000 * (2 ** attempt) + Math.floor(Math.random() * 501))));
      }
      if (!response?.ok) {
        await mutateQueue((current) => {
          current.curveFailures = current.curveFailures || [];
          current.curveFailures.push({ video_id: item.video_id, analysis_type: analysisType, attempts: 5, http_status: Number(response?.status || 0) });
        });
      }
      }
    }
  }
  async function collectCatalogPages() {
    if (!learnedCatalogRequest) return;
    let url = new URL(learnedCatalogRequest, location.origin);
    const seenCursors = new Set();
    for (let page = 0; page < 200 && !paused; page += 1) {
      const response = await scheduledPageFetch(url.toString());
      if (!response?.ok) return;
      const payload = await response.clone().json();
      await captureCatalog(payload);
      const cursor = String(payload?.max_cursor ?? '');
      if (!payload?.has_more || !cursor || seenCursors.has(cursor)) return;
      seenCursors.add(cursor); url.searchParams.set('max_cursor', cursor);
    }
  }
  async function heartbeat(status) {
    const settings = await config(); if (!settings?.uploadToken) return;
    const state = await queueState(); const stableInstallationId = await ensureInstallationId();
    await scheduledRequest({ method: 'POST', url: `${API_ORIGIN}${API_PREFIX}/collector-heartbeats`, headers: { Authorization: `Bearer ${settings.uploadToken}`, 'Content-Type': 'application/json' },
      data: JSON.stringify({ installation_id: stableInstallationId, script_version: SCRIPT_VERSION, schema_version: SCHEMA_VERSION, current_page_path: location.pathname, current_page_type: 'creator_page', document_visibility: document.visibilityState, queued_batch_count: state.batches.length, queued_bytes: bytes(state) }) });
    console.info('douyin-color-v31-status', status);
  }
  async function uploadPending() {
    const settings = await config(); if (!settings?.uploadToken) return;
    const stableInstallationId = await ensureInstallationId();
    const batches = await mutateQueue((state) => state.batches
      .filter((item) => !item.uploaded && (item.status === 'receiving' || item.status === 'uploading'))
      .map((item) => { item.status = 'uploading'; return structuredClone(item); }));
    for (const batch of batches) {
      const records = batch.records.map((item) => safeClone(item.record));
      if (hasSensitive(records)) continue;
      const parts = splitUploadParts(records, settings.max_part_uncompressed_bytes, settings.max_part_records);
      batch.uploadedParts = batch.uploadedParts || [];
      const missingParts = await serverMissingParts(batch.id, settings.uploadToken);
      if (Array.isArray(missingParts)) batch.uploadedParts = Array.from({ length: parts.length }, (_, index) => index + 1).filter((partNumber) => !missingParts.includes(partNumber));
      for (let index = 0; index < parts.length; index += 1) {
        if (batch.uploadedParts.includes(index + 1)) continue;
        const partRecords = parts[index];
        const envelope = { schema_version: SCHEMA_VERSION, client_batch_id: batch.id, script_version: SCRIPT_VERSION, created_at: new Date(batch.createdAt).toISOString(), installation_id: stableInstallationId, observed_creator_id: settings.observedCreatorId, part_number: index + 1, part_count: parts.length, records: partRecords };
        envelope.part_hash = await sha256(canonicalJson({ client_batch_id: envelope.client_batch_id, records: partRecords }));
        batch.failedParts = batch.failedParts || [];
        if (batch.failedParts.some((part) => part.part_number === index + 1)) continue;
        let response;
        for (let attempt = 0; attempt < 5; attempt += 1) {
          response = await scheduledRequest({ method: 'POST', url: `${API_ORIGIN}${API_PREFIX}/collection-batches/${encodeURIComponent(batch.id)}/parts`, headers: { Authorization: `Bearer ${settings.uploadToken}`, 'Content-Encoding': 'gzip', 'Content-Type': 'application/json' }, data: await gzip(envelope) });
          if (response.status >= 200 && response.status < 300) break;
          if (response.status === 401 || response.status === 403) { stopForAuth(); return; }
          if (attempt < 4) await new Promise((resolve) => setTimeout(resolve, Math.min(60000, 1000 * (2 ** attempt) + Math.floor(Math.random() * 501))));
        }
        if (!(response?.status >= 200 && response.status < 300)) {
          batch.failedParts.push({ part_number: index + 1, attempts: 5, status: Number(response?.status || 0) });
          await mutateQueue((current) => {
            const saved = current.batches.find((item) => item.id === batch.id);
            if (saved) saved.failedParts = structuredClone(batch.failedParts);
          });
          break;
        }
        batch.uploadedParts.push(index + 1);
        await mutateQueue((current) => {
          const saved = current.batches.find((item) => item.id === batch.id);
          if (saved) saved.uploadedParts = [...batch.uploadedParts];
        });
      }
      batch.uploaded = batch.uploadedParts.length === parts.length && await finalizeBatch(batch.id, settings.uploadToken);
      await mutateQueue((current) => {
        const saved = current.batches.find((item) => item.id === batch.id);
        if (saved) { saved.uploaded = batch.uploaded; saved.status = batch.uploaded ? 'completed' : 'uploading'; }
      });
    }
    await mutateQueue((state) => { state.batches = state.batches.filter((item) => !item.uploaded || now() - item.createdAt < 7 * 86400000); });
    await heartbeat('online_active');
  }
  async function detectTimerDrift() {
    const timerDriftMs = now() - lastWakeCheckAt;
    lastWakeCheckAt = now();
    if (document.visibilityState !== 'visible' || timerDriftMs <= 120000) return;
    await heartbeat('suspended');
    paused = true;
    setTimeout(() => {
      if (document.visibilityState !== 'visible') return;
      paused = false;
      void heartbeat('online_active');
      void uploadPending();
    }, 5000);
  }
  function observePageRequests() {
    const observerState = PAGE_WINDOW.__huabangDouyinColorV31Observer = { ready: true, observed: 0 };
    const originalFetch = PAGE_WINDOW.fetch;
    PAGE_WINDOW.fetch = async function (...args) {
      const result = await originalFetch.apply(this, args);
      try {
        const rawUrl = typeof args[0] === 'string' ? args[0] : args[0]?.url;
        const url = new URL(rawUrl, location.origin);
        if (url.pathname === '/web/api/creator/item/list') { observerState.observed += 1; void captureCatalog(await result.clone().json(), rawUrl); }
        if (url.pathname.endsWith('/janus/douyin/creator/data/realtime/analysis/data_center')) {
          observerState.observed += 1;
          learnedCurveRequest = rawUrl;
          const record = recordFromAnalysis(await result.clone().json(), Number(url.searchParams.get('analysis_type')), url.searchParams.get('item_id'));
          if (record) void enqueue(record);
        }
      } catch (_) { /* collection must never alter the creator page */ }
      return result;
    };
    const originalOpen = PAGE_WINDOW.XMLHttpRequest.prototype.open;
    PAGE_WINDOW.XMLHttpRequest.prototype.open = function (method, rawUrl, ...rest) {
      this.__huabangDouyinColorRawUrl = typeof rawUrl === 'string' ? rawUrl : '';
      this.addEventListener('load', () => {
        try {
          const url = new URL(this.__huabangDouyinColorRawUrl, location.origin);
          if (url.pathname === '/web/api/creator/item/list') { observerState.observed += 1; void captureCatalog(JSON.parse(this.responseText), this.__huabangDouyinColorRawUrl); }
          if (url.pathname.endsWith('/janus/douyin/creator/data/realtime/analysis/data_center')) {
            observerState.observed += 1;
            learnedCurveRequest = this.__huabangDouyinColorRawUrl;
            const record = recordFromAnalysis(JSON.parse(this.responseText), Number(url.searchParams.get('analysis_type')), url.searchParams.get('item_id'));
            if (record) void enqueue(record);
          }
        } catch (_) { /* collection must never alter the creator page */ }
      });
      return originalOpen.call(this, method, rawUrl, ...rest);
    };
  }
  function registerMenus() {
    GM_registerMenuCommand('配置本机采集令牌', async () => {
      const uploadToken = prompt('粘贴后台签发的短期采集令牌（仅保存在当前页面内存，刷新后需重新输入）', '');
      const observedCreatorId = prompt('粘贴当前账号的创作者 ID（仅用于请求时核验，不进入队列）', '');
      if (!uploadToken || !observedCreatorId) return;
      runtimeConfig = { uploadToken, observedCreatorId, max_part_uncompressed_bytes: 1024 * 1024, max_part_records: 50, max_local_batches: DEFAULT_MAX_LOCAL_BATCHES, max_local_bytes: DEFAULT_MAX_QUEUE_BYTES };
      const control = await loadCollectorConfig(uploadToken);
      if (!control) { runtimeConfig = null; paused = true; console.warn('douyin-color-v31-status', 'config_incompatible'); return; }
      runtimeConfig = { uploadToken, observedCreatorId, max_part_uncompressed_bytes: control.max_part_uncompressed_bytes, max_part_records: control.max_part_records, max_local_batches: control.max_local_batches, max_local_bytes: control.max_local_bytes };
    });
        GM_registerMenuCommand('立即上传已采集批次', () => void uploadPending());
        GM_registerMenuCommand('按目录补采留存与平台跳出曲线', () => void collectCatalogCurves());
        GM_registerMenuCommand('采集到期 T+2/T+7/T+30 曲线', () => void collectCatalogCurves({ onlyDueObservationWindows: true }));
        GM_registerMenuCommand('继续采集视频目录', () => void collectCatalogPages());
    GM_registerMenuCommand('导出未上传批次', async () => console.info('douyin-color-v31-unuploaded', safeClone((await queueState()).batches.filter((item) => !item.uploaded))));
    GM_registerMenuCommand('放弃未上传批次', async () => {
      await mutateQueue((state) => { state.batches = state.batches.filter((item) => item.uploaded); });
    });
  }
  observePageRequests(); registerMenus();
  document.addEventListener('visibilitychange', () => { paused = document.visibilityState !== 'visible'; if (!paused) void uploadPending(); });
  window.addEventListener('pagehide', () => { paused = true; });
  window.addEventListener('online', () => void uploadPending());
  setInterval(() => void detectTimerDrift(), 60 * 1000);
  setInterval(() => void uploadPending(), 5 * 60 * 1000);
}());
