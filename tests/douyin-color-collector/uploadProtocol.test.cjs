const test = require('node:test');
const assert = require('node:assert/strict');

const { buildParts, uploadWithRetry, UnsafeCollectorPayloadError } = require('../../tools/douyin-color-collector/uploadProtocol');
const { toWhitelistedRecord, normalizeCatalogPage } = require('../../tools/douyin-color-collector/collectorFieldWhitelist');
const fs = require('node:fs');
const path = require('node:path');

test('protocol emits deterministic fixed parts and never serializes signed browser fields', () => {
  const parts = buildParts({ clientBatchId: 'b', records: [{ video_id: '1', title: 'ok', query: 'drop' }, { video_id: '2', signature: 'drop' }] }, { maxBytes: 240 });
  assert.ok(parts.length >= 1);
  assert.equal(parts.every((part, index) => part.part_number === index + 1 && part.part_count === parts.length), true);
  assert.equal(parts.every((part) => /^[0-9a-f]{64}$/.test(part.part_hash)), true);
  assert.equal(JSON.stringify(parts).match(/signature|query/), null);
  assert.throws(() => buildParts({ clientBatchId: 'b', records: [{ video_id: '1', cookie: 'x' }] }), UnsafeCollectorPayloadError);
});

test('uploads retry at most five times and halt immediately on auth rejection', async () => {
  let attempts = 0;
  const retried = await uploadWithRetry({
    send: async () => ({ status: ++attempts < 3 ? 429 : 200 }),
    sleep: async () => {}, random: () => 0,
  });
  assert.deepEqual(retried, { status: 'uploaded', attempts: 3 });
  assert.equal(attempts, 3);
  const auth = await uploadWithRetry({ send: async () => ({ status: 403 }), sleep: async () => {} });
  assert.deepEqual(auth, { status: 'stopped', reason: 'auth_required', attempts: 1 });
});

test('part hashes include nested analytics points and 429 jitter spans the required 0..500ms range', async () => {
  const left = buildParts({ clientBatchId: 'b', records: [{ analysis_trend: { current_item: [{ key: '00:00', value: 1 }] } }] });
  const right = buildParts({ clientBatchId: 'b', records: [{ analysis_trend: { current_item: [{ key: '00:00', value: 2 }] } }] });
  assert.notEqual(left[0].part_hash, right[0].part_hash);

  const delays = [];
  await uploadWithRetry({
    send: async () => ({ status: 429 }),
    sleep: async (delay) => { delays.push(delay); },
    random: () => 0.999999,
  });
  assert.deepEqual(delays, [2500, 4500, 8500, 16500]);
});

test('field whitelist keeps only analytics facts and rejects browser-session fields', () => {
  const record = toWhitelistedRecord({
    video_id: '7666046377541012755', title: 'safe title', duration_ms: 112000,
    analysis_type: 1, response: { status_code: 0, analysis_trend: { current_item: [{ key: '00:00', value: 1 }] } },
    msToken: 'must-not-persist', cookie: 'must-not-persist', signed_url: 'must-not-persist',
  });
  assert.deepEqual(record, {
    video_id: '7666046377541012755', sanitized_title: 'safe title', duration_ms: 112000, analysis_type: 1,
    http_status: 200, business_status_code: 0,
    analysis_trend: { current_item: [{ key: '00:00', value: 1 }] },
  });
  assert.throws(() => toWhitelistedRecord({ video_id: '1', response: { authorization: 'x' } }), { name: 'UnsafeCollectorPayloadError' });
});

test('catalog page maps real top-level items without creator or media fields', () => {
  const page = normalizeCatalogPage({ has_more: true, max_cursor: 42, items: [{ id: '7666046377541012755', description: 'safe', create_time: 1720000000, type: 4, user_id: 'do-not-store', cover: { url_list: ['do-not-store'] }, video_info: { duration: 111000 } }] });
  assert.deepEqual(page, { has_more: true, max_cursor: 42, items: [{ video_id: '7666046377541012755', sanitized_title: 'safe', published_at_epoch_seconds: 1720000000, duration_ms: 111000, item_status: 'pending' }] });
});

test('installable userscript has one API connect target and never embeds credentials', () => {
  const script = fs.readFileSync(path.resolve(__dirname, '../../tools/douyin-color-analytics-collector.user.js'), 'utf8');
  assert.match(script, /@connect\s+hbreare\.com/);
  assert.equal((script.match(/@connect/g) || []).length, 1);
  assert.match(script, /GM_xmlhttpRequest/);
  assert.match(script, /indexedDB\.open/);
  assert.doesNotMatch(script, /GM_setValue\('douyin_color_v31_config'/);
  assert.doesNotMatch(script, /recordHash/);
  assert.match(script, /splitUploadParts\(records, settings\.max_part_uncompressed_bytes, settings\.max_part_records\)/);
  assert.match(script, /uploadedParts/);
  assert.match(script, /navigator\.locks\.request\('huabang-douyin-color-v31-network'/);
  assert.match(script, /nextRequestStartAt = startAt \+ 1000/);
  assert.match(script, /window\.addEventListener\('pagehide'/);
  assert.match(script, /account_switched/);
  assert.match(script, /catalogCreatorId/);
  assert.match(script, /guardObservedCreator\(\{ user_id: catalogCreatorId \}\)/);
  assert.match(script, /\/web\/api\/creator\/item\/list/);
  assert.match(script, /learnedCurveRequest/);
  assert.match(script, /ensureInstallationId/);
  assert.match(script, /canonicalJson\(\{ client_batch_id: envelope\.client_batch_id, records: partRecords \}\)/);
  assert.match(script, /Math\.floor\(Math\.random\(\) \* 501\)/);
  assert.match(script, /failedParts/);
  assert.match(script, /\[1, 7\]/);
  assert.match(script, /learnedCatalogRequest/);
  assert.match(script, /collectCatalogPages/);
  assert.match(script, /requestedVideoId \|\| currentVideoId\(\)/);
  assert.match(script, /curveFailures/);
  assert.match(script, /serverMissingParts/);
  assert.match(script, /collector-config/);
  assert.match(script, /minimum_script_version/);
  assert.match(script, /collection_enabled/);
  assert.match(script, /max_local_batches/);
  assert.match(script, /max_local_bytes/);
  assert.match(script, /splitUploadParts/);
  assert.match(script, /missing-parts/);
  assert.match(script, /\/finalize/);
  assert.match(script, /observationWindow/);
  assert.match(script, /queue-state/);
  assert.match(script, /status = 'uploading'/);
  assert.match(script, /function stopForAuth/);
  assert.match(script, /stopForAuth\(\); return;/);
  assert.match(script, /timerDriftMs <= 120000/);
  assert.match(script, /heartbeat\('suspended'\)/);
  assert.match(script, /@grant\s+unsafeWindow/);
  assert.match(script, /const PAGE_WINDOW = unsafeWindow/);
  assert.match(script, /PAGE_WINDOW\.fetch = async function/);
  assert.match(script, /PAGE_WINDOW\.XMLHttpRequest\.prototype\.open/);
  assert.match(script, /__huabangDouyinColorV31Observer/);
  assert.doesNotMatch(script, /Bearer\s+[A-Za-z0-9._-]{12,}/);
  assert.doesNotMatch(script, /password\s*[:=]\s*['"][^'"]+/i);
});
