const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const product = fs.readFileSync(path.resolve(__dirname, '../src/views/product/Index.vue'), 'utf8')
const wall = fs.readFileSync(path.resolve(__dirname, '../src/views/product/SizeWall.vue'), 'utf8')

test('product page displays the structured decision label and evidence tooltip', () => {
  assert.match(product, /row\.decision\?\.action_label/)
  assert.match(product, /row\.decision\?\.reason/)
  for (const action of ['replenish', 'transfer', 'clearance', 'continue_sale']) {
    assert.equal(product.includes(action), true, `missing ${action}`)
  }
})

test('product, sku and size-wall quantity columns remain sortable', () => {
  for (const prop of ['inventory_qty', 'sales_qty', 'sales_amount']) {
    assert.match(product, new RegExp(`prop="${prop}"[^>]*sortable="custom"`))
  }
  assert.match(wall, /prop="inventory_qty"[^>]*sortable/)
  assert.match(wall, /prop="sales_qty_30d"[^>]*sortable/)
})
