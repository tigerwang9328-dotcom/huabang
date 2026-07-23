/**
 * 财务中心模块配置（牧马人风格）
 * 用于 MainLayout 侧边栏二级菜单
 */
import {
  Compass, Search, Plus, TrendCharts, CopyDocument, Refresh, List, Document, Link,
  DataLine, Histogram, Money, ShoppingCart, Ticket, Coin,
  CreditCard, Wallet, Key, Notebook, Setting, Box, Files, Timer, FolderOpened
} from "@element-plus/icons-vue"

export interface FinanceNavItem {
  key: string
  label: string
  icon: any
  path: string
  children?: FinanceNavItem[]
}

export const financeProfitNavigation: FinanceNavItem[] = [
  { key: "compass",          label: "数据罗盘",     icon: Compass,    path: "/app/finance/compass" },
  { key: "voucher-list",      label: "查凭证",       icon: Document,   path: "/app/finance/voucher/list" },
  { key: "voucher-new",       label: "录凭证",       icon: Plus,       path: "/app/finance/voucher/new" },
  { key: "voucher-summary",   label: "凭证汇总",     icon: TrendCharts,  path: "/app/finance/voucher/summary" },
  { key: "voucher-templates", label: "凭证模板",     icon: CopyDocument, path: "/app/finance/voucher/templates" },
  { key: "auto-entry",        label: "自动凭证",     icon: Refresh,    path: "/app/finance/auto-entry" },
  { key: "ar-recv",           label: "应收单据",     icon: Money,      path: "/app/finance/ar/recv-orders" },
  { key: "ar-payable",        label: "应付单据",     icon: ShoppingCart, path: "/app/finance/ar/payable-orders" },
  { key: "ar-aging",          label: "账龄分析",     icon: DataLine,   path: "/app/finance/ar/aging" },
  { key: "books-general",     label: "总账",         icon: Histogram,  path: "/app/finance/books/general" },
  { key: "books-balance",     label: "科目余额表",   icon: TrendCharts, path: "/app/finance/books/balance" },
  { key: "books-detail",      label: "明细账",       icon: List,       path: "/app/finance/books/detail" },
  { key: "reports-bs",        label: "资产负债表",   icon: Notebook,   path: "/app/finance/reports/balance-sheet" },
  { key: "reports-pl",        label: "利润表",       icon: TrendCharts, path: "/app/finance/reports/profit" },
  { key: "reports-cf",        label: "现金流量表",   icon: Wallet,     path: "/app/finance/reports/cashflow" },
  { key: "reports-recv",      label: "应收明细",     icon: Money,      path: "/app/finance/reports/receivable-detail" },
  { key: "reports-payable",   label: "应付明细",     icon: Ticket,     path: "/app/finance/reports/payable-detail" },
  { key: "reports-expense",   label: "费用明细表",   icon: Coin,       path: "/app/finance/reports/expense-detail" },
  { key: "reports-tax",       label: "税金明细表",   icon: Coin,       path: "/app/finance/reports/tax-detail" },
  { key: "closing",           label: "结账",         icon: Setting,    path: "/app/finance/closing" },
  { key: "assets",            label: "固定资产",     icon: Box,        path: "/app/finance/assets" },
  { key: "invoices",          label: "发票管理",     icon: Ticket,     path: "/app/finance/invoices" },
  { key: "payments",          label: "出纳",         icon: Wallet,     path: "/app/finance/payments" },
  { key: "cashier-accounts",    label: "账户与流水",     icon: Wallet,   path: "/app/finance/cashier/accounts" },
  { key: "cashier-recon",       label: "银行余额调节表", icon: DataLine, path: "/app/finance/cashier/reconciliation" },
  { key: "payroll",           label: "工资管理",     icon: CreditCard, path: "/app/finance/payroll" },
  { key: "tax",               label: "税务管理",     icon: Coin,       path: "/app/finance/tax" },
  { key: "settings-subjects", label: "科目管理",     icon: Setting,    path: "/app/finance/settings/subjects" },
  { key: "settings-books",    label: "账套管理",     icon: Notebook,   path: "/app/finance/settings/books" },
  { key: "settings-aux",      label: "辅助核算",     icon: Files,      path: "/app/finance/settings/aux" },
  { key: "settings-logs",     label: "操作日志",     icon: Timer,      path: "/app/finance/settings/logs" },
  { key: "history-archive",    label: "历史数据存档", icon: FolderOpened, path: "/app/finance/history-archive" },
]

export const financeCenterModules = financeProfitNavigation.map(item => ({
  key: item.key,
  label: item.label,
  icon: item.icon,
  path: item.path,
  status: "active" as const,
  description: "",
}))
