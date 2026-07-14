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
  getSegmentOverview: (params?: any) => request.get("/member/segments/overview", { params }),
  listSegments: (params?: any) => request.get("/member/segments/list", { params }),
  listSegmentRisks: (params?: any) => request.get("/member/segments/risks", { params }),
  listWakeups: (params?: any) => request.get("/member/segments/wakeups", { params }),
  rebuildSegments: (params?: any) => request.post("/member/segments/rebuild", null, { params }),
  exportSegments: (params?: any) => request.get("/member/segments/export", { params, responseType: "blob" }),
  getActionOverview: (params?: any) => request.get("/member/actions/overview", { params }),
  listActions: (params?: any) => request.get("/member/actions/list", { params }),
  rebuildActions: (params?: any) => request.post("/member/actions/rebuild", null, { params }),
};
