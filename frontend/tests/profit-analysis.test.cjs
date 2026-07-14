const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");
const api = read("src/api/finance.ts");
const index = read("src/views/finance/Index.vue");
const overview = read("src/views/finance/FinanceOverview.vue");
const expenses = read("src/views/finance/ExpenseAnalysis.vue");

test("finance api exposes the profit analysis contract", () => {
  assert.match(api, /export interface ProfitAnalysis/);
  assert.match(api, /getProfitAnalysis/);
  assert.match(api, /\/finance\/profit-analysis/);
  for (const field of [
    "cost_coverage_rate",
    "expense_coverage_rate",
    "operating_profit",
    "inventory_amount",
    "discount_loss",
    "return_loss",
    "clearance_loss",
    "missing_expense_types",
    "data_quality",
  ]) {
    assert.match(api, new RegExp(`\\b${field}\\b`));
  }
});

test("profit analysis page presents the complete operating console", () => {
  assert.match(index, /financeApi\.getProfitAnalysis/);
  for (const label of ["利润分析", "门店利润", "单款利润", "损失及库存资金", "折扣损失", "退货损失", "清仓损失", "库存资金"]) {
    assert.match(index, new RegExp(label));
  }
  assert.match(index, /费用覆盖/);
  assert.match(index, /成本覆盖/);
  assert.match(index, /class="profit-analysis-page/);
  assert.match(index, /border-radius:\s*8px/);
});

test("incomplete expenses stay pending instead of becoming zero profit", () => {
  assert.match(index, /operating_profit\s*==\s*null/);
  assert.match(index, /待接入/);
  assert.match(index, /missing_expense_types/);
  assert.doesNotMatch(index, /operating_profit\s*\|\|\s*0/);
});

test("legacy finance payload mismatches are normalized", () => {
  assert.match(index, /res\.data\.data\?\.items\s*\|\|\s*\[\]/);
  assert.match(index, /cashForm\.data_type/);
  assert.doesNotMatch(index, /cashForm\.is_verified/);
});

test("finance overview and expense analysis expose expense coverage", () => {
  for (const source of [overview, expenses]) {
    assert.match(source, /financeApi\.getProfitAnalysis/);
    assert.match(source, /费用覆盖/);
    assert.match(source, /待接入/);
  }
});

