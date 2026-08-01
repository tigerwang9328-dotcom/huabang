import type { FinanceNavigationItem } from "@/config/financeCenterModules";

export const MUMAREN_FINANCE_CENTER_ROOT = "/app/finance-center/mumaren";

export type MumarenFinanceCapabilityAvailability = "available" | "planned_backend";

export interface MumarenFinanceCapability {
  title: string;
  description: string;
  sourceModule?: string;
  availability: MumarenFinanceCapabilityAvailability;
  unavailableReason?: string;
}

// 标准财务中心导航:13 个一级条目,5 个一级带子项,共 30 个子项。
export interface MumarenFinanceNavItem {
  key: string;
  title: string;
  path: string;
  routeName: string;
  availability: MumarenFinanceCapabilityAvailability;
  children?: MumarenFinanceNavItem[];
  placeholder?: {
    summary: string;
    capabilities: Omit<MumarenFinanceCapability, "availability">[];
  };
}

const R = MUMAREN_FINANCE_CENTER_ROOT;

export const mumarenFinanceNavigation: MumarenFinanceNavItem[] = [
  { key: "compass", title: "数据罗盘", path: `${R}/compass`, routeName: "MumarenFinanceCompass", availability: "available" },
  { key: "history", title: "历史数据存档", path: `${R}/history`, routeName: "MumarenFinanceHistory", availability: "available" },
  {
    key: "vouchers",
    title: "凭证",
    path: `${R}/vouchers`,
    routeName: "MumarenFinanceVouchers",
    availability: "available",
    children: [
      { key: "voucher-create", title: "录凭证", path: `${R}/vouchers/create`, routeName: "MumarenFinanceVoucherCreate", availability: "available" },
      { key: "voucher-list", title: "查凭证", path: `${R}/vouchers/list`, routeName: "MumarenFinanceVoucherList", availability: "available" },
      { key: "voucher-summary", title: "凭证汇总", path: `${R}/vouchers/summary`, routeName: "MumarenFinanceVoucherSummary", availability: "available" },
      { key: "voucher-template", title: "凭证模板", path: `${R}/vouchers/template`, routeName: "MumarenFinanceVoucherTemplate", availability: "available" },
      { key: "voucher-auto", title: "自动凭证", path: `${R}/vouchers/auto`, routeName: "MumarenFinanceVoucherAuto", availability: "available" },
    ],
  },
  {
    key: "ledgers",
    title: "账簿",
    path: `${R}/ledgers`,
    routeName: "MumarenFinanceLedgers",
    availability: "available",
    children: [
      { key: "general-ledger", title: "总账", path: `${R}/ledgers/general`, routeName: "MumarenFinanceGeneralLedger", availability: "available" },
      { key: "trial-balance", title: "科目余额表", path: `${R}/ledgers/trial-balance`, routeName: "MumarenFinanceTrialBalance", availability: "available" },
      { key: "ledger-detail", title: "明细账", path: `${R}/ledgers/detail`, routeName: "MumarenFinanceLedgerDetail", availability: "available" },
    ],
  },
  {
    key: "reports",
    title: "报表",
    path: `${R}/reports`,
    routeName: "MumarenFinanceReports",
    availability: "available",
    children: [
      { key: "balance-sheet", title: "资产负债表", path: `${R}/reports/balance-sheet`, routeName: "MumarenFinanceBalanceSheet", availability: "available" },
      { key: "profit-statement", title: "利润表", path: `${R}/reports/profit-statement`, routeName: "MumarenFinanceProfitStatement", availability: "available" },
      { key: "cash-flow-statement", title: "现金流量表", path: `${R}/reports/cash-flow-statement`, routeName: "MumarenFinanceCashFlowStatement", availability: "available" },
      { key: "receivable-detail", title: "应收明细", path: `${R}/reports/receivable-detail`, routeName: "MumarenFinanceReceivableDetail", availability: "available" },
      { key: "payable-detail", title: "应付明细", path: `${R}/reports/payable-detail`, routeName: "MumarenFinancePayableDetail", availability: "available" },
      { key: "expense-detail", title: "费用明细表", path: `${R}/reports/expense-detail`, routeName: "MumarenFinanceExpenseDetail", availability: "available" },
      { key: "tax-detail", title: "税金明细表", path: `${R}/reports/tax-detail`, routeName: "MumarenFinanceTaxDetail", availability: "available" },
      { key: "sales-monthly", title: "销售月报表", path: `${R}/reports/sales-monthly`, routeName: "MumarenFinanceSalesMonthly", availability: "available" },
    ],
  },
  { key: "ar-ap", title: "应收应付", path: `${R}/ar-ap`, routeName: "MumarenFinanceArAp", availability: "available" },
  { key: "closing", title: "结账", path: `${R}/closing`, routeName: "MumarenFinanceClosing", availability: "available" },
  { key: "assets", title: "资产", path: `${R}/assets`, routeName: "MumarenFinanceAssets", availability: "available" },
  { key: "invoices", title: "发票", path: `${R}/invoices`, routeName: "MumarenFinanceInvoices", availability: "available" },
  {
    key: "cashier",
    title: "出纳",
    path: `${R}/cashier`,
    routeName: "MumarenFinanceCashier",
    availability: "available",
    children: [
      { key: "cashier-accounts", title: "账户与流水", path: `${R}/cashier/accounts`, routeName: "MumarenFinanceCashierAccounts", availability: "available" },
      { key: "cashier-reconciliation", title: "银行余额调节表", path: `${R}/cashier/reconciliation`, routeName: "MumarenFinanceCashierReconciliation", availability: "available" },
    ],
  },
  { key: "payroll", title: "工资", path: `${R}/payroll`, routeName: "MumarenFinancePayroll", availability: "available" },
  { key: "tax", title: "税务", path: `${R}/tax`, routeName: "MumarenFinanceTax", availability: "available" },
  {
    key: "settings",
    title: "设置",
    path: `${R}/settings`,
    routeName: "MumarenFinanceSettings",
    availability: "available",
    children: [
      { key: "settings-accounts", title: "科目管理", path: `${R}/settings/accounts`, routeName: "MumarenFinanceSettingsAccounts", availability: "available" },
      { key: "settings-books", title: "账套管理", path: `${R}/settings/books`, routeName: "MumarenFinanceSettingsBooks", availability: "available" },
      { key: "settings-auxiliary", title: "辅助核算", path: `${R}/settings/auxiliary`, routeName: "MumarenFinanceSettingsAuxiliary", availability: "available" },
      { key: "settings-audit-logs", title: "操作日志", path: `${R}/settings/audit-logs`, routeName: "MumarenFinanceSettingsAuditLogs", availability: "available" },
    ],
  },
];

// 扁平化所有 navItem(含子项),用于查找
export const flattenMumarenFinanceNavigation = (): MumarenFinanceNavItem[] => {
  const result: MumarenFinanceNavItem[] = [];
  const walk = (items: MumarenFinanceNavItem[]) => {
    for (const it of items) {
      result.push(it);
      if (it.children?.length) walk(it.children);
    }
  };
  walk(mumarenFinanceNavigation);
  return result;
};

// 主侧边栏"财务中心"菜单项:可展开,children 为 13 个一级条目(其中有子项的再展开)。
export const mumarenFinanceCenterMenuItem: FinanceNavigationItem = {
  label: "财务中心",
  key: "mumaren-finance-center",
  permission: "mumaren_finance_center:access",
  children: [
    { path: `${R}/compass`, label: "数据罗盘" },
    { path: `${R}/history`, label: "历史数据存档" },
    {
      label: "凭证",
      key: "mumaren-vouchers",
      children: [
        { path: `${R}/vouchers/create`, label: "录凭证" },
        { path: `${R}/vouchers/list`, label: "查凭证" },
        { path: `${R}/vouchers/summary`, label: "凭证汇总" },
      ],
    },
    {
      label: "账簿",
      key: "mumaren-ledgers",
      children: [
        { path: `${R}/ledgers/general`, label: "总账" },
        { path: `${R}/ledgers/trial-balance`, label: "科目余额表" },
        { path: `${R}/ledgers/detail`, label: "明细账" },
      ],
    },
    {
      label: "报表",
      key: "mumaren-reports",
      children: [
        { path: `${R}/reports/balance-sheet`, label: "资产负债表" },
        { path: `${R}/reports/profit-statement`, label: "利润表" },
        { path: `${R}/reports/cash-flow-statement`, label: "现金流量表" },
        { path: `${R}/reports/receivable-detail`, label: "应收明细" },
        { path: `${R}/reports/payable-detail`, label: "应付明细" },
        { path: `${R}/reports/expense-detail`, label: "费用明细表" },
        { path: `${R}/reports/tax-detail`, label: "税金明细表" },
        { path: `${R}/reports/sales-monthly`, label: "销售月报表" },
      ],
    },
    { path: `${R}/ar-ap`, label: "应收应付" },
    { path: `${R}/closing`, label: "结账" },
    { path: `${R}/assets`, label: "资产" },
    { path: `${R}/invoices`, label: "发票" },
    {
      label: "出纳",
      key: "mumaren-cashier",
      children: [
        { path: `${R}/cashier/accounts`, label: "账户与流水" },
        { path: `${R}/cashier/reconciliation`, label: "银行余额调节表" },
      ],
    },
    { path: `${R}/payroll`, label: "工资" },
    { path: `${R}/tax`, label: "税务" },
    {
      label: "设置",
      key: "mumaren-settings",
      children: [
        { path: `${R}/settings/accounts`, label: "科目管理" },
        { path: `${R}/settings/books`, label: "账套管理" },
        { path: `${R}/settings/auxiliary`, label: "辅助核算" },
        { path: `${R}/settings/audit-logs`, label: "操作日志" },
      ],
    },
  ],
};
