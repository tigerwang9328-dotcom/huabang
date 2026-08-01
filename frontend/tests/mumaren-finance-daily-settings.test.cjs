const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const read = (...segments) => fs.readFileSync(path.join(root, ...segments), 'utf8')

test('每日经营参数和每日广告费页面提供独立账簿、店铺组、导入、批量和保存操作', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')
  const params = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceDailyParameters.vue')
  const ads = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceDailyAdCosts.vue')

  assert.match(config, /每日经营参数/)
  assert.match(config, /每日广告费/)
  assert.match(router, /MumarenFinanceDailyParameters/)
  assert.match(router, /MumarenFinanceDailyAdCosts/)
  for (const action of ['管理店铺组', '从表格导入数据', '复制上月参数', '保存全部']) assert.match(params, new RegExp(action))
  for (const action of ['管理店铺组', '从表格导入数据', '批量设置广告费', '保存全部']) assert.match(ads, new RegExp(action))
  assert.match(params, /useMumarenFinanceBook/)
  assert.match(ads, /useMumarenFinanceBook/)
})

test('每日经营参数和每日广告费丢弃过期账簿或期间请求，不能把旧数据写到当前期间', () => {
  const params = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceDailyParameters.vue')
  const ads = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceDailyAdCosts.vue')

  for (const page of [params, ads]) {
    assert.match(page, /loadRequestVersion/)
    assert.match(page, /requestVersion !== loadRequestVersion/)
    assert.match(page, /requestedBookId !== bookId\.value/)
  }
  assert.match(params, /requestedPeriod !== period\.value/)
  assert.match(ads, /requestedBusinessDate !== businessDate\.value/)
})
