const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const source = fs.readFileSync(
  path.resolve(__dirname, '../src/views/report/Index.vue'),
  'utf8',
)

test('14-day report contains the complete operating record columns', () => {
  for (const label of [
    '日期', '销售额', '实收金额', '订单', '件数', '客单价', '连带率',
    '折扣率', '退货率', '毛利额', '毛利率', '成本状态', '数据状态',
  ]) {
    assert.match(source, new RegExp(`label="${label}"`), `missing ${label}`)
  }
})

test('14-day rows remain clickable and use compact no-wrap cells', () => {
  assert.match(source, /@row-click="selectHistory"/)
  assert.match(source, /white-space:\s*nowrap/)
  assert.match(source, /\.history-panel\s+:deep\(\.el-table__cell\)\s*\{[^}]*padding:\s*7px 0/)
})
