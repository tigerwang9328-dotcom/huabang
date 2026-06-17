import request from "./request";

export const aiApi = {
  ask: (question: string, contextData?: any) =>
    request.post("/ai/ask", { question, context_data: contextData }),
};
