import request from './request'

export const lifeDataAnalysisApi = {
  getOverview: () => request.get('/life-data-analysis/overview'),
}
