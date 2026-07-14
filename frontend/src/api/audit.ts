import request from "./request";

export const auditApi = {
  listExceptions: (params?: Record<string, unknown>) => request.get("/audit/exceptions", { params }),
  getException: (id: number) => request.get(`/audit/exceptions/${id}`),
  getRuleStatuses: () => request.get("/audit/rules/status"),
  getAttributionStatus: (businessDate?: string) => request.get("/audit/attribution/status", {
    params: businessDate ? { business_date: businessDate } : undefined,
  }),
  evaluateAttribution: (body: Record<string, unknown>) => request.post("/audit/attribution/evaluate", body),
  adjudicateAttribution: (id: number, body: Record<string, unknown>) => request.post(`/audit/exceptions/${id}/adjudicate`, body),
  rebuild: (businessDate?: string) => request.post("/audit/rebuild", null, {
    params: businessDate ? { business_date: businessDate } : undefined,
  }),
};

export default auditApi;
