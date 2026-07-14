const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const root = path.resolve(__dirname, "..");
const view = fs.readFileSync(path.join(root, "src/views/warning/Index.vue"), "utf8");
const api = fs.readFileSync(path.join(root, "src/api/audit.ts"), "utf8");

test("attribution source readiness is visible without inventing an owner", () => {
  assert.match(view, /业绩归属数据门禁/);
  assert.match(view, /attributionSources/);
  assert.match(view, /getAttributionStatus/);
  assert.match(view, /来源不足时不自动归责/);
  assert.match(api, /audit\/attribution\/status/);
});

test("attribution conflicts require a reason and evidence before adjudication", () => {
  assert.match(view, /人工裁决/);
  assert.match(view, /selected_owner_id/);
  assert.match(view, /decision_evidence/);
  assert.match(view, /adjudicateAttribution/);
  assert.match(api, /exceptions\/\$\{id\}\/adjudicate/);
});
