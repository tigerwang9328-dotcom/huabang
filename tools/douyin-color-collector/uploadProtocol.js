(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.DouyinColorUploadProtocol = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const SENSITIVE = /(?:token|cookie|password|authorization|signature|captcha|query|url|hash)/i;
  class UnsafeCollectorPayloadError extends Error { constructor() { super('unsafe_collector_payload'); this.name = 'UnsafeCollectorPayloadError'; } }
  const canonical = (value) => {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  };
  const scrub = (value) => {
    if (Array.isArray(value)) return value.map(scrub);
    if (!value || typeof value !== 'object') return value;
    const output = {};
    for (const [key, item] of Object.entries(value)) {
      if (SENSITIVE.test(key)) { if (key === 'cookie') throw new UnsafeCollectorPayloadError(); continue; }
      output[key] = scrub(item);
    }
    return output;
  };
  const hash = (value) => {
    if (typeof require !== 'undefined') return require('node:crypto').createHash('sha256').update(value).digest('hex');
    throw new Error('browser_hash_adapter_required');
  };
  function buildParts({ clientBatchId, records }, { maxBytes = 1024 * 1024 } = {}) {
    const clean = records.map(scrub); const groups = [[]];
    for (const record of clean) {
      const candidate = [...groups.at(-1), record];
      const encoded = canonical({ client_batch_id: clientBatchId, records: candidate });
      const byteLength = typeof Buffer !== 'undefined' ? Buffer.byteLength(encoded) : new TextEncoder().encode(encoded).byteLength;
      if (groups.at(-1).length && byteLength > maxBytes) groups.push([record]); else groups[groups.length - 1] = candidate;
    }
    return groups.map((recordsForPart, index) => {
      const payload = { client_batch_id: clientBatchId, records: recordsForPart };
      return { ...payload, part_number: index + 1, part_count: groups.length, part_hash: hash(canonical(payload)) };
    });
  }
  async function uploadWithRetry({ send, sleep = async () => {}, random = Math.random }) {
    for (let attempts = 1; attempts <= 5; attempts += 1) {
      const response = await send();
      if (response.status >= 200 && response.status < 300) return { status: 'uploaded', attempts };
      if (response.status === 401 || response.status === 403) return { status: 'stopped', reason: 'auth_required', attempts };
      if (attempts === 5) return { status: 'failed', reason: 'retry_exhausted', attempts };
      await sleep(Math.min(60_000, 1000 * (2 ** attempts) + Math.floor(random() * 501)));
    }
  }
  return { buildParts, uploadWithRetry, UnsafeCollectorPayloadError };
}));
