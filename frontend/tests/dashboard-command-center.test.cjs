const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { pathToFileURL } = require('node:url')

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

test('dashboard falls back to confirmed overview refund metrics when snapshot refunds are unavailable', () => {
  assert.equal(source.includes('"yesterday_refund_amount" : "yesterday_refund_rate"'), true)
  assert.equal(source.includes('confirmedOverviewMetric(overviewKey)'), true)
  assert.equal(source.includes('baison_pos.refund_amount'), true)
})

test('dashboard never trusts a metadata-less refund snapshot over overview sync state', () => {
  assert.equal(source.includes('metric_status?.returns === "ready"'), true)
  const refundMetric = source.slice(source.indexOf('function refundMetric'), source.indexOf('function refundDisplay'))
  assert.ok(refundMetric.indexOf('overviewMetric') < refundMetric.indexOf('snapshot'))
})

test('dashboard defaults to Shanghai yesterday before 08:00 local time', async () => {
  const moduleUrl = pathToFileURL(
    path.resolve(__dirname, '../src/utils/shanghaiDate.mjs'),
  ).href
  const { shanghaiDateOffset } = await import(moduleUrl)

  assert.equal(
    shanghaiDateOffset(-1, new Date('2026-07-14T21:03:00Z')),
    '2026-07-14',
  )
  assert.equal(source.includes('shanghaiDateOffset(-1)'), true)
  assert.equal(source.includes('yesterday.toISOString().slice(0, 10)'), false)
})
