import request from "./request";

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
};
