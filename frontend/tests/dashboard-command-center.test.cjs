const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const source = fs.readFileSync(
  path.resolve(__dirname, '../src/views/dashboard/Index.vue'),
  'utf8',
)

test('dashboard keeps the phase-one metric contract visible', () => {
  for (const label of [
    '销售额', '线下销售', '线上销售', '实收金额', '订单数', '销售件数',
    '客单价', '连带率', '折扣率', '退货金额', '退货率', '毛利额', '毛利率',
    '库存金额', '90天以上库存', '180天以上库存', 'VIP余额', 'VIP销售',
  ]) {
    assert.equal(source.includes(`label: "${label}"`), true, `missing ${label}`)
  }
})

test('dashboard places risks and actions after data quality at the bottom', () => {
  const conclusion = source.indexOf('class="decision-strip"')
  const metrics = source.indexOf('class="module-card api-panel"')
  const sales = source.indexOf('class="module-card sales-panel"')
  const assets = source.indexOf('class="module-grid two-col"')
  const quality = source.indexOf('class="module-card governance-panel"')
  const decisions = source.indexOf('class="decision-grid"')

  assert.ok(conclusion < metrics)
  assert.ok(metrics < sales)
  assert.ok(sales < assets)
  assert.ok(assets < quality)
  assert.ok(quality < decisions)
  assert.ok(decisions > source.lastIndexOf('<section'))
})
