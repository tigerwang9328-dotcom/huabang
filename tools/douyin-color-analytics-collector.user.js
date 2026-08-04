// ==UserScript==
// @name         华邦抖音颜色分析采集器 v3.1
// @namespace    https://hbreare.com/
// @version      3.5.12
// @description  仅采集目录和留存/平台跳出曲线的白名单字段；不保存浏览器会话或签名参数。
// @match        https://creator.douyin.com/creator-micro/*
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_listValues
// @grant        unsafeWindow
// @connect      hbreare.com
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-start
// ==/UserScript==

(function () {
  'use strict';
  const API_ORIGIN = 'https://hbreare.com';
  const API_PREFIX = '/api/v1/douyin-color-analytics';
  const SCRIPT_VERSION = '3.5.12';
  const SCHEMA_VERSION = 1;
  const DEFAULT_MAX_QUEUE_BYTES = 500 * 1024 * 1024;
  const DEFAULT_MAX_LOCAL_BATCHES = 100;
  const CATALOG_ENDPOINT = '/web/api/creator/item/list';
  const CURVE_ENDPOINT = '/janus/douyin/creator/data/realtime/analysis/data_center';
  const SENSITIVE_KEY = /(?:token|cookie|authorization|signature|captcha|query|url|hash)/i;
  const now = () => Date.now();
  let installationId = null;
  const PAGE_WINDOW = unsafeWindow;

  let runtimeConfig = null;
  let fixedCollectionInFlight = false;
  const observedAnalyses = new Map();
  // `paused` 只表示鉴权失效或抖音账号切换，不能把窗口失焦当成停止采集。
  // Chrome 在后台会限速计时器，但仍可按小时继续执行；请求节流由队列锁统一控制。
  let paused = false;
  let lastWakeCheckAt = now();
  let lastClaimedCollectionHour = null;

  function claimCollectionHour(epochMs = now()) {
    const hour = Math.floor(epochMs / 3600000);
    if (lastClaimedCollectionHour === hour) return false;
    lastClaimedCollectionHour = hour;
    return true;
  }

  // v3.5.0: 启动时从 GM 存储加载已保存的 token,实现持久化
  const CONFIG_STORAGE_KEY = 'huabang:douyinColor:runtimeConfig';
  async function loadSavedConfig() {
    try {
      const saved = GM_getValue(CONFIG_STORAGE_KEY);
      if (!saved) return;
      const parsed = JSON.parse(saved);
      if (!parsed?.uploadToken) return;
      const control = await loadCollectorConfig(parsed.uploadToken);
      if (!control) { console.warn('[douyin-color] 已保存的令牌已失效,请重新配置'); GM_setValue(CONFIG_STORAGE_KEY, ''); return; }
      runtimeConfig = { ...parsed, max_part_uncompressed_bytes: control.max_part_uncompressed_bytes, max_part_records: control.max_part_records, max_local_batches: control.max_local_batches, max_local_bytes: control.max_local_bytes };
      console.info('[douyin-color] 已自动加载保存的令牌,采集器就绪');
      // 每次页面打开或刷新都立即采集一次；随后由整点调度器继续采集。
      // 小时标记仅保存在当前页面生命周期，刷新后的立即采集符合运营要求。
      claimCollectionHour(now());
      void startFixedCollection();
    } catch (e) { console.warn('[douyin-color] 加载保存的令牌失败:', e.message); }
  }
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
  function fixedCatalogUrl() {
    const url = new URL(CATALOG_ENDPOINT, location.origin);
    url.searchParams.set('count', '20');
    url.searchParams.set('cursor', '0');
    return url;
  }
  function fixedCurveUrl(videoId, creatorId, analysisType) {
    const url = new URL(CURVE_ENDPOINT, location.origin);
    url.searchParams.set('item_id', String(videoId));
    url.searchParams.set('user_id', String(creatorId));
    url.searchParams.set('analysis_type', String(analysisType));
    return url;
  }
  function curve(points) {
    return Array.isArray(points) ? points.filter((item) => item && typeof item.key === 'string' && Number.isFinite(item.value))
      .map((item) => ({ key: item.key, value: item.value })) : [];
  }
  function guardObservedCreator(response) {
    // 兼容多种字段:user_id / author_user_id / author.user_id
    const observed = response?.user_id || response?.author_user_id || response?.data?.user_id || response?.data?.author?.user_id || response?.data?.author_user_id;
    const observedName = response?.data?.author?.nickname || response?.data?.nickname || response?.nickname || response?.author?.nickname;
    if (observed && runtimeConfig && !runtimeConfig.observedCreatorId) {
      runtimeConfig.observedCreatorId = String(observed);
      runtimeConfig.observedAccountName = observedName || runtimeConfig.observedAccountName || '';
      // v3.5.0: 同步更新 GM 存储中的 creator_id
      GM_setValue(CONFIG_STORAGE_KEY, JSON.stringify({ uploadToken: runtimeConfig.uploadToken, observedCreatorId: runtimeConfig.observedCreatorId, observedAccountName: runtimeConfig.observedAccountName }));
      console.info('[douyin-color] 已自动识别创作者:', runtimeConfig.observedCreatorId, runtimeConfig.observedAccountName || '(昵称待补)');
    } else if (observedName && runtimeConfig && !runtimeConfig.observedAccountName) {
      runtimeConfig.observedAccountName = observedName;
      GM_setValue(CONFIG_STORAGE_KEY, JSON.stringify({ uploadToken: runtimeConfig.uploadToken, observedCreatorId: runtimeConfig.observedCreatorId, observedAccountName: runtimeConfig.observedAccountName }));
    }
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
    // 平台响应还带有不参与采集的关联项等字段；只从中投影冻结的
    // 曲线白名单，不能因为无关字段名触发敏感字段保护而丢弃整条曲线。
    if (!guardObservedCreator(response)) return null;
    const videoId = requestedVideoId || currentVideoId();
    const currentItem = curve(response?.analysis_trend?.current_item);
    if (!videoId || !currentItem.length || ![1, 7].includes(analysisType)) return null;
    const trend = { current_item: currentItem };
    const similar = curve(response?.analysis_trend?.similar_author);
    if (similar.length) trend.similar_author = similar;
    return {
      video_id: videoId, analysis_type: analysisType, http_status: 200,
      business_status_code: Number.isInteger(response.status_code) ? response.status_code : undefined,
      response_data: { analysis_trend: trend },
    };
  }
  function catalogItemsFromResponse(response) {
    // 兼容新旧接口:旧 /web/api/creator/item/list 返回 items[],新 /janus/douyin/creator/pc/work_list 返回 aweme_list[]
    const list = Array.isArray(response?.aweme_list) ? response.aweme_list : (Array.isArray(response?.items) ? response.items : []);
    return list.map((item) => {
      const playCount = Number(item?.statistics?.play_count ?? item?.play_count ?? 0);
      // v3.5.0: 排除播放量小于 1000 的视频
      if (playCount < 1000) return { video_id: String(item.aweme_id || item.id || item.item_id), item_status: 'skipped_low_play_count' };
      return {
        video_id: String(item.aweme_id || item.id || item.item_id),
        sanitized_title: typeof (item.desc || item.description) === 'string' ? (item.desc || item.description).slice(0, 500) : undefined,
        published_at_epoch_seconds: Number.isInteger(item.create_time) ? item.create_time : undefined,
        duration_ms: Number.isInteger(item.duration) ? item.duration : (Number.isInteger(item.video_info?.duration) ? item.video_info.duration : undefined),
        item_status: (item.type === 0 || item.type === 4) ? 'pending' : 'skipped_non_video',
      };
    }).map((item) => Object.fromEntries(Object.entries(item).filter(([, value]) => value !== undefined)));
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
  async function enqueueObservedAnalysis(record) {
    if (!record?.video_id || ![1, 7].includes(record.analysis_type)) return;
    const pair = observedAnalyses.get(record.video_id) || {};
    pair[record.analysis_type] = record;
    if (!pair[1] || !pair[7]) {
      observedAnalyses.set(record.video_id, pair);
      return;
    }
    observedAnalyses.delete(record.video_id);
    await enqueue({
      video_id: record.video_id,
      source_type: 'video',
      retention: pair[1],
      platform_bounce: pair[7],
    });
  }
  async function captureCatalog(response) {
    // 兼容新旧接口:aweme_list[] 或 items[]
    const list = Array.isArray(response?.aweme_list) ? response.aweme_list : (Array.isArray(response?.items) ? response.items : []);
    const catalogCreatorId = list.find((item) => item?.author_user_id || item?.user_id)?.author_user_id || list.find((item) => item?.user_id)?.user_id || null;
    const catalogNickname = list.find((item) => item?.author?.nickname)?.author?.nickname || list.find((item) => item?.nickname)?.nickname || null;
    // 统一交给 guardObservedCreator 写回 GM 存储；不能先只改内存，
    // 否则刷新后 observedCreatorId 丢失，待上传批次会被永久阻止。
    if (catalogCreatorId && !guardObservedCreator({ user_id: catalogCreatorId, author: { nickname: catalogNickname } })) return;
    const items = catalogItemsFromResponse(response); if (!items.length) return;
    await mutateQueue((state) => {
      state.catalogItems = state.catalogItems || [];
      for (const item of items) {
        const saved = state.catalogItems.find((existing) => existing.video_id === item.video_id);
        // 旧版可能只缓存了 video_id；目录刷新时必须用完整目录字段回填，
        // 才能让后端补齐发布时间和视频时长。
        if (saved) Object.assign(saved, item);
        else state.catalogItems.push(item);
      }
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
    if (paused) return { status: 0, paused: true };
    return navigator.locks.request('huabang-douyin-color-v31-network', async () => {
      const delay = await mutateQueue((state) => {
        const startAt = Math.max(now(), Number(state.nextRequestStartAt || 0));
        state.nextRequestStartAt = startAt + 1000; return startAt - now();
      });
      if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
      if (paused) return { status: 0, paused: true };
      return request(details);
    });
  }
  async function scheduledPageFetch(url) {
    if (paused) return null;
    return navigator.locks.request('huabang-douyin-color-v31-network', async () => {
      const delay = await mutateQueue((state) => {
        const startAt = Math.max(now(), Number(state.nextRequestStartAt || 0));
        state.nextRequestStartAt = startAt + 1000; return startAt - now();
      });
      if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
      if (paused) return null;
      return fetch(url);
    });
  }
  async function collectCatalogCurves({ onlyDueObservationWindows = false } = {}) {
    if (!runtimeConfig?.observedCreatorId) await collectCatalogPages();
    const creatorId = runtimeConfig?.observedCreatorId;
    if (!creatorId) return;
    const state = await queueState();
    for (const item of state.catalogItems || []) {
      if (onlyDueObservationWindows && !observationWindow(item.published_at_epoch_seconds)) continue;
      const analyses = {};
      for (const analysisType of [1, 7]) {
      if (paused) return;
      const url = fixedCurveUrl(item.video_id, creatorId, analysisType);
      let response;
      for (let attempt = 0; attempt < 5; attempt += 1) {
        try { response = await scheduledPageFetch(url.toString()); } catch (_) { response = null; }
        if (response?.ok) break;
        if (response?.status === 401 || response?.status === 403) { paused = true; return; }
        if (attempt < 4) await new Promise((resolve) => setTimeout(resolve, Math.min(60000, 1000 * (2 ** attempt) + Math.floor(Math.random() * 501))));
      }
        if (response?.ok) {
          try {
          const record = recordFromAnalysis(await response.clone().json(), analysisType, item.video_id);
          if (record) { analyses[analysisType] = record; continue; }
          } catch (_) { /* invalid curve response is recorded below */ }
      }
      await mutateQueue((current) => {
        current.curveFailures = current.curveFailures || [];
        current.curveFailures.push({ video_id: item.video_id, analysis_type: analysisType, attempts: 5, http_status: Number(response?.status || 0) });
      });
      }
      if (analyses[1] && analyses[7]) {
        await enqueue({
          video_id: item.video_id,
          source_type: 'video',
          sanitized_title: item.sanitized_title,
          published_at_epoch_seconds: item.published_at_epoch_seconds,
          duration_ms: item.duration_ms,
          retention: analyses[1],
          platform_bounce: analyses[7],
        });
      }
    }
  }
  async function collectCatalogPages() {
    let url = fixedCatalogUrl();
    const seenCursors = new Set();
    for (let page = 0; page < 200 && !paused; page += 1) {
      const response = await scheduledPageFetch(url.toString());
      if (!response?.ok) return;
      const payload = await response.clone().json();
      await captureCatalog(payload);
      const cursor = String(payload?.max_cursor ?? '');
      if (!payload?.has_more || !cursor || seenCursors.has(cursor)) return;
      seenCursors.add(cursor); url.searchParams.set('cursor', cursor);
    }
  }
  async function startFixedCollection() {
    if (fixedCollectionInFlight || paused || !runtimeConfig?.uploadToken) return;
    fixedCollectionInFlight = true;
    try {
      // 先上报并清空已有队列。完整目录回填可能持续数分钟，不能让旧批次
      // 因为回填尚未完成而一直没有心跳或无法上传。
      await heartbeat('online_active');
      await uploadPending();
      await collectCatalogPages();
      await collectCatalogCurves();
      await uploadPending();
    } finally {
      fixedCollectionInFlight = false;
    }
  }
  async function recoverPending() {
    // 后台页面不再扫描目录或曲线，但必须维持采集器心跳并上传已采集队列。
    // 这样独立窗口、切换后台标签或浏览器失焦不会把服务端状态误判为离线。
    if (!runtimeConfig?.uploadToken) return;
    await heartbeat('online_active');
    await uploadPending();
  }
  async function runScheduledCollection() {
    // 每次调度先可靠上传；每个自然小时只允许一次目录及曲线采集。
    await recoverPending();
    if (claimCollectionHour(now())) await startFixedCollection();
  }
  async function heartbeat(status) {
    const settings = await config(); if (!settings?.uploadToken) return;
    const state = await queueState(); const stableInstallationId = await ensureInstallationId();
    const pendingBatches = state.batches.filter((item) => !item.uploaded);
    await scheduledRequest({ method: 'POST', url: `${API_ORIGIN}${API_PREFIX}/collector-heartbeats`, headers: { Authorization: `Bearer ${settings.uploadToken}`, 'Content-Type': 'application/json' },
      data: JSON.stringify({ installation_id: stableInstallationId, script_version: SCRIPT_VERSION, schema_version: SCHEMA_VERSION, observed_creator_id: settings.observedCreatorId || undefined, observed_account_name: settings.observedAccountName || undefined, current_page_path: location.pathname, current_page_type: 'creator_page', document_visibility: document.visibilityState, queued_batch_count: pendingBatches.length, queued_bytes: bytes({ batches: pendingBatches }) }) });
    console.info('douyin-color-v31-status', status);
  }
  async function uploadPending() {
    const settings = await config(); if (!settings?.uploadToken) return;
    if (!settings?.observedCreatorId) { console.warn('[douyin-color] 尚未识别到创作者 ID,请在创作者中心浏览作品或数据中心页面后重试'); return; }
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
        const envelope = { schema_version: SCHEMA_VERSION, client_batch_id: batch.id, script_version: SCRIPT_VERSION, created_at: new Date(batch.createdAt).toISOString(), installation_id: stableInstallationId, observed_creator_id: settings.observedCreatorId, observed_account_name: settings.observedAccountName || undefined, part_number: index + 1, part_count: parts.length, records: partRecords };
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
    setTimeout(() => {
      if (document.visibilityState !== 'visible') return;
      void heartbeat('online_active');
      void runScheduledCollection();
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
        if (url.pathname === '/janus/douyin/creator/pc/work_list' || url.pathname === CATALOG_ENDPOINT) { observerState.observed += 1; void captureCatalog(await result.clone().json()); }
        if (url.pathname === CURVE_ENDPOINT) {
          observerState.observed += 1;
          const record = recordFromAnalysis(await result.clone().json(), Number(url.searchParams.get('analysis_type')), url.searchParams.get('item_id'));
          if (record) void enqueueObservedAnalysis(record);
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
          if (url.pathname === '/janus/douyin/creator/pc/work_list' || url.pathname === CATALOG_ENDPOINT) { observerState.observed += 1; void captureCatalog(JSON.parse(this.responseText)); }
          if (url.pathname === CURVE_ENDPOINT) {
            observerState.observed += 1;
            const record = recordFromAnalysis(JSON.parse(this.responseText), Number(url.searchParams.get('analysis_type')), url.searchParams.get('item_id'));
            if (record) void enqueueObservedAnalysis(record);
          }
        } catch (_) { /* collection must never alter the creator page */ }
      });
      return originalOpen.call(this, method, rawUrl, ...rest);
    };
  }
  function registerMenus() {
    GM_registerMenuCommand('配置本机采集令牌', async () => {
      const uploadToken = prompt('粘贴后台签发的采集令牌（将持久保存,刷新页面无需重新输入）', '');
      if (!uploadToken) return;
      runtimeConfig = { uploadToken, observedCreatorId: runtimeConfig?.observedCreatorId || '', observedAccountName: runtimeConfig?.observedAccountName || '', max_part_uncompressed_bytes: 1024 * 1024, max_part_records: 50, max_local_batches: DEFAULT_MAX_LOCAL_BATCHES, max_local_bytes: DEFAULT_MAX_QUEUE_BYTES };
      const control = await loadCollectorConfig(uploadToken);
      if (!control) { runtimeConfig = null; paused = true; console.warn('douyin-color-v31-status', 'config_incompatible'); alert('令牌验证失败,请检查令牌是否正确或已过期'); return; }
      runtimeConfig = { uploadToken, observedCreatorId: runtimeConfig?.observedCreatorId || '', observedAccountName: runtimeConfig?.observedAccountName || '', max_part_uncompressed_bytes: control.max_part_uncompressed_bytes, max_part_records: control.max_part_records, max_local_batches: control.max_local_batches, max_local_bytes: control.max_local_bytes };
      // v3.5.0: 持久化到 GM 存储,刷新页面后自动加载
      GM_setValue(CONFIG_STORAGE_KEY, JSON.stringify({ uploadToken, observedCreatorId: runtimeConfig.observedCreatorId, observedAccountName: runtimeConfig.observedAccountName }));
      if (!runtimeConfig.observedCreatorId) {
        console.warn('[douyin-color] 创作者 ID 将在您浏览作品或数据中心时自动识别,无需手动输入');
      }
      console.info('[douyin-color] 令牌已保存,采集器就绪');
      claimCollectionHour(now());
      void startFixedCollection();
      alert('令牌已保存成功！采集器已就绪。\n刷新页面或重启浏览器后无需重新配置。\n创作者 ID 将在浏览作品时自动识别。');
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
  observePageRequests(); registerMenus(); void loadSavedConfig();
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') void recoverPending(); });
  window.addEventListener('online', () => void runScheduledCollection());
  setInterval(() => void detectTimerDrift(), 60 * 1000);
  setInterval(() => void runScheduledCollection(), 60 * 1000);
}());
