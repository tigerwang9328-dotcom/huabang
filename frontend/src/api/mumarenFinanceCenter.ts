import request, { type ApiResponse } from "@/api/request";

// request 的 baseURL 已固定为 /api/v1；此常量记录本模块唯一的完整公网接口根路径。
export const MUMAREN_FINANCE_CENTER_API_ROOT = "/api/v1/finance-center/mumaren";
const requestPath = (path: string) => MUMAREN_FINANCE_CENTER_API_ROOT.replace("/api/v1", "") + path;

export interface FinanceCenterCatalog {
  module: string;
  capabilities: string[];
}

export interface MumarenFinanceBook {
  id: number;
  book_code: string;
  book_name: string;
  company_name: string | null;
  status: string;
  is_readonly: boolean;
  source_system: string | null;
  source_database: string | null;
}

export interface MumarenFinanceAccount {
  id: number;
  account_code: string;
  account_name: string;
  account_type: string;
  direction: string;
  level: number;
}

// 凭证分录录入(对应后端 VoucherLineInput)
export interface VoucherLineInput {
  account_id: number;
  summary?: string | null;
  debit_amount: number;
  credit_amount: number;
}

// 凭证草稿创建载荷(对应后端 VoucherCreateInput)
export interface VoucherCreatePayload {
  book_id: number;
  voucher_no: string;
  voucher_date: string;
  summary?: string | null;
  voucher_type?: string;
  lines: VoucherLineInput[];
}

// AR/AP 草稿创建载荷(对应后端 ArApOrderInput)
export interface ArApOrderCreatePayload {
  book_id: number;
  order_type: "receivable" | "payable";
  order_no: string;
  order_date: string;
  counterparty_id?: number | null;
  counterparty_name: string;
  total_amount: number;
  remark?: string | null;
}

// AR/AP 人工结算载荷(对应后端 ArApSettleInput)
export interface ArApSettlePayload {
  settlement_date: string;
  amount: number;
  remark?: string | null;
}

// AR/AP 单据(含状态机字段,用于刚创建单据的审核/结算)
// 后端契约:结算后改 settlement_status(open/partial/settled),workflow_status 仍为 reviewed。
export interface MumarenArApOrder {
  id: number;
  book_id: number;
  order_type: string;
  order_no: string;
  order_date: string;
  counterparty_id: number | null;
  counterparty_name: string;
  total_amount: number;
  settled_amount: number;
  settlement_status: "open" | "partial" | "settled";
  workflow_status: "draft" | "reviewed" | "posted";
}

// 税务草稿创建载荷(对应后端 TaxRecordInput)
export interface TaxRecordCreatePayload {
  book_id: number;
  tax_type_id: number;
  period: string;
  tax_amount: number;
  due_date?: string | null;
  remark?: string | null;
}

// 税务人工缴税载荷(对应后端 TaxPayInput)
export interface TaxPayPayload {
  payment_date: string;
  amount: number;
  remark?: string | null;
}

// 税务记录完整字段(含 id/workflow_status/unpaid_amount,用于审核/缴税)
// 注:MumarenTaxRecord 已包含全部字段,此别名仅为语义标注,统一使用 MumarenTaxRecord。
export type MumarenTaxRecordFull = MumarenTaxRecord;

// 税种(用于录入税务草稿时选择税种)
export interface MumarenTaxType {
  id: number;
  tax_code: string;
  tax_name: string;
}

export interface MumarenFinanceVoucher {
  id: number;
  book_id: number;
  voucher_no: string;
  voucher_date: string;
  summary: string | null;
  status: "draft" | "reviewed" | "posted";
  total_debit: number;
  total_credit: number;
}

export interface MumarenFinanceHistoryVoucher {
  id: number;
  source_system: string;
  source_key: string;
  record_type: string;
  is_readonly: boolean;
  voucher_no: string | null;
  voucher_date: string | null;
  summary: string | null;
}

export interface MumarenTrialBalanceRow {
  account_code: string;
  account_name: string;
  debit_amount: number;
  credit_amount: number;
  closing_debit: number;
  closing_credit: number;
}

export interface MumarenProfitStatement {
  total_income: number;
  total_expense: number;
  net_profit: number;
}

export interface MumarenArApAging {
  as_of: string;
  total_balance: number;
  buckets: Record<string, number>;
  counterparties: Array<{
    counterparty_name: string;
    total_balance: number;
    [bucket: string]: string | number | undefined;
  }>;
}

export interface MumarenTaxAlert {
  tax_name: string;
  period: string;
  outstanding: number;
  due_date: string;
  level: "danger" | "warning";
}

export interface MumarenTaxRecord {
  id: number;
  tax_code?: string | null;
  tax_name: string;
  period: string;
  tax_amount: number;
  paid_amount: number;
  unpaid_amount?: number;
  due_date: string | null;
  // 后端契约:缴税后改 status(pending/paid),workflow_status 仍为 reviewed。
  status: "pending" | "paid";
  workflow_status?: "draft" | "reviewed";
}

export const mumarenFinanceCenterApi = {
  getCatalog: () => request.get<ApiResponse<FinanceCenterCatalog>>(requestPath("/catalog")),
  listVouchers: (params?: { book_id?: number }) => request.get<ApiResponse<MumarenFinanceVoucher[]>>(requestPath("/vouchers"), { params }),
  listBooks: () => request.get<ApiResponse<MumarenFinanceBook[]>>(requestPath("/books")),
  listHistory: (params?: { source_system?: string; limit?: number }) => request.get<ApiResponse<MumarenFinanceHistoryVoucher[]>>(requestPath("/history/vouchers"), { params }),
  getTrialBalance: (params: { book_id: number; period?: string }) => request.get<ApiResponse<{ rows?: MumarenTrialBalanceRow[] }>>(requestPath("/reports/trial-balance"), { params }),
  getProfitStatement: (params: { book_id: number; period?: string }) => request.get<ApiResponse<MumarenProfitStatement>>(requestPath("/reports/profit-statement"), { params }),
  getArApAging: (params: { book_id: number; order_type: "receivable" | "payable" }) => request.get<ApiResponse<MumarenArApAging>>(requestPath("/ar-ap/aging"), { params }),
  getTaxAlerts: (params: { book_id: number; today?: string }) => request.get<ApiResponse<{ alerts: MumarenTaxAlert[]; record_count: number }>>(requestPath("/tax/alerts"), { params }),
  listTaxRecords: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenTaxRecord[]>>(requestPath("/tax/records"), { params }),

  // ── 科目查询(只读,按账簿隔离) ──
  listAccounts: (bookId: number) => request.get<ApiResponse<MumarenFinanceAccount[]>>(requestPath(`/books/${bookId}/accounts`)),

  // ── 凭证写入:草稿 → 财务审核 → 人工过账(禁止自动过账) ──
  createVoucher: (payload: VoucherCreatePayload) => request.post<ApiResponse<MumarenFinanceVoucher>>(requestPath("/vouchers"), payload),
  reviewVoucher: (voucherId: number) => request.post<ApiResponse<MumarenFinanceVoucher>>(requestPath(`/vouchers/${voucherId}/review`)),
  postVoucher: (voucherId: number) => request.post<ApiResponse<MumarenFinanceVoucher>>(requestPath(`/vouchers/${voucherId}/post`)),

  // ── AR/AP 写入:草稿 → 财务审核 → 人工结算(不产生凭证分录) ──
  createArApOrder: (payload: ArApOrderCreatePayload) => request.post<ApiResponse<MumarenArApOrder>>(requestPath("/ar-ap/orders"), payload),
  reviewArApOrder: (orderId: number) => request.post<ApiResponse<MumarenArApOrder>>(requestPath(`/ar-ap/orders/${orderId}/review`)),
  settleArApOrder: (orderId: number, payload: ArApSettlePayload) => request.post<ApiResponse<MumarenArApOrder>>(requestPath(`/ar-ap/orders/${orderId}/settle`), payload),

  // ── 税务写入:草稿 → 财务审核 → 人工缴税(不产生凭证分录) ──
  createTaxRecord: (payload: TaxRecordCreatePayload) => request.post<ApiResponse<MumarenTaxRecord>>(requestPath("/tax/records"), payload),
  reviewTaxRecord: (recordId: number) => request.post<ApiResponse<MumarenTaxRecord>>(requestPath(`/tax/records/${recordId}/review`)),
  payTaxRecord: (recordId: number, payload: TaxPayPayload) => request.post<ApiResponse<MumarenTaxRecord>>(requestPath(`/tax/records/${recordId}/pay`), payload),
};

// ─────────────────────────────────────────────────────────────
// Task 18 扩展:12 组 CRUD + 状态转换 API(仅 /finance-center/mumaren/*)
// 所有写入均落库持久化,前端不再维护会话内数组。
// ─────────────────────────────────────────────────────────────

// ── 固定资产 ──
export interface MumarenFixedAsset {
  id: number;
  book_id: number;
  asset_code: string;
  asset_name: string;
  category: string;
  original_value: number;
  purchase_date: string;
  useful_life: number;
  accumulated_depreciation: number;
  net_value: number;
  status: "in_use" | "disposed";
  created_at: string;
}
export interface FixedAssetInput {
  book_id: number;
  asset_code: string;
  asset_name: string;
  category: string;
  original_value: number;
  purchase_date: string;
  useful_life: number;
}
export interface FixedAssetUpdate {
  asset_name?: string;
  category?: string;
  original_value?: number;
  useful_life?: number;
  status?: "in_use" | "disposed";
}
export const fixedAssetsApi = {
  list: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenFixedAsset[]>>(requestPath("/fixed-assets"), { params }),
  create: (data: FixedAssetInput) => request.post<ApiResponse<MumarenFixedAsset>>(requestPath("/fixed-assets"), data),
  update: (id: number, data: FixedAssetUpdate) => request.put<ApiResponse<MumarenFixedAsset>>(requestPath(`/fixed-assets/${id}`), data),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/fixed-assets/${id}`), { params: { book_id } }),
  dispose: (id: number, book_id: number) => request.put<ApiResponse<MumarenFixedAsset>>(requestPath(`/fixed-assets/${id}`), { status: "disposed" }, { params: { book_id } }),
  depreciate: (id: number, book_id: number) => request.post<ApiResponse<MumarenFixedAsset>>(requestPath(`/fixed-assets/${id}/depreciate`), null, { params: { book_id } }),
};

// ── 发票 ──
export interface MumarenInvoice {
  id: number;
  book_id: number;
  invoice_code: string;
  invoice_no: string;
  direction: "input" | "output";
  counterparty: string;
  amount: number;
  tax_amount: number;
  total_amount: number;
  invoice_date: string;
  certified: boolean;
  status: "draft" | "verified";
  created_at: string;
}
export interface InvoiceInput {
  book_id: number;
  invoice_code: string;
  invoice_no: string;
  direction: "input" | "output";
  counterparty: string;
  amount: number;
  tax_amount: number;
  invoice_date: string;
}
export interface InvoiceUpdate {
  counterparty?: string;
  amount?: number;
  tax_amount?: number;
  invoice_date?: string;
}
export const invoicesApi = {
  list: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenInvoice[]>>(requestPath("/invoices"), { params }),
  create: (data: InvoiceInput) => request.post<ApiResponse<MumarenInvoice>>(requestPath("/invoices"), data),
  update: (id: number, data: InvoiceUpdate, book_id: number) => request.put<ApiResponse<MumarenInvoice>>(requestPath(`/invoices/${id}`), data, { params: { book_id } }),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/invoices/${id}`), { params: { book_id } }),
  verify: (id: number, book_id: number) => request.post<ApiResponse<MumarenInvoice>>(requestPath(`/invoices/${id}/verify`), null, { params: { book_id } }),
};

// ── 出纳账户 ──
export interface MumarenCashAccount {
  id: number;
  book_id: number;
  account_name: string;
  account_type: string;
  opening_balance: number;
  current_balance: number;
  created_at: string;
}
export interface CashAccountInput {
  book_id: number;
  account_name: string;
  account_type: string;
  opening_balance: number;
}
export interface CashAccountUpdate {
  account_name?: string;
  account_type?: string;
}
export const cashAccountsApi = {
  list: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenCashAccount[]>>(requestPath("/cash-accounts"), { params }),
  create: (data: CashAccountInput) => request.post<ApiResponse<MumarenCashAccount>>(requestPath("/cash-accounts"), data),
  update: (id: number, data: CashAccountUpdate, book_id: number) => request.put<ApiResponse<MumarenCashAccount>>(requestPath(`/cash-accounts/${id}`), data, { params: { book_id } }),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/cash-accounts/${id}`), { params: { book_id } }),
};

// ── 现金流水 ──
export interface MumarenCashFlow {
  id: number;
  book_id: number;
  cash_account_id: number;
  transaction_date: string;
  direction: "income" | "expense";
  amount: number;
  counterparty: string;
  remark: string;
  created_at: string;
}
export interface CashFlowInput {
  book_id: number;
  cash_account_id: number;
  transaction_date: string;
  direction: "income" | "expense";
  amount: number;
  counterparty: string;
  remark: string;
}
export const cashFlowsApi = {
  list: (params: { book_id: number; cash_account_id?: number; limit?: number }) => request.get<ApiResponse<MumarenCashFlow[]>>(requestPath("/cash-flows"), { params }),
  create: (data: CashFlowInput) => request.post<ApiResponse<MumarenCashFlow>>(requestPath("/cash-flows"), data),
};

// ── 工资 ──
export interface MumarenPayroll {
  id: number;
  book_id: number;
  employee_name: string;
  department: string;
  period: string;
  base_salary: number;
  bonus: number;
  gross_salary: number;
  social_insurance: number;
  housing_fund: number;
  income_tax: number;
  net_salary: number;
  status: "draft" | "paid";
  created_at: string;
}
export interface PayrollInput {
  book_id: number;
  employee_name: string;
  department: string;
  period: string;
  base_salary: number;
  bonus: number;
  social_insurance: number;
  housing_fund: number;
  income_tax: number;
}
export interface PayrollUpdate {
  employee_name?: string;
  department?: string;
  base_salary?: number;
  bonus?: number;
  social_insurance?: number;
  housing_fund?: number;
  income_tax?: number;
}
export const payrollsApi = {
  list: (params: { book_id: number; period?: string; limit?: number }) => request.get<ApiResponse<MumarenPayroll[]>>(requestPath("/payrolls"), { params }),
  create: (data: PayrollInput) => request.post<ApiResponse<MumarenPayroll>>(requestPath("/payrolls"), data),
  update: (id: number, data: PayrollUpdate, book_id: number) => request.put<ApiResponse<MumarenPayroll>>(requestPath(`/payrolls/${id}`), data, { params: { book_id } }),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/payrolls/${id}`), { params: { book_id } }),
  pay: (id: number, book_id: number) => request.post<ApiResponse<MumarenPayroll>>(requestPath(`/payrolls/${id}/pay`), null, { params: { book_id } }),
};

// ── 期间(结账) ──
export interface MumarenPeriod {
  id: number;
  book_id: number;
  period: string;
  status: "open" | "closing" | "closed";
  closed_at: string | null;
  created_at: string;
}
export const periodsApi = {
  list: (params: { book_id: number }) => request.get<ApiResponse<MumarenPeriod[]>>(requestPath("/periods"), { params }),
  close: (id: number, book_id: number) => request.post<ApiResponse<MumarenPeriod>>(requestPath(`/periods/${id}/close`), null, { params: { book_id } }),
  reopen: (id: number, book_id: number) => request.post<ApiResponse<MumarenPeriod>>(requestPath(`/periods/${id}/reopen`), null, { params: { book_id } }),
};

// ── AR/AP 订单(补充列表查询与删除) ──
export interface ArApOrderUpdate {
  counterparty_name?: string;
  total_amount?: number;
  order_date?: string;
  remark?: string | null;
}
export const arApOrdersApi = {
  list: (params: { book_id: number; order_type: "receivable" | "payable"; limit?: number }) => request.get<ApiResponse<MumarenArApOrder[]>>(requestPath("/ar-ap/orders"), { params }),
  update: (id: number, data: ArApOrderUpdate, book_id: number, order_type: string) => request.put<ApiResponse<MumarenArApOrder>>(requestPath(`/ar-ap/orders/${id}`), data, { params: { book_id, order_type } }),
  delete: (id: number, book_id: number, order_type: string) => request.delete<ApiResponse<null>>(requestPath(`/ar-ap/orders/${id}`), { params: { book_id, order_type } }),
};

// ── 审计日志(只读) ──
export interface MumarenAuditLog {
  id: number;
  book_id: number | null;
  operation_time: string;
  module: string;
  action: string;
  operator: string;
  operator_id: number | null;
  detail: string;
}
export const auditLogsApi = {
  list: (params: { book_id?: number; action?: string; operator_id?: number; start_date?: string; end_date?: string; limit?: number }) => request.get<ApiResponse<MumarenAuditLog[]>>(requestPath("/audit-logs"), { params }),
};

// ── 凭证模板 ──
export interface MumarenVoucherTemplate {
  id: number;
  book_id: number;
  template_name: string;
  voucher_type: string;
  summary: string;
  created_at: string;
}
export interface VoucherTemplateInput {
  book_id: number;
  template_name: string;
  voucher_type: string;
  summary: string;
}
export interface VoucherTemplateUpdate {
  template_name?: string;
  voucher_type?: string;
  summary?: string;
}
export const voucherTemplatesApi = {
  list: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenVoucherTemplate[]>>(requestPath("/voucher-templates"), { params }),
  create: (data: VoucherTemplateInput) => request.post<ApiResponse<MumarenVoucherTemplate>>(requestPath("/voucher-templates"), data),
  update: (id: number, data: VoucherTemplateUpdate, book_id: number) => request.put<ApiResponse<MumarenVoucherTemplate>>(requestPath(`/voucher-templates/${id}`), data, { params: { book_id } }),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/voucher-templates/${id}`), { params: { book_id } }),
};

// ── 自动凭证规则 ──
export interface MumarenAutoVoucherRule {
  id: number;
  book_id: number;
  rule_name: string;
  business_type: string;
  account_code: string;
  direction: "debit" | "credit";
  amount_source: string;
  fixed_amount?: number;
  enabled: boolean;
  created_at: string;
}
export interface AutoVoucherRuleInput {
  book_id: number;
  rule_name: string;
  business_type: string;
  account_code: string;
  direction: "debit" | "credit";
  amount_source: string;
  fixed_amount?: number;
  enabled: boolean;
}
export interface AutoVoucherRuleUpdate {
  rule_name?: string;
  business_type?: string;
  account_code?: string;
  direction?: "debit" | "credit";
  enabled?: boolean;
}
export const autoVoucherRulesApi = {
  list: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenAutoVoucherRule[]>>(requestPath("/auto-voucher-rules"), { params }),
  create: (data: AutoVoucherRuleInput) => request.post<ApiResponse<MumarenAutoVoucherRule>>(requestPath("/auto-voucher-rules"), data),
  update: (id: number, data: AutoVoucherRuleUpdate, book_id: number) => request.put<ApiResponse<MumarenAutoVoucherRule>>(requestPath(`/auto-voucher-rules/${id}`), data, { params: { book_id } }),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/auto-voucher-rules/${id}`), { params: { book_id } }),
};

// ── 费用明细(草稿 → 财务审核 → 人工过账) ──
export interface MumarenExpenseEntry {
  id: number;
  book_id: number;
  period: string;
  account_code: string;
  account_name: string;
  amount: number;
  remark: string;
  status: "draft" | "reviewed" | "posted";
  created_at: string;
}
export interface ExpenseEntryInput {
  book_id: number;
  period: string;
  account_code: string;
  account_name: string;
  amount: number;
  remark: string;
}
export interface ExpenseEntryUpdate {
  account_code?: string;
  account_name?: string;
  amount?: number;
  remark?: string;
}
export const expenseEntriesApi = {
  list: (params: { book_id: number; period?: string; limit?: number }) => request.get<ApiResponse<MumarenExpenseEntry[]>>(requestPath("/expense-entries"), { params }),
  create: (data: ExpenseEntryInput) => request.post<ApiResponse<MumarenExpenseEntry>>(requestPath("/expense-entries"), data),
  update: (id: number, data: ExpenseEntryUpdate, book_id: number) => request.put<ApiResponse<MumarenExpenseEntry>>(requestPath(`/expense-entries/${id}`), data, { params: { book_id } }),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/expense-entries/${id}`), { params: { book_id } }),
  review: (id: number, book_id: number) => request.post<ApiResponse<MumarenExpenseEntry>>(requestPath(`/expense-entries/${id}/review`), null, { params: { book_id } }),
  post: (id: number, book_id: number) => request.post<ApiResponse<MumarenExpenseEntry>>(requestPath(`/expense-entries/${id}/post`), null, { params: { book_id } }),
};

// ── 销售月报 ──
export interface MumarenSalesMonthlyReport {
  id: number;
  book_id: number;
  period: string;
  store_name: string;
  sales_amount: number;
  return_amount: number;
  net_sales: number;
  remark: string;
  created_at: string;
}
export interface SalesMonthlyReportInput {
  book_id: number;
  period: string;
  store_name: string;
  sales_amount: number;
  return_amount: number;
  remark: string;
}
export interface SalesMonthlyReportUpdate {
  sales_amount?: number;
  return_amount?: number;
  remark?: string;
}
export const salesMonthlyReportsApi = {
  list: (params: { book_id: number; period?: string; limit?: number }) => request.get<ApiResponse<MumarenSalesMonthlyReport[]>>(requestPath("/sales-monthly-reports"), { params }),
  create: (data: SalesMonthlyReportInput) => request.post<ApiResponse<MumarenSalesMonthlyReport>>(requestPath("/sales-monthly-reports"), data),
  update: (id: number, data: SalesMonthlyReportUpdate, book_id: number) => request.put<ApiResponse<MumarenSalesMonthlyReport>>(requestPath(`/sales-monthly-reports/${id}`), data, { params: { book_id } }),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/sales-monthly-reports/${id}`), { params: { book_id } }),
};

// ── 银行余额调节 ──
export interface MumarenBankReconciliation {
  id: number;
  book_id: number;
  account_name: string;
  reconcile_date: string;
  book_balance: number;
  bank_balance: number;
  difference: number;
  status: "pending" | "reconciled";
  remark: string;
  created_at: string;
}
export interface BankReconciliationInput {
  book_id: number;
  account_name: string;
  reconcile_date: string;
  book_balance: number;
  bank_balance: number;
  remark: string;
}
export interface BankReconciliationUpdate {
  book_balance?: number;
  bank_balance?: number;
  status?: "pending" | "reconciled";
  remark?: string;
}
export const bankReconciliationsApi = {
  list: (params: { book_id: number; period?: string; limit?: number }) => request.get<ApiResponse<MumarenBankReconciliation[]>>(requestPath("/bank-reconciliations"), { params }),
  create: (data: BankReconciliationInput) => request.post<ApiResponse<MumarenBankReconciliation>>(requestPath("/bank-reconciliations"), data),
  update: (id: number, data: BankReconciliationUpdate, book_id: number) => request.put<ApiResponse<MumarenBankReconciliation>>(requestPath(`/bank-reconciliations/${id}`), data, { params: { book_id } }),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/bank-reconciliations/${id}`), { params: { book_id } }),
};

// ── 辅助核算 ──
export interface MumarenAuxiliaryAccounting {
  id: number;
  book_id: number;
  aux_type: string;
  code: string;
  name: string;
  parent_code: string | null;
  status: "active" | "inactive";
  remark: string;
  created_at: string;
}
export interface AuxiliaryAccountingInput {
  book_id: number;
  aux_type: string;
  code: string;
  name: string;
  parent_code?: string | null;
  remark: string;
}
export interface AuxiliaryAccountingUpdate {
  name?: string;
  parent_code?: string | null;
  status?: "active" | "inactive";
  remark?: string;
}
export const auxiliaryAccountingsApi = {
  list: (params: { book_id: number; aux_type?: string; limit?: number }) => request.get<ApiResponse<MumarenAuxiliaryAccounting[]>>(requestPath("/auxiliary-accountings"), { params }),
  create: (data: AuxiliaryAccountingInput) => request.post<ApiResponse<MumarenAuxiliaryAccounting>>(requestPath("/auxiliary-accountings"), data),
  update: (id: number, data: AuxiliaryAccountingUpdate, book_id: number) => request.put<ApiResponse<MumarenAuxiliaryAccounting>>(requestPath(`/auxiliary-accountings/${id}`), data, { params: { book_id } }),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/auxiliary-accountings/${id}`), { params: { book_id } }),
};
