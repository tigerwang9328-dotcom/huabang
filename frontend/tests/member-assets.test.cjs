const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const source = fs.readFileSync(path.resolve(__dirname, '../src/views/member/Index.vue'), 'utf8')
const api = fs.readFileSync(path.resolve(__dirname, '../src/api/member.ts'), 'utf8')

test('member page exposes VIP sales analysis without replacing asset views', () => {
  assert.match(source, /label="VIP资产"/)
  assert.match(source, /label="VIP销售"/)
  assert.match(source, /VIP销售额/)
  assert.match(source, /客单价/)
  assert.match(source, /连带率/)
  assert.match(source, /复购率/)
  assert.match(source, /平均折扣/)
  assert.match(source, /退货率/)
  assert.match(api, /\/member\/sales\/analysis/)
})

test('unreliable VIP profit and product dimensions stay pending', () => {
  assert.match(source, /VIP毛利/)
  assert.match(source, /品类\/款式/)
  assert.match(source, /待接入/)
})
