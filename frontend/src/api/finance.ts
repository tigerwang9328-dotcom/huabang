import request from "./request";

export type FinanceDataType = "estimate" | "actual";
export type ProfitStatus = "ready" | "pending_data" | "estimated";
export type ExpenseType = "rent" | "wages" | "social_security" | "platform_fee" | "utilities" | "logistics" | "marketing" | "other";

export interface FinanceExpenseRecord {
  id: number;
  applicant_name: string | null;
  department_name: string | null;
  expense_type: string | null;
  amount: number;
  category: "payment" | "reimbursement";
  approval_status: string | null;
  payment_status: string | null;
  expense_date: string | null;
  created_at: string | null;
}

export interface FinanceOverview {
  today: { reimbursement_amount: number; payment_amount: number };
  month: { reimbursement_amount: number; payment_amount: number };
  pending_count: number;
  approved_unpaid_count: number;
  recent_records: FinanceExpenseRecord[];
  department_rank: Array<{ department: string; amount: number }>;
}

export interface ExpenseList {
  items: FinanceExpenseRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProfitSummary {
  net_sales: number;
  cost_of_goods: number | null;
  standard_purchase_price_coverage_rate?: number;
  gross_profit: number | null;
  gross_margin: number | null;
  total_expense: number;
  expense_coverage_rate: number;
  operating_profit: number | null;
  inventory_amount: number;
  discount_loss: number;
  return_loss: number | null;
  clearance_loss: number | null;
}

export interface ProfitStore {
  store_code: string;
  store_name: string;
  net_sales: number;
  gross_profit: number | null;
  operating_profit: number | null;
}

export interface ProfitProduct {
  product_code: string;
  product_name: string;
  net_sales: number;
  gross_profit: number | null;
}

export interface ProfitAnalysis {
  period: { start_date: string; end_date: string };
  status: ProfitStatus;
  status_label: string;
  summary: ProfitSummary;
  expense_coverage: Array<{ expense_type: ExpenseType; label: string; amount: number; status: ProfitStatus; approved: boolean }>;
  missing_expense_types: ExpenseType[];
  stores: ProfitStore[];
  products: ProfitProduct[];
  data_quality: { warnings: string[]; source_updated_at?: string };
}

export interface ProfitDailyItem {
  stat_date: string;
  net_sales: number | null;
  gross_profit: number | null;
  operating_profit: number | null;
  status: "ready" | "pending_data";
  data_type: FinanceDataType;
  data_type_label?: string;
  completeness_note: string | null;
}

export interface CashSafety {
  total_cash_balance: number;
  daily_avg_expense_30d: number | null;
  cash_safety_days: number | null;
  risk_level: "critical" | "warning" | "normal" | "unknown";
  note: string;
}

export interface ManualExpensePayload {
  expense_date: string;
  store_code: string;
  expense_type: ExpenseType;
  expense_amount: number;
  data_type: FinanceDataType;
  description: string;
}

export interface ManualCashPayload {
  record_date: string;
  account_type: "bank" | "cash";
  account_name: string;
  balance: number;
  data_type: FinanceDataType;
}

export const financeApi = {
  getOverview: () => request.get<{ data: FinanceOverview }>("/finance/overview"),
  getExpenses: (params?: { page?: number; page_size?: number }) => request.get<{ data: ExpenseList }>("/finance/expenses", { params }),
  getReimbursements: (params?: { page?: number; page_size?: number }) => request.get<{ data: ExpenseList }>("/finance/reimbursements", { params }),
  getPayments: (params?: { page?: number; page_size?: number }) => request.get<{ data: ExpenseList }>("/finance/payments", { params }),
  createExpense: (payload: ManualExpensePayload) => request.post("/finance/manual-expense", payload),
  createCash: (payload: ManualCashPayload) => request.post("/finance/manual-cash", payload),
  getCashSafety: () => request.get<{ data: CashSafety }>("/finance/cash-safety"),
  getProfitComparison: (params?: { start_date?: string; end_date?: string; store_code?: string }) =>
    request.get<{ data: { items: ProfitDailyItem[] } }>("/finance/profit-daily", { params }),
  getProfitAnalysis: (params?: { start_date?: string; end_date?: string; store_code?: string }) =>
    request.get<{ data: ProfitAnalysis }>("/finance/profit-analysis", { params }),
};
