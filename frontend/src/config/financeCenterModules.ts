import {
  Box,
  Coin,
  DataAnalysis,
  DataLine,
  Document,
  Files,
  Finished,
  List,
  Money,
  OfficeBuilding,
  Setting,
  Tickets,
  Wallet,
} from "@element-plus/icons-vue";

export type FinanceModuleStatus = "ready" | "partial" | "foundation";

export interface FinanceCenterModule {
  key: string;
  label: string;
  path: string;
  icon: unknown;
  status: FinanceModuleStatus;
  source: string;
  primaryObjects: string[];
  currentScope: string;
}

export interface FinanceNavigationItem {
  path?: string;
  label: string;
  icon?: unknown;
  key?: string;
  permission?: string;
  disabled?: boolean;
  badge?: string;
  children?: FinanceNavigationItem[];
}

export const financeCenterModules: FinanceCenterModule[] = [
  {
    key: "core-workspace",
    label: "会计工作台",
    path: "/app/finance-center/core-workspace",
    icon: Tickets,
    status: "partial",
    source: "fin_current（V2 独立会计内核）",
    primaryObjects: ["当前账簿", "凭证草稿", "审核", "人工过账", "切换 Gate"],
    currentScope: "V2.0 先只读验收；制单、审核和人工过账仅在最终切换批准后按开关启用。",
  },
  {
    key: "data-cockpit",
    label: "数据罗盘",
    path: "/app/finance-center/data-cockpit",
    icon: DataLine,
    status: "partial",
    source: "华邦经营看板 + 金蝶历史财务",
    primaryObjects: ["销售", "库存", "费用", "历史财务"],
    currentScope: "已接入经营看板和历史财务指标，后续补齐牧马人式财务钻取总览。",
  },
  {
    key: "archive",
    label: "历史数据存档",
    path: "/app/finance-center/archive",
    icon: Files,
    status: "partial",
    source: "fin_history（V2 隔离历史账，待恢复副本验证）",
    primaryObjects: ["历史账套", "导入批次", "凭证", "科目余额", "数据质量"],
    currentScope: "本地金蝶快照已完成只读校验；暂存、发布与生产只读验收必须在恢复副本和受控导入账号下完成。",
  },
  {
    key: "vouchers",
    label: "凭证",
    path: "/app/finance-center/vouchers",
    icon: Tickets,
    status: "partial",
    source: "fin_current.voucher / fin_current.voucher_line",
    primaryObjects: ["凭证头", "凭证分录", "版本记录", "过账", "冲销"],
    currentScope: "V2 已实现草稿、审核和人工过账状态机；生产写入 Gate 仍保持关闭，历史凭证仅可查不可改。",
  },
  {
    key: "ledger",
    label: "账簿",
    path: "/app/finance-center/ledger",
    icon: List,
    status: "partial",
    source: "fin_current.book / fin_current.account_version / fin_current.ledger_balance",
    primaryObjects: ["账簿", "期间", "科目", "月余额", "来源链接"],
    currentScope: "当前账账簿、科目和期初余额必须在切换 Gate 前完成证据核对；不能把旧 fin schema 直接视为 V2 当前账。",
  },
  {
    key: "reports",
    label: "报表",
    path: "/app/finance-center/reports",
    icon: DataAnalysis,
    status: "foundation",
    source: "fin_current 报表映射（正式报表保持阻断）",
    primaryObjects: ["报表行", "科目映射", "资产负债表", "利润表", "现金流量表"],
    currentScope: "会计政策签字例外不替代报表映射事实；缺少可核对映射时，正式报表保持阻断。",
  },
  {
    key: "receivable-payable",
    label: "应收应付",
    path: "/app/finance-center/receivable-payable",
    icon: Money,
    status: "foundation",
    source: "fin.receivable / fin.payable / fin.settlement",
    primaryObjects: ["应收", "应付", "结算", "往来单位", "草稿凭证"],
    currentScope: "数据模型和约束已建，业务采集和页面操作流待接入。",
  },
  {
    key: "closing",
    label: "结账",
    path: "/app/finance-center/closing",
    icon: Finished,
    status: "partial",
    source: "fin_current.fiscal_period / fin_current.operation_event",
    primaryObjects: ["会计期间", "打开期间", "关闭状态", "操作审计"],
    currentScope: "期间领域约束和打开期间查询已实现；完整月结检查、恢复副本演练和最终切换窗口执行待完成。",
  },
  {
    key: "assets",
    label: "资产",
    path: "/app/finance-center/assets",
    icon: OfficeBuilding,
    status: "foundation",
    source: "fin.fixed_asset / fin.depreciation",
    primaryObjects: ["固定资产", "折旧", "部门", "费用科目"],
    currentScope: "资产和折旧底表已建，资产卡片、计提和处置流程待接入。",
  },
  {
    key: "invoices",
    label: "发票",
    path: "/app/finance-center/invoices",
    icon: Document,
    status: "foundation",
    source: "fin.invoice",
    primaryObjects: ["发票代码", "发票号码", "税额", "往来单位", "草稿凭证"],
    currentScope: "发票登记底表已建，发票采集、认证和勾稽页面待接入。",
  },
  {
    key: "cashier",
    label: "出纳",
    path: "/app/finance-center/cashier",
    icon: Wallet,
    status: "foundation",
    source: "fin.cash_account / fin.bank_transaction / fin.reconciliation",
    primaryObjects: ["现金账户", "银行流水", "对账", "资金余额"],
    currentScope: "出纳账户、流水和对账底表已建，银行流水采集和对账工作台待接入。",
  },
  {
    key: "payroll",
    label: "工资",
    path: "/app/finance-center/payroll",
    icon: Coin,
    status: "foundation",
    source: "fin.payroll",
    primaryObjects: ["员工", "部门", "应发", "社保公积金", "个税", "实发"],
    currentScope: "工资底表已建，钉钉人员、考勤和薪资数据补采后接入。",
  },
  {
    key: "tax",
    label: "税务",
    path: "/app/finance-center/tax",
    icon: Box,
    status: "foundation",
    source: "fin.tax_record",
    primaryObjects: ["税种", "期间", "计税金额", "税额", "缴纳状态"],
    currentScope: "税务记录底表已建，申报、缴纳和税票凭证流程待接入。",
  },
  {
    key: "settings",
    label: "设置",
    path: "/app/finance-center/settings",
    icon: Setting,
    status: "partial",
    source: "V2 数据库角色、报表映射、操作审计",
    primaryObjects: ["财务权限", "报表行", "科目映射", "导入批次", "操作日志"],
    currentScope: "最小权限角色脚本已就绪；生产角色创建、凭据轮换与集中设置页仍待完成。",
  },
];

export const financeCenterModuleMap = Object.fromEntries(
  financeCenterModules.map((item) => [item.key, item]),
) as Record<string, FinanceCenterModule>;

export const financeLegacyModules: FinanceNavigationItem[] = [
  { path: "/app/fin/overview", icon: Money, label: "财务首页", permission: "finance:overview:view" },
  { path: "/app/finance", icon: DataLine, label: "利润分析", permission: "finance:profit:view" },
  { path: "/app/fin/reimbursements", icon: List, label: "报销管理", permission: "finance:reimbursement:view" },
  { path: "/app/fin/payments", icon: Money, label: "付款申请", permission: "finance:payment:view" },
  { path: "/app/fin/expense-analysis", icon: DataAnalysis, label: "费用分析", permission: "finance:expense:view" },
  { path: "/app/fin/formal-ledger", icon: Money, label: "正式账簿", permission: "finance:voucher:write" },
];

export const financeHistoryModules: FinanceNavigationItem = {
  icon: Files,
  label: "历史财务",
  key: "finance-history",
  permission: "finance:profit:view",
  children: [
    { path: "/app/fin/history/account-sets", label: "历史账套" },
    { path: "/app/fin/history/statements", label: "财务报表" },
    { path: "/app/fin/history/account-balances", label: "科目余额" },
    { path: "/app/fin/history/vouchers", label: "凭证查询" },
    { path: "/app/fin/history/data-quality", label: "数据质量" },
  ],
};

export const mirroredFinanceCenterNavigation: FinanceNavigationItem = {
  icon: Money,
  label: "财务中心",
  key: "finance-center",
  permission: "finance:center:view",
  children: financeCenterModules.map((item) => ({
    path: item.path,
    label: item.label,
    permission: "finance:center:view",
  })),
};

export const financeProfitNavigation: FinanceNavigationItem[] = [
  ...financeLegacyModules,
  financeHistoryModules,
  { label: "现金安全", icon: Box, disabled: true, badge: "规划中", permission: "finance:cash:view" },
];
