const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");
const { pathToFileURL } = require("node:url");

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

test("exception audit deep links open a specific evidence record after loading the list", () => {
  assert.match(view, /useRoute/);
  assert.match(view, /route\.query\.exception_id/);
  assert.match(view, /await openDetail\(exceptionId, true\)/);
  assert.match(view, /prop="id" label="ID"/);
  assert.ok(view.indexOf("await loadData()") < view.indexOf("await openDetail(exceptionId, true)"));
});

test("exception audit accepts only one canonical positive integer id", async () => {
  const moduleUrl = pathToFileURL(
    path.join(root, "src/utils/routeQuery.mjs"),
  ).href;
  const { parsePositiveIntegerQuery } = await import(moduleUrl);

  assert.equal(parsePositiveIntegerQuery("217"), 217);
  for (const invalid of [undefined, null, "", "0", "-1", "1.0", "1e2", "0x10", " 12 ", ["217"], ["217", "226"]]) {
    assert.equal(parsePositiveIntegerQuery(invalid), null, `accepted ${JSON.stringify(invalid)}`);
  }
  assert.equal(parsePositiveIntegerQuery("9007199254740992"), null);
});
