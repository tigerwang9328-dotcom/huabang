const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const source = fs.readFileSync(
  path.resolve(__dirname, '../src/views/store/Index.vue'),
  'utf8',
)

test('store analysis exposes comparisons and source dates', () => {
  for (const label of ['日环比', '周同比', '销售数据', '库存快照', '会员数据']) {
    assert.equal(source.includes(label), true, `missing ${label}`)
  }
})

test('store analysis exposes product, member, exception and store drilldowns', () => {
  assert.match(source, /@row-click="openStore"/)
  assert.match(source, /openProduct/)
  assert.match(source, /openMember/)
  assert.match(source, /openException/)
  assert.match(source, /畅销款/)
  assert.match(source, /滞销款/)
})

test('missing store metrics stay visibly pending instead of showing zero', () => {
  for (const label of ['客流', '成交人数', '试穿率', '新老客', '导购业绩']) {
    assert.equal(source.includes(label), true, `missing ${label}`)
  }
  assert.match(source, /pending_metrics/)
  assert.match(source, /待接入/)
})
