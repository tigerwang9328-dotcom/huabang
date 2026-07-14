import request from "./request";

export interface ProfitAnalysis {
  period: { start_date: string; end_date: string };
  status: "ready" | "pending_data" | "estimated";
  status_label: string;
  summary: {
    net_sales: number; cost_of_goods: number | null; cost_coverage_rate?: number;
    gross_profit: number | null; gross_margin: number | null; total_expense: number;
    expense_coverage_rate: number; operating_profit: number | null;
    inventory_amount: number; discount_loss: number; return_loss: number | null;
    clearance_loss: number | null;
  };
  expense_coverage: Array<{ expense_type: string; label: string; amount: number; status: string; approved: boolean }>;
  missing_expense_types: string[];
  stores: Record<string, any>[];
  products: Record<string, any>[];
  data_quality: { warnings: string[]; source_updated_at?: string };
}

export const financeApi = {
  getOverview: () => request.get("/finance/overview"),
  getExpenses: (params?: { page?: number; page_size?: number }) => request.get("/finance/expenses", { params }),
  getReimbursements: (params?: { page?: number; page_size?: number }) => request.get("/finance/reimbursements", { params }),
  getPayments: (params?: { page?: number; page_size?: number }) => request.get("/finance/payments", { params }),
  createExpense: (payload: Record<string, unknown>) => request.post("/finance/manual-expense", payload),
  createCash: (payload: Record<string, unknown>) => request.post("/finance/manual-cash", payload),
  getCashSafety: () => request.get("/finance/cash-safety"),
  getProfitComparison: (params?: { start_date?: string; end_date?: string; store_code?: string }) =>
    request.get("/finance/profit-daily", { params }),
  getProfitAnalysis: (params?: { start_date?: string; end_date?: string; store_code?: string }) =>
    request.get<{ data: ProfitAnalysis }>("/finance/profit-analysis", { params }),
};
