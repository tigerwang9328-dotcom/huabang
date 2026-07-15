const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

const productIndex = read("src/views/product/Index.vue");
const productMaster = read("src/views/product/ProductMaster.vue");
const skuArchive = read("src/views/product/SkuArchive.vue");
const inventoryIndex = read("src/views/inventory/Index.vue");
const inventoryBalance = read("src/views/inventory/InventoryBalance.vue");
const financeIndex = read("src/views/finance/Index.vue");

test("sku archive displays authorized standard purchase price and missing-price filter", () => {
  for (const source of [skuArchive, productIndex]) {
    assert.match(source, /standard_purchase_price/);
    assert.match(source, /standard_purchase_price_status/);
    assert.match(source, /标准进价/);
  }
  assert.match(skuArchive, /can_view_standard_purchase_price/);
});

test("product and inventory pages use standard purchase price fields and wording", () => {
  for (const source of [productIndex, productMaster, skuArchive, inventoryIndex, inventoryBalance, financeIndex]) {
    assert.doesNotMatch(source, /缺成本|成本价|SKU成本|成本覆盖/);
  }
  assert.match(inventoryIndex, /standard_purchase_price_coverage_rate/);
  assert.match(inventoryBalance, /row\.standard_purchase_price/);
  assert.doesNotMatch(inventoryBalance, /sku_cost_price/);
  assert.match(financeIndex, /标准进价覆盖/);
  assert.match(financeIndex, /standard_purchase_price_coverage_rate/);
  assert.doesNotMatch(financeIndex, /cost_coverage_rate/);
});

test("expense gaps keep estimated operating profit visible and labeled", () => {
  assert.match(financeIndex, /经营利润（估算）/);
  assert.match(financeIndex, /missing_expense_types/);
  assert.match(financeIndex, /费用缺失/);
});
