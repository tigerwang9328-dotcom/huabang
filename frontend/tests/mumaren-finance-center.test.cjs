const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const frontendRoot = path.resolve(__dirname, '..')
const read = (...parts) => fs.readFileSync(path.join(frontendRoot, ...parts), 'utf8')

test('牧马人财务中心拥有独立前端入口和完整业务导航页面', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')

  assert.match(config, /MUMAREN_FINANCE_CENTER_ROOT\s*=\s*['\"]\/app\/finance-center\/mumaren['\"]/)
  for (const section of ['工作台', '凭证', '账簿', '应收应付', '业务台账', '税务', '经营报表', '历史归档']) {
    assert.match(config, new RegExp(`title:\\s*['\"]${section}['\"]`))
  }
  assert.match(router, /\/app\/finance-center\/mumaren/)
  assert.match(router, /mumaren-finance-center/)
})

test('未移植的牧马人业务域必须显示真实接入状态，不能伪装成可操作功能', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceCapabilityBoard.vue')

  assert.match(config, /availability:\s*['"]available['"]|availability:\s*['"]planned_backend['"]/)
  assert.match(page, /后端适配待完成/)
  assert.match(page, /不可录入/)
  assert.doesNotMatch(page, /自动过账/)
})

test('扩展业务页面保持在牧马人独立命名空间，且不引用旧华邦财务页面', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  for (const suffix of ['ar-ap', 'business', 'tax', 'operations']) {
    assert.ok(config.includes(`MUMAREN_FINANCE_CENTER_ROOT}/${suffix}`) || config.includes(`MUMAREN_FINANCE_CENTER_ROOT}/\\${suffix}`))
  }
  assert.doesNotMatch(api, /FormalLedger|HistoricalFinance|\/api\/v1\/finance\/(?!center\/mumaren)/)
})

test('财务利润保留旧菜单并将独立财务中心置于首项', () => {
  const layout = read('src', 'layouts', 'MainLayout.vue')
  assert.match(layout, /import\s+\{\s*financeProfitNavigation\s*\}\s+from\s+['\"]@\/config\/financeCenterModules['\"]/) 
  assert.match(layout, /import\s+\{\s*mumarenFinanceCenterMenuItem\s*\}\s+from\s+['\"]@\/config\/mumarenFinanceCenter['\"]/) 
  assert.match(layout, /items:\s*\[mumarenFinanceCenterMenuItem,\s*\.\.\.financeProfitNavigation\]/)
})

test('牧马人财务中心 API 只指向独立后端命名空间', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  assert.match(api, /\/api\/v1\/finance-center\/mumaren/)
  assert.doesNotMatch(api, /\/api\/v1\/finance(?!-center\/mumaren)/)
  assert.doesNotMatch(api, /financeCenterModules|FormalLedger|HistoricalFinance/)
})

test('牧马人财务中心前端入口只使用新模块访问权限', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')

  assert.match(config, /permission:\s*['"]mumaren_finance_center:access['"]/) 
  assert.match(router, /\["\/app\/finance-center\/mumaren", "mumaren_finance_center:access"\]/)
  assert.doesNotMatch(router, /\["\/app\/finance-center\/mumaren", "finance:center:view"\]/)
})

test('牧马人财务中心页面不展示已禁用的上传和自动过账能力', () => {
  const shell = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceCenterShell.vue')
  assert.match(shell, /历史数据只读/)
  assert.doesNotMatch(shell, /上传附件|自动过账/)
})

test('已存在的独立财务 API 必须被工作台、账簿、凭证、报表和历史页面实际使用', () => {
  for (const page of [
    'MumarenFinanceWorkspace.vue',
    'MumarenFinanceVouchers.vue',
    'MumarenFinanceLedgers.vue',
    'MumarenFinanceReports.vue',
    'MumarenFinanceHistory.vue',
  ]) {
    const source = read('src', 'views', 'mumaren-finance-center', page)
    assert.match(source, /mumarenFinanceCenterApi/)
    assert.doesNotMatch(source, /@\/api\/financeCenter|@\/api\/kingdeeFinance|FormalLedger|HistoricalFinance/)
  }
})

test('应收应付与税务页面只读取牧马人独立端点，且不提供写入操作', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const arAp = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const tax = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTax.vue')

  assert.match(api, /\/ar-ap\/aging/)
  assert.match(api, /\/tax\/alerts/)
  assert.match(api, /\/tax\/records/)
  assert.match(arAp, /getArApAging/)
  assert.match(tax, /getTaxAlerts/)
  assert.match(tax, /listTaxRecords/)
  assert.doesNotMatch(`${arAp}\n${tax}`, /\.post\(|\.put\(|\.delete\(/)
})

test('税务 API 必须接收并传递 book_id，后端按账簿隔离查询', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  // getTaxAlerts 与 listTaxRecords 必须接收 book_id 并作为 query 参数传递
  assert.match(api, /getTaxAlerts:\s*\(params:\s*\{\s*book_id:\s*number[\s\S]*?\}\s*\)\s*=>/)
  assert.match(api, /listTaxRecords:\s*\(params:\s*\{\s*book_id:\s*number[\s\S]*?\}\s*\)\s*=>/)
})

test('税务页面必须先选择独立账簿，无账簿时不请求后端并提示', () => {
  const tax = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTax.vue')

  // 必须有账簿选择器
  assert.match(tax, /listBooks/)
  assert.match(tax, /bookId/)
  // 无账簿时必须显示提示，且不调用税务接口
  assert.match(tax, /请选择账簿|请选择独立账簿/)
  // 调用税务接口时必须传 book_id
  assert.match(tax, /getTaxAlerts\(\s*\{\s*book_id:\s*bookId/)
  assert.match(tax, /listTaxRecords\(\s*\{\s*book_id:\s*bookId/)
  // 不允许在未选账簿时 onMounted 直接调用税务接口
  assert.doesNotMatch(tax, /onMounted\(load\)/)
  // onMounted 内不允许自动选择第一个账簿(用户必须主动选择)
  assert.doesNotMatch(tax, /books\.value\[0\]\?\.id/)
  // onMounted 回调内不允许调用 load()(只能在用户主动点击查询时触发)
  assert.doesNotMatch(tax, /onMounted\(async\s*\(\)\s*=>\s*\{[\s\S]*?await\s+load\(\)/)
})
