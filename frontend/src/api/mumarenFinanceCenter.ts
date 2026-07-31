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
