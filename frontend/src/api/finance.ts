import request from "./request";

export const financeApi = {
  getProfitDaily: (params?: any) => request.get("/finance/profit-daily", { params }),
  getCashSafety: () => request.get("/finance/cash-safety"),
  createExpense: (data: any) => request.post("/finance/manual-expense", data),
  createCash: (data: any) => request.post("/finance/manual-cash", data),
};
