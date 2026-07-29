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
