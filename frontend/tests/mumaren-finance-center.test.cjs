const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const frontendRoot = path.resolve(__dirname, '..')
const read = (...parts) => fs.readFileSync(path.join(frontendRoot, ...parts), 'utf8')

// ─────────────────────────────────────────────────────────────
// 标准财务中心导航:13 个一级条目 + 22 个子项(共 35 个 navItem)
// ─────────────────────────────────────────────────────────────
const STANDARD_TOP_LEVEL = [
  '数据罗盘', '历史数据存档', '凭证', '账簿', '报表', '应收应付',
  '结账', '资产', '发票', '出纳', '工资', '税务', '设置',
]

const STANDARD_CHILDREN = {
  '凭证': ['录凭证', '查凭证', '凭证汇总', '凭证模板', '自动凭证'],
  '账簿': ['总账', '科目余额表', '明细账'],
  '报表': ['资产负债表', '利润表', '现金流量表', '应收明细', '应付明细', '费用明细表', '税金明细表', '销售月报表'],
  '出纳': ['账户与流水', '银行余额调节表'],
  '设置': ['科目管理', '账套管理', '辅助核算', '操作日志'],
}

test('财务中心导航结构匹配标准导航:13 个一级条目 + 22 个子项', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')

  // 一级条目
  for (const title of STANDARD_TOP_LEVEL) {
    assert.match(config, new RegExp(`title:\\s*['"]${title}['"]`))
  }
  // 子项
  for (const children of Object.values(STANDARD_CHILDREN)) {
    for (const title of children) {
      assert.match(config, new RegExp(`title:\\s*['"]${title}['"]`))
    }
  }
  // 一级条目数量校验:13 个一级 + 22 个子项 = 至少 35 个 title 字段
  const allTitleMatches = config.match(/title:\s*['"][^'"]+['"]/g) || []
  assert.ok(allTitleMatches.length >= 35, `导航配置应至少有 35 个 title 字段(13 一级 + 22 子项),实际 ${allTitleMatches.length}`)
})

test('所有导航项 availability 全部为 available,无 planned_backend 占位项', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')

  // 所有 availability 必须为 available
  assert.match(config, /availability:\s*['"]available['"]/)
  // 不允许再有 planned_backend 占位项
  assert.doesNotMatch(config, /availability:\s*['"]planned_backend['"]/)
  // 不允许再有 placeholder 字段
  assert.doesNotMatch(config, /placeholder:\s*\{/)
  // mumarenFinanceCenterMenuItem 不允许再有 badge: "待适配"
  assert.doesNotMatch(config, /badge:\s*['"]待适配['"]/)
})

test('19 个原占位页路由全部指向新组件,不再指向 Placeholder', () => {
  const router = read('src', 'router', 'index.ts')

  // 路由不允许再引用 MumarenFinancePlaceholder.vue
  assert.doesNotMatch(router, /MumarenFinancePlaceholder\.vue/)
  // 路由不允许再有 meta.placeholderKey
  assert.doesNotMatch(router, /placeholderKey/)

  // 19 个原占位页必须指向各自新组件
  const componentMappings = [
    ['MumarenFinanceCompass', 'MumarenFinanceCompass.vue'],
    ['MumarenFinanceVoucherSummary', 'MumarenFinanceVoucherSummary.vue'],
    ['MumarenFinanceVoucherTemplate', 'MumarenFinanceVoucherTemplate.vue'],
    ['MumarenFinanceVoucherAuto', 'MumarenFinanceVoucherAuto.vue'],
    ['MumarenFinanceLedgerDetail', 'MumarenFinanceLedgerDetail.vue'],
    ['MumarenFinanceBalanceSheet', 'MumarenFinanceReportBalanceSheet.vue'],
    ['MumarenFinanceCashFlowStatement', 'MumarenFinanceReportCashFlow.vue'],
    ['MumarenFinanceReceivableDetail', 'MumarenFinanceReportReceivable.vue'],
    ['MumarenFinancePayableDetail', 'MumarenFinanceReportPayable.vue'],
    ['MumarenFinanceExpenseDetail', 'MumarenFinanceReportExpense.vue'],
    ['MumarenFinanceSalesMonthly', 'MumarenFinanceReportSalesMonthly.vue'],
    ['MumarenFinanceClosing', 'MumarenFinanceClosing.vue'],
    ['MumarenFinanceAssets', 'MumarenFinanceAssets.vue'],
    ['MumarenFinanceInvoices', 'MumarenFinanceInvoices.vue'],
    ['MumarenFinanceCashierAccounts', 'MumarenFinanceCashierAccounts.vue'],
    ['MumarenFinanceCashierReconciliation', 'MumarenFinanceCashierReconciliation.vue'],
    ['MumarenFinancePayroll', 'MumarenFinancePayroll.vue'],
    ['MumarenFinanceSettingsAuxiliary', 'MumarenFinanceSettingsAuxiliary.vue'],
    ['MumarenFinanceSettingsAuditLogs', 'MumarenFinanceSettingsAuditLogs.vue'],
  ]
  for (const [routeName, component] of componentMappings) {
    const pattern = new RegExp(`name:\\s*['"]${routeName}['"],\\s*component:\\s*\\(\\)\\s*=>\\s*import\\(['"][^'"]*${component}['"]\\)`)
    assert.match(router, pattern, `路由 ${routeName} 必须指向组件 ${component}`)
  }
})

test('12 个 CRUD 页面不再显示"会话内数据刷新清空"黄色横幅,改为调用真实 API', () => {
  const crudPages = [
    'MumarenFinanceVoucherTemplate.vue',
    'MumarenFinanceVoucherAuto.vue',
    'MumarenFinanceReportExpense.vue',
    'MumarenFinanceReportSalesMonthly.vue',
    'MumarenFinanceClosing.vue',
    'MumarenFinanceAssets.vue',
    'MumarenFinanceInvoices.vue',
    'MumarenFinanceCashierAccounts.vue',
    'MumarenFinanceCashierReconciliation.vue',
    'MumarenFinancePayroll.vue',
    'MumarenFinanceSettingsAuxiliary.vue',
    'MumarenFinanceSettingsAuditLogs.vue',
  ]
  for (const page of crudPages) {
    const source = read('src', 'views', 'mumaren-finance-center', page)
    // 不得再包含黄色横幅提示
    assert.doesNotMatch(source, /完整数据接口待后端补/, `页面 ${page} 不得包含"完整数据接口待后端补"横幅`)
    assert.doesNotMatch(source, /本会话数据刷新后清空/, `页面 ${page} 不得包含"本会话数据刷新后清空"横幅`)
    // 不得再使用 el-alert type="warning" 作为数据提示横幅
    assert.doesNotMatch(source, /el-alert\s+type="warning"\s+[^>]*title="完整数据接口待后端补"/)
  }
})

test('12 个 CRUD 页面调用正确的 API 方法进行数据持久化', () => {
  const pageApiMap = [
    { file: 'MumarenFinanceAssets.vue', api: 'fixedAssetsApi', methods: ['list', 'create', 'delete'] },
    { file: 'MumarenFinanceInvoices.vue', api: 'invoicesApi', methods: ['list', 'create', 'delete'] },
    { file: 'MumarenFinanceCashierAccounts.vue', api: 'cashAccountsApi', methods: ['list', 'create'] },
    { file: 'MumarenFinanceCashierReconciliation.vue', api: 'bankReconciliationsApi', methods: ['list', 'create', 'delete'] },
    { file: 'MumarenFinancePayroll.vue', api: 'payrollsApi', methods: ['list', 'create', 'delete'] },
    { file: 'MumarenFinanceClosing.vue', api: 'periodsApi', methods: ['list', 'close', 'reopen'] },
    { file: 'MumarenFinanceSettingsAuditLogs.vue', api: 'auditLogsApi', methods: ['list'] },
    { file: 'MumarenFinanceVoucherTemplate.vue', api: 'voucherTemplatesApi', methods: ['list', 'create', 'delete'] },
    { file: 'MumarenFinanceVoucherAuto.vue', api: 'autoVoucherRulesApi', methods: ['list', 'create', 'delete'] },
    { file: 'MumarenFinanceReportExpense.vue', api: 'expenseEntriesApi', methods: ['list', 'create', 'delete'] },
    { file: 'MumarenFinanceReportSalesMonthly.vue', api: 'salesMonthlyReportsApi', methods: ['list', 'create', 'delete'] },
    { file: 'MumarenFinanceSettingsAuxiliary.vue', api: 'auxiliaryAccountingsApi', methods: ['list', 'create', 'delete'] },
  ]
  for (const { file, api, methods } of pageApiMap) {
    const source = read('src', 'views', 'mumaren-finance-center', file)
    // 必须导入对应的 API 客户端
    assert.match(source, new RegExp(api), `页面 ${file} 必须导入 ${api}`)
    // 必须调用指定的方法
    for (const method of methods) {
      assert.match(source, new RegExp(`${api}\\.${method}\\(`), `页面 ${file} 必须调用 ${api}.${method}()`)
    }
    // 不得直接使用 request.post/put/delete 裸 HTTP 调用
    assert.doesNotMatch(source, /request\.post\(|request\.put\(|request\.delete\(/, `页面 ${file} 不得直接使用裸 HTTP 写入`)
  }
})

test('派生展示类页面调用已有 API,不新增后端接口', () => {
  const derivedPages = [
    { file: 'MumarenFinanceCompass.vue', apis: ['listBooks', 'getTrialBalance', 'getProfitStatement'] },
    { file: 'MumarenFinanceVoucherSummary.vue', apis: ['listBooks', 'listVouchers'] },
    { file: 'MumarenFinanceLedgerDetail.vue', apis: ['listBooks', 'listAccounts', 'listVouchers'] },
    { file: 'MumarenFinanceReportBalanceSheet.vue', apis: ['listBooks', 'getTrialBalance'] },
    { file: 'MumarenFinanceReportCashFlow.vue', apis: ['listBooks', 'getTrialBalance'] },
    { file: 'MumarenFinanceReportReceivable.vue', apis: ['listBooks', 'getArApAging'] },
    { file: 'MumarenFinanceReportPayable.vue', apis: ['listBooks', 'getArApAging'] },
  ]
  for (const { file, apis } of derivedPages) {
    const source = read('src', 'views', 'mumaren-finance-center', file)
    for (const api of apis) {
      assert.match(source, new RegExp(api), `页面 ${file} 必须调用 API ${api}`)
    }
    // 不得调用旧财务 API
    assert.doesNotMatch(source, /\/api\/v1\/finance(?!-center\/mumaren)/)
  }
})

test('CapabilityBoard 展示真实接入状态,不伪装可操作功能', () => {
  const board = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceCapabilityBoard.vue')

  assert.match(board, /后端适配待完成/)
  assert.match(board, /不可录入|不可操作|不可查询/)
  assert.doesNotMatch(board, /自动过账/)
})

test('路由配置与导航项一一对应,所有路由均注册', () => {
  const router = read('src', 'router', 'index.ts')

  // 一级路由名
  const topRoutes = [
    'MumarenFinanceCompass', 'MumarenFinanceHistory',
    'MumarenFinanceArAp', 'MumarenFinanceClosing',
    'MumarenFinanceAssets', 'MumarenFinanceInvoices',
    'MumarenFinancePayroll', 'MumarenFinanceTax',
  ]
  for (const name of topRoutes) {
    assert.match(router, new RegExp(`name:\\s*['"]${name}['"]`))
  }

  // 子项路由名
  const childRoutes = [
    'MumarenFinanceVoucherCreate', 'MumarenFinanceVoucherList',
    'MumarenFinanceVoucherSummary', 'MumarenFinanceVoucherTemplate', 'MumarenFinanceVoucherAuto',
    'MumarenFinanceGeneralLedger', 'MumarenFinanceTrialBalance', 'MumarenFinanceLedgerDetail',
    'MumarenFinanceBalanceSheet', 'MumarenFinanceProfitStatement', 'MumarenFinanceCashFlowStatement',
    'MumarenFinanceReceivableDetail', 'MumarenFinancePayableDetail', 'MumarenFinanceExpenseDetail',
    'MumarenFinanceTaxDetail', 'MumarenFinanceSalesMonthly',
    'MumarenFinanceCashierAccounts', 'MumarenFinanceCashierReconciliation',
    'MumarenFinanceSettingsAccounts', 'MumarenFinanceSettingsBooks',
    'MumarenFinanceSettingsAuxiliary', 'MumarenFinanceSettingsAuditLogs',
  ]
  for (const name of childRoutes) {
    assert.match(router, new RegExp(`name:\\s*['"]${name}['"]`))
  }
})

test('财务中心入口在主菜单首项,并使用独立访问权限', () => {
  const layout = read('src', 'layouts', 'MainLayout.vue')
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')

  assert.match(layout, /import\s+\{\s*financeProfitNavigation\s*\}\s+from\s+['"]@\/config\/financeCenterModules['"]/)
  assert.match(layout, /import\s+\{\s*mumarenFinanceCenterMenuItem\s*\}\s+from\s+['"]@\/config\/mumarenFinanceCenter['"]/)
  assert.match(layout, /items:\s*\[mumarenFinanceCenterMenuItem,\s*\.\.\.financeProfitNavigation\]/)

  assert.match(config, /permission:\s*['"]mumaren_finance_center:access['"]/)
  assert.match(router, /\["\/app\/finance-center\/mumaren", "mumaren_finance_center:access"\]/)
  assert.doesNotMatch(router, /\["\/app\/finance-center\/mumaren", "finance:center:view"\]/)
})

test('mumarenFinanceCenterMenuItem 带 children(13个一级条目),不再直接跳转', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')

  // 必须有 children,不再有 path
  assert.match(config, /mumarenFinanceCenterMenuItem[^=]*=\s*\{[\s\S]*?children:\s*\[/)
  // 13个一级条目
  for (const title of STANDARD_TOP_LEVEL) {
    assert.match(config, new RegExp(`label:\\s*['"]${title}['"]`))
  }
})

test('MainLayout 模板支持第4级菜单(submenu-list-3)', () => {
  const layout = read('src', 'layouts', 'MainLayout.vue')

  // 必须有第4级渲染逻辑
  assert.match(layout, /submenu-list-3/)
  assert.match(layout, /nav-parent-3/)
  assert.match(layout, /nav-sub-3/)
  // expandActiveMenuPath 必须展开第3级
  assert.match(layout, /展开第3级中包含活跃路由的节点/)
})

test('财务中心 API 只指向独立后端命名空间 /api/v1/finance-center/mumaren', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  assert.match(api, /\/api\/v1\/finance-center\/mumaren/)
  assert.doesNotMatch(api, /\/api\/v1\/finance(?!-center\/mumaren)/)
  assert.doesNotMatch(api, /financeCenterModules|FormalLedger|HistoricalFinance|kingdeeFinance/)
  assert.doesNotMatch(api, /mumaren\.cn|mumaren\.com|finance_module\/api\//)
})

test('Shell 组件仅渲染内容区,不含 aside 侧边栏(导航已集成到主侧边栏)', () => {
  const shell = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceCenterShell.vue')

  // 必须有 router-view 渲染内容
  assert.match(shell, /router-view/)
  // 不得包含 aside 侧边栏
  assert.doesNotMatch(shell, /finance-center-sidebar|nav-list|nav-group-toggle|openGroups/)
  // 历史数据只读
  assert.match(shell, /历史数据只读/)
  // 不展示已禁用的上传和自动过账能力
  assert.doesNotMatch(shell, /上传附件|自动过账/)
})

test('凭证写入流程:草稿录入 → 财务审核 → 人工过账(录凭证/查凭证拆分页面)', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const create = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherCreate.vue')
  const list = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherList.vue')

  // API 必须暴露 create/review/post 三个写入方法
  assert.match(api, /createVoucher:\s*\(payload:\s*VoucherCreatePayload\)/)
  assert.match(api, /reviewVoucher:\s*\(voucherId:\s*number\)/)
  assert.match(api, /postVoucher:\s*\(voucherId:\s*number\)/)

  // 录凭证页面必须调用 createVoucher
  assert.match(create, /createVoucher\(/)
  assert.match(create, /mumarenFinanceCenterApi/)
  // 查凭证页面必须调用 review/post(列表页提供审核/过账操作)
  assert.match(list, /reviewVoucher\(|postVoucher\(/)
  assert.match(list, /mumarenFinanceCenterApi/)

  // 状态机标记:draft → reviewed → posted
  const combined = `${create}\n${list}`
  assert.match(combined, /'draft'/)
  assert.match(combined, /'reviewed'/)
  assert.match(combined, /'posted'/)

  // 禁止自动过账、反过账的代码逻辑
  assert.doesNotMatch(combined, /autoPost\(|autoPostVoucher|reversePost\(|reversePostVoucher/)
  // 页面不得直接发起裸 HTTP 写入
  assert.doesNotMatch(combined, /request\.post\(|request\.put\(|request\.delete\(/)
})

test('AR-AP 写入流程:草稿录入 → 财务审核 → 人工结算,不自动生成凭证', () => {
  const arAp = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')

  assert.match(arAp, /createArApOrder\(/)
  assert.match(arAp, /reviewArApOrder\(/)
  assert.match(arAp, /settleArApOrder\(/)
  assert.match(arAp, /'draft'/)
  assert.match(arAp, /'reviewed'/)
  assert.match(arAp, /'settled'/)
  assert.doesNotMatch(arAp, /autoCreateVoucher|autoPost\(|reversePost\(/)
})

test('AR/AP 订单列表从后端持久化加载,不再使用 sessionOrders 会话数组', () => {
  const arAp = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')

  // 不得再使用 sessionOrders 会话数组
  assert.doesNotMatch(arAp, /sessionOrders/, 'AR/AP 页面不得再使用 sessionOrders 会话数组')
  // 不得再有 updateSessionOrder 工具方法
  assert.doesNotMatch(arAp, /updateSessionOrder/, 'AR/AP 页面不得再有 updateSessionOrder')
  // 不得再显示"完整订单列表接口待后端补"提示
  assert.doesNotMatch(arAp, /完整订单列表接口待后端补|刷新后列表清空/, 'AR/AP 页面不得再有会话清空提示')
  // 不得再显示"本会话单据"
  assert.doesNotMatch(arAp, /本会话单据/, 'AR/AP 页面不得再有"本会话单据"字样')
  // 必须调用 arApOrdersApi.list 从后端加载订单
  assert.match(arAp, /arApOrdersApi\.list\(/, 'AR/AP 页面必须调用 arApOrdersApi.list() 加载订单')
  // 必须调用 arApOrdersApi.delete 支持删除
  assert.match(arAp, /arApOrdersApi\.delete\(/, 'AR/AP 页面必须调用 arApOrdersApi.delete() 删除订单')
})

test('税务写入流程:草稿录入 → 财务审核 → 人工缴税,不自动生成凭证', () => {
  const tax = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTax.vue')

  assert.match(tax, /createTaxRecord\(/)
  assert.match(tax, /reviewTaxRecord\(/)
  assert.match(tax, /payTaxRecord\(/)
  assert.match(tax, /'draft'/)
  assert.match(tax, /'reviewed'/)
  assert.match(tax, /'paid'/)
  assert.doesNotMatch(tax, /autoCreateVoucher|autoPost\(|reverseReview\(|reversePost\(/)
})

test('AR/AP 结算状态读取 settlement_status,不得把 workflow_status 误判为 settled', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const arAp = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')

  assert.match(api, /settlement_status:\s*["']open["']\s*\|\s*["']partial["']\s*\|\s*["']settled["']/)
  assert.doesNotMatch(api, /workflow_status:\s*["']draft["']\s*\|\s*["']reviewed["']\s*\|\s*["']settled["']/)
  assert.match(arAp, /settlement_status/)
  assert.doesNotMatch(arAp, /workflow_status\s*===?\s*['"]settled['"]/)
})

test('税务缴税状态读取后端 status 字段,不得把 workflow_status 误判为 paid', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const tax = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTax.vue')

  assert.match(api, /status:\s*["']pending["']\s*\|\s*["']paid["']/)
  assert.doesNotMatch(api, /workflow_status\??:\s*["']draft["']\s*\|\s*["']reviewed["']\s*\|\s*["']paid["']/)
  assert.match(tax, /\.status\s*===?\s*['"]paid['"]/)
  assert.doesNotMatch(tax, /workflow_status\s*===?\s*['"]paid['"]/)
})

test('税务 API 必须接收并传递 book_id,后端按账簿隔离查询', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  assert.match(api, /getTaxAlerts:\s*\(params:\s*\{\s*book_id:\s*number[\s\S]*?\}\s*\)\s*=>/)
  assert.match(api, /listTaxRecords:\s*\(params:\s*\{\s*book_id:\s*number[\s\S]*?\}\s*\)\s*=>/)
})

test('税务页面必须先选择独立账簿,无账簿时不请求后端并提示', () => {
  const tax = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTax.vue')

  assert.match(tax, /listBooks/)
  assert.match(tax, /bookId/)
  assert.match(tax, /请选择独立账簿/)
  assert.match(tax, /getTaxAlerts\(\s*\{\s*book_id:\s*bookId/)
  assert.match(tax, /listTaxRecords\(\s*\{\s*book_id:\s*bookId/)
  // 不允许在未选账簿时 onMounted 直接调用税务接口
  assert.doesNotMatch(tax, /onMounted\(load\)/)
  assert.doesNotMatch(tax, /books\.value\[0\]\?\.id/)
  assert.doesNotMatch(tax, /onMounted\(async\s*\(\)\s*=>\s*\{(?:(?!\}\);)[\s\S])*?await\s+load\(\)/)
})

test('科目管理与账套管理页面只读,期末结账与辅助核算已持久化', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')

  // 设置下的子项
  assert.match(config, /key:\s*['"]settings-accounts['"]/)
  assert.match(config, /key:\s*['"]settings-books['"]/)
  assert.match(config, /key:\s*['"]settings-auxiliary['"]/)
  assert.match(config, /key:\s*['"]settings-audit-logs['"]/)
  assert.match(config, /title:\s*['"]科目管理['"]/)
  assert.match(config, /title:\s*['"]账套管理['"]/)
  assert.match(config, /title:\s*['"]辅助核算['"]/)
  assert.match(config, /title:\s*['"]操作日志['"]/)
  // 路由存在
  assert.match(router, /name:\s*['"]MumarenFinanceSettingsAccounts['"]/)
  assert.match(router, /name:\s*['"]MumarenFinanceSettingsBooks['"]/)
  assert.match(router, /name:\s*['"]MumarenFinanceSettingsAuxiliary['"]/)
  assert.match(router, /name:\s*['"]MumarenFinanceSettingsAuditLogs['"]/)

  // 科目页面只读
  const accounts = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceAccounts.vue')
  assert.match(accounts, /listAccounts/)
  assert.doesNotMatch(accounts, /createAccount|updateAccount|deleteAccount|request\.post\(|request\.put\(|request\.delete\(/)

  // 期末结账:已改为持久化 CRUD 页面,指向新组件 MumarenFinanceClosing.vue
  assert.match(router, /path:\s*['"]closing['"],\s*name:\s*['"]MumarenFinanceClosing['"],\s*component:\s*\(\)\s*=>\s*import\(['"][^'"]*MumarenFinanceClosing\.vue['"]\),\s*meta:\s*\{\s*title:\s*['"]结账['"]\s*\}/)
  // 期末结账页面不再有会话内 CRUD 提示,改为调用 periodsApi
  const closing = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceClosing.vue')
  assert.doesNotMatch(closing, /完整数据接口待后端补/, '结账页面不得再有黄色横幅')
  assert.doesNotMatch(closing, /本会话数据刷新后清空/, '结账页面不得再有会话清空提示')
  assert.match(closing, /periodsApi/, '结账页面必须调用 periodsApi')
})

test('历史归档页面必须只读,不出现编辑/审核/过账操作按钮', () => {
  const history = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceHistory.vue')

  assert.match(history, /历史数据|is_readonly|只读/)
  assert.match(history, /listHistory/)
  assert.doesNotMatch(history, /reviewVoucher|postVoucher|createVoucher|deleteVoucher|reviewArApOrder|settleArApOrder|payTaxRecord|request\.post\(|request\.put\(|request\.delete\(/)
})

test('利润表与科目余额表页面调用独立报表接口', () => {
  const profit = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportProfit.vue')
  const trial = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportTrialBalance.vue')

  assert.match(profit, /getProfitStatement/)
  assert.match(profit, /mumarenFinanceCenterApi/)
  assert.match(trial, /getTrialBalance/)
  assert.match(trial, /mumarenFinanceCenterApi/)
})

test('税金明细表页面调用税务记录接口(只读展示)', () => {
  const taxRecords = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTaxRecords.vue')

  assert.match(taxRecords, /listTaxRecords|mumarenFinanceCenterApi/)
  // 只读页面,不得有写入操作
  assert.doesNotMatch(taxRecords, /createTaxRecord|reviewTaxRecord|payTaxRecord|request\.post\(|request\.put\(|request\.delete\(/)
})

test('所有牧马人财务中心页面不得调用旧财务 API 或残留牧马人服务器地址', () => {
  const dir = path.join(frontendRoot, 'src', 'views', 'mumaren-finance-center')
  const files = fs.readdirSync(dir).filter((f) => f.endsWith('.vue'))
  assert.ok(files.length >= 13, '应至少有 13 个牧马人财务中心页面')

  for (const file of files) {
    const source = read('src', 'views', 'mumaren-finance-center', file)
    assert.doesNotMatch(source, /@\/api\/finance['"]|@\/api\/financeCenter['"]|@\/api\/kingdeeFinance['"]|FormalLedger|HistoricalFinance/)
    assert.doesNotMatch(source, /\/api\/v1\/finance(?!-center\/mumaren)[/'"`]/)
    assert.doesNotMatch(source, /useFinanceStore|finStore/)
    assert.doesNotMatch(source, /mumaren\.cn|mumaren\.com|finance_module\/api\//)
  }

  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  assert.doesNotMatch(api, /\/api\/v1\/finance(?!-center\/mumaren)[/'"`]/)
  assert.doesNotMatch(api, /mumaren\.cn|mumaren\.com|finance_module\/api\//)
})
