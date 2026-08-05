const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const list = read("src", "views", "mumaren-finance-center", "MumarenFinanceVoucherList.vue");
const summary = read("src", "views", "mumaren-finance-center", "MumarenFinanceVoucherSummary.vue");
const api = read("src", "api", "mumarenFinanceCenter.ts");

test("voucher query exposes header and line views with server pagination and formula-safe CSV", () => {
  for (const token of ["queryVouchers", "queryVoucherLines", "viewMode", "dateFrom", "dateTo", "period", "accountId", "loadRequestVersion", "exportCsv", "^[=+@-]"]) assert.ok(list.includes(token));
  assert.doesNotMatch(list, /limit:\s*500/);
  assert.match(list, /@change="\(\) => load\(\)"/);
  assert.match(list, /accountRequestVersion/);
  assert.match(list, /selectedBook === bookId\.value/);
});

test("voucher list and summary share the readonly detail drawer instead of navigating away", () => {
  for (const page of [list, summary]) {
    assert.match(page, /MumarenVoucherDetailDrawer/);
    assert.match(page, /openVoucher/);
  }
  assert.doesNotMatch(summary, /router\.push/);
  assert.match(api, /getVoucherDetail/);
  const drawer = read("src", "views", "mumaren-finance-center", "MumarenVoucherDetailDrawer.vue");
  assert.match(drawer, /const version = \+\+requestVersion/);
  assert.match(drawer, /detail\.value = undefined/);
});
