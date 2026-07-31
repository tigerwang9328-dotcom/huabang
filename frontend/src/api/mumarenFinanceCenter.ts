import request from "@/api/request";

// request 的 baseURL 已固定为 /api/v1；此常量记录本模块唯一的完整公网接口根路径。
export const MUMAREN_FINANCE_CENTER_API_ROOT = "/api/v1/finance-center/mumaren";
const requestPath = (path: string) => MUMAREN_FINANCE_CENTER_API_ROOT.replace("/api/v1", "") + path;

export interface FinanceCenterCatalog {
  module: string;
  capabilities: string[];
}

export const mumarenFinanceCenterApi = {
  getCatalog: () => request.get<FinanceCenterCatalog>(requestPath("/catalog")),
  listVouchers: () => request.get(requestPath("/vouchers")),
  listBooks: () => request.get(requestPath("/books")),
  listHistory: () => request.get(requestPath("/history/vouchers")),
};
