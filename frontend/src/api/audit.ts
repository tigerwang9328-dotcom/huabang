import request from "./request";

export const auditApi = {
  listExceptions: (params?: Record<string, unknown>) => request.get("/audit/exceptions", { params }),
  getException: (id: number) => request.get(`/audit/exceptions/${id}`),
  getRuleStatuses: () => request.get("/audit/rules/status"),
  rebuild: (businessDate?: string) => request.post("/audit/rebuild", null, {
    params: businessDate ? { business_date: businessDate } : undefined,
  }),
};

export default auditApi;
