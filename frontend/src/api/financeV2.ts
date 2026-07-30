import request from "./request";

export interface FinanceV2Book {
  id: number;
  book_code: string;
  book_name: string;
  status: string;
  formal_report_blocked: boolean;
}

export interface FinanceV2Period {
  id: number;
  period_code: string;
  start_date: string;
  end_date: string;
  status: "open" | "closing" | "closed" | "reopening";
  version: number;
}

export interface FinanceV2Account {
  id: number;
  account_code: string;
  account_name: string;
  normal_balance: "debit" | "credit";
  effective_from: string;
  effective_to: string | null;
}

export interface FinanceV2Voucher {
  id: number;
  period_id: number;
  voucher_no: string | null;
  voucher_group: string;
  voucher_date: string;
  status: string;
  version: number;
  total_debit: number;
  total_credit: number;
  prepared_by: string;
  reviewer_id: string | null;
  approved_by: string | null;
  posted_by: string | null;
}

export interface FinanceV2VoucherLine {
  id: number;
  line_no: number;
  account_version_id: number | null;
  dimension_set_id: number | null;
  summary: string;
  currency_code: string;
  exchange_rate: number;
  debit_amount: number;
  credit_amount: number;
}

export interface FinanceV2VoucherDetail extends FinanceV2Voucher {
  book_id: number;
  source_system: string;
  lines: FinanceV2VoucherLine[];
  operation_events: Array<{
    id: number;
    action: string;
    actor_id: string;
    reason: string | null;
    command_id: string | null;
    before_data: Record<string, unknown> | null;
    after_data: Record<string, unknown> | null;
    created_at: string;
  }>;
}

export interface FinanceV2HistoryVoucher {
  id: number;
  voucher_no: string;
  voucher_group: string | null;
  voucher_date: string;
  fiscal_year: number;
  fiscal_period: number;
  total_debit: number;
  total_credit: number;
  source_system: string;
  source_database: string;
  historical_marker: boolean;
}

export interface FinanceV2HistoryVoucherLine {
  id: number;
  voucher_id: number;
  line_no: number;
  line_source_pk: string;
  account_code: string;
  summary: string;
  currency_code: string;
  exchange_rate: number;
  debit_amount: number;
  credit_amount: number;
  raw_dimensions: unknown;
  source_system: string;
  source_database: string;
  voucher_no: string;
  voucher_date: string;
  fiscal_year: number;
  fiscal_period: number;
  historical_marker: boolean;
}

export interface FinanceV2SourceInboxItem {
  id: number;
  status: "received" | "preview_ready" | "pending_mapping" | "exception" | "ignored";
  received_at: string;
  last_previewed_at: string | null;
  source_system: string;
  source_pk: string;
  business_type: string;
  legal_entity_code: string | null;
  organization_code: string | null;
  book_id: number | null;
  source_version_no: number;
  source_hash: string;
  source_occurred_at: string | null;
}

export interface FinanceV2SourcePreview {
  id: number;
  source_inbox_id: number;
  posting_rule_version_id: number | null;
  status: "preview_ready" | "pending_mapping" | "exception";
  input_hash: string;
  result_payload: Record<string, unknown>;
  exception_code: string | null;
  created_at: string;
  creates_draft: false;
}

export interface FinanceV2WriteReadiness {
  book_id: number;
  role: "finance_manager" | "super_admin";
  commands: Record<"draft" | "review" | "post" | "period_close", { enabled: boolean; reason: string | null }>;
}

export interface FinanceV2OpeningBalanceBatch {
  id: number;
  book_id: number;
  batch_kind: "provisional" | "final";
  status: "draft" | "validated" | "locked" | "discarded";
  history_coverage_end_date: string;
  go_live_date: string;
  coverage_continuous: boolean;
  coverage_gap_id: number | null;
  approved_by: string | null;
  approved_at: string | null;
  locked_at: string | null;
  version: number;
}

export interface FinanceV2OpeningBalanceLineInput {
  account_version_id: number;
  dimension_set_id: number;
  currency_code?: string;
  debit_amount: number;
  credit_amount: number;
  source_system: string;
  source_reference?: string;
}

export interface FinanceV2OpeningBalanceCreateInput {
  batch_kind: "provisional" | "final";
  history_coverage_end_date: string;
  go_live_date: string;
  coverage_continuous: boolean;
  command_id: string;
  lines: FinanceV2OpeningBalanceLineInput[];
}

export interface FinanceV2PeriodCloseReadiness {
  book_id: number;
  period_id: number;
  period_code: string;
  status: FinanceV2Period["status"];
  version: number;
  ready_to_start_close: boolean;
  checks: {
    unposted_voucher_count: number;
    unbalanced_voucher_count: number;
    source_exception_count: number;
    ledger_difference_count: number;
    posted_debit: string;
    posted_credit: string;
    ledger_debit: string;
    ledger_credit: string;
    profit_closing_evidence_required: boolean;
    profit_closing_evidence_count: number;
    profit_closing_evidence_missing_count: number;
    source_exception_scope: string;
  };
}

export interface FinanceV2PeriodCommandInput {
  action: "register_profit_closing" | "start_close" | "complete_close" | "request_reopen" | "approve_reopen";
  command_id: string;
  expected_version: number;
  reason?: string;
  voucher_id?: number;
}

export interface FinanceV2TrialBalance {
  book_id: number;
  period_id: number;
  period_code: string;
  formal_report_status: "blocked" | "pending_mapping";
  formal_report_message: string;
  rows: Array<{ account_version_id: number; account_code: string; account_name: string; dimension_set_id: number; currency_code: string; opening_debit: number; opening_credit: number; period_debit: number; period_credit: number; closing_debit: number; closing_credit: number }>;
}

export interface FinanceV2ReportReadiness {
  report_code: "balance_sheet" | "profit_statement";
  status: "ready" | "blocked" | "pending_mapping" | "pending_data" | "pending_gap";
  reason_code: string | null;
  formal_export_allowed: boolean;
  template_version: string | null;
  rows: Record<string, number>;
  unmapped_account_version_ids: number[];
}

export interface FinanceV2MonitoringMetric {
  metric_key: string;
  availability: "available" | "unavailable";
  threshold: string;
  owner: string;
  notification_route: string;
  notification_configured: boolean;
  close_condition: string;
  labels: string[];
  unavailable_reason: string | null;
  value: number | null;
}

export interface FinanceV2MonitoringSummary {
  metrics: Record<string, number>;
  metric_policies: FinanceV2MonitoringMetric[];
  gates: Array<{ scope_type: string; scope_key: string; gate_name: string; enabled: boolean; effective_at: string }>;
  unavailable_metrics: string[];
  message: string;
}

export interface FinanceV2VoucherLineInput {
  account_version_id: number;
  dimension_set_id?: number;
  summary: string;
  debit_amount: number;
  credit_amount: number;
  currency_code?: string;
  exchange_rate?: number;
}

export interface FinanceV2DraftInput {
  book_id: number;
  period_id: number;
  voucher_date: string;
  request_id: string;
  entries: FinanceV2VoucherLineInput[];
}

export const financeV2Api = {
  listBooks: () => request.get<FinanceV2Book[]>("/finance-center/v2/books"),
  listPeriods: (bookId: number) => request.get<FinanceV2Period[]>(`/finance-center/v2/books/${bookId}/periods`),
  getWriteReadiness: (bookId: number) => request.get<FinanceV2WriteReadiness>(`/finance-center/v2/books/${bookId}/write-readiness`),
  listOpeningBalances: (bookId: number) => request.get<FinanceV2OpeningBalanceBatch[]>(`/finance-center/v2/books/${bookId}/opening-balances`),
  createOpeningBalance: (bookId: number, payload: FinanceV2OpeningBalanceCreateInput) =>
    request.post(`/finance-center/v2/books/${bookId}/opening-balances`, payload),
  validateOpeningBalance: (bookId: number, batchId: number, payload: { command_id: string; expected_version: number; reason?: string }) =>
    request.post(`/finance-center/v2/books/${bookId}/opening-balances/${batchId}/validate`, payload),
  lockOpeningBalance: (bookId: number, batchId: number, payload: { command_id: string; expected_version: number; reason?: string }) =>
    request.post(`/finance-center/v2/books/${bookId}/opening-balances/${batchId}/lock`, payload),
  getPeriodCloseReadiness: (bookId: number, periodId: number) => request.get<FinanceV2PeriodCloseReadiness>(
    `/finance-center/v2/books/${bookId}/periods/${periodId}/close-readiness`,
  ),
  getTrialBalance: (bookId: number, periodId: number) => request.get<FinanceV2TrialBalance>(
    `/finance-center/v2/books/${bookId}/periods/${periodId}/trial-balance`,
  ),
  getReportReadiness: (bookId: number, periodId: number, reportCode: FinanceV2ReportReadiness["report_code"]) => request.get<FinanceV2ReportReadiness>(
    `/finance-center/v2/books/${bookId}/periods/${periodId}/reports/${reportCode}/readiness`,
  ),
  getMonitoringSummary: () => request.get<FinanceV2MonitoringSummary>("/finance-center/v2/monitoring/summary"),
  listAccounts: (bookId: number, activeOn?: string) => request.get<FinanceV2Account[]>(
    `/finance-center/v2/books/${bookId}/accounts`,
    { params: activeOn ? { active_on: activeOn } : undefined },
  ),
  listVouchers: (bookId: number, params?: { period_id?: number; status?: string; limit?: number }) => request.get<FinanceV2Voucher[]>(
    "/finance-center/v2/vouchers",
    { params: { book_id: bookId, ...params } },
  ),
  getVoucherDetail: (voucherId: number) => request.get<FinanceV2VoucherDetail>(`/finance-center/v2/vouchers/${voucherId}`),
  listHistoryVouchers: (params?: { limit?: number }) => request.get<FinanceV2HistoryVoucher[]>(
    "/finance-center/v2/history/vouchers",
    { params },
  ),
  listHistoryVoucherLines: (voucherId: number, params?: { limit?: number }) => request.get<FinanceV2HistoryVoucherLine[]>(
    `/finance-center/v2/history/vouchers/${voucherId}/lines`,
    { params },
  ),
  listSourceInbox: (params?: { status?: FinanceV2SourceInboxItem["status"]; limit?: number }) => request.get<FinanceV2SourceInboxItem[]>(
    "/finance-center/v2/source-inbox",
    { params },
  ),
  listSourcePreviews: (sourceInboxId: number, params?: { limit?: number }) => request.get<FinanceV2SourcePreview[]>(
    `/finance-center/v2/source-inbox/${sourceInboxId}/previews`,
    { params },
  ),
  createDraft: (payload: FinanceV2DraftInput) => request.post("/finance-center/v2/vouchers", payload),
  updateDraft: (voucherId: number, payload: { voucher_date: string; entries: FinanceV2VoucherLineInput[]; command_id: string; expected_version: number }) =>
    request.put(`/finance-center/v2/vouchers/${voucherId}`, payload),
  executePeriodCommand: (bookId: number, periodId: number, payload: FinanceV2PeriodCommandInput) =>
    request.post(`/finance-center/v2/books/${bookId}/periods/${periodId}/commands`, payload),
  executeCommand: (voucherId: number, payload: { action: string; command_id: string; expected_version: number; reason?: string }) =>
    request.post(`/finance-center/v2/vouchers/${voucherId}/commands`, payload),
};
