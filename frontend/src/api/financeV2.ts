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

export const financeV2Api = {
  listBooks: () => request.get<FinanceV2Book[]>("/finance-center/v2/books"),
  listPeriods: (bookId: number) => request.get<FinanceV2Period[]>(`/finance-center/v2/books/${bookId}/periods`),
  listAccounts: (bookId: number, activeOn?: string) => request.get<FinanceV2Account[]>(
    `/finance-center/v2/books/${bookId}/accounts`,
    { params: activeOn ? { active_on: activeOn } : undefined },
  ),
  listVouchers: (bookId: number, params?: { period_id?: number; status?: string; limit?: number }) => request.get<FinanceV2Voucher[]>(
    "/finance-center/v2/vouchers",
    { params: { book_id: bookId, ...params } },
  ),
};
