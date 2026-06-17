import request from "./request";

export const dashboardApi = {
  getOverview: (params?: { stat_date?: string }) => request.get("/dashboard/overview", { params }),
  getSalesTrend: (params?: { days?: number }) => request.get("/dashboard/sales-trend", { params }),
  getStoreRank: (params?: { stat_date?: string; top_n?: number }) => request.get("/dashboard/store-rank", { params }),
  getTaskSummary: () => request.get("/dashboard/task-summary"),
};
