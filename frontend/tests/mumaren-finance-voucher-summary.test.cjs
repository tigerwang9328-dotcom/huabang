const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const page = read("src", "views", "mumaren-finance-center", "MumarenFinanceVoucherSummary.vue");
const api = read("src", "api", "mumarenFinanceCenter.ts");

test("voucher summary uses server aggregation and real voucher types", () => {
  assert.match(api, /getVoucherSummary/);
  assert.match(api, /getVoucherSummaryDetails/);
  assert.match(api, /voucher_type/);
  assert.match(page, /getVoucherSummary/);
  assert.doesNotMatch(page, /extractVoucherType/);
  assert.doesNotMatch(page, /listVouchers\(/);
});

test("voucher summary defaults to posted and labels non-posted data", () => {
  assert.match(page, /status\s*=\s*ref(?:<[^>]+>)?\(["']posted["']\)/);
  assert.match(page, /当前为非正式凭证汇总，不代表正式账簿数据/);
});

test("voucher summary provides all approved filters, detail drilldown, reset, and CSV export", () => {
  for (const token of ["monthFilter", "voucherTypeFilter", "keyword", "resetFilters", "exportCsv", "expand-change", "openVoucher"]) {
    assert.match(page, new RegExp(token));
  }
});

test("voucher summary discards stale summary and detail responses", () => {
  for (const token of ["loadRequestVersion", "detailRequestVersion", "requestVersion !== loadRequestVersion.value", "requestVersion !== detailRequestVersion.value[key]"]) assert.ok(page.includes(token));
});
