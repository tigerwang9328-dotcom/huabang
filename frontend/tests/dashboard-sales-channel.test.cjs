'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const source = fs.readFileSync(
  path.join(__dirname, '..', 'src', 'views', 'dashboard', 'Index.vue'),
  'utf8',
)

test('dashboard reads explicit online and offline sales metrics', () => {
  assert.equal(source.includes('yesterday_offline_sales'), true)
  assert.equal(source.includes('yesterday_online_sales'), true)
  assert.equal(source.includes('百胜011线上支付'), true)
  assert.equal(source.includes('百胜非011结算'), true)
})

test('dashboard keeps total sales and both channel labels visible', () => {
  for (const label of ['销售额', '线下销售', '线上销售']) {
    assert.equal(source.includes(`label: "${label}"`), true, `missing ${label}`)
  }
})

test('dashboard keeps two decimals for small channel shares', () => {
  assert.match(source, /offline \/ total\) \* 100\)\.toFixed\(2\)/)
  assert.match(source, /online \/ total\) \* 100\)\.toFixed\(2\)/)
})
