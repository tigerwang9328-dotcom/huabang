const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const source = fs.readFileSync(path.resolve(__dirname, '../src/views/inventory/Index.vue'), 'utf8')

test('inventory warnings expose every phase-one rule type', () => {
  for (const value of [
    'seasonal', 'size_break', 'low_motion_high_stock', 'stockout',
    'store_imbalance', 'transfer', 'clearance_return',
  ]) {
    assert.match(source, new RegExp(`value="${value}"`), `missing ${value}`)
  }
})

test('inventory warning table displays evidence, source and generation time', () => {
  assert.match(source, /prop="source_name"/)
  assert.match(source, /row\.evidence/)
  assert.match(source, /generated_at/)
  assert.match(source, /标准进价覆盖率/)
})
