const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

test("AI diagnosis exposes model evidence limitations and explicit assignment confirmation", () => {
  const page = read("src/views/diagnosis/Index.vue");
  const api = read("src/api/ai.ts");

  for (const token of [
    "executive_summary", "key_findings", "evidence_refs", "confidence",
    "model_used", "generated_at", "fallback_reason", "suggestion_key",
    "assignee_id", "due_date", "getAssigneeOptions",
  ]) assert.ok(page.includes(token), `missing ${token}`);
  assert.ok(page.includes("el-dialog"));
  assert.ok(api.includes("getAdviceStatus"));
  assert.ok(api.includes("refreshAdvice"));
  assert.ok(api.includes("suggestion_key"));
  assert.ok(page.includes("formatLocalDate(tomorrow)"));
});

test("boss report shows model identity generated time findings actions and fallback", () => {
  const page = read("src/views/report/Index.vue");
  for (const token of [
    "command_conclusion", "model_used", "generated_at", "executive_summary",
    "key_findings", "recommendations", "evidence_refs", "fallback_reason",
  ]) assert.ok(page.includes(token), `missing ${token}`);
  assert.ok(page.includes("@media(max-width:700px)"));
});

test("AI advice pages translate internal sources and role codes before display", () => {
  const diagnosis = read("src/views/diagnosis/Index.vue");
  const report = read("src/views/report/Index.vue");
  const helper = read("src/utils/businessDisplay.ts");

  assert.ok(helper.includes('dws_product_daily: "商品销售汇总"'));
  assert.ok(helper.includes('dwd_inventory_balance: "库存余额"'));
  assert.ok(helper.includes('product_manager: "商品负责人"'));
  assert.ok(helper.includes('deterministic_rules: "确定性规则模板"'));

  for (const page of [diagnosis, report]) {
    assert.ok(page.includes("sourceLabel("), "missing source display formatter");
    assert.ok(page.includes("roleLabel("), "missing role display formatter");
    assert.ok(page.includes("evidenceFallbackLabel("), "missing safe evidence fallback");
    assert.ok(!page.includes("{{ fact.note }} · {{ fact.source }}"), "raw fact source is exposed");
    assert.ok(!page.includes("{{ item.responsible_role"), "raw recommendation role is exposed");
    assert.ok(!page.includes("{{ item.owner }}"), "raw action owner is exposed");
    assert.ok(!page.includes("{{ risk.source }}"), "raw risk source is exposed");
  }
});
