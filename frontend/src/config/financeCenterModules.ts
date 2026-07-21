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
    status: "ready",
    source: "金蝶 K/3 WISE 已验证历史账套",
    primaryObjects: ["历史账套", "导入批次", "凭证", "科目余额", "数据质量"],
    currentScope: "三套正式账套已写入正式账簿，原始历史链路仍保留只读对照。",
  },
  {
    key: "vouchers",
    label: "凭证",
    path: "/app/finance-center/vouchers",
    icon: Tickets,
    status: "ready",
    source: "fin.voucher / fin.voucher_entry",
    primaryObjects: ["凭证头", "凭证分录", "版本记录", "过账", "冲销"],
    currentScope: "支持草稿、过账、冲销和历史凭证分录修订；正式分录保持单边非负。",
  },
  {
    key: "ledger",
    label: "账簿",
    path: "/app/finance-center/ledger",
    icon: List,
    status: "ready",
    source: "fin.book / fin.account / fin.ledger_balance",
    primaryObjects: ["账簿", "期间", "科目", "月余额", "来源链接"],
    currentScope: "三套法人账簿、416 个科目、1,125 条正式月余额已上线。",
  },
  {
    key: "reports",
    label: "报表",
    path: "/app/finance-center/reports",
    icon: DataAnalysis,
    status: "partial",
    source: "fin.statement_line / fin.statement_mapping / dm_finance_statement_monthly",
    primaryObjects: ["报表行", "科目映射", "资产负债表", "利润表", "现金流量表"],
    currentScope: "报表生成和映射表已上线，未确认映射时保持 pending_mapping。",
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
    source: "fin.period / fin.operation_log",
    primaryObjects: ["会计期间", "打开期间", "关闭状态", "操作审计"],
    currentScope: "期间模型和打开期间接口已上线，完整月结检查流待补齐。",
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
    source: "权限、报表映射、操作审计",
    primaryObjects: ["财务权限", "报表行", "科目映射", "导入批次", "操作日志"],
    currentScope: "权限与映射接口已上线，集中设置页待补齐批量维护能力。",
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
  permission: "finance:profit:view",
  children: financeCenterModules.map((item) => ({
    path: item.path,
    label: item.label,
    permission: "finance:profit:view",
  })),
};

export const financeProfitNavigation: FinanceNavigationItem[] = [
  ...financeLegacyModules,
  financeHistoryModules,
  mirroredFinanceCenterNavigation,
  { label: "现金安全", icon: Box, disabled: true, badge: "规划中", permission: "finance:cash:view" },
];
