const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const frontendRoot = path.resolve(__dirname, '..')
const read = (...parts) => fs.readFileSync(path.join(frontendRoot, ...parts), 'utf8')

test('牧马人财务中心拥有独立前端入口和五个导航页面', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')

  assert.match(config, /MUMAREN_FINANCE_CENTER_ROOT\s*=\s*['\"]\/app\/finance-center\/mumaren['\"]/)
  for (const section of ['工作台', '凭证', '账簿', '报表', '历史归档']) {
    assert.match(config, new RegExp(`title:\\s*['\"]${section}['\"]`))
  }
  assert.match(router, /\/app\/finance-center\/mumaren/)
  assert.match(router, /mumaren-finance-center/)
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
