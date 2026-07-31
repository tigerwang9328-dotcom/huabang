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
  tax_name: string;
  period: string;
  tax_amount: number;
  paid_amount: number;
  due_date: string | null;
  status: string;
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
};
