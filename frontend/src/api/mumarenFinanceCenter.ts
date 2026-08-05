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

export interface MumarenFinanceBookCreatePayload {
  book_code: string;
  book_name: string;
  company_name?: string | null;
  status?: "active" | "inactive";
}
export interface MumarenFinanceBookUpdatePayload {
  book_name?: string;
  company_name: string | null;
}

export interface MumarenFinanceAccount {
  id: number;
  account_code: string;
  account_name: string;
  account_type: string;
  direction: string;
  level: number;
  is_active?: boolean;
  required_auxiliary_types?: string[];
}

export interface AccountCreatePayload {
  account_code: string;
  account_name: string;
  account_type: "asset" | "liability" | "equity" | "income" | "expense";
  direction: "debit" | "credit";
  level: number;
}

export interface AccountUpdatePayload {
  book_id: number;
  account_name?: string;
  account_type?: AccountCreatePayload["account_type"];
  direction?: AccountCreatePayload["direction"];
  level?: number;
  is_active?: boolean;
}

export interface AccountAuxiliaryDimensionsPayload {
  book_id: number;
  auxiliary_types: Array<"customer" | "supplier" | "employee" | "project" | "department">;
}

// 凭证分录录入(对应后端 VoucherLineInput)
export interface VoucherLineInput {
  account_id: number;
  summary?: string | null;
  /** 保留录入人主动点×清空摘要的语义，避免明细账兼容回填。 */
  summary_explicitly_cleared?: boolean;
  debit_amount: number;
  credit_amount: number;
  auxiliaries?: Array<{ aux_type: "customer" | "supplier" | "employee" | "project" | "department"; auxiliary_id: number }>;
}

// 凭证草稿创建载荷(对应后端 VoucherCreateInput)
export interface VoucherCreatePayload {
  book_id: number;
  voucher_no?: string | null;
  voucher_date: string;
  summary?: string | null;
  voucher_type?: string;
  lines: VoucherLineInput[];
}

export interface ArApOrderLineInput {
  item_name: string;
  spec?: string | null;
  quantity: number;
  unit_price: number;
  amount: number;
  tax_rate?: number;
  tax_amount?: number;
  remark?: string | null;
}

export interface MumarenArApSettlement {
  id: number;
  settlement_date: string;
  amount: number;
  remark: string | null;
  created_by: number | null;
  created_at: string | null;
}

// AR/AP 草稿创建载荷(对应后端 ArApOrderInput)
export interface ArApOrderCreatePayload {
  book_id: number;
  order_type: "receivable" | "payable";
  order_no: string;
  order_date: string;
  counterparty_id?: number | null;
  counterparty_name: string;
  contact?: string | null;
  total_amount: number;
  remark?: string | null;
  lines?: ArApOrderLineInput[];
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
  contact: string | null;
  total_amount: number;
  settled_amount: number;
  remark: string | null;
  settlement_status: "open" | "partial" | "settled";
  workflow_status: "draft" | "reviewed" | "posted";
  has_details?: boolean;
  lines?: ArApOrderLineInput[];
  settlements?: MumarenArApSettlement[];
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
  default_rate: number;
  tax_category?: string | null;
  is_active?: boolean;
}

export interface TaxTypeCreatePayload {
  book_id: number;
  tax_code: string;
  tax_name: string;
  default_rate: number;
  tax_category?: string | null;
}

export interface TaxTypeUpdatePayload {
  book_id: number;
  tax_name?: string;
  default_rate?: number;
  tax_category?: string | null;
  is_active?: boolean;
}

export const taxTypesApi = {
  list: (params: { book_id: number }) => request.get<ApiResponse<MumarenTaxType[]>>(requestPath("/tax-types"), { params }),
  createTaxType: (data: TaxTypeCreatePayload) => request.post<ApiResponse<MumarenTaxType>>(requestPath("/tax-types"), data),
  updateTaxType: (id: number, data: TaxTypeUpdatePayload) => request.put<ApiResponse<MumarenTaxType>>(requestPath(`/tax-types/${id}`), data),
};

export interface MumarenFinanceVoucher {
  id: number;
  book_id: number;
  voucher_no: string;
  voucher_type: string | null;
  voucher_date: string;
  summary: string | null;
  status: "draft" | "reviewed" | "posted";
  total_debit: number;
  total_credit: number;
  /** 金蝶迁移凭证的只读来源标记；普通当前账为空。 */
  source_system?: string | null;
  source_database?: string | null;
  is_readonly?: boolean;
  is_normalized?: boolean;
}

export interface MumarenVoucherSummaryRow {
  period: string;
  voucher_type: string;
  voucher_count: number;
  total_debit: number;
  total_credit: number;
  is_balanced: boolean;
}

export interface MumarenVoucherSummary {
  rows: MumarenVoucherSummaryRow[];
  total_voucher_count: number;
  total_debit: number;
  total_credit: number;
  is_balanced: boolean;
  available_periods: string[];
  available_voucher_types: string[];
}

export interface MumarenVoucherSummaryDetailPage {
  items: MumarenFinanceVoucher[];
  total: number;
  offset: number;
  limit: number;
}

export interface MumarenVoucherSummaryParams {
  book_id: number;
  status?: MumarenFinanceVoucher["status"];
  period?: string;
  voucher_type?: string;
  keyword?: string;
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

export interface MumarenTrialBalanceReport {
  rows?: MumarenTrialBalanceRow[];
  /** 金蝶来源未提供会计报表分类时，由后端返回的待映射科目数。 */
  unclassified_account_count?: number;
}

export interface MumarenProfitStatement {
  total_income: number;
  total_expense: number;
  net_profit: number;
  unclassified_account_count?: number;
}

export interface MumarenCashFlowSection {
  inflow: number;
  outflow: number;
  net: number;
}

export interface MumarenCashFlowStatement {
  sections: Record<"operating" | "investing" | "financing", MumarenCashFlowSection>;
  total_inflow: number;
  total_outflow: number;
  total_net: number;
  cash_net_increase: number;
  unclassified_account_count?: number;
}

export interface MumarenArApAging {
  as_of: string;
  total_balance: number;
  buckets: Record<string, number>;
  counterparties: Array<{
    counterparty_name: string;
    total_balance: number;
    [bucket: string]: string | number | undefined | Array<{
      order_no: string;
      order_date: string;
      days: number;
      bucket: string;
      balance: number;
    }>;
    orders?: Array<{
      order_no: string;
      order_date: string;
      days: number;
      bucket: string;
      balance: number;
    }>;
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

export type DingtalkExpenseCategory = "reimbursement" | "payment";

export interface MumarenDingtalkExpense {
  id: number;
  applicant_name: string | null;
  department_name: string | null;
  expense_type: string | null;
  amount: number;
  category: DingtalkExpenseCategory | null;
  approval_status: string | null;
  payment_status: string | null;
  expense_date: string | null;
  updated_at: string | null;
}

export interface MumarenDingtalkExpensePage {
  items: MumarenDingtalkExpense[];
  total: number;
  page: number;
  page_size: number;
  source: "dingtalk:finance_expense_records";
  readonly: true;
}

export interface MumarenCashSafety {
  total_cash_balance: number;
  cash_record_date: string | null;
  daily_avg_expense_30d: number | null;
  expense_record_count_30d: number;
  cash_safety_days: number | null;
  risk_level: "critical" | "warning" | "normal" | "unknown";
  status: "ready" | "pending_data";
  note: string;
}

export const mumarenFinanceCenterApi = {
  getCatalog: () => request.get<ApiResponse<FinanceCenterCatalog>>(requestPath("/catalog")),
  listVouchers: (params?: { book_id?: number; voucher_id?: number; limit?: number; offset?: number }) => request.get<ApiResponse<MumarenFinanceVoucher[]>>(requestPath("/vouchers"), { params }),
  getVoucherSummary: (params: MumarenVoucherSummaryParams) => request.get<ApiResponse<MumarenVoucherSummary>>(requestPath("/vouchers/summary"), { params }),
  getVoucherSummaryDetails: (params: MumarenVoucherSummaryParams & { offset?: number; limit?: number }) => request.get<ApiResponse<MumarenVoucherSummaryDetailPage>>(requestPath("/vouchers/summary/details"), { params }),
  listBooks: () => request.get<ApiResponse<MumarenFinanceBook[]>>(requestPath("/books")),
  createBook: (data: MumarenFinanceBookCreatePayload) => request.post<ApiResponse<Pick<MumarenFinanceBook, "id" | "book_code" | "book_name" | "company_name" | "status">>>(requestPath("/books"), data),
  updateBook: (bookId: number, data: MumarenFinanceBookUpdatePayload) => request.put<ApiResponse<Pick<MumarenFinanceBook, "id" | "book_code" | "book_name" | "company_name" | "status" | "is_readonly">>>(requestPath(`/books/${bookId}`), data),
  replenishStarterAccounts: (bookId: number) => request.post<ApiResponse<{ added: number }>>(requestPath(`/books/${bookId}/starter-accounts`)),
  getLedgerLines: (params: { book_id: number; account_id?: number; start_date?: string; end_date?: string; limit?: number; offset?: number }) => request.get<ApiResponse<MumarenFinanceLedgerLinePage>>(requestPath("/ledger/lines"), { params }),
  listHistory: (params?: { source_system?: string; limit?: number }) => request.get<ApiResponse<MumarenFinanceHistoryVoucher[]>>(requestPath("/history/vouchers"), { params }),
  getHistoryBalanceSnapshots: (params: { book_id: number; period?: string; limit?: number; offset?: number }) => request.get<ApiResponse<MumarenFinanceBalanceSnapshot[]>>(requestPath("/history/balance-snapshots"), { params }),
  getTrialBalance: (params: { book_id: number; period?: string; start_date?: string; end_date?: string }) => request.get<ApiResponse<MumarenTrialBalanceReport>>(requestPath("/reports/trial-balance"), { params }),
  getNextVoucherNumber: (params: { book_id: number; voucher_date: string; voucher_type?: string }) => request.get<ApiResponse<{ voucher_no: string }>>(requestPath("/vouchers/next-number"), { params }),
  getProfitStatement: (params: { book_id: number; period?: string }) => request.get<ApiResponse<MumarenProfitStatement>>(requestPath("/reports/profit-statement"), { params }),
  getCashFlowStatement: (params: { book_id: number; period?: string }) => request.get<ApiResponse<MumarenCashFlowStatement>>(requestPath("/reports/cash-flow-statement"), { params }),
  getArApAging: (params: { book_id: number; order_type: "receivable" | "payable"; as_of?: string }) => request.get<ApiResponse<MumarenArApAging>>(requestPath("/ar-ap/aging"), { params }),
  getTaxAlerts: (params: { book_id: number; today?: string }) => request.get<ApiResponse<{ alerts: MumarenTaxAlert[]; record_count: number }>>(requestPath("/tax/alerts"), { params }),
  listTaxRecords: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenTaxRecord[]>>(requestPath("/tax/records"), { params }),
  listDingtalkExpenses: (params: { category?: DingtalkExpenseCategory; start_date?: string; end_date?: string; approval_status?: string; page?: number; page_size?: number }) => request.get<ApiResponse<MumarenDingtalkExpensePage>>(requestPath("/dingtalk-expenses"), { params }),
  getCashSafety: () => request.get<ApiResponse<MumarenCashSafety>>(requestPath("/cash-safety")),

  // ── 科目查询(只读,按账簿隔离) ──
  listAccounts: (bookId: number) => request.get<ApiResponse<MumarenFinanceAccount[]>>(requestPath(`/books/${bookId}/accounts`)),
  createAccount: (bookId: number, data: AccountCreatePayload) => request.post<ApiResponse<MumarenFinanceAccount>>(requestPath(`/books/${bookId}/accounts`), data),
  updateAccount: (bookId: number, accountId: number, data: AccountUpdatePayload) => request.put<ApiResponse<MumarenFinanceAccount>>(requestPath(`/books/${bookId}/accounts/${accountId}`), data),
  replaceAccountAuxiliaryDimensions: (bookId: number, accountId: number, data: AccountAuxiliaryDimensionsPayload) =>
    request.put<ApiResponse<{ account_id: number; required_auxiliary_types: string[] }>>(requestPath(`/books/${bookId}/accounts/${accountId}/auxiliary-dimensions`), data),

  // ── 凭证写入:草稿 → 财务审核 → 人工过账(禁止自动过账) ──
  createVoucher: (payload: VoucherCreatePayload) => request.post<ApiResponse<MumarenFinanceVoucher>>(requestPath("/vouchers"), payload),
  deleteVoucher: (voucherId: number) => request.delete<ApiResponse<null>>(requestPath(`/vouchers/${voucherId}`)),
  reviewVoucher: (voucherId: number) => request.post<ApiResponse<MumarenFinanceVoucher>>(requestPath(`/vouchers/${voucherId}/review`)),
  postVoucher: (voucherId: number) => request.post<ApiResponse<MumarenFinanceVoucher>>(requestPath(`/vouchers/${voucherId}/post`)),

  // ── AR/AP 写入:草稿 → 财务审核 → 人工结算(不产生凭证分录) ──
  createArApOrder: (payload: ArApOrderCreatePayload) => request.post<ApiResponse<MumarenArApOrder>>(requestPath("/ar-ap/orders"), payload),
  reviewArApOrder: (orderId: number, orderType: "receivable" | "payable") => request.post<ApiResponse<MumarenArApOrder>>(requestPath(`/ar-ap/orders/${orderId}/review`), null, { params: { order_type: orderType } }),
  settleArApOrder: (orderId: number, orderType: "receivable" | "payable", payload: ArApSettlePayload) => request.post<ApiResponse<MumarenArApOrder>>(requestPath(`/ar-ap/orders/${orderId}/settle`), payload, { params: { order_type: orderType } }),

  // ── 税务写入:草稿 → 财务审核 → 人工缴税(不产生凭证分录) ──
  createTaxRecord: (payload: TaxRecordCreatePayload) => request.post<ApiResponse<MumarenTaxRecord>>(requestPath("/tax/records"), payload),
  deleteTaxRecord: (recordId: number, bookId: number) => request.delete<ApiResponse<null>>(requestPath(`/tax/records/${recordId}`), { params: { book_id: bookId } }),
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
  asset_category: string | null;
  original_value: number;
  purchase_date: string;
  useful_life_months: number;
  accumulated_depreciation: number;
  status: "draft" | "active" | "disposed";
}
export interface FixedAssetInput {
  book_id: number;
  asset_code: string;
  asset_name: string;
  asset_category: string;
  original_value: number;
  purchase_date: string;
  residual_value: number;
  useful_life_months: number;
}
export interface FixedAssetUpdate {
  book_id: number;
  asset_name?: string;
  asset_category?: string;
  purchase_date?: string;
  original_value?: number;
  residual_value?: number;
  useful_life_months?: number;
  status?: "disposed";
}

export interface MumarenFinanceBalanceSnapshot {
  id: number;
  period_code: string;
  account_code: string;
  account_name: string;
  opening_amount: number;
  period_debit: number;
  period_credit: number;
  closing_amount: number;
  source_database: string;
  is_readonly: boolean;
}

export interface MumarenFinanceLedgerLine {
  id: number;
  voucher_id: number;
  line_no: number;
  voucher_no: string;
  voucher_type: string;
  voucher_date: string;
  voucher_summary?: string;
  line_summary?: string;
  account_id: number;
  account_code: string;
  account_name: string;
  debit_amount: number;
  credit_amount: number;
  running_balance: number;
  balance_direction: "debit" | "credit";
  is_readonly: boolean;
}

export interface MumarenFinanceLedgerLinePage {
  rows: MumarenFinanceLedgerLine[];
  has_more: boolean;
  next_offset: number;
}
export const fixedAssetsApi = {
  list: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenFixedAsset[]>>(requestPath("/fixed-assets"), { params }),
  create: (data: FixedAssetInput) => request.post<ApiResponse<MumarenFixedAsset>>(requestPath("/fixed-assets"), data),
  update: (id: number, data: FixedAssetUpdate) => request.put<ApiResponse<MumarenFixedAsset>>(requestPath(`/fixed-assets/${id}`), data),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/fixed-assets/${id}`), { params: { book_id } }),
  dispose: (id: number, book_id: number) => request.put<ApiResponse<MumarenFixedAsset>>(requestPath(`/fixed-assets/${id}`), { book_id, status: "disposed" }),
  depreciate: (id: number, book_id: number) => request.post<ApiResponse<MumarenFixedAsset>>(requestPath(`/fixed-assets/${id}/depreciate`), null, { params: { book_id } }),
};

// ── 发票 ──
export interface MumarenInvoice {
  id: number;
  book_id: number;
  invoice_no: string;
  invoice_type: "input" | "output";
  counterparty_name: string | null;
  amount: number;
  tax_amount: number;
  invoice_date: string;
  verification_status: "draft" | "verified";
  workflow_status: "draft" | "reviewed";
}
export interface InvoiceInput {
  book_id: number;
  invoice_no: string;
  invoice_type: "input" | "output";
  counterparty_name?: string | null;
  amount: number;
  tax_amount: number;
  invoice_date: string;
}
export interface InvoiceUpdate {
  book_id: number;
  invoice_type?: "input" | "output";
  counterparty_name?: string | null;
  amount?: number;
  tax_amount?: number;
  invoice_date?: string;
}
export const invoicesApi = {
  list: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenInvoice[]>>(requestPath("/invoices"), { params }),
  create: (data: InvoiceInput) => request.post<ApiResponse<MumarenInvoice>>(requestPath("/invoices"), data),
  update: (id: number, data: InvoiceUpdate) => request.put<ApiResponse<MumarenInvoice>>(requestPath(`/invoices/${id}`), data),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/invoices/${id}`), { params: { book_id } }),
  verify: (id: number, book_id: number) => request.post<ApiResponse<MumarenInvoice>>(requestPath(`/invoices/${id}/verify`), null, { params: { book_id } }),
};

// ── 出纳账户 ──
export interface MumarenCashAccount {
  id: number;
  book_id: number;
  account_code: string;
  account_name: string;
  account_type: string;
  currency: string;
  is_active: boolean;
}
export interface CashAccountInput {
  book_id: number;
  account_code: string;
  account_name: string;
  account_type: string;
  currency: string;
}
export interface CashAccountUpdate {
  book_id: number;
  account_name?: string;
  account_type?: string;
  currency?: string;
}
export const cashAccountsApi = {
  list: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenCashAccount[]>>(requestPath("/cash-accounts"), { params }),
  create: (data: CashAccountInput) => request.post<ApiResponse<MumarenCashAccount>>(requestPath("/cash-accounts"), data),
  update: (id: number, data: CashAccountUpdate) => request.put<ApiResponse<MumarenCashAccount>>(requestPath(`/cash-accounts/${id}`), data),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/cash-accounts/${id}`), { params: { book_id } }),
};

// ── 现金流水 ──
export interface MumarenCashFlow {
  id: number;
  book_id: number;
  cash_account_id: number;
  flow_date: string;
  direction: "in" | "out";
  amount: number;
  category: string | null;
  counterparty_name: string | null;
  workflow_status: "draft" | "reviewed";
}
export interface CashFlowInput {
  book_id: number;
  cash_account_id: number;
  flow_date: string;
  direction: "in" | "out";
  amount: number;
  category?: string | null;
  counterparty_name?: string | null;
}
export const cashFlowsApi = {
  list: (params: { book_id: number; cash_account_id?: number; limit?: number }) => request.get<ApiResponse<MumarenCashFlow[]>>(requestPath("/cash-flows"), { params }),
  create: (data: CashFlowInput) => request.post<ApiResponse<MumarenCashFlow>>(requestPath("/cash-flows"), data),
};

// ── 工资 ──
export interface MumarenPayroll {
  id: number;
  book_id: number;
  employee_no: string;
  employee_name: string;
  period: string;
  gross_amount: number;
  deduction_amount: number;
  net_amount: number;
  workflow_status: "draft" | "paid";
  voucher_id: number | null;
}
export interface PayrollInput {
  book_id: number;
  period: string;
  employee_no: string;
  employee_name: string;
  gross_amount: number;
  deduction_amount: number;
  net_amount: number;
}
export interface PayrollUpdate {
  book_id: number;
  employee_name?: string;
  gross_amount?: number;
  deduction_amount?: number;
  net_amount?: number;
}
export const payrollsApi = {
  list: (params: { book_id: number; period?: string; limit?: number }) => request.get<ApiResponse<MumarenPayroll[]>>(requestPath("/payrolls"), { params }),
  create: (data: PayrollInput) => request.post<ApiResponse<MumarenPayroll>>(requestPath("/payrolls"), data),
  update: (id: number, data: PayrollUpdate) => request.put<ApiResponse<MumarenPayroll>>(requestPath(`/payrolls/${id}`), data),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/payrolls/${id}`), { params: { book_id } }),
  pay: (id: number, book_id: number) => request.post<ApiResponse<MumarenPayroll>>(requestPath(`/payrolls/${id}/pay`), null, { params: { book_id } }),
};

// ── 期间(结账) ──
export interface MumarenPeriod {
  id: number;
  book_id: number;
  period_code: string;
  start_date: string;
  end_date: string;
  status: "open" | "closed";
  closed_by: number | null;
  closed_at: string | null;
}
export interface MumarenPeriodPrecheck {
  period: string;
  can_close: boolean;
  blocking_count: number;
  checks: Array<{ key: string; title: string; count: number; passed: boolean; message: string }>;
}
export const periodsApi = {
  list: (params: { book_id: number }) => request.get<ApiResponse<MumarenPeriod[]>>(requestPath("/periods"), { params }),
  initialize: (book_id: number, period: string) => request.post<ApiResponse<MumarenPeriod>>(requestPath("/periods/initialize"), null, { params: { book_id, period } }),
  precheck: (book_id: number, period: string) => request.post<ApiResponse<MumarenPeriodPrecheck>>(requestPath("/periods/pre-check"), null, { params: { book_id, period } }),
  close: (id: number, book_id: number) => request.post<ApiResponse<MumarenPeriod>>(requestPath(`/periods/${id}/close`), null, { params: { book_id } }),
  reopen: (id: number, book_id: number) => request.post<ApiResponse<MumarenPeriod>>(requestPath(`/periods/${id}/reopen`), null, { params: { book_id } }),
};

// ── AR/AP 订单(补充列表查询与删除) ──
export interface ArApOrderUpdate {
  counterparty_name?: string;
  contact?: string | null;
  total_amount?: number;
  order_date?: string;
  remark?: string | null;
  lines?: ArApOrderLineInput[];
}
export interface MumarenArApSummary {
  total_count: number;
  total_amount: number;
  settled_amount: number;
  outstanding_amount: number;
  open_count: number;
}
export const arApOrdersApi = {
  list: (params: { book_id: number; order_type: "receivable" | "payable"; period?: string; status?: "draft" | "open" | "partial" | "settled"; counterparty_name?: string; limit?: number }) => request.get<ApiResponse<MumarenArApOrder[]>>(requestPath("/ar-ap/orders"), { params }),
  summary: (params: { book_id: number; order_type: "receivable" | "payable"; period?: string; status?: "draft" | "open" | "partial" | "settled"; counterparty_name?: string }) => request.get<ApiResponse<MumarenArApSummary>>(requestPath("/ar-ap/orders/summary"), { params }),
  // 后端 ArApOrderUpdate 的 book_id 是请求体字段；查询参数仅用于路由过滤，不能替代它。
  update: (id: number, data: ArApOrderUpdate, book_id: number, order_type: "receivable" | "payable") => request.put<ApiResponse<MumarenArApOrder>>(requestPath(`/ar-ap/orders/${id}`), { ...data, book_id }, { params: { order_type } }),
  detail: (id: number, book_id: number, order_type: "receivable" | "payable") => request.get<ApiResponse<MumarenArApOrder>>(requestPath(`/ar-ap/orders/${id}`), { params: { book_id, order_type } }),
  delete: (id: number, book_id: number, order_type: string) => request.delete<ApiResponse<null>>(requestPath(`/ar-ap/orders/${id}`), { params: { book_id, order_type } }),
};

// 付款台账以独立应付单及其人工结算为唯一事实来源，避免重复付款表。
export const paymentsApi = arApOrdersApi;

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
  summary: string | null;
  lines_json: VoucherTemplateLines | null;
  created_at: string;
}
export interface VoucherTemplateLine {
  account_id: number;
  summary?: string | null;
  debit_amount: number;
  credit_amount: number;
}
export interface VoucherTemplateLines {
  lines: VoucherTemplateLine[];
}
export interface VoucherTemplateInput {
  book_id: number;
  template_name: string;
  voucher_type: string;
  summary: string;
  lines_json: VoucherTemplateLines;
}
export interface VoucherTemplateUpdate {
  book_id: number;
  template_name?: string;
  voucher_type?: string;
  summary?: string;
  lines_json?: VoucherTemplateLines;
}
export const voucherTemplatesApi = {
  list: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenVoucherTemplate[]>>(requestPath("/voucher-templates"), { params }),
  create: (data: VoucherTemplateInput) => request.post<ApiResponse<MumarenVoucherTemplate>>(requestPath("/voucher-templates"), data),
  update: (id: number, data: VoucherTemplateUpdate) => request.put<ApiResponse<MumarenVoucherTemplate>>(requestPath(`/voucher-templates/${id}`), data),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/voucher-templates/${id}`), { params: { book_id } }),
};

// ── 自动凭证规则 ──
export interface MumarenAutoVoucherRule {
  id: number;
  book_id: number;
  rule_name: string;
  trigger_event: string;
  debit_account_id: number | null;
  credit_account_id: number | null;
  default_amount: number | null;
  summary: string | null;
  voucher_type: string;
  is_active: boolean;
  created_at: string;
}
export interface AutoVoucherRuleInput {
  book_id: number;
  rule_name: string;
  trigger_event: string;
  debit_account_id: number;
  credit_account_id: number;
  default_amount?: number;
  summary?: string;
  voucher_type: string;
  is_active: boolean;
}
export interface AutoVoucherRuleUpdate {
  book_id: number;
  rule_name?: string;
  trigger_event?: string;
  debit_account_id?: number;
  credit_account_id?: number;
  default_amount?: number;
  summary?: string;
  voucher_type?: string;
  is_active?: boolean;
}
export interface AutoVoucherDraftRequest {
  book_id: number;
  voucher_no: string;
  voucher_date: string;
  source_key: string;
  amount?: number;
  summary?: string;
}
export interface AutoVoucherDraftPreview {
  status: "draft";
  source_key: string;
  summary: string;
  voucher_type: string;
  amount: number;
  voucher_no: string;
  voucher_date: string;
  lines: VoucherTemplateLine[];
}
export const autoVoucherRulesApi = {
  list: (params: { book_id: number; limit?: number }) => request.get<ApiResponse<MumarenAutoVoucherRule[]>>(requestPath("/auto-voucher-rules"), { params }),
  create: (data: AutoVoucherRuleInput) => request.post<ApiResponse<MumarenAutoVoucherRule>>(requestPath("/auto-voucher-rules"), data),
  update: (id: number, data: AutoVoucherRuleUpdate) => request.put<ApiResponse<MumarenAutoVoucherRule>>(requestPath(`/auto-voucher-rules/${id}`), data),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/auto-voucher-rules/${id}`), { params: { book_id } }),
  previewAutoVoucherDraft: (ruleId: number, data: AutoVoucherDraftRequest) => request.post<ApiResponse<AutoVoucherDraftPreview>>(requestPath(`/auto-voucher-rules/${ruleId}/preview`), data),
  generateAutoVoucherDraft: (ruleId: number, data: AutoVoucherDraftRequest) => request.post<ApiResponse<{ voucher_id: number; voucher_no: string; status: "draft" | "reviewed" | "posted"; reused: boolean }>>(requestPath(`/auto-voucher-rules/${ruleId}/generate-draft`), data),
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
  store_code: string;
  store_name: string | null;
  sales_amount: number;
  return_amount: number;
  net_sales: number;
  remark: string | null;
  created_at: string | null;
}
export interface SalesMonthlyReportInput {
  book_id: number;
  period: string;
  store_code: string;
  store_name: string;
  sales_amount: number;
  return_amount: number;
  remark: string;
}
export interface SalesMonthlyReportUpdate {
  book_id: number;
  period?: string;
  store_code?: string;
  store_name?: string;
  sales_amount?: number;
  return_amount?: number;
  remark?: string | null;
}
export const salesMonthlyReportsApi = {
  list: (params: { book_id: number; period?: string; limit?: number }) => request.get<ApiResponse<MumarenSalesMonthlyReport[]>>(requestPath("/sales-monthly-reports"), { params }),
  create: (data: SalesMonthlyReportInput) => request.post<ApiResponse<MumarenSalesMonthlyReport>>(requestPath("/sales-monthly-reports"), data),
  update: (id: number, data: SalesMonthlyReportUpdate) => request.put<ApiResponse<MumarenSalesMonthlyReport>>(requestPath(`/sales-monthly-reports/${id}`), data),
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
  parent_id: number | null;
  is_active: boolean;
  created_at: string;
}
export interface AuxiliaryAccountingInput {
  book_id: number;
  aux_type: string;
  code: string;
  name: string;
  parent_id?: number | null;
}
export interface AuxiliaryAccountingUpdate {
  book_id: number;
  name?: string;
  parent_id?: number | null;
  is_active?: boolean;
}
export const auxiliaryAccountingsApi = {
  list: (params: { book_id: number; aux_type?: string; limit?: number }) => request.get<ApiResponse<MumarenAuxiliaryAccounting[]>>(requestPath("/auxiliary-accountings"), { params }),
  create: (data: AuxiliaryAccountingInput) => request.post<ApiResponse<MumarenAuxiliaryAccounting>>(requestPath("/auxiliary-accountings"), data),
  update: (id: number, data: AuxiliaryAccountingUpdate) => request.put<ApiResponse<MumarenAuxiliaryAccounting>>(requestPath(`/auxiliary-accountings/${id}`), data),
  delete: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/auxiliary-accountings/${id}`), { params: { book_id } }),
};

// ── 每日经营参数与广告费(独立账簿；不读取旧财务或牧马人数据) ──
export interface MumarenOperatingStoreGroup {
  id: number;
  book_id: number;
  group_name: string;
  store_codes: string[];
}
export interface MumarenDailyOperatingParameter {
  id?: number;
  book_id: number;
  period: string;
  store_code: string;
  store_name: string;
  platform_income_rate: number;
  estimated_return_rate_pct: number;
  refund_only_rate_pct: number;
  freight_insurance_unit_cost: number;
  express_unit_cost: number;
  package_unit_cost: number;
  promotion_unit_cost: number;
  return_labor_unit_cost: number;
  goods_loss_unit_cost: number;
  return_rate_warning_threshold_pct: number;
  warning_enabled: boolean;
  remark: string | null;
  updated_at?: string | null;
}
export interface MumarenDailyAdCost {
  id?: number;
  book_id: number;
  business_date: string;
  store_code: string;
  store_name: string;
  platform: string | null;
  ad_cost: number;
  compensation_amount: number;
  remark: string | null;
  updated_at?: string | null;
}
export const operatingSettingsApi = {
  listStoreGroups: (params: { book_id: number }) => request.get<ApiResponse<MumarenOperatingStoreGroup[]>>(requestPath("/operating/store-groups"), { params }),
  createStoreGroup: (data: Omit<MumarenOperatingStoreGroup, "id">) => request.post<ApiResponse<MumarenOperatingStoreGroup>>(requestPath("/operating/store-groups"), data),
  updateStoreGroup: (id: number, data: Omit<MumarenOperatingStoreGroup, "id">) => request.put<ApiResponse<MumarenOperatingStoreGroup>>(requestPath(`/operating/store-groups/${id}`), data),
  deleteStoreGroup: (id: number, book_id: number) => request.delete<ApiResponse<null>>(requestPath(`/operating/store-groups/${id}`), { params: { book_id } }),
  listDailyParameters: (params: { book_id: number; period: string }) => request.get<ApiResponse<MumarenDailyOperatingParameter[]>>(requestPath("/operating/daily-parameters"), { params }),
  saveDailyParameters: (data: { book_id: number; period: string; rows: Omit<MumarenDailyOperatingParameter, "id" | "book_id" | "period" | "updated_at">[] }) => request.post<ApiResponse<MumarenDailyOperatingParameter[]>>(requestPath("/operating/daily-parameters/batch-save"), data),
  batchDailyParameter: (data: { book_id: number; period: string; field: string; value: number; store_codes: string[] }) => request.post<ApiResponse<MumarenDailyOperatingParameter[]>>(requestPath("/operating/daily-parameters/batch-field"), data),
  copyPreviousDailyParameters: (data: { book_id: number; period: string; overwrite?: boolean }) => request.post<ApiResponse<{ source_period: string; copied_count: number; rows: MumarenDailyOperatingParameter[] }>>(requestPath("/operating/daily-parameters/copy-previous"), data),
  listDailyAdCosts: (params: { book_id: number; business_date: string; platform?: string }) => request.get<ApiResponse<MumarenDailyAdCost[]>>(requestPath("/operating/daily-ad-costs"), { params }),
  saveDailyAdCosts: (data: { book_id: number; business_date: string; rows: Omit<MumarenDailyAdCost, "id" | "book_id" | "business_date" | "updated_at">[] }) => request.post<ApiResponse<MumarenDailyAdCost[]>>(requestPath("/operating/daily-ad-costs/batch-save"), data),
  batchDailyAdCost: (data: { book_id: number; business_date: string; store_codes: string[]; ad_cost: number }) => request.post<ApiResponse<MumarenDailyAdCost[]>>(requestPath("/operating/daily-ad-costs/batch-ad-cost"), data),
};
