const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

test("finance center base URL opens the V2 core workspace with the existing finance read permission", () => {
  const router = read("src/router/index.ts");

  assert.ok(
    router.includes('{ path: "finance-center", redirect: "/app/finance-center/core-workspace" }'),
    "the finance center base route must redirect to the V2 core workspace",
  );
  assert.ok(
    router.includes('["/app/finance-center", "finance:profit:view"]'),
    "the finance center route family must use the existing finance read permission",
  );
});

test("V2 workspace reads periods, postable accounts, and voucher workflow state from isolated endpoints", () => {
  const api = read("src/api/financeV2.ts");
  const workspace = read("src/views/finance-center/V2CoreWorkspace.vue");

  for (const token of ["listPeriods", "listAccounts", "listVouchers"]) {
    assert.ok(api.includes(token), `missing ${token} API`);
  }
  for (const token of ["selectedBookId", "loadWorkspace", "vouchers", "accounts"]) {
    assert.ok(workspace.includes(token), `missing ${token} workspace state`);
  }
});

test("V2 workspace exposes immutable historical Kingdee vouchers and their marked line details", () => {
  const api = read("src/api/financeV2.ts");
  const workspace = read("src/views/finance-center/V2CoreWorkspace.vue");

  assert.ok(api.includes("listHistoryVouchers"));
  assert.ok(api.includes("listHistoryVoucherLines"));
  assert.ok(workspace.includes("历史金蝶凭证"));
  assert.ok(workspace.includes("historical_marker"));
  assert.ok(workspace.includes("viewHistoryVoucher"));
});

test("finance center navigation does not present V2 history or current accounts as already production-published", () => {
  const modules = read("src/config/financeCenterModules.ts");

  assert.ok(modules.includes("待恢复副本验证"));
  assert.ok(modules.includes("正式报表保持阻断"));
  assert.ok(!modules.includes("三套正式账套已写入正式账簿"));
  assert.ok(!modules.includes("416 个科目、1,125 条正式月余额已上线"));
});

test("V2 workspace exposes write actions only through server-reported Gate readiness", () => {
  const api = read("src/api/financeV2.ts");
  const workspace = read("src/views/finance-center/V2CoreWorkspace.vue");

  assert.ok(api.includes("getWriteReadiness"));
  assert.ok(api.includes("createDraft"));
  assert.ok(api.includes("executeCommand"));
  assert.ok(workspace.includes("writeReadiness"));
  assert.ok(workspace.includes("draftEnabled"));
  assert.ok(workspace.includes("runCommand"));
});
