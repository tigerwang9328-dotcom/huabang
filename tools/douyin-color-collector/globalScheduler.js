(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.DouyinColorGlobalScheduler = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const DEFAULT_STATE = { nextStartAt: 0, inFlight: [], activeAccountKey: null, generation: 0 };
  const storeLocks = new WeakMap();

  class GlobalScheduler {
    constructor({ store, now = Date.now, random = Math.random, minIntervalMs = 1000, maxInFlight = 2 } = {}) {
      if (!store || typeof store.get !== 'function' || typeof store.set !== 'function') throw new TypeError('scheduler_store_required');
      this.store = store;
      this.now = now;
      this.random = random;
      this.minIntervalMs = minIntervalMs;
      this.maxInFlight = maxInFlight;
    }

    _withStoreLock(work) {
      const previous = storeLocks.get(this.store) || Promise.resolve();
      const current = previous.catch(() => undefined).then(work);
      storeLocks.set(this.store, current.catch(() => undefined));
      return current;
    }

    async _state() {
      const stored = (await this.store.get()) || {};
      return { ...DEFAULT_STATE, ...stored, inFlight: [...(stored.inFlight || [])] };
    }

    async tryAcquire(accountKey) {
      return this._withStoreLock(async () => {
        const state = await this._state();
        const now = this.now();
        if (state.activeAccountKey && state.activeAccountKey !== accountKey) return { granted: false, reason: 'account_switched', waitMs: 0 };
        if (!state.activeAccountKey) state.activeAccountKey = accountKey;
        if (now < state.nextStartAt) return { granted: false, reason: 'rate_limited', waitMs: state.nextStartAt - now };
        if (state.inFlight.length >= this.maxInFlight) return { granted: false, reason: 'concurrency_limited', waitMs: this.minIntervalMs };
        const leaseId = `${state.generation}:${now}:${Math.floor(this.random() * 1e9)}`;
        state.generation += 1;
        state.nextStartAt = now + this.minIntervalMs;
        state.inFlight.push(leaseId);
        await this.store.set(state);
        return { granted: true, leaseId };
      });
    }

    async release(leaseId) {
      return this._withStoreLock(async () => {
        const state = await this._state();
        state.inFlight = state.inFlight.filter((item) => item !== leaseId);
        await this.store.set(state);
      });
    }

    async recordFailure(leaseId, { status, retryCount = 0 } = {}) {
      await this.release(leaseId);
      if (status === 401 || status === 403) return { retryable: false, reason: 'auth_required' };
      if (retryCount >= 5) return { retryable: false, reason: 'retry_exhausted' };
      const nextRetry = retryCount + 1;
      const base = status === 429 ? 1000 * (2 ** retryCount) : 1000 * nextRetry;
      const waitMs = Math.min(60_000, base + Math.floor(this.random() * 501));
      const state = await this._state();
      state.nextStartAt = Math.max(state.nextStartAt, this.now() + waitMs);
      await this.store.set(state);
      return { retryable: true, retryCount: nextRetry, waitMs };
    }

    async classifyResponse(status) {
      return status === 401 || status === 403 ? { stopped: true, reason: 'auth_required' } : { stopped: false };
    }

    async switchAccount(accountKey) {
      return this._withStoreLock(async () => {
        const state = await this._state();
        state.activeAccountKey = accountKey;
        state.inFlight = [];
        state.nextStartAt = this.now() + this.minIntervalMs;
        await this.store.set(state);
        return { stopped: true, reason: 'account_switched' };
      });
    }
  }

  return { GlobalScheduler };
}));
