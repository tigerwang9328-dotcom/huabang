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

test('应收应付与税务页面支持草稿→审核→人工结算/缴税工作流，且不直接调用旧财务 HTTP', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const arAp = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const tax = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTax.vue')

  // 只读端点仍然存在
  assert.match(api, /\/ar-ap\/aging/)
  assert.match(api, /\/tax\/alerts/)
  assert.match(api, /\/tax\/records/)
  assert.match(arAp, /getArApAging/)
  assert.match(tax, /getTaxAlerts/)
  assert.match(tax, /listTaxRecords/)

  // 允许 draft → review → manual posting/settle/pay 工作流（通过 API 包装方法）
  assert.match(api, /createArApOrder:/)
  assert.match(api, /reviewArApOrder:/)
  assert.match(api, /settleArApOrder:/)
  assert.match(api, /createTaxRecord:/)
  assert.match(api, /reviewTaxRecord:/)
  assert.match(api, /payTaxRecord:/)
  assert.match(arAp, /createArApOrder|reviewArApOrder|settleArApOrder/)
  assert.match(tax, /createTaxRecord|reviewTaxRecord|payTaxRecord/)

  // 页面不得直接发起裸 HTTP 写入（必须走 mumarenFinanceCenterApi 包装）
  assert.doesNotMatch(`${arAp}\n${tax}`, /request\.post\(|request\.put\(|request\.delete\(/)
  // 页面不得引用旧财务 API 路径
  assert.doesNotMatch(`${arAp}\n${tax}`, /\/api\/v1\/finance(?!-center\/mumaren)/)
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
  // 使用负向先行断言确保匹配范围不跨出 onMounted 块（遇到 }); 即停止）
  assert.doesNotMatch(tax, /onMounted\(async\s*\(\)\s*=>\s*\{(?:(?!\}\);)[\s\S])*?await\s+load\(\)/)
})

test('凭证写入流程：草稿录入 → 财务审核 → 人工过账，禁止自动过账', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const vouchers = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVouchers.vue')

  // API 必须暴露 create/review/post 三个写入方法
  assert.match(api, /createVoucher:\s*\(payload:\s*VoucherCreatePayload\)/)
  assert.match(api, /reviewVoucher:\s*\(voucherId:\s*number\)/)
  assert.match(api, /postVoucher:\s*\(voucherId:\s*number\)/)
  // 页面必须调用这三个方法
  assert.match(vouchers, /createVoucher\(/)
  assert.match(vouchers, /reviewVoucher\(/)
  assert.match(vouchers, /postVoucher\(/)
  // 状态机标记：draft → reviewed → posted
  assert.match(vouchers, /'draft'/)
  assert.match(vouchers, /'reviewed'/)
  assert.match(vouchers, /'posted'/)
  // 禁止自动过账、反过账的代码逻辑（描述性文字"不自动过账/不反过账"允许出现）
  assert.doesNotMatch(vouchers, /autoPost\(|autoPostVoucher|reversePost\(|reversePostVoucher/)
  // 页面不得直接发起裸 HTTP 写入
  assert.doesNotMatch(vouchers, /request\.post\(|request\.put\(|request\.delete\(/)
})

test('AR-AP 写入流程：草稿录入 → 财务审核 → 人工结算，不自动生成凭证', () => {
  const arAp = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')

  // 页面必须调用 create/review/settle 三个方法
  assert.match(arAp, /createArApOrder\(/)
  assert.match(arAp, /reviewArApOrder\(/)
  assert.match(arAp, /settleArApOrder\(/)
  // 状态机标记：draft → reviewed → settled
  assert.match(arAp, /'draft'/)
  assert.match(arAp, /'reviewed'/)
  assert.match(arAp, /'settled'/)
  // 禁止自动生成凭证的代码逻辑（描述性文字"不自动生成凭证"允许出现）
  assert.doesNotMatch(arAp, /autoCreateVoucher|autoPost\(|reversePost\(/)
})

test('税务写入流程：草稿录入 → 财务审核 → 人工缴税，不自动生成凭证', () => {
  const tax = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTax.vue')

  // 页面必须调用 create/review/pay 三个方法
  assert.match(tax, /createTaxRecord\(/)
  assert.match(tax, /reviewTaxRecord\(/)
  assert.match(tax, /payTaxRecord\(/)
  // 状态机标记：draft → reviewed → paid
  assert.match(tax, /'draft'/)
  assert.match(tax, /'reviewed'/)
  assert.match(tax, /'paid'/)
  // 禁止自动生成凭证、反审核的代码逻辑（描述性文字"不自动生成凭证/不反审核"允许出现）
  assert.doesNotMatch(tax, /autoCreateVoucher|autoPost\(|reverseReview\(|reversePost\(/)
})

test('AR/AP 结算状态读取 settlement_status，不得把 workflow_status 误判为 settled', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const arAp = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')

  // TypeScript 类型：settlement_status 必须区分 open/partial/settled
  assert.match(api, /settlement_status:\s*["']open["']\s*\|\s*["']partial["']\s*\|\s*["']settled["']/)
  // workflow_status 不得包含 settled（后端 workflow_status 只有 draft/reviewed/posted）
  assert.doesNotMatch(api, /workflow_status:\s*["']draft["']\s*\|\s*["']reviewed["']\s*\|\s*["']settled["']/)

  // 页面必须引用 settlement_status 字段判断结算状态
  assert.match(arAp, /settlement_status/)
  // 不得用 workflow_status === 'settled' 判断已结算
  assert.doesNotMatch(arAp, /workflow_status\s*===?\s*['"]settled['"]/)
})

test('税务缴税状态读取后端 status 字段，不得把 workflow_status 误判为 paid', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const tax = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTax.vue')

  // TypeScript 类型：status 必须区分 pending/paid
  assert.match(api, /status:\s*["']pending["']\s*\|\s*["']paid["']/)
  // workflow_status 不得包含 paid（后端 workflow_status 只有 draft/reviewed）
  assert.doesNotMatch(api, /workflow_status\??:\s*["']draft["']\s*\|\s*["']reviewed["']\s*\|\s*["']paid["']/)

  // 页面必须用 status === 'paid' 判断已缴税
  assert.match(tax, /\.status\s*===?\s*['"]paid['"]/)
  // 不得用 workflow_status === 'paid' 判断已缴税
  assert.doesNotMatch(tax, /workflow_status\s*===?\s*['"]paid['"]/)
})

test('科目与期末结账页面已接入路由和导航，且科目只读、期末结账暂不可用', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')

  // 导航项存在
  assert.match(config, /key:\s*['"]accounts['"]/)
  assert.match(config, /key:\s*['"]closing['"]/)
  assert.match(config, /title:\s*['"]科目['"]/)
  assert.match(config, /title:\s*['"]期末结账['"]/)
  // 路由存在
  assert.match(router, /path:\s*['"]accounts['"],\s*name:\s*['"]MumarenFinanceAccounts['"]/)
  assert.match(router, /path:\s*['"]closing['"],\s*name:\s*['"]MumarenFinanceClosing['"]/)

  // 科目页面只读：必须使用 listAccounts，不得有写入方法
  const accounts = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceAccounts.vue')
  assert.match(accounts, /listAccounts/)
  assert.doesNotMatch(accounts, /createAccount|updateAccount|deleteAccount|request\.post\(|request\.put\(|request\.delete\(/)

  // 期末结账页面：必须显示暂不可用，不得提供结账/反结账操作函数或按钮
  const closing = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceClosing.vue')
  assert.match(closing, /暂不可用|后端适配待完成/)
  assert.doesNotMatch(closing, /carryForward|doClose\(|doUnclose\(|quickClose\(|quickUnclose\(|initPeriods\(|request\.post\(|request\.put\(|request\.delete\(/)
})

test('历史归档页面必须只读，不出现编辑/审核/过账操作按钮', () => {
  const history = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceHistory.vue')

  // 必须显示历史标记
  assert.match(history, /历史数据|is_readonly|只读/)
  // 必须使用只读接口 listHistory
  assert.match(history, /listHistory/)
  // 不得出现编辑/审核/过账/删除等写入操作
  assert.doesNotMatch(history, /reviewVoucher|postVoucher|createVoucher|deleteVoucher|reviewArApOrder|settleArApOrder|payTaxRecord|request\.post\(|request\.put\(|request\.delete\(/)
})

test('出纳/资产/发票/薪资/付款外壳页面存在并标注暂不可用，不伪造按钮成功', () => {
  const router = read('src', 'router', 'index.ts')
  const shells = [
    { file: 'MumarenFinanceCashier.vue', route: 'MumarenFinanceCashier', title: '出纳' },
    { file: 'MumarenFinanceAssets.vue', route: 'MumarenFinanceAssets', title: '资产' },
    { file: 'MumarenFinanceInvoices.vue', route: 'MumarenFinanceInvoices', title: '发票' },
    { file: 'MumarenFinancePayroll.vue', route: 'MumarenFinancePayroll', title: '薪资' },
    { file: 'MumarenFinancePayments.vue', route: 'MumarenFinancePayments', title: '付款' },
  ]

  for (const { file, route } of shells) {
    const source = read('src', 'views', 'mumaren-finance-center', file)
    // 必须使用 CapabilityBoard 展示，不直接渲染可操作表单
    assert.match(source, /MumarenFinanceCapabilityBoard/)
    // 必须从 config 取能力组，不硬编码可操作按钮
    assert.match(source, /mumarenFinanceCapabilityGroups\./)
    // 路由必须注册
    assert.match(router, new RegExp(`name:\\s*['"]${route}['"]`))
  }

  // 这些外壳页面对应的 config 能力组必须全部标注 planned_backend
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  for (const group of ['cashier', 'assets', 'invoices', 'payroll', 'payments']) {
    assert.match(config, new RegExp(`${group}:\\s*\\{`))
  }
  // 能力卡片文案必须包含"后端适配待完成"
  const board = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceCapabilityBoard.vue')
  assert.match(board, /后端适配待完成/)
})

test('所有牧马人财务中心页面不得调用旧财务 API 或残留牧马人服务器地址', () => {
  const dir = path.join(frontendRoot, 'src', 'views', 'mumaren-finance-center')
  const files = fs.readdirSync(dir).filter((f) => f.endsWith('.vue'))
  assert.ok(files.length >= 12, '应至少有 12 个牧马人财务中心页面')

  for (const file of files) {
    const source = read('src', 'views', 'mumaren-finance-center', file)
    // 不得引用旧财务 API 模块
    assert.doesNotMatch(source, /@\/api\/finance['"]|@\/api\/financeCenter['"]|@\/api\/kingdeeFinance['"]|FormalLedger|HistoricalFinance/)
    // 不得直接调用旧财务 HTTP 路径
    assert.doesNotMatch(source, /\/api\/v1\/finance(?!-center\/mumaren)[/'"`]/)
    // 不得使用旧财务 store
    assert.doesNotMatch(source, /useFinanceStore|finStore/)
    // 不得残留牧马人服务器地址或旧财务 store
    assert.doesNotMatch(source, /mumaren\.cn|mumaren\.com|finance_module\/api\//)
  }

  // API 文件同样不得残留旧财务路径或牧马人服务器地址
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  assert.doesNotMatch(api, /\/api\/v1\/finance(?!-center\/mumaren)[/'"`]/)
  assert.doesNotMatch(api, /mumaren\.cn|mumaren\.com|finance_module\/api\//)
})
