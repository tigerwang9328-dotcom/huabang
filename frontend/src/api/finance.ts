import request from "./request";

export const financeApi = {
  getOverview: () => request.get("/finance/overview"),
  getExpenses: (params?: { page?: number; page_size?: number }) => request.get("/finance/expenses", { params }),
  getReimbursements: (params?: { page?: number; page_size?: number }) => request.get("/finance/reimbursements", { params }),
  getPayments: (params?: { page?: number; page_size?: number }) => request.get("/finance/payments", { params }),
};
