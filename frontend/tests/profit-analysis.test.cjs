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
const layout = read("src/layouts/MainLayout.vue");

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
  assert.match(index, /getProfitComparison/);
  assert.match(index, /data\.data\?\.items\s*\|\|\s*\[\]/);
  assert.match(index, /cashForm\.data_type/);
  assert.doesNotMatch(index, /cashForm\.is_verified/);
});

test("finance overview and expense analysis expose expense coverage", () => {
  for (const source of [overview, expenses]) assert.doesNotMatch(source, /financeApi\.getProfitAnalysis/);
});

test("profit entry uses all eight canonical categories and separates request errors", () => {
  for (const type of ["rent","wages","social_security","platform_fee","utilities","logistics","marketing","other"]) assert.match(index, new RegExp(`value="${type}"`));
  assert.doesNotMatch(index, /value="(?:labor|admin)"/);
  assert.match(index, /profitError/);
  assert.match(index, /catch\s*\{/);
  assert.match(index, /profit\?\.period/);
});

test("finance data contracts and views avoid untyped profit and expense payloads", () => {
  for (const name of ["FinanceOverview", "FinanceExpenseRecord", "ExpenseList", "ProfitDailyItem", "CashSafety"]) {
    assert.match(api, new RegExp(`interface\\s+${name}`));
  }
  for (const source of [api, index, overview, expenses]) assert.doesNotMatch(source, /\bany\b/);
});

test("finance views render loading, errors, empty data, and ready data as separate states", () => {
  assert.match(index, /type ProfitViewState = "loading" \| "error" \| "empty" \| "pending" \| "ready"/);
  for (const state of ["profitState", "dailyState", "cashState"]) assert.match(index, new RegExp(`\\b${state}\\b`));
  assert.match(index, /v-else-if="profitState === 'pending' \|\| profitState === 'ready'"/);
  assert.match(index, /v-else-if="dailyState === 'ready'"/);
  assert.match(index, /v-else-if="cashState === 'ready' && cashSafety"/);
  assert.match(overview, /overviewState/);
  assert.match(expenses, /expenseState/);
  for (const source of [overview, expenses]) assert.match(source, /v-else-if=.*=== 'ready'/);
});

test("profit daily table is an honest daily status view with Chinese labels", () => {
  assert.match(index, /每日利润状态/);
  assert.doesNotMatch(index, /预估vs核准对比/);
  assert.match(index, /data_type_label/);
  assert.match(index, /dailyStatusLabel/);
  assert.doesNotMatch(index, /fmtActual|fmtDiffPct/);
});

test("all eight expense coverage categories have visible Chinese status labels", () => {
  for (const label of ["租金", "工资", "社保", "平台费", "水电", "物流", "营销", "其他"]) assert.match(index, new RegExp(label));
  assert.match(index, /expenseCoverageStatus/);
  assert.match(index, /费用覆盖状态/);
});

test("finance headers and cash metrics adapt on mobile", () => {
  assert.match(index, /class="cash-cards"/);
  assert.match(index, /\.loss-grid, \.cash-cards/);
  for (const source of [index, overview, expenses]) assert.match(source, /@media\s*\(max-width:\s*768px\)/);
  assert.match(index, /flex-wrap:\s*wrap/);
});

test("finance tabs and parent menu follow the matching child permissions", () => {
  assert.match(index, /v-if="canCreateExpense"[^>]*label="费用补录"/);
  assert.match(index, /v-if="canCreateCash"[^>]*label="现金补录"/);
  assert.match(index, /v-if="canViewCash"[^>]*label="现金安全天数"/);
  assert.match(index, /authStore\.hasPermission\("finance:expense:create"\)/);
  assert.doesNotMatch(index, /<el-radio value="actual">财务核准/);
  const financeGroup = layout.slice(layout.indexOf('label: "财务利润"'), layout.indexOf('label: "人力资源"'));
  assert.doesNotMatch(financeGroup, /permission: "finance:overview:view",\s*items:/);
});
