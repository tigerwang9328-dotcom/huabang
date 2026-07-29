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

export interface FinanceV2WriteReadiness {
  book_id: number;
  role: "finance_manager" | "super_admin";
  commands: Record<"draft" | "review" | "post" | "period_close", { enabled: boolean; reason: string | null }>;
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
    source_exception_scope: string;
  };
}

export interface FinanceV2VoucherLineInput {
  account_version_id: number;
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
  getPeriodCloseReadiness: (bookId: number, periodId: number) => request.get<FinanceV2PeriodCloseReadiness>(
    `/finance-center/v2/books/${bookId}/periods/${periodId}/close-readiness`,
  ),
  listAccounts: (bookId: number, activeOn?: string) => request.get<FinanceV2Account[]>(
    `/finance-center/v2/books/${bookId}/accounts`,
    { params: activeOn ? { active_on: activeOn } : undefined },
  ),
  listVouchers: (bookId: number, params?: { period_id?: number; status?: string; limit?: number }) => request.get<FinanceV2Voucher[]>(
    "/finance-center/v2/vouchers",
    { params: { book_id: bookId, ...params } },
  ),
  listHistoryVouchers: (params?: { limit?: number }) => request.get<FinanceV2HistoryVoucher[]>(
    "/finance-center/v2/history/vouchers",
    { params },
  ),
  listHistoryVoucherLines: (voucherId: number, params?: { limit?: number }) => request.get<FinanceV2HistoryVoucherLine[]>(
    `/finance-center/v2/history/vouchers/${voucherId}/lines`,
    { params },
  ),
  createDraft: (payload: FinanceV2DraftInput) => request.post("/finance-center/v2/vouchers", payload),
  executePeriodCommand: (bookId: number, periodId: number, payload: { action: string; command_id: string; expected_version: number; reason?: string }) =>
    request.post(`/finance-center/v2/books/${bookId}/periods/${periodId}/commands`, payload),
  executeCommand: (voucherId: number, payload: { action: string; command_id: string; expected_version: number; reason?: string }) =>
    request.post(`/finance-center/v2/vouchers/${voucherId}/commands`, payload),
};
