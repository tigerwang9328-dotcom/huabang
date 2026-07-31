(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.DouyinColorCollectorWhitelist = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const SENSITIVE = /(?:token|cookie|password|authorization|signature|captcha|query|url|hash)/i;
  class UnsafeCollectorPayloadError extends Error { constructor() { super('unsafe_collector_payload'); this.name = 'UnsafeCollectorPayloadError'; } }
  const assertSafe = (value) => {
    if (Array.isArray(value)) return value.forEach(assertSafe);
    if (!value || typeof value !== 'object') return;
    for (const [key, item] of Object.entries(value)) {
      if (SENSITIVE.test(key)) throw new UnsafeCollectorPayloadError();
      assertSafe(item);
    }
  };
  const curve = (input) => Array.isArray(input) ? input.filter((point) => point && typeof point.key === 'string' && Number.isFinite(point.value)).map((point) => ({ key: point.key, value: point.value })) : [];
  function toWhitelistedRecord(input) {
    assertSafe(input.response || {});
    const response = input.response || {};
    const trend = response.analysis_trend || {};
    const currentItem = curve(trend.current_item);
    const similarAuthor = curve(trend.similar_author);
    const output = {
      video_id: String(input.video_id),
      sanitized_title: typeof input.title === 'string' ? input.title.slice(0, 500) : undefined,
      duration_ms: Number.isInteger(input.duration_ms) ? input.duration_ms : undefined,
      analysis_type: Number(input.analysis_type),
      http_status: Number.isInteger(input.http_status) ? input.http_status : 200,
      business_status_code: Number.isInteger(response.status_code) ? response.status_code : undefined,
      analysis_trend: Object.fromEntries([
        currentItem.length ? ['current_item', currentItem] : null,
        similarAuthor.length ? ['similar_author', similarAuthor] : null,
      ].filter(Boolean)),
    };
    return Object.fromEntries(Object.entries(output).filter(([, value]) => value !== undefined));
  }
  function normalizeCatalogPage(response) {
    const items = Array.isArray(response?.items) ? response.items : [];
    return {
      has_more: response?.has_more === true,
      max_cursor: Number.isFinite(response?.max_cursor) ? response.max_cursor : null,
      items: items.map((item) => ({
        video_id: String(item.id),
        sanitized_title: typeof item.description === 'string' ? item.description.slice(0, 500) : undefined,
        published_at_epoch_seconds: Number.isInteger(item.create_time) ? item.create_time : undefined,
        duration_ms: Number.isInteger(item.video_info?.duration) ? item.video_info.duration : undefined,
        item_status: item.type === 4 ? 'pending' : 'skipped_non_video',
      })).map((item) => Object.fromEntries(Object.entries(item).filter(([, value]) => value !== undefined))),
    };
  }
  return { toWhitelistedRecord, normalizeCatalogPage, UnsafeCollectorPayloadError };
}));
