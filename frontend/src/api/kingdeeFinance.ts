import request from "./request";

export type FinanceQualityStatus = "ready" | "pending_mapping" | "pending_data";

export interface AccountSet {
  id: number;
  entity_code: string;
  account_set_code: string;
  company_name: string;
  short_name: string | null;
  start_period: string | null;
  current_period: string | null;
  status: string;
}

export interface FinancePeriod {
  account_set_code: string;
  period: string;
  status: string;
}

export interface StatementLine {
  line_code: string;
  line_name: string;
  current_amount: number | null;
  year_to_date_amount: number | null;
  status: FinanceQualityStatus;
}

export interface StatementResult {
  status: FinanceQualityStatus;
  items: StatementLine[];
  issues: string[];
}

export interface AccountBalance {
  account_code: string;
  account_name: string;
  balance_direction: "debit" | "credit";
  period: string;
  opening_debit: number;
  opening_credit: number;
  period_debit: number;
  period_credit: number;
  closing_debit: number;
  closing_credit: number;
}

export interface VoucherListItem {
  id: number;
  voucher_no: string;
  voucher_date: string;
  period: string;
  source_status: string;
  is_posted: boolean;
  total_debit: number;
  total_credit: number;
  read_only: true;
}

export interface VoucherDetail extends VoucherListItem {
  entries: Array<{
    line_no: number;
    account_code: string;
    account_name: string;
    summary: string | null;
    debit_amount: number;
    credit_amount: number;
    currency_code: string;
  }>;
}

export interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface DataQuality {
  status: FinanceQualityStatus;
  account_set_code: string | null;
  account_count: number;
  mapped_account_count: number;
  issues: Array<{ code: string; severity: string; count: number }>;
}

export interface ImportBatch {
  batch_id: string;
  run_id: string;
  source_database: string;
  backup_sha256: string;
  status: string;
  actual_counts: Record<string, number>;
  validation_result: Record<string, unknown>;
  started_at: string | null;
  completed_at: string | null;
}

export const kingdeeFinanceApi = {
  getAccountSets: () => request.get<{ data: AccountSet[] }>("/finance/account-sets"),
  getPeriods: (account_set_code: string) => request.get<{ data: FinancePeriod[] }>("/finance/periods", { params: { account_set_code } }),
  getStatements: (params: { account_set_code: string; period: string; statement_type: string }) => request.get<{ data: StatementResult }>("/finance/statements", { params }),
  getAccountBalances: (params: { account_set_code: string; period: string; keyword?: string; page?: number; page_size?: number }) => request.get<{ data: PageResult<AccountBalance> }>("/finance/account-balances", { params }),
  getVouchers: (params: { account_set_code: string; period?: string; keyword?: string; page?: number; page_size?: number }) => request.get<{ data: PageResult<VoucherListItem> }>("/finance/vouchers", { params }),
  getVoucher: (voucherId: number) => request.get<{ data: VoucherDetail }>(`/finance/vouchers/${voucherId}`),
  getImportBatches: () => request.get<{ data: ImportBatch[] }>("/finance/kingdee/import-batches"),
  getDataQuality: (account_set_code?: string) => request.get<{ data: DataQuality }>("/finance/data-quality", { params: { account_set_code } }),
};
