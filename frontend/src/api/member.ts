import request from "./request";

export const memberApi = {
  getOverview: () => request.get("/member/overview"),
  listPosMembers: (params?: any) => request.get("/member/pos-members", { params }),
  listMembers: (params?: any) => request.get("/member/list", { params }),
  listVisits: (params?: any) => request.get("/member/visits", { params }),
};
