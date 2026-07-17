'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const root = path.join(__dirname, '..', 'src')

test('investment optimization page exposes verified-outcome decision UI', () => {
  const source = fs.readFileSync(path.join(root, 'views', 'marketing', 'InvestmentOptimization.vue'), 'utf8')
  for (const required of ['实际核销ROI', 'DeepSeek 增强建议', '规则兜底建议', '决策历史', '人工决定', '登记实际执行', '24小时', '72小时', '7天结果', '同期估算', '素材效能', '人群分析', '地域分析', '时间趋势', '采集分组', '经营', '广告', '投放人群地域消耗分布（按居住地）', '省份', '城市', '仅代表广告消耗流向，不能单独判断地域效果']) {
    assert.equal(source.includes(required), true, `missing: ${required}`)
  }
  assert.equal(source.includes('贵阳及周边消耗分布'), false)
})

test('investment API reads persisted history and records human workflow', () => {
  const source = fs.readFileSync(path.join(root, 'api', 'lifeDataAnalysis.ts'), 'utf8')
  for (const required of ['getDecisionOverview', 'getDecisionHistory', 'getDecisionDetail', 'recordDecision', 'recordExecution', 'getDailyPatterns']) {
    assert.equal(source.includes(required), true, `missing API method: ${required}`)
  }
})

test('online sales owns investment optimization and business report', () => {
  const router = fs.readFileSync(path.join(root, 'router', 'index.ts'), 'utf8')
  const layout = fs.readFileSync(path.join(root, 'layouts', 'MainLayout.vue'), 'utf8')

  const menuStart = layout.indexOf('const menuGroups')
  const salesCenterStart = layout.indexOf('label: "销售中心"', menuStart)
  const onlineSalesStart = layout.indexOf('label: "线上销售"', salesCenterStart)
  const productStart = layout.indexOf('label: "商品经营"', onlineSalesStart)
  const topLevelBlock = layout.slice(menuStart, salesCenterStart)
  const onlineSalesBlock = layout.slice(onlineSalesStart, productStart)

  assert.equal(router.includes('marketing/investment'), true)
  assert.equal(router.includes('path: "report"'), true)
  assert.equal(topLevelBlock.includes('/app/marketing/investment'), false)
  assert.equal(topLevelBlock.includes('/app/report'), false)
  assert.equal(onlineSalesBlock.includes('/app/marketing/investment'), true)
  assert.equal(onlineSalesBlock.includes('/app/report'), true)
  assert.equal(onlineSalesBlock.indexOf('投流优化') < onlineSalesBlock.indexOf('经营日报'), true)
  assert.equal(onlineSalesBlock.indexOf('经营日报') < onlineSalesBlock.indexOf('线上总览'), true)
})

test('an active nested route expands its menu hierarchy', () => {
  const layout = fs.readFileSync(path.join(root, 'layouts', 'MainLayout.vue'), 'utf8')

  assert.equal(layout.includes('const expandActiveMenuPath'), true)
  assert.equal(layout.includes('next.add(groupKey(group))'), true)
  assert.equal(layout.includes('next.add(menuKey(item))'), true)
  assert.match(layout, /watch\(\(\) => route\.path, expandActiveMenuPath, \{ immediate: true \}\)/)
})
