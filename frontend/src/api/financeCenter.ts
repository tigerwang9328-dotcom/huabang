import request from "./request";

export interface VoucherEntryPayload {
  account_id: number;
  summary: string;
  debit_amount: number;
  credit_amount: number;
  currency_code?: string;
  exchange_rate?: number;
  aux_items?: Record<string, unknown>;
}

export interface VoucherCreatePayload {
  book_id: number;
  period: string;
  voucher_no: string;
  voucher_date: string;
  reason: string;
  entries: VoucherEntryPayload[];
}

export interface StatementGeneratePayload {
  book_id: number;
  period: string;
  statement_type: "balance_sheet" | "income_statement" | "cashflow";
}

export interface StatementGenerateResult {
  status: "ready" | "pending_mapping" | "pending_data";
  items: Array<{ line_code: string; line_name: string; current_amount: number | null; status: string }>;
  issues: Array<Record<string, unknown>>;
}

export const financeCenterApi = {
  importKingdeeHistory: (account_set_code: string) =>
    request.post<{ data: Record<string, unknown> }>("/finance-center/kingdee/import", { account_set_code }),
  openPeriod: (payload: { book_id: number; period: string }) =>
    request.post<{ data: Record<string, unknown> }>("/finance-center/periods/open", payload),
  createVoucher: (payload: VoucherCreatePayload) =>
    request.post<{ data: Record<string, unknown> }>("/finance-center/vouchers", payload),
  postVoucher: (voucherId: number, reason: string) =>
    request.post<{ data: Record<string, unknown> }>(`/finance-center/vouchers/${voucherId}/post`, { reason }),
  reverseVoucher: (voucherId: number, payload: { voucher_no: string; reason: string }) =>
    request.post<{ data: Record<string, unknown> }>(`/finance-center/vouchers/${voucherId}/reverse`, payload),
  generateStatement: (payload: StatementGeneratePayload) =>
    request.post<{ data: StatementGenerateResult }>("/finance-center/statements/generate", payload),
};
