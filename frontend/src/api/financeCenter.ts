import request from "./request";

// ============================================================
// Type definitions
// ============================================================

export interface FinBook {
  id: number;
  company_name: string;
  entity_code: string;
  account_set_code: string;
  currency_code: string;
  start_period: string | null;
  current_period: string | null;
  status: string;
}

export interface FinPeriod {
  id: number;
  book_id: number;
  period: string;
  fiscal_year: number;
  fiscal_period: number;
  start_date: string;
  end_date: string;
  status: string;
}

export interface FinAccount {
  id: number;
  book_id: number;
  account_code: string;
  account_name: string;
  parent_id: number | null;
  account_type: string;
  balance_direction: string;
  level: number;
  is_bank: boolean;
  is_cash: boolean;
  status: string;
}

export interface FinAuxCategory {
  id: number;
  category_code: string;
  category_name: string;
  status: string;
}

export interface FinAuxItem {
  id: number;
  category_id: number;
  item_code: string;
  item_name: string;
  target_type: string | null;
  target_code: string | null;
  status: string;
}

export interface FinVoucherEntry {
  id: number;
  line_no: number;
  account_id: number;
  account_code?: string;
  account_name?: string;
  summary: string;
  debit_amount: number;
  credit_amount: number;
  currency_code: string;
  exchange_rate: number;
  aux_items: Record<string, unknown>;
}

export interface FinVoucher {
  id: number;
  book_id: number;
  period_id: number;
  voucher_no: string;
  voucher_group: string;
  voucher_date: string;
  period: string;
  status: string;
  origin_kind: string;
  total_debit: number;
  total_credit: number;
  prepared_name: string;
  posted_at: string | null;
  version: number;
  reversal_of_id: number | null;
  reversed_by_id: number | null;
  entries?: FinVoucherEntry[];
}

export interface FinLedgerBalance {
  id: number;
  book_id: number;
  account_id: number;
  account_code?: string;
  account_name?: string;
  period: string;
  opening_debit: number;
  opening_credit: number;
  period_debit: number;
  period_credit: number;
  closing_debit: number;
  closing_credit: number;
  balance_direction?: string;
}

export interface FinReceivable {
  id: number;
  book_id: number;
  document_no: string;
  counterparty_aux_id: number;
  counterparty_name?: string;
  business_date: string;
  due_date: string | null;
  original_amount: number;
  settled_amount: number;
  remaining_amount: number;
  currency_code: string;
  status: string;
}

export interface FinPayable {
  id: number;
  book_id: number;
  document_no: string;
  counterparty_aux_id: number;
  counterparty_name?: string;
  business_date: string;
  due_date: string | null;
  original_amount: number;
  settled_amount: number;
  remaining_amount: number;
  currency_code: string;
  status: string;
}

export interface FinSettlement {
  id: number;
  book_id: number;
  settlement_type: string;
  receivable_id: number | null;
  payable_id: number | null;
  settlement_date: string;
  amount: number;
  reason: string;
  status: string;
}

export interface FinCashAccount {
  id: number;
  account_code: string;
  account_name: string;
  account_type: string;
  ledger_account_id: number;
  bank_name: string | null;
  bank_account_masked: string | null;
  currency_code: string;
  status: string;
}

export interface FinBankTransaction {
  id: number;
  book_id: number;
  cash_account_id: number;
  transaction_date: string;
  amount: number;
  direction: string;
  counterparty_name: string | null;
  reference_no: string | null;
  summary: string | null;
  source_system: string;
}

export interface FinFixedAsset {
  id: number;
  book_id: number;
  asset_code: string;
  asset_name: string;
  category: string;
  acquisition_date: string;
  in_service_date: string;
  original_cost: number;
  residual_rate: number;
  useful_life_months: number;
  monthly_depreciation?: number;
  accumulated_depreciation?: number;
  net_book_value?: number;
  status: string;
}

export interface FinInvoice {
  id: number;
  book_id: number;
  invoice_code: string;
  invoice_no: string;
  invoice_type: string;
  direction: string;
  invoice_date: string;
  amount_excluding_tax: number;
  tax_amount: number;
  total_amount: number;
  counterparty_aux_id: number | null;
  currency_code: string;
  status: string;
}

export interface FinPayroll {
  id: number;
  book_id: number;
  period: string;
  employee_aux_id: number;
  department_aux_id: number | null;
  gross_amount: number;
  social_security_amount: number;
  housing_fund_amount: number;
  tax_amount: number;
  other_deduction: number;
  net_amount: number;
  status: string;
}

export interface FinTaxRecord {
  id: number;
  book_id: number;
  tax_type: string;
  period: string;
  tax_amount: number;
  taxable_amount: number;
  paid_amount: number;
  due_date: string | null;
  paid_date: string | null;
  status: string;
}

export interface FinAutoEntryRule {
  id: number;
  book_id: number;
  rule_name: string;
  business_type: string;
  source_system: string;
  entry_template: Record<string, unknown>;
  effective_from: string;
  effective_to: string | null;
  priority: number;
  conditions: Record<string, unknown>;
  status: string;
}

export interface FinAutoEntryRun {
  id: number;
  rule_id: number;
  period: string;
  status: string;
  draft_count: number;
  exception_count: number;
  exceptions: Array<Record<string, unknown>>;
  created_at: string;
}

export interface FinOperationLog {
  id: number;
  book_id: number;
  actor_name: string;
  action: string;
  target_type: string;
  target_id: string;
  reason: string;
  before_data?: Record<string, unknown>;
  after_data?: Record<string, unknown>;
  created_at: string;
}

export interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AgingItem {
  counterparty_aux_id: number;
  counterparty_name: string;
  total_amount: number;
  within_30: number;
  days_31_90: number;
  days_91_180: number;
  over_180: number;
}

export interface TrialBalanceItem {
  account_id: number;
  account_code: string;
  account_name: string;
  opening_debit: number;
  opening_credit: number;
  period_debit: number;
  period_credit: number;
  closing_debit: number;
  closing_credit: number;
}

export interface GeneralLedgerItem {
  voucher_id: number;
  voucher_no: string;
  voucher_date: string;
  summary: string;
  debit_amount: number;
  credit_amount: number;
  balance: number;
  direction: string;
}

export interface StatementItem {
  line_code: string;
  line_name: string;
  current_amount: number | null;
  year_to_date_amount?: number | null;
  status: string;
}

export interface StatementResult {
  status: string;
  items: StatementItem[];
  issues: Array<Record<string, unknown>>;
}

export interface DepreciationItem {
  id: number;
  fixed_asset_id: number;
  asset_code?: string;
  asset_name?: string;
  period: string;
  depreciation_amount: number;
  accumulated_depreciation: number;
  net_book_value: number;
}

// ============================================================
// API client
// ============================================================

export const financeCenterApi = {
  // ---- Books (账套) ----
  listBooks: () => request.get<{ data: FinBook[] }>("/finance/books"),
  getBook: (id: number) => request.get<{ data: FinBook }>(`/finance/books/${id}`),

  // ---- Periods (期间) ----
  listPeriods: (params?: any) => request.get<{ data: FinPeriod[] }>("/finance/periods", { params }),
  openPeriod: (payload: { book_id: number; period: string }) => request.post<{ data: Record<string, unknown> }>("/finance/periods/open", payload),
  closePeriod: (payload: { book_id: number; period: string; reason: string }) => request.post<{ data: Record<string, unknown> }>("/finance/periods/close", payload),
  reopenPeriod: (payload: { book_id: number; period: string; reason: string }) => request.post<{ data: Record<string, unknown> }>("/finance/periods/reopen", payload),
  profitLossCarryover: (payload: { book_id: number; period: string; reason: string }) => request.post<{ data: Record<string, unknown> }>("/finance/periods/profit-loss-carryover", payload),

  // ---- Accounts (科目) ----
  listAccounts: (params?: any) => request.get<{ data: FinAccount[] }>("/finance/accounts", { params }),

  // ---- Aux Categories (辅助核算类别) ----
  listAuxCategories: (params?: any) => request.get<{ data: FinAuxCategory[] }>("/finance/aux-categories", { params }),
  upsertAuxCategory: (payload: { book_id: number; category_code: string; category_name: string; status?: string }) => request.post<{ data: Record<string, unknown> }>("/finance/aux-categories", payload),

  // ---- Aux Items (辅助核算项目) ----
  listAuxItems: (params?: any) => request.get<{ data: FinAuxItem[] }>("/finance/aux-items", { params }),
  upsertAuxItem: (payload: { book_id: number; category_id: number; item_code: string; item_name: string; target_type?: string; target_code?: string }) => request.post<{ data: Record<string, unknown> }>("/finance/aux-items", payload),

  // ---- Vouchers (凭证) ----
  listVouchers: (params?: any) => request.get<{ data: PageResult<FinVoucher> }>("/finance/vouchers", { params }),
  getVoucher: (id: number) => request.get<{ data: FinVoucher }>(`/finance/vouchers/${id}`),
  createVoucher: (payload: { book_id: number; period: string; voucher_no: string; voucher_date: string; reason: string; entries: Array<{ account_id: number; summary: string; debit_amount: number; credit_amount: number; currency_code?: string; exchange_rate?: number; aux_items?: Record<string, unknown> }> }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/vouchers", payload),
  reviewVoucher: (id: number, reason: string) => request.post<{ data: Record<string, unknown> }>(`/finance/vouchers/${id}/review`, { reason }),
  postVoucher: (id: number, reason: string) => request.post<{ data: Record<string, unknown> }>(`/finance/vouchers/${id}/post`, { reason }),
  unpostVoucher: (id: number, reason: string) => request.post<{ data: Record<string, unknown> }>(`/finance/vouchers/${id}/unpost`, { reason }),
  reverseVoucher: (id: number, payload: { voucher_no: string; reason: string }) => request.post<{ data: Record<string, unknown> }>(`/finance/vouchers/${id}/reverse`, payload),
  deleteVoucher: (id: number, reason: string) => request.delete<{ data: Record<string, unknown> }>(`/finance/vouchers/${id}`, { data: { reason } }),
  reviseVoucherEntries: (id: number, entries: Array<{ account_id: number; summary: string; debit_amount: number; credit_amount: number }>) =>
    request.post<{ data: Record<string, unknown> }>(`/finance/vouchers/${id}/revise-entries`, { entries }),

  // ---- Ledger (账簿) ----
  listLedgerBalances: (params?: any) => request.get<{ data: FinLedgerBalance[] }>("/finance/ledger/balances", { params }),
  generalLedger: (params?: any) => request.get<{ data: GeneralLedgerItem[] }>("/finance/ledger/general-ledger", { params }),
  subsidiaryLedger: (params?: any) => request.get<{ data: GeneralLedgerItem[] }>("/finance/ledger/subsidiary-ledger", { params }),
  trialBalance: (params?: any) => request.get<{ data: TrialBalanceItem[] }>("/finance/ledger/trial-balance", { params }),

  // ---- Receivables/Payables (应收应付) ----
  listReceivables: (params?: any) => request.get<{ data: PageResult<FinReceivable> }>("/finance/receivables", { params }),
  createReceivable: (payload: { book_id: number; document_no: string; counterparty_aux_id: number; business_date: string; due_date?: string; original_amount: number; currency_code?: string; source_system?: string }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/receivables", payload),
  listPayables: (params?: any) => request.get<{ data: PageResult<FinPayable> }>("/finance/payables", { params }),
  createPayable: (payload: { book_id: number; document_no: string; counterparty_aux_id: number; business_date: string; due_date?: string; original_amount: number; currency_code?: string; source_system?: string }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/payables", payload),
  listSettlements: (params?: any) => request.get<{ data: PageResult<FinSettlement> }>("/finance/settlements", { params }),
  createSettlement: (payload: { book_id: number; settlement_type: string; receivable_id?: number; payable_id?: number; settlement_date: string; amount: number; reason: string }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/settlements", payload),
  agingAnalysis: (params?: any) => request.get<{ data: AgingItem[] }>("/finance/aging", { params }),

  // ---- Cashier (出纳) ----
  listCashAccounts: (params?: any) => request.get<{ data: FinCashAccount[] }>("/finance/cash-accounts", { params }),
  upsertCashAccount: (payload: { book_id: number; account_code: string; account_name: string; account_type: string; ledger_account_id: number; bank_name?: string; bank_account_masked?: string; currency_code?: string }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/cash-accounts", payload),
  listBankTransactions: (params?: any) => request.get<{ data: PageResult<FinBankTransaction> }>("/finance/bank-transactions", { params }),
  createBankTransaction: (payload: { book_id: number; cash_account_id: number; transaction_date: string; amount: number; direction: string; counterparty_name?: string; reference_no?: string; summary?: string; source_system?: string }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/bank-transactions", payload),
  createReconciliation: (payload: { book_id: number; cash_account_id: number; period: string; statement_balance: number; ledger_balance: number; matched_transaction_ids?: number[] }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/reconciliations", payload),

  // ---- Fixed Assets (固定资产) ----
  listFixedAssets: (params?: any) => request.get<{ data: PageResult<FinFixedAsset> }>("/finance/fixed-assets", { params }),
  createFixedAsset: (payload: { book_id: number; asset_code: string; asset_name: string; category: string; acquisition_date: string; in_service_date: string; original_cost: number; residual_rate?: number; useful_life_months: number; department_aux_id?: number; expense_account_id?: number; accumulated_account_id?: number }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/fixed-assets", payload),
  calculateDepreciation: (fixedAssetId: number, period: string) =>
    request.post<{ data: Record<string, unknown> }>(`/finance/fixed-assets/${fixedAssetId}/depreciate`, { period }),
  listDepreciations: (params?: any) => request.get<{ data: PageResult<DepreciationItem> }>("/finance/depreciations", { params }),

  // ---- Invoices (发票) ----
  listInvoices: (params?: any) => request.get<{ data: PageResult<FinInvoice> }>("/finance/invoices", { params }),
  createInvoice: (payload: { book_id: number; invoice_code?: string; invoice_no: string; invoice_type: string; direction: string; invoice_date: string; amount_excluding_tax: number; tax_amount: number; counterparty_aux_id?: number; currency_code?: string; source_system?: string }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/invoices", payload),

  // ---- Payroll (工资) ----
  listPayrolls: (params?: any) => request.get<{ data: PageResult<FinPayroll> }>("/finance/payrolls", { params }),
  createPayroll: (payload: { book_id: number; period: string; employee_aux_id: number; department_aux_id?: number; gross_amount: number; social_security_amount?: number; housing_fund_amount?: number; tax_amount?: number; other_deduction?: number; source_system?: string }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/payrolls", payload),

  // ---- Tax (税务) ----
  listTaxRecords: (params?: any) => request.get<{ data: PageResult<FinTaxRecord> }>("/finance/tax-records", { params }),
  createTaxRecord: (payload: { book_id: number; tax_type: string; period: string; tax_amount: number; taxable_amount?: number; due_date?: string; source_system?: string }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/tax-records", payload),
  markTaxPaid: (taxRecordId: number, payload: { paid_date: string; reason: string }) =>
    request.post<{ data: Record<string, unknown> }>(`/finance/tax-records/${taxRecordId}/mark-paid`, payload),

  // ---- Auto Entry Rules (自动凭证) ----
  listAutoEntryRules: (params?: any) => request.get<{ data: FinAutoEntryRule[] }>("/finance/auto-entry-rules", { params }),
  upsertAutoEntryRule: (payload: { book_id: number; rule_name: string; business_type: string; source_system: string; entry_template: Record<string, unknown>; effective_from: string; effective_to?: string; priority?: number; conditions?: Record<string, unknown>; status?: string }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/auto-entry-rules", payload),
  runAutoEntry: (payload: { rule_id: number; period: string; source_data?: Array<Record<string, unknown>>; mode?: string }) =>
    request.post<{ data: FinAutoEntryRun }>("/finance/auto-entry-rules/run", payload),
  listAutoEntryRuns: (params?: any) => request.get<{ data: PageResult<FinAutoEntryRun> }>("/finance/auto-entry-runs", { params }),

  // ---- Operation Logs (操作日志) ----
  listOperationLogs: (params?: any) => request.get<{ data: PageResult<FinOperationLog> }>("/finance/operation-logs", { params }),

  // ---- Statements (财务报表) ----
  upsertStatementLine: (payload: { template_code: string; template_version: number; statement_type: string; line_code: string; line_name: string; display_order: number }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/statement-lines", payload),
  mapAccountToStatement: (payload: { book_id: number; account_id: number; statement_line_id: number; amount_sign: number }) =>
    request.post<{ data: Record<string, unknown> }>("/finance/statement-mappings", payload),
  generateStatement: (payload: { book_id: number; period: string; statement_type: string }) =>
    request.post<{ data: StatementResult }>("/finance/statements/generate", payload),
  getStatement: (params: { book_id: number; period: string; statement_type: string }) =>
    request.get<{ data: StatementResult }>("/finance/statements", { params }),

  // ---- Kingdee Import (金蝶导入) ----
  importKingdeeHistory: (accountSetCode: string) => request.post<{ data: Record<string, unknown> }>("/finance/kingdee/import", { account_set_code: accountSetCode }),
};