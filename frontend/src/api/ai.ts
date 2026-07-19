import request from "./request";

export const aiApi = {
  ask: (question: string, contextData?: any) =>
    request.post("/ai/ask", { question, context_data: contextData }),
};

export const aiAssistantApi = {
  getBrief: (params?: { route?: string; stat_date?: string; store_code?: string }) =>
    request.get("/ai-assistant/brief", { params, silentError: true }),
  listConversations: () =>
    request.get("/ai-assistant/conversations", { silentError: true }),
  createConversation: (contextData?: { route?: string; stat_date?: string; store_code?: string }) =>
    request.post("/ai-assistant/conversations", contextData || {}, { silentError: true }),
  getMessages: (conversationId: number) =>
    request.get(`/ai-assistant/conversations/${conversationId}/messages`, { silentError: true }),
  sendMessage: (
    conversationId: number,
    question: string,
    contextData?: { route?: string; stat_date?: string; store_code?: string },
    signal?: AbortSignal,
  ) =>
    request.post(`/ai-assistant/conversations/${conversationId}/messages`, {
      question,
      web_mode: "auto",
      ...(contextData || {}),
    }, { signal }),
  archiveConversation: (conversationId: number) =>
    request.delete(`/ai-assistant/conversations/${conversationId}`),
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
