/**
 * 财务中心 - API 请求封装
 * 所有财务接口统一从此文件导出
 */
import request from "./request"

// ── 财务总览 ──
export const getFinanceOverview = (month?: string) =>
  request.get("/finance/compass/overview", { params: { month } })

// ── 趋势 ──
export const getFinanceTrend = (month?: string, months = 6) =>
  request.get("/finance/compass/trend", { params: { month, months } })

// ── 店铺利润排行 ──
export const getStoreRanking = (month?: string, platformId?: number, limit = 20) =>
  request.get("/finance/compass/store-ranking", { params: { month, platform_id: platformId, limit } })

// ── 现金流日报 ──
export const getCashflowDaily = (begin?: string, end?: string) =>
  request.get("/finance/cashflow-daily", { params: { begin, end } })

// ── 财务明细 ──
export const getFinanceDetails = (params: { month?: string; store_id?: number; page?: number; page_size?: number }) =>
  request.get("/finance/details", { params })

// ── 风险预警 ──
export const getRiskAlerts = (unreadOnly = false, limit = 50) =>
  request.get("/finance/compass/risk-alerts", { params: { unread_only: unreadOnly, limit } })

export const markAlertRead = (alertId: number) =>
  request.put(`/finance/compass/risk-alerts/${alertId}/read`)

// ── 费用 ──
export const getFees = (month?: string, feeType?: string) =>
  request.get("/finance/compass/fees", { params: { month, fee_type: feeType } })

export const createFee = (data: any) =>
  request.post("/finance/compass/fees", data)

// ── 回款 ──
export const getReceipts = (limit = 20) =>
  request.get("/finance/compass/receipts", { params: { limit } })

export const createReceipt = (data: any) =>
  request.post("/finance/compass/receipts", data)

// ── 月度汇总（兼容旧组件） ──
export const getFinanceSummary = (month?: string) =>
  request.get("/finance/compass/summary", { params: { month } })

// ── 固定费用配置 ──
export const getCostConfig = (month?: string) =>
  request.get("/finance/compass/cost-config", { params: { month } })

export const upsertCostConfig = (data: any) =>
  request.post("/finance/compass/cost-config", data)

// ── 导出（预留） ──
export const exportFinance = (month?: string) =>
  request.get("/finance/compass/export", { params: { month }, responseType: "blob" as any })
