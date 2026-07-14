const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const root = path.resolve(__dirname, "..");
const view = fs.readFileSync(path.join(root, "src/views/warning/Index.vue"), "utf8");

test("exception audit replaces the placeholder with evidence-backed filters and drilldown", () => {
  assert.match(view, /auditApi\.listExceptions/);
  assert.match(view, /auditApi\.getException/);
  assert.match(view, /规则版本/);
  assert.match(view, /证据明细/);
  assert.match(view, /来源时间/);
  assert.match(view, /生成时间/);
  assert.doesNotMatch(view, /source_updated_at \|\| row\.generated_at/);
  assert.match(view, /下钻/);
  assert.doesNotMatch(view, /功能开发中/);
});

test("exception audit displays pending sources instead of zero findings", () => {
  assert.match(view, /pending_data/);
  assert.match(view, /待接入/);
});
