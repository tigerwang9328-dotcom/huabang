import request from "./request";

export const memberApi = {
  getOverview: () => request.get("/member/overview"),
  listPosMembers: (params?: any) => request.get("/member/pos-members", { params }),
  listMembers: (params?: any) => request.get("/member/list", { params }),
  listVisits: (params?: any) => request.get("/member/visits", { params }),
  getAssetOverview: () => request.get("/member/assets/overview"),
  getSalesAnalysis: (params?: any) => request.get("/member/sales/analysis", { params }),
  listAssets: (params?: any) => request.get("/member/assets/list", { params }),
  listAssetTransactions: (params?: any) => request.get("/member/assets/transactions", { params }),
};
