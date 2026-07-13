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
  confirmTasks: (data: { module: string; diagnosis_ids: string[]; stat_date?: string; store_code?: string }) =>
    request.post("/ai-diagnosis/action-tasks/confirm", data),
};
