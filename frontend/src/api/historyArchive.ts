import request from "@/api/request"

export const ARCHIVE_PERMISSIONS = {
  view: "finance:history-archive:view",
  upload: "finance:history-archive:upload",
  download: "finance:history-archive:download",
  update: "finance:history-archive:update",
  delete: "finance:history-archive:delete",
  category: "finance:history-archive:category",
} as const

export const DATA_TYPE_OPTIONS = [
  { label: "原始数据", value: "RAW_DATA" },
  { label: "财务报表", value: "FINANCIAL_REPORT" },
  { label: "分析报表", value: "ANALYSIS_REPORT" },
] as const

export type ArchiveStatus = "NORMAL" | "DELETED"
export type ArchiveDataType = "RAW_DATA" | "FINANCIAL_REPORT" | "ANALYSIS_REPORT"

export interface CategoryPathItem { id: number; name: string; level: number }
export interface ArchiveCategory extends CategoryPathItem {
  parent_id: number | null
  sort_order: number
  is_fixed: boolean
  status: "ACTIVE" | "INACTIVE"
  children: ArchiveCategory[]
}

export interface ArchiveFile {
  id: number
  data_name: string
  original_filename: string
  file_size: number
  file_extension: string
  mime_type: string
  md5: string | null
  sha256: string
  storage_provider: "LOCAL" | "MINIO"
  category_id: number
  category_root_id: number
  category_path: CategoryPathItem[]
  category_path_text: string
  project_name: string
  company_name: string
  store_id: number | null
  store_name: string
  data_year: number
  data_month: number
  data_start_date: string | null
  data_end_date: string | null
  data_type: ArchiveDataType
  description: string
  status: ArchiveStatus
  uploaded_by: number | null
  uploader_name: string
  created_at: string | null
  updated_at: string | null
  deleted_at: string | null
  deleted_by: number | null
  delete_reason: string
}

export interface ArchiveLog {
  id: number
  operation_type: "UPLOAD" | "DOWNLOAD" | "UPDATE" | "DELETE" | "RESTORE"
  operation_user_id: number | null
  operation_user_name: string
  operation_time: string | null
  ip_address: string
  user_agent: string
  change_detail: Record<string, unknown>
}

export interface ArchiveSummary {
  total_files: number
  total_size: number
  covered_year_count: number
  covered_years: number[]
  category_count: number
  category_distribution: Array<{ category_id: number; name: string; file_count: number }>
  recent_uploads: ArchiveFile[]
  recent_downloads: Array<{
    file_id: number
    data_name: string
    original_filename: string
    user_name: string
    operation_time: string
  }>
}

export interface ArchiveOptions {
  projects: string[]
  companies: string[]
  stores: Array<{ id: number; name: string }>
  uploaders: Array<{ id: number; name: string }>
}

export interface ArchiveFilters {
  keyword?: string
  category_id?: number
  project_name?: string
  company_name?: string
  store_id?: number
  year?: number
  month?: number
  uploader?: string
  data_type?: ArchiveDataType | ""
  status?: ArchiveStatus
  page?: number
  page_size?: number
}

export interface ArchiveList { rows: ArchiveFile[]; total: number; page: number; page_size: number }

const BASE = "/finance/history-archive"

export const getArchiveSummary = () => request.get<any, ArchiveSummary>(`${BASE}/summary`)
export const getArchiveFiles = (params: ArchiveFilters) => request.get<any, ArchiveList>(`${BASE}/files`, { params })
export const getArchiveFile = (id: number) => request.get<any, ArchiveFile>(`${BASE}/files/${id}`)
export const getArchiveLogs = (id: number) => request.get<any, { rows: ArchiveLog[] }>(`${BASE}/files/${id}/logs`)
export const getArchiveOptions = () => request.get<any, ArchiveOptions>(`${BASE}/options`)
export const getCategoryTree = () => request.get<any, { rows: ArchiveCategory[] }>(`${BASE}/categories/tree`)
export const getManageCategoryTree = () => request.get<any, { rows: ArchiveCategory[] }>(`${BASE}/categories/manage-tree`)

export function uploadArchiveFile(form: FormData, onProgress?: (percent: number) => void) {
  return request.post<any, ArchiveFile>(`${BASE}/files`, form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 180000,
    onUploadProgress: event => {
      if (event.total && onProgress) onProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
}

export const updateArchiveFile = (id: number, body: Partial<ArchiveFile>) =>
  request.patch<any, ArchiveFile>(`${BASE}/files/${id}`, body)

export const deleteArchiveFile = (id: number, reason: string) =>
  request.delete<any, ArchiveFile>(`${BASE}/files/${id}`, { data: { reason } })

export const restoreArchiveFile = (id: number) =>
  request.post<any, ArchiveFile>(`${BASE}/files/${id}/restore`)

export const downloadArchiveFile = (id: number) =>
  request.get<any, Blob>(`${BASE}/files/${id}/download`, { responseType: "blob", timeout: 180000 })

export const createArchiveCategory = (body: { name: string; parent_id: number; sort_order?: number }) =>
  request.post<any, ArchiveCategory>(`${BASE}/categories`, body)

export const updateArchiveCategory = (id: number, body: { name?: string; sort_order?: number }) =>
  request.patch<any, ArchiveCategory>(`${BASE}/categories/${id}`, body)

export const deactivateArchiveCategory = (id: number) =>
  request.delete<any, ArchiveCategory>(`${BASE}/categories/${id}`)
