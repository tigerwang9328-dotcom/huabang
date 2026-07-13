'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const root = path.join(__dirname, '..', 'src')

test('investment optimization page exposes verified-outcome decision UI', () => {
  const source = fs.readFileSync(path.join(root, 'views', 'marketing', 'InvestmentOptimization.vue'), 'utf8')
  for (const required of ['实际核销ROI', 'AI 下一步建议', '人工确认后执行', '同期估算', '素材效能', '人群分析', '地域分析', '时间趋势']) {
    assert.equal(source.includes(required), true, `missing: ${required}`)
  }
})

test('router and menu expose the investment optimization page', () => {
  const router = fs.readFileSync(path.join(root, 'router', 'index.ts'), 'utf8')
  const layout = fs.readFileSync(path.join(root, 'layouts', 'MainLayout.vue'), 'utf8')
  assert.equal(router.includes('marketing/investment'), true)
  assert.equal(layout.includes('/app/marketing/investment'), true)
})
