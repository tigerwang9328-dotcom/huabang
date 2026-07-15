import request from "./request";

export const aiApi = {
  ask: (question: string, contextData?: any) =>
    request.post("/ai/ask", { question, context_data: contextData }),
};

export const aiDiagnosisApi = {
  getModule: (module = "overview", params?: { stat_date?: string; store_code?: string }) =>
    request.get(`/ai-diagnosis/${module}`, { params }),
  generateTasks: (data: { module?: string; stat_date?: string; store_code?: string }) =>
    request.post("/ai-diagnosis/action-tasks/generate", data),
  getAdviceStatus: (params?: { stat_date?: string }) =>
    request.get("/ai-diagnosis/advice/status", { params }),
  refreshAdvice: (module: string, params?: { stat_date?: string; store_code?: string }) =>
    request.post(`/ai-diagnosis/${module}/refresh`, undefined, { params }),
  getAssigneeOptions: (params?: { store_code?: string }) =>
    request.get("/ai-diagnosis/assignee-options", { params }),
  confirmTasks: (data: {
    module: string;
    suggestion_key?: string;
    diagnosis_ids?: string[];
    assignee_id: number;
    due_date: string;
    stat_date?: string;
    store_code?: string;
  }) =>
    request.post("/ai-diagnosis/action-tasks/confirm", data),
};
