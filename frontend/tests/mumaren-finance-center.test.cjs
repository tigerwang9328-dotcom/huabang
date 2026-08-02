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

test('无金蝶来源的历史页面明确展示只读缺失状态且不提供写入操作', () => {
  const moduleConfig = read('src', 'config', 'financeCenterModules.ts')
  const source = read('src', 'views', 'mumaren-finance-center', 'MumarenFinancePlaceholder.vue')

  assert.match(moduleConfig, /availability:\s*["']historical_source_unavailable["']/)
  assert.match(moduleConfig, /unavailableReason:\s*["']该类历史来源未迁入；历史凭证、余额快照和报表不受影响。["']/)
  assert.match(source, /历史来源未迁入/)
  assert.match(source, /historical_source_unavailable/)
  assert.doesNotMatch(source, /新增|保存|删除/)
})

test('运行时牧马人导航和实际历史账页面消费共享来源缺失状态', () => {
  const navigation = read('src', 'config', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')
  const notice = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceHistoricalSourceNotice.vue')

  assert.match(navigation, /MumarenFinanceCapabilityAvailability\s*=\s*[^;]*["']historical_source_unavailable["']/)
  for (const key of ['ar-ap-receivable', 'ar-ap-payable', 'ar-ap-aging', 'assets', 'invoices', 'cashier-accounts', 'cashier-reconciliation', 'payroll', 'tax']) {
    assert.match(navigation, new RegExp(`key:\\s*["']${key}["'][\\s\\S]{0,240}?availability:\\s*["']historical_source_unavailable["']`))
  }
  assert.match(notice, /isMumarenHistoricalSourceUnavailable/)
  assert.match(notice, /历史来源未迁入/)
  assert.doesNotMatch(notice, /新增|保存|删除/)

  for (const filename of [
    'MumarenFinanceArAp.vue',
    'MumarenFinanceArApAging.vue',
    'MumarenFinanceAssets.vue',
    'MumarenFinanceInvoices.vue',
    'MumarenFinanceCashierAccounts.vue',
    'MumarenFinanceCashierReconciliation.vue',
    'MumarenFinancePayroll.vue',
    'MumarenFinanceTax.vue',
  ]) {
    const page = read('src', 'views', 'mumaren-finance-center', filename)
    assert.match(page, /MumarenFinanceHistoricalSourceNotice/)
    assert.match(page, /:readonly="isReadonly"/)
  }
  assert.match(router, /MumarenFinanceAssets\.vue/)
  assert.match(router, /MumarenFinanceTax\.vue/)
})

test('每日经营参数和每日广告费仅撤销前端入口，保留数据接口代码', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  assert.doesNotMatch(config, /title:\s*['"]每日经营参数['"]/)
  assert.doesNotMatch(config, /title:\s*['"]每日广告费['"]/)
  assert.doesNotMatch(router, /MumarenFinanceDailyParameters/)
  assert.doesNotMatch(router, /MumarenFinanceDailyAdCosts/)
  assert.match(api, /daily-parameters/)
  assert.match(api, /daily-ad-costs/)
})

test('金蝶迁移账簿在历史查询页和核心汇总页初始化后会自动读取已有数据', () => {
  const history = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceHistory.vue')
  const voucherSummary = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherSummary.vue')
  const ledgerDetail = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceLedgerDetail.vue')
  const balanceSheet = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportBalanceSheet.vue')
  const cashFlow = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportCashFlow.vue')

  assert.match(history, /listVouchers\(\{ book_id: requestedBookId, limit: 500 \}\)/)
  assert.match(history, /金蝶迁移凭证/)
  assert.match(voucherSummary, /await loadBooks\(\)[\s\S]*await load\(\)/)
  for (const page of [balanceSheet, cashFlow]) {
    assert.match(page, /initializeBook\(books\.value\)[\s\S]*await load\(\)/)
  }
  assert.match(ledgerDetail, /initializeBook\(books\.value\)[\s\S]*await onBookChange\(\)/)
  assert.match(ledgerDetail, /listAccounts\(requestedBookId\)[\s\S]*await load\(\)/)
})

test('金蝶余额快照有独立只读查询页，不混入当前账报表', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const history = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceHistory.vue')
  const router = read('src', 'router', 'index.ts')

  assert.match(api, /getHistoryBalanceSnapshots/)
  assert.match(history, /余额快照核对/)
  assert.match(router, /history\/balance-snapshots/)
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceHistoryBalanceSnapshots.vue')
  assert.match(page, /filter\(\(book\) => book\.is_readonly\)/)
  assert.match(page, /getHistoryBalanceSnapshots/)
  assert.match(page, /offset/)
  assert.match(page, /加载更多/)
  assert.doesNotMatch(page, /request\.post\(|request\.put\(|request\.delete\(/)
})

test('金蝶迁移凭证与汇总查询至少覆盖单账簿 339 张凭证', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const list = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherList.vue')
  const history = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceHistory.vue')
  const summary = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherSummary.vue')

  assert.match(api, /listVouchers: \(params\?: \{ book_id\?: number; limit\?: number; offset\?: number \}\)/)
  for (const page of [list, history, summary]) {
    assert.match(page, /limit: 500/)
  }
})

test('历史凭证与查凭证切换账簿时不会被旧请求覆盖', () => {
  const list = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherList.vue')
  const history = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceHistory.vue')

  for (const page of [list, history]) {
    assert.match(page, /loadRequestVersion/)
    assert.match(page, /requestedBookId/)
    assert.match(page, /requestedBookId === bookId\.value/)
    assert.match(page, /if \(requestVersion === loadRequestVersion && requestedBookId === bookId\.value\) loading\.value = false;/)
  }
})

test('明细账查询真实已过账分录，不再按凭证头摘要模糊匹配', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceLedgerDetail.vue')

  assert.match(api, /getLedgerLines/)
  assert.match(page, /getLedgerLines/)
  assert.match(page, /loadMore/)
  assert.match(page, /running_balance/)
  assert.match(page, /has_more/)
  assert.match(page, /loadRequestVersion/)
  assert.match(page, /requestedAccountId !== accountId\.value/)
  assert.match(page, /onBookChange[\s\S]*loading\.value = true[\s\S]*finally[\s\S]*loading\.value = false/)
  assert.doesNotMatch(page, /凭证分录明细接口待后端补/)
  assert.doesNotMatch(page, /summary\.includes\(keyword\)/)
})

test('金蝶迁移账簿在三张正式报表中展示真实只读汇总，打印与导出仍受限', () => {
  for (const filename of [
    'MumarenFinanceReportBalanceSheet.vue',
    'MumarenFinanceReportProfit.vue',
    'MumarenFinanceReportCashFlow.vue',
  ]) {
    const page = read('src', 'views', 'mumaren-finance-center', filename)
    assert.match(page, /isReadonly/)
    assert.match(page, /金蝶迁移账簿只读/)
    assert.doesNotMatch(page, /v-else-if="isHistoricalBook"/)
    assert.doesNotMatch(page, /:loading="loading" :disabled="!bookId \|\| isHistoricalBook" @click="load"/)
  }
})

test('金蝶迁移账簿不会在数据罗盘或结账页运行当前账专属计算和操作', () => {
  const compass = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceCompass.vue')
  const closing = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceClosing.vue')
  const voucherList = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherList.vue')
  const arAp = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const aging = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArApAging.vue')
  const assets = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceAssets.vue')
  const invoices = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceInvoices.vue')
  const cashier = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceCashierAccounts.vue')
  const payroll = read('src', 'views', 'mumaren-finance-center', 'MumarenFinancePayroll.vue')
  const tax = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTax.vue')
  const reconciliation = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceCashierReconciliation.vue')
  const expense = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportExpense.vue')
  const salesMonthly = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportSalesMonthly.vue')
  const auxiliary = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceSettingsAuxiliary.vue')
  const taxRecords = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTaxRecords.vue')
  const receivable = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportReceivable.vue')
  const payable = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportPayable.vue')
  const voucherTemplate = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherTemplate.vue')
  const voucherAuto = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherAuto.vue')
  const auditLogs = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceSettingsAuditLogs.vue')
  const voucherSummary = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherSummary.vue')

  assert.match(compass, /v-else-if="isReadonly"/)
  assert.match(compass, /余额快照核对/)
  assert.match(compass, /if \(isReadonly\.value\)/)
  assert.match(closing, /金蝶迁移账簿的期间仅供查询/)
  assert.match(closing, /:disabled="!bookId \|\| isReadonly \|\| !isPeriodCode"/)
  assert.match(closing, /if \(\s*isReadonly\.value \|\| !bookId\.value \|\| !isPeriodCode\.value\) return/)
  assert.match(voucherList, /金蝶迁移账簿凭证；永久只读/)
  assert.match(voucherList, /金蝶迁移/)
  assert.match(arAp, /金蝶迁移账簿未导入应收应付业务单据/)
  assert.match(arAp, /if \(isReadonly\.value\)/)
  assert.match(aging, /金蝶迁移账簿未导入应收应付业务单据/)
  assert.match(aging, /if \(isReadonly\.value\)/)
  for (const page of [assets, invoices, cashier, payroll, tax]) {
    assert.match(page, /金蝶迁移账簿未导入/)
    assert.match(page, /if \(isReadonly\.value\)/)
    assert.match(page, /loadRequestVersion/)
  }
  for (const page of [reconciliation, expense, salesMonthly, auxiliary]) {
    assert.match(page, /金蝶迁移账簿未导入/)
    assert.match(page, /if \(isReadonly\.value\)/)
    assert.match(page, /loadRequestVersion/)
  }
  for (const page of [taxRecords, receivable, payable, voucherTemplate, voucherAuto]) {
    assert.match(page, /金蝶迁移账簿未导入/)
    assert.match(page, /if\s*\(isReadonly\.value\)/)
  }
  assert.match(auditLogs, /金蝶迁移账簿未导入操作审计日志/)
  assert.match(auditLogs, /if \(isReadonly\.value\)/)
  assert.match(voucherSummary, /金蝶迁移账簿已导入的已过账凭证/)
  assert.match(voucherSummary, /loadBooks/)
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

test('固定资产处置将账簿 ID 与目标状态一并放入请求体', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  assert.match(
    api,
    /dispose:\s*\(id:\s*number,\s*book_id:\s*number\)\s*=>\s*request\.put[^\n]*\{\s*book_id,\s*status:\s*"disposed"\s*\}/,
  )
})

test('新增固定资产使用后端的分类字段和原样的月折旧年限', () => {
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceAssets.vue')
  assert.match(page, /asset_category:\s*form\.category/)
  assert.match(page, /useful_life_months:\s*Number\(form\.useful_life_months\s*\|\|\s*0\)/)
})

test('应收应付审核把当前单据类型传给后端', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  assert.match(api, /reviewArApOrder:\s*\(orderId:\s*number,\s*orderType:\s*"receivable"\s*\|\s*"payable"\)/)
  assert.match(page, /reviewArApOrder\(row\.id,\s*orderType\.value\)/)
  assert.match(api, /settleArApOrder:\s*\(orderId:\s*number,\s*orderType:\s*"receivable"\s*\|\s*"payable",\s*payload/)
  assert.match(page, /settleArApOrder\(settleTarget\.value\.id,\s*orderType\.value,/)
})

test('应收应付台账展示汇总、筛选和与单据类型一致的回款付款文案', () => {
  const ledger = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  for (const label of ['应收总额', '应付总额', '已回款', '已付款', '未结余额', '未结清单数']) {
    assert.match(ledger, new RegExp(label), `台账缺少汇总指标：${label}`)
  }
  assert.match(ledger, /结算状态/)
  assert.match(ledger, /筛选期间/)
  assert.match(ledger, /登记回款/)
  assert.match(ledger, /登记付款/)
  assert.match(ledger, /arApOrdersApi\.summary\(/)
  assert.match(api, /summary: \(params:/)
})

test('应收应付草稿可编辑，并把账簿标识放入后端要求的请求体', () => {
  const ledger = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  assert.match(ledger, /编辑/)
  assert.match(ledger, /openEdit\(scope\.row\)/)
  assert.match(ledger, /arApOrdersApi\.update\(editingId\.value/)
  assert.match(api, /\{\s*\.\.\.data,\s*book_id\s*}/)
})

test('应收应付与账龄分析不会让旧账簿请求覆盖当前选择', () => {
  const ledger = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const aging = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArApAging.vue')

  assert.match(ledger, /loadRequestVersion/)
  assert.match(ledger, /requestedBookId\s*!==\s*bookId\.value/)
  assert.match(aging, /loadRequestVersion/)
  assert.match(aging, /requestedBookId\s*!==\s*bookId\.value/)
  assert.match(aging, /watch\(\[bookId, orderType\], \(\) => \{ aging\.value = undefined; load\(\); \}\)/)
  assert.match(aging, /:disabled="!bookId \|\| loading \|\| !orderRows\.length"/)
})

test('清空账簿会结束应收应付与账龄页面在途请求的加载状态', () => {
  const ledger = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const aging = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArApAging.vue')

  assert.match(ledger, /if \(!requestedBookId\) \{ orders\.value = \[\]; summary\.value = undefined; loading\.value = false;/)
  assert.match(aging, /if \(!requestedBookId\) \{ aging\.value = undefined; loading\.value = false;/)
})

test('账龄分析展示往来单位各账龄段和单据明细', () => {
  const aging = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArApAging.vue')

  for (const label of ['0-30天', '31-60天', '61-90天', '91-120天', '120天以上', '单据明细']) {
    assert.match(aging, new RegExp(label), `账龄分析缺少：${label}`)
  }
  assert.match(aging, /watch\(\[bookId, orderType\]/)
})

test('应收应付拆分为应收单台账、应付单台账和账龄分析入口', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')

  assert.match(config, /key: "ar-ap"[\s\S]*children:/)
  assert.match(config, /title: "应收单台账"/)
  assert.match(config, /path: `\$\{R\}\/ar-ap\/receivable`/)
  assert.match(config, /title: "应付单台账"/)
  assert.match(config, /path: `\$\{R\}\/ar-ap\/payable`/)
  assert.match(config, /title: "账龄分析"/)
  assert.match(config, /path: `\$\{R\}\/ar-ap\/aging`/)
  assert.match(router, /path: "ar-ap\/receivable", name: "MumarenFinanceReceivableLedger"/)
  assert.match(router, /path: "ar-ap\/payable", name: "MumarenFinancePayableLedger"/)
  assert.match(router, /path: "ar-ap\/aging", name: "MumarenFinanceArApAging"/)
})

test('拆分后的应收应付页面从共享账簿仓库加载并随路由账簿类型刷新', () => {
  const ledger = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const aging = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArApAging.vue')
  const sharedBook = read('src', 'composables', 'useMumarenFinanceBook.ts')

  assert.match(sharedBook, /return \{ books, bookId, isReadonly, error, loadBooks, initializeBook \}/)
  assert.match(ledger, /await loadBooks\(\)/)
  assert.match(ledger, /watch\(\(\) => props\.fixedOrderType/)
  assert.match(aging, /await loadBooks\(\)/)
})

test('所有账簿页面使用共享账簿，历史账簿写入页有界面只读守卫', () => {
  const financeViews = [
    'MumarenFinanceAssets', 'MumarenFinanceCashierAccounts', 'MumarenFinanceCashierReconciliation',
    'MumarenFinanceClosing', 'MumarenFinanceCompass', 'MumarenFinanceInvoices',
    'MumarenFinanceLedgerDetail', 'MumarenFinancePayroll', 'MumarenFinanceReportBalanceSheet',
    'MumarenFinanceReportCashFlow', 'MumarenFinanceReportExpense', 'MumarenFinanceReportPayable',
    'MumarenFinanceReportProfit', 'MumarenFinanceReportReceivable', 'MumarenFinanceReportSalesMonthly',
    'MumarenFinanceReportTrialBalance', 'MumarenFinanceSettingsAuditLogs', 'MumarenFinanceSettingsAuxiliary',
    'MumarenFinanceTax', 'MumarenFinanceTaxRecords', 'MumarenFinanceVoucherAuto',
    'MumarenFinanceVoucherList', 'MumarenFinanceVoucherSummary', 'MumarenFinanceVoucherTemplate',
  ]
  for (const view of financeViews) {
    assert.match(read('src', 'views', 'mumaren-finance-center', `${view}.vue`), /useMumarenFinanceBook|useMumarenFinanceBookStore/, view)
  }
  for (const view of [
    'MumarenFinanceAssets', 'MumarenFinanceCashierAccounts', 'MumarenFinanceCashierReconciliation',
    'MumarenFinanceInvoices', 'MumarenFinancePayroll', 'MumarenFinanceSettingsAuxiliary',
    'MumarenFinanceTax', 'MumarenFinanceVoucherAuto', 'MumarenFinanceVoucherList', 'MumarenFinanceVoucherTemplate',
  ]) {
    assert.match(read('src', 'views', 'mumaren-finance-center', `${view}.vue`), /isReadonly/, `${view} must guard historical books`)
  }
})

test('数据罗盘以共享账簿为唯一来源，并在账簿切换后重新加载指标', () => {
  const compass = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceCompass.vue')
  const sharedBook = read('src', 'composables', 'useMumarenFinanceBook.ts')

  assert.match(compass, /const \{ books, bookId, (?:isReadonly, )?loadBooks, error: bookError \} = useMumarenFinanceBook\(\)/)
  assert.match(compass, /await loadBooks\(\);\s*booksLoaded\.value = true;\s*await load\(\)/)
  assert.match(compass, /watch\(bookId,\s*\(\)\s*=>\s*\{\s*if \(booksLoaded\.value\) void load\(\);/)
  assert.match(compass, /const requestVersion = ref\(0\)/)
  assert.match(compass, /const requestedBookId = bookId\.value;\s*const version = \+\+requestVersion\.value;/)
  assert.match(compass, /if \(!requestedBookId\) \{\s*loading\.value = false;/)
  assert.match(compass, /if \(version !== requestVersion\.value \|\| requestedBookId !== bookId\.value\) return;/)
  assert.match(compass, /v-if="error \|\| bookError"/)
  assert.doesNotMatch(compass, /const books = ref<MumarenFinanceBook\[\]>\(\[\]\)/)
  assert.match(sharedBook, /const \{ books, bookId, isReadonly, error \} = storeToRefs\(store\)/)
  assert.match(sharedBook, /return \{ books, bookId, isReadonly, error, loadBooks, initializeBook \}/)
})

test('付款台账在独立财务中心可访问，并遵循草稿审核人工支付和历史账簿只读规则', () => {
  const navigation = read('src', 'config', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinancePayments.vue')
  assert.match(navigation, /key: "payments"/)
  assert.match(router, /payments[\s\S]*MumarenFinancePayments/)
  assert.match(api, /paymentsApi/)
  assert.match(api, /finance-center\/mumaren/)
  assert.match(page, /MumarenFinanceArAp/)
  assert.match(page, /fixed-order-type="payable"/)
})

test('展示类页面调用明确的独立财务接口', () => {
  const derivedPages = [
    { file: 'MumarenFinanceCompass.vue', apis: ['loadBooks', 'getTrialBalance', 'getProfitStatement'] },
    { file: 'MumarenFinanceVoucherSummary.vue', apis: ['loadBooks', 'listVouchers'] },
    { file: 'MumarenFinanceLedgerDetail.vue', apis: ['listBooks', 'listAccounts', 'getLedgerLines'] },
    { file: 'MumarenFinanceReportBalanceSheet.vue', apis: ['listBooks', 'getTrialBalance'] },
    { file: 'MumarenFinanceReportCashFlow.vue', apis: ['listBooks', 'getCashFlowStatement'] },
    { file: 'MumarenFinanceReportReceivable.vue', apis: ['loadBooks', 'getArApAging'] },
    { file: 'MumarenFinanceReportPayable.vue', apis: ['loadBooks', 'getArApAging'] },
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

test('已接通的凭证模板和自动凭证均显示在主侧边栏', () => {
  const config = read('src', 'config', 'mumarenFinanceCenter.ts')
  const menuStart = config.indexOf('export const mumarenFinanceCenterMenuItem')
  const menuConfig = config.slice(menuStart)

  assert.match(menuConfig, /path:\s*`\$\{R\}\/vouchers\/template`/)
  assert.match(menuConfig, /path:\s*`\$\{R\}\/vouchers\/auto`/)
})

test('自动凭证必须预览并生成草稿，不得自动过账', () => {
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherAuto.vue')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  assert.match(page, /生成凭证草稿/)
  assert.match(page, /previewAutoVoucherDraft/)
  assert.match(page, /generateAutoVoucherDraft/)
  assert.match(page, /debit_account_id/)
  assert.match(page, /credit_account_id/)
  assert.match(api, /\/auto-voucher-rules\/\$\{ruleId\}\/preview/)
  assert.match(api, /\/auto-voucher-rules\/\$\{ruleId\}\/generate-draft/)
  assert.doesNotMatch(page, /autoPost\(|自动过账/)
})

test('销售月报支持对未锁定记录编辑，不强迫删除后重建', () => {
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportSalesMonthly.vue')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  assert.match(page, /编辑/)
  assert.match(page, /openEdit/)
  assert.match(page, /salesMonthlyReportsApi\.update/)
  assert.match(page, /store_code/)
  assert.match(page, /return_amount/)
  assert.match(api, /export interface SalesMonthlyReportUpdate\s*\{\s*book_id: number;/)
  assert.match(api, /update:\s*\(id: number, data: SalesMonthlyReportUpdate\) => request\.put/)
  assert.match(api, /return_amount\?: number/)
})

test('凭证模板保存平衡分录并可套用为未保存的凭证草稿', () => {
  const template = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherTemplate.vue')
  const create = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherCreate.vue')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  assert.match(template, /lines_json/)
  assert.match(template, /mumarenFinanceCenterApi\.listAccounts/)
  assert.match(template, /voucherTemplatesApi\.update/)
  assert.match(template, /router\.push/)
  assert.match(template, /templateRequestVersion/)
  assert.match(create, /useRoute/)
  assert.match(create, /voucherTemplatesApi\.list/)
  assert.match(create, /route\.query\.template_id/)
  assert.match(create, /templateApplyVersion/)
  assert.match(api, /interface VoucherTemplateLine/)
  assert.match(api, /book_id: number;[\s\S]*lines_json/)
})

test('财务中心各账簿页面共享并持久化所选账簿', () => {
  const sharedBook = read('src', 'composables', 'useMumarenFinanceBook.ts')
  const sharedBookStore = read('src', 'stores', 'mumarenFinanceBook.ts')

  assert.match(sharedBook, /useMumarenFinanceBookStore/)
  assert.match(sharedBookStore, /localStorage/)
  assert.match(sharedBookStore, /mumaren-finance-center:selected-book-id/)
  assert.match(sharedBook, /initializeBook/)

  for (const view of [
    'MumarenFinanceInvoices', 'MumarenFinanceCashierAccounts',
    'MumarenFinanceCashierReconciliation', 'MumarenFinanceSettingsAuxiliary',
    'MumarenFinanceTax', 'MumarenFinanceReportBalanceSheet',
  ]) {
    assert.match(read('src', 'views', 'mumaren-finance-center', `${view}.vue`), /useMumarenFinanceBook/)
  }
})

test('税务草稿从当前账簿的启用税种下拉选择', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const view = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTax.vue')

  assert.match(api, /taxTypesApi/)
  assert.match(api, /requestPath\("\/tax-types"\)/)
  assert.match(view, /taxTypesApi\.list\(\{ book_id: bookId\.value \}\)/)
  assert.match(view, /<el-select v-model="form\.tax_type_id"/)
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

  assert.match(tax, /useMumarenFinanceBook/)
  assert.match(tax, /bookId/)
  assert.match(tax, /请选择独立账簿/)
  assert.match(tax, /getTaxAlerts\(\s*\{\s*book_id:\s*requestedBookId/)
  assert.match(tax, /listTaxRecords\(\s*\{\s*book_id:\s*requestedBookId/)
  assert.match(tax, /onBookChange[\s\S]*loadRequestVersion \+= 1;[\s\S]*loading\.value = false/)
  // 不允许在未选账簿时 onMounted 直接调用税务接口
  assert.doesNotMatch(tax, /onMounted\(load\)/)
  assert.doesNotMatch(tax, /books\.value\[0\]\?\.id/)
  assert.doesNotMatch(tax, /onMounted\(async\s*\(\)\s*=>\s*\{(?:(?!\}\);)[\s\S])*?await\s+load\(\)/)
})

test('科目管理与账套管理按账簿隔离,期末结账与辅助核算已持久化', () => {
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

  // 科目页面只能通过独立 API 写当前账；历史账簿由 isReadonly 禁用入口。
  const accounts = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceAccounts.vue')
  assert.match(accounts, /listAccounts/)
  assert.match(accounts, /createAccount|updateAccount/)
  assert.match(accounts, /isReadonly/)
  assert.doesNotMatch(accounts, /request\.post\(|request\.put\(|request\.delete\(/)

  // 期末结账:已改为持久化 CRUD 页面,指向新组件 MumarenFinanceClosing.vue
  assert.match(router, /path:\s*['"]closing['"],\s*name:\s*['"]MumarenFinanceClosing['"],\s*component:\s*\(\)\s*=>\s*import\(['"][^'"]*MumarenFinanceClosing\.vue['"]\),\s*meta:\s*\{\s*title:\s*['"]结账['"]\s*\}/)
  // 期末结账页面不再有会话内 CRUD 提示,改为调用 periodsApi
  const closing = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceClosing.vue')
  assert.doesNotMatch(closing, /完整数据接口待后端补/, '结账页面不得再有黄色横幅')
  assert.doesNotMatch(closing, /本会话数据刷新后清空/, '结账页面不得再有会话清空提示')
  assert.match(closing, /periodsApi/, '结账页面必须调用 periodsApi')
})

test('录凭证补齐牧马人辅助录入按钮，导出不改变人工审核过账边界', () => {
  const create = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherCreate.vue')
  const list = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherList.vue')

  assert.match(create, /复制上一行/)
  assert.match(create, /收款分录/)
  assert.match(create, /付款分录/)
  assert.match(create, /自动找平/)
  assert.match(create, /copyLastLine|addReceiptPair|addPaymentPair|balanceLastLine/)
  assert.match(list, /导出当前列表/)
  assert.match(list, /exportVouchers/)
  assert.match(list, /[=+@-]/)
  assert.match(list, /text = `'/)
  assert.doesNotMatch(`${create}\n${list}`, /unreviewVoucher|unpostVoucher|reversePostVoucher/)
})

test('凭证模板与录凭证页保留牧马人安全的复制和刷新辅助操作', () => {
  const template = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherTemplate.vue')
  const create = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherCreate.vue')

  assert.match(template, /复制上一行/)
  assert.match(template, /const copyLastLine/)
  assert.match(create, /@click="reloadAll"/)
  assert.match(create, /const reloadAll = async/)
})

test('共享账簿切换会重建当前页面，避免旧账簿异步响应覆盖新账簿', () => {
  const layout = read('src', 'layouts', 'MainLayout.vue')
  assert.match(layout, /useMumarenFinanceBookStore/)
  assert.match(layout, /storeToRefs\(useMumarenFinanceBookStore\(\)\)/)
  assert.match(layout, /:key="`\$\{route\.fullPath\}:\$\{mumarenFinanceBookId \?\? 'none'\}`"/)
  assert.match(read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceAccounts.vue'), /await bookStore\.loadBooks\(\);\s*await load\(\);/)
})

test('辅助核算页面使用独立后端的 parent_id 和 is_active 契约显示层级与启停状态', () => {
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceSettingsAuxiliary.vue')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  assert.match(page, /row\.parent_id/)
  assert.match(page, /row\.is_active/)
  assert.doesNotMatch(page, /row\.parent_code|row\.status/)
  assert.match(page, /is_active:\s*!row\.is_active,\s*book_id:\s*bookId\.value/)
  assert.match(api, /export interface AuxiliaryAccountingUpdate\s*\{\s*book_id: number;/)
  assert.match(api, /request\.put<ApiResponse<MumarenAuxiliaryAccounting>>\(requestPath\(`\/auxiliary-accountings\/\$\{id\}`\), data\)/)
})

test('金蝶迁移凭证页只读查询迁移账簿,不出现编辑/审核/过账操作按钮', () => {
  const history = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceHistory.vue')

  assert.match(history, /金蝶迁移|is_readonly|只读/)
  assert.match(history, /listVouchers\(\{ book_id: requestedBookId, limit: 500 \}\)/)
  assert.doesNotMatch(history, /reviewVoucher|postVoucher|createVoucher|deleteVoucher|reviewArApOrder|settleArApOrder|payTaxRecord|request\.post\(|request\.put\(|request\.delete\(/)
})

test('录凭证页会随共享账簿加载科目,并将金蝶历史账簿整表单设为只读', () => {
  const voucherCreate = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherCreate.vue')

  assert.match(voucherCreate, /await bookStore\.loadBooks\(\);\s*await onBookChange\(\)/)
  assert.match(voucherCreate, /watch\(bookId,\s*\(\)\s*=>\s*void onBookChange\(\)\)/)
  assert.doesNotMatch(voucherCreate, /@change="onBookChange"/)
  assert.match(voucherCreate, /const accountRequestVersion = ref\(0\)/)
  assert.match(voucherCreate, /<el-form :model="form" label-width="84px" :disabled="isReadonly">/)
  assert.match(voucherCreate, /<el-table[^>]*:class="\{ 'is-readonly': isReadonly \}"/)
})

test('利润表与科目余额表页面调用独立报表接口', () => {
  const profit = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportProfit.vue')
  const trial = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportTrialBalance.vue')
  const cashFlow = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportCashFlow.vue')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  assert.match(profit, /getProfitStatement/)
  assert.match(profit, /mumarenFinanceCenterApi/)
  assert.match(trial, /getTrialBalance/)
  assert.match(trial, /mumarenFinanceCenterApi/)
  assert.match(api, /getCashFlowStatement/)
  assert.match(cashFlow, /getCashFlowStatement/)
  assert.doesNotMatch(cashFlow, /待后端补/)
})

test('税金明细表页面调用税务记录接口(只读展示)', () => {
  const taxRecords = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTaxRecords.vue')

  assert.match(taxRecords, /listTaxRecords|mumarenFinanceCenterApi/)
  // 只读页面,不得有写入操作
  assert.doesNotMatch(taxRecords, /createTaxRecord|reviewTaxRecord|payTaxRecord|request\.post\(|request\.put\(|request\.delete\(/)
})

test('应收应付台账支持单据明细行和逐笔回款付款流水查询', () => {
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  assert.match(page, /添加明细/)
  assert.match(page, /form\.lines/)
  assert.match(page, /settlements/)
  assert.match(page, /arApOrdersApi\.detail/)
  assert.match(api, /export interface ArApOrderLineInput/)
  assert.match(api, /lines\?: ArApOrderLineInput\[\]/)
  assert.match(api, /detail: \(id: number, book_id: number, order_type: "receivable" \| "payable"\)/)
})

test('应收应付明细支持录入并展示税率和税额，税额随金额和税率重新计算', () => {
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')

  assert.match(page, /label="税率\(%\)"/)
  assert.match(page, /label="税额"/)
  assert.match(page, /v-model="scope\.row\.tax_rate"/)
  assert.match(page, /scope\.row\.tax_amount/)
  assert.match(page, /syncTaxAmount\(scope\.row\)/)
  assert.match(page, /const syncTaxAmount/)
})

test('应收应付台账按往来单位筛选时列表与汇总使用同一独立账簿查询条件', () => {
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')

  assert.match(page, /v-model="counterpartyFilter"/)
  assert.match(page, /counterparty_name:\s*counterpartyFilter\.value\s*\|\|\s*undefined/)
  assert.match(api, /counterparty_name\?: string; limit\?: number/)
  assert.match(api, /summary:\s*\(params:\s*\{[\s\S]*?counterparty_name\?: string[\s\S]*?\}\)\s*=> request\.get/)
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

test('账套管理可创建独立当前账，凭证列表仅允许删除草稿', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const router = read('src', 'router', 'index.ts')
  const books = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceBooks.vue')
  const vouchers = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherList.vue')

  assert.match(api, /createBook:\s*\(data:/)
  assert.match(api, /deleteVoucher:\s*\(voucherId: number\)/)
  assert.match(router, /MumarenFinanceSettingsBooks[\s\S]*MumarenFinanceBooks\.vue/)
  assert.match(books, /新增账簿/)
  assert.match(books, /createBook/)
  assert.match(vouchers, /scope\.row\.status === 'draft'/)
  assert.match(vouchers, /deleteVoucher/)
})

test('对照牧马人快捷操作，数据罗盘只导航到受控录入流程，资产负债表和利润表可打印', () => {
  const compass = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceCompass.vue')
  const balanceSheet = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportBalanceSheet.vue')
  const profit = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportProfit.vue')
  const closing = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceClosing.vue')

  assert.match(compass, /记录回款/)
  assert.match(compass, /录入费用/)
  assert.match(compass, /\/ar-ap\/receivable/)
  assert.match(compass, /\/reports\/expense-detail/)
  assert.match(balanceSheet, /window\.print\(\)/)
  assert.match(profit, /window\.print\(\)/)
  assert.match(closing, /初始化期间/)
  assert.match(closing, /结账预检/)
  assert.match(closing, /periodsApi\.initialize/)
  assert.match(closing, /periodsApi\.precheck/)
})

test('应收应付完整保留联系人、草稿明细编辑和账龄来源单据钻取', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const ledger = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const aging = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArApAging.vue')

  assert.match(api, /contact\?: string \| null/)
  assert.match(api, /contact: string \| null/)
  assert.match(ledger, /<el-form-item label="联系人"/)
  assert.match(ledger, /prop="contact"/)
  assert.match(ledger, /lines: \(detail\.lines \|\| \[\]\)\.map/)
  assert.match(ledger, /lines: form\.lines/)
  assert.match(ledger, /remark: detail\.remark \|\| ""/)
  assert.doesNotMatch(ledger, /<el-form-item v-if="!editingId" label="单据明细">/)
  assert.match(aging, /type="expand"/)
  assert.match(aging, /scope\.row\.orders/)
})

test('当前账可维护科目和税种，历史金蝶账簿不暴露维护入口', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const accounts = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceAccounts.vue')
  const tax = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceTax.vue')

  assert.match(api, /createAccount:/)
  assert.match(api, /updateAccount:/)
  assert.match(api, /createTaxType:/)
  assert.match(api, /updateTaxType:/)
  assert.match(accounts, /新增科目/)
  assert.match(accounts, /isReadonly/)
  assert.match(tax, /管理税种/)
  assert.match(tax, /isReadonly/)
})

test('参考模块已有后端能力的资产、工资与辅助核算编辑入口均可在当前账落库', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const assets = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceAssets.vue')
  const payroll = read('src', 'views', 'mumaren-finance-center', 'MumarenFinancePayroll.vue')
  const auxiliary = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceSettingsAuxiliary.vue')

  assert.match(api, /export interface FixedAssetUpdate \{\s+book_id: number;/)
  assert.match(assets, /编辑/)
  assert.match(assets, /openEdit/)
  assert.match(assets, /fixedAssetsApi\.update/)
  assert.match(payroll, /编辑/)
  assert.match(payroll, /openEdit/)
  assert.match(payroll, /payrollsApi\.update/)
  assert.match(auxiliary, /编辑/)
  assert.match(auxiliary, /openEdit/)
  assert.match(auxiliary, /auxiliaryAccountingsApi\.update/)
})

test('销售月报可导出当前独立账簿的已持久化记录', () => {
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportSalesMonthly.vue')

  assert.match(page, /导出当前月报/)
  assert.match(page, /exportReports/)
  assert.match(page, /text\/csv/)
  assert.match(page, /[=+@-]/)
  assert.match(page, /`'\$\{text\}`/)
})

test('应收应付台账与账龄分析可安全导出当前账簿的核对数据', () => {
  const ledger = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArAp.vue')
  const aging = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceArApAging.vue')

  assert.match(ledger, /导出当前台账/)
  assert.match(ledger, /exportLedger/)
  assert.match(aging, /导出账龄明细/)
  assert.match(aging, /exportAging/)
  assert.match(ledger, /`'\$\{text\}`/)
  assert.match(aging, /`'\$\{text\}`/)
})

test('出纳和发票页面与独立后端的实际请求字段保持一致', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const cashier = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceCashierAccounts.vue')
  const invoices = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceInvoices.vue')

  assert.match(api, /account_code: string/)
  assert.match(api, /cash_account_id: number/)
  assert.match(api, /flow_date: string/)
  assert.match(api, /direction: "in" \| "out"/)
  assert.match(api, /invoice_type: "input" \| "output"/)
  assert.match(api, /counterparty_name/)
  assert.match(api, /export interface InvoiceUpdate \{\s+book_id: number;/)
  assert.match(api, /export interface CashAccountUpdate \{\s+book_id: number;/)
  const invoiceUpdates = api.slice(api.indexOf("export const invoicesApi"), api.indexOf("export interface MumarenCashAccount"))
  const cashAccountApiStart = api.indexOf("export const cashAccountsApi")
  const cashAccountUpdates = api.slice(cashAccountApiStart, api.indexOf("export interface MumarenCashFlow", cashAccountApiStart))
  const invoiceUpdateLine = invoiceUpdates.match(/update:[^\r\n]+/)[0]
  const cashAccountUpdateLine = cashAccountUpdates.match(/update:[^\r\n]+/)[0]
  assert.match(invoiceUpdateLine, /update: \(id: number, data: InvoiceUpdate\) => request\.put[\s\S]*, data\)/)
  assert.doesNotMatch(invoiceUpdateLine, /params:\s*\{\s*book_id/)
  assert.match(cashAccountUpdateLine, /update: \(id: number, data: CashAccountUpdate\) => request\.put[\s\S]*, data\)/)
  assert.doesNotMatch(cashAccountUpdateLine, /params:\s*\{\s*book_id/)
  assert.match(cashier, /cash_account_id/)
  assert.match(cashier, /flow_date/)
  assert.match(invoices, /invoice_type/)
  assert.match(invoices, /verification_status/)
})

test('工资页面使用后端工资草稿模型而非已废弃的薪资拆分字段', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinancePayroll.vue')

  assert.match(api, /employee_no: string/)
  assert.match(api, /gross_amount: number/)
  assert.match(api, /deduction_amount: number/)
  assert.match(api, /net_amount: number/)
  assert.match(api, /export interface PayrollUpdate \{\s+book_id: number;/)
  assert.match(page, /employee_no/)
  assert.match(page, /gross_amount/)
  assert.match(page, /deduction_amount/)
  assert.match(page, /net_amount/)
  assert.doesNotMatch(page, /base_salary/)
  assert.doesNotMatch(page, /social_insurance/)
})

test('固定资产编辑按月保留后端折旧年限，不能四舍五入为整年', () => {
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceAssets.vue')

  assert.match(page, /折旧月数/)
  assert.match(page, /useful_life_months/)
  assert.doesNotMatch(page, /Math\.round\(Number\(row\.useful_life_months/)
  assert.doesNotMatch(page, /Number\(form\.useful_life \|\| 0\) \* 12/)
})

test('当前账簿可受控编辑并幂等补齐基础科目，金蝶迁移账簿没有维护入口', () => {
  const api = read('src', 'api', 'mumarenFinanceCenter.ts')
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceBooks.vue')

  assert.match(api, /updateBook:/)
  assert.match(api, /updateBook:[\s\S]*ApiResponse<Pick<MumarenFinanceBook, "id" \| "book_code" \| "book_name" \| "company_name" \| "status" \| "is_readonly">>/)
  assert.match(api, /replenishStarterAccounts:/)
  assert.match(page, /编辑/)
  assert.match(page, /补齐基础科目/)
  assert.match(page, /openEdit/)
  assert.match(page, /replenishStarterAccounts/)
  assert.match(page, /row\.is_readonly/)
})

test('录凭证快捷操作左对齐，金额汇总独立靠右并支持小屏换行', () => {
  const page = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceVoucherCreate.vue')

  assert.match(page, /<div class="voucher-actions">[\s\S]*添加分录[\s\S]*自动找平[\s\S]*<\/div>/)
  assert.match(page, /<div class="totals">[\s\S]*借方[\s\S]*贷方[\s\S]*差额[\s\S]*<\/div>/)
  assert.match(page, /\.voucher-actions\s*\{[^}]*display:\s*flex[^}]*flex-wrap:\s*wrap[^}]*gap:/)
  assert.match(page, /@media \(max-width: 640px\)[\s\S]*\.dialog-toolbar\s*\{[^}]*align-items:\s*flex-start/)
})

test('金蝶历史账簿报表仍查询同一账簿数据，且不允许旧响应覆盖新的账簿选择', () => {
  const balanceSheet = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportBalanceSheet.vue')
  const profit = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportProfit.vue')
  const cashFlow = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportCashFlow.vue')
  const trial = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportTrialBalance.vue')

  for (const source of [balanceSheet, profit, cashFlow]) {
    assert.doesNotMatch(source, /:loading="loading" :disabled="!bookId \|\| isHistoricalBook" @click="load"/)
    assert.doesNotMatch(source, /v-else-if="isHistoricalBook"/)
    assert.match(source, /const requestedBookId = bookId\.value;/)
    assert.match(source, /const requestVersion = \+\+loadRequestVersion;/)
    assert.match(source, /requestVersion !== loadRequestVersion \|\| requestedBookId !== bookId\.value/)
    assert.match(source, /:disabled="!bookId \|\| isHistoricalBook"[^\n]*@(click|click)=/)
  }

  assert.match(trial, /const requestedBookId = bookId\.value;/)
  assert.match(trial, /const requestVersion = \+\+loadRequestVersion;/)
  assert.match(trial, /requestVersion !== loadRequestVersion \|\| requestedBookId !== bookId\.value/)
  assert.match(profit, /const onBookChange = async \(\) => \{\s*await load\(\);\s*\};/)
  assert.match(trial, /const onBookChange = async \(\) => \{\s*await load\(\);\s*\};/)
})

test('利润表与现金流量表说明准确覆盖所选历史或当前账簿', () => {
  const profit = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportProfit.vue')
  const cashFlow = read('src', 'views', 'mumaren-finance-center', 'MumarenFinanceReportCashFlow.vue')

  assert.match(profit, /所选账簿.*已过账凭证/)
  assert.match(cashFlow, /所选账簿.*已过账凭证.*已过账资金流水/)
  assert.doesNotMatch(`${profit}\n${cashFlow}`, /独立当前账|不混入历史归档/)
})
