(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.DouyinColorLocalQueue = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const SENSITIVE = /(?:token|cookie|password|authorization|signature|captcha|query|url|hash)/i;
  class QueueCapacityError extends Error { constructor() { super('queue_capacity_reached'); this.name = 'QueueCapacityError'; } }
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const scrub = (value) => {
    if (Array.isArray(value)) return value.map(scrub);
    if (!value || typeof value !== 'object') return value;
    return Object.fromEntries(Object.entries(value).filter(([key]) => !SENSITIVE.test(key)).map(([key, item]) => [key, scrub(item)]));
  };

  class LocalQueue {
    constructor({ store, now = Date.now, capacityBytes = 40 * 1024 * 1024 } = {}) {
      if (!store || typeof store.load !== 'function' || typeof store.save !== 'function') throw new TypeError('queue_store_required');
      this.store = store; this.now = now; this.capacityBytes = capacityBytes;
    }
    async _load() { const state = await this.store.load(); return { batches: state && state.batches ? state.batches : [] }; }
    async _save(state) { await this.store.save(state); }
    _bytes(state) { return state.batches.reduce((sum, batch) => sum + batch.parts.reduce((n, part) => n + String(part.body || '').length, 0), 0); }
    async enqueueBatch({ id, parts }) {
      const state = await this._load();
      if (this._bytes(state) >= this.capacityBytes * 0.8) throw new QueueCapacityError();
      if (state.batches.some((batch) => batch.id === id)) return;
      state.batches.push({ id, createdAt: this.now(), completedAt: null, parts: parts.map((part) => ({ ...scrub(part), uploaded: false })) });
      await this._save(state);
    }
    async missingParts(id) {
      const batch = (await this._load()).batches.find((item) => item.id === id);
      return batch ? batch.parts.filter((part) => !part.uploaded).map((part) => part.number) : [];
    }
    async markPartUploaded(id, number) {
      const state = await this._load(); const batch = state.batches.find((item) => item.id === id);
      if (!batch) return;
      const part = batch.parts.find((item) => item.number === number);
      if (part) part.uploaded = true;
      if (batch.parts.every((item) => item.uploaded)) batch.completedAt = this.now();
      await this._save(state);
    }
    async cleanupCompleted() {
      const state = await this._load(); const before = state.batches.length; const cutoff = this.now() - 7 * 24 * 60 * 60 * 1000;
      state.batches = state.batches.filter((batch) => !batch.completedAt || batch.completedAt > cutoff);
      await this._save(state); return before - state.batches.length;
    }
    async exportUnuploaded() {
      const state = await this._load();
      return scrub(state.batches.map((batch) => ({ ...batch, parts: batch.parts.filter((part) => !part.uploaded) }))).filter((batch) => batch.parts.length);
    }
  }
  return { LocalQueue, QueueCapacityError };
}));
