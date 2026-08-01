import request from './request'

export const lifeDataAnalysisApi = {
  getOverview: () => request.get('/life-data-analysis/overview'),
  getDecisionOverview: () => request.get('/investment-decisions/overview'),
  getDecisionHistory: (params: { limit?: number; offset?: number } = {}) => request.get('/investment-decisions/history', { params }),
  getDecisionDetail: (runId: number) => request.get(`/investment-decisions/${runId}`),
  recordDecision: (recommendationId: number, data: { decision: 'accepted' | 'rejected' | 'partially_accepted' | 'expired'; note?: string }) => request.post(`/investment-decisions/${recommendationId}/decision`, data),
  recordExecution: (recommendationId: number, data: { actual_budget_fen: number; external_campaign_id?: string; external_plan_id?: string; external_creative_id?: string; note?: string }) => request.post(`/investment-decisions/${recommendationId}/execution`, data),
  getDailyPatterns: (limit = 30) => request.get('/investment-decisions/patterns/daily', { params: { limit } }),
}
