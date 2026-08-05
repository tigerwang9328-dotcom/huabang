import request, { type ApiResponse } from "./request";

const basePath = "/douyin-color-analytics";

function unwrapDouyinColorAnalytics<T>(response: Promise<{ data: ApiResponse<T> | T }>) {
  return response.then((result) => {
    const payload = result.data;
    const data = payload && typeof payload === "object" && "code" in payload && "success" in payload && "data" in payload
      ? payload.data
      : payload;
    return { data };
  });
}

export type DouyinFocusStatus = "clear_primary" | "multi_focus" | "unclear";
export type DouyinAnnotationStatus = "draft" | "submitted" | "approved" | "rejected" | "deleted";

export type GarmentPosition = "outer" | "top" | "bottom" | "none";

export interface OutfitPart {
  position: GarmentPosition;
  style_id: number;
  sku_code: string | null;
}

export interface DouyinAnnotationContext {
  account: {
    id: number;
    account_key: string;
    display_name: string;
    observed_account_name?: string | null;
    last_heartbeat_at?: string | null;
  };
}

export interface DouyinVideo {
  id: number;
  account_id: number;
  video_id_string: string;
  title: string | null;
  published_at: string | null;
  duration_ms: number;
  cover_path: string | null;
  creator_detail_path: string | null;
  collection_status: string;
}

export interface DouyinVideoAnalysisSnapshot {
  id: number;
  analysis_type: number;
  collected_at: string;
  normalized_curve: Array<{ second: number; value: number }>;
  curve_quality_status: string;
  observation_window: string;
}

export interface DouyinGarmentStyle {
  id: number;
  style_code: string;
  style_name: string;
  main_image: string | null;
  status: string;
}

export interface DouyinGarmentColor {
  id: number;
  style_id: number;
  color_code: string;
  color_name: string;
  color_image: string | null;
  status: string;
}

export interface DouyinVideoClip {
  id: number;
  video_id: number;
  outfit_parts_json: OutfitPart[];
  start_ms: number;
  end_ms: number;
  input_start_ms: number;
  input_end_ms: number;
  curve_resolution_ms: number | null;
  focus_status: DouyinFocusStatus;
  focus_note: string | null;
  annotation_status: DouyinAnnotationStatus;
  overlap_status: string | null;
  overlap_reason: string | null;
  version: number;
  created_by: string | null;
  updated_by: string | null;
  submitted_by: string | null;
  submitted_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DouyinVideoClipInput {
  account_id: number;
  video_id: number;
  input_start_ms: number;
  input_end_ms: number;
  curve_resolution_ms: number;
  focus_status: DouyinFocusStatus;
  outfit_parts_json?: OutfitPart[];
  focus_note?: string | null;
}

export interface DouyinVideoClipPatch extends Omit<DouyinVideoClipInput, "video_id"> {
  expected_version: number;
}

export interface DouyinClipActionInput {
  account_id: number;
  expected_version: number;
}

export interface DouyinCreateResult {
  id: number;
}

export interface DouyinPagedResult<T> {
  items: T[];
  total?: number;
}

export interface DouyinStyleInput {
  account_id: number;
  style_code: string;
  style_name: string;
  main_image?: string | null;
}

export interface DouyinColorInput {
  account_id: number;
  color_code: string;
  color_name: string;
  color_image?: string | null;
}

export const douyinColorAnalyticsApi = {
  getAnnotationContext() {
    return unwrapDouyinColorAnalytics(request.get<DouyinAnnotationContext>(`${basePath}/annotation-context`));
  },
  listVideos(params: { account_id: number; limit?: number; offset?: number; annotation_status?: DouyinAnnotationStatus }) {
    return unwrapDouyinColorAnalytics(request.get<DouyinPagedResult<DouyinVideo>>(`${basePath}/videos`, { params }));
  },
  getVideo(videoId: string, accountId: number) {
    return unwrapDouyinColorAnalytics(request.get<DouyinVideo>(`${basePath}/videos/${encodeURIComponent(videoId)}`, { params: { account_id: accountId } }));
  },
  listVideoAnalysisSnapshots(videoId: string, accountId: number) {
    return unwrapDouyinColorAnalytics(request.get<DouyinVideoAnalysisSnapshot[]>(`${basePath}/videos/${encodeURIComponent(videoId)}/analysis-snapshots`, { params: { account_id: accountId } }));
  },
  listVideoClips(params: { account_id: number; video_id: number; include_deleted?: boolean }) {
    return unwrapDouyinColorAnalytics(request.get<DouyinPagedResult<DouyinVideoClip>>(`${basePath}/video-clips`, { params }));
  },
  createVideoClip(payload: DouyinVideoClipInput) {
    return unwrapDouyinColorAnalytics(request.post<DouyinVideoClip>(`${basePath}/video-clips`, payload));
  },
  updateVideoClip(clipId: number, payload: DouyinVideoClipPatch) {
    return unwrapDouyinColorAnalytics(request.patch<DouyinVideoClip>(`${basePath}/video-clips/${clipId}`, payload, { params: { account_id: payload.account_id } }));
  },
  deleteVideoClip(clipId: number, payload: Pick<DouyinClipActionInput, "account_id" | "expected_version">) {
    return unwrapDouyinColorAnalytics(request.delete<DouyinVideoClip>(`${basePath}/video-clips/${clipId}`, { params: { account_id: payload.account_id }, data: payload }));
  },
  submitVideoClip(clipId: number, payload: DouyinClipActionInput) {
    return unwrapDouyinColorAnalytics(request.post<DouyinVideoClip>(`${basePath}/video-clips/${clipId}/submit`, payload, { params: { account_id: payload.account_id } }));
  },
  approveVideoClip(clipId: number, payload: DouyinClipActionInput) {
    return unwrapDouyinColorAnalytics(request.post<DouyinVideoClip>(`${basePath}/video-clips/${clipId}/approve`, payload, { params: { account_id: payload.account_id } }));
  },
  rejectVideoClip(clipId: number, payload: DouyinClipActionInput) {
    return unwrapDouyinColorAnalytics(request.post<DouyinVideoClip>(`${basePath}/video-clips/${clipId}/reject`, payload, { params: { account_id: payload.account_id } }));
  },
  restoreVideoClip(clipId: number, payload: DouyinClipActionInput) {
    return unwrapDouyinColorAnalytics(request.post<DouyinVideoClip>(`${basePath}/video-clips/${clipId}/restore`, payload, { params: { account_id: payload.account_id } }));
  },
  listStyles(accountId: number) {
    return unwrapDouyinColorAnalytics(request.get<DouyinPagedResult<DouyinGarmentStyle>>(`${basePath}/styles`, { params: { account_id: accountId } }));
  },
  searchProductArchiveStyles(accountId: number, q: string) {
    return unwrapDouyinColorAnalytics(request.get<DouyinPagedResult<{ product_code: string; product_name: string }>>(`${basePath}/product-archive/styles`, { params: { account_id: accountId, q } }));
  },
  resolveProductArchiveStyle(accountId: number, productCode: string) {
    return unwrapDouyinColorAnalytics(request.post<{ id: number; style_code: string; style_name: string }>(`${basePath}/product-archive/styles/${encodeURIComponent(productCode)}/resolve`, null, { params: { account_id: accountId } }));
  },
  createStyle(payload: DouyinStyleInput) {
    return unwrapDouyinColorAnalytics(request.post<DouyinCreateResult>(`${basePath}/styles`, payload));
  },
  updateStyle(styleId: number, payload: Partial<DouyinStyleInput> & Pick<DouyinStyleInput, "account_id">) {
    const { account_id, ...body } = payload;
    return unwrapDouyinColorAnalytics(request.patch<DouyinGarmentStyle>(basePath + "/styles/" + styleId, body, { params: { account_id } }));
  },
  listColors(styleId: number, accountId: number) {
    return unwrapDouyinColorAnalytics(request.get<DouyinPagedResult<DouyinGarmentColor>>(`${basePath}/styles/${styleId}/colors`, { params: { account_id: accountId } }));
  },
  createColor(styleId: number, payload: DouyinColorInput) {
    return unwrapDouyinColorAnalytics(request.post<DouyinCreateResult>(`${basePath}/styles/${styleId}/colors`, payload));
  },
  updateColor(styleId: number, colorId: number, payload: Partial<DouyinColorInput> & Pick<DouyinColorInput, "account_id">) {
    const { account_id, ...body } = payload;
    return unwrapDouyinColorAnalytics(request.patch<DouyinGarmentColor>(basePath + "/styles/" + styleId + "/colors/" + colorId, body, { params: { account_id } }));
  },
};

// ====== Task 18: 颜色留存报告 API ======
export type DouyinColorReportTab = "outfit" | "top" | "bottom";
export type DouyinColorExportFormat = "csv" | "xlsx";

export interface DouyinColorRankingParams {
  observation_window: string;
  position_segment: string;
}

export interface DouyinColorRankingRow {
  combination_key: string;
  avg_retention: number | null;
  avg_rank: number | null;
  stability_rank: number | null;
  sample_count: number;
  position_segment: string;
  observation_window: string;
  sku_color_code: string | null;
  sku_color_name: string | null;
}

export interface DouyinColorRankingResult {
  items: DouyinColorRankingRow[];
  total?: number;
}

export interface DouyinColorExportResult {
  download_url: string | null;
  format: DouyinColorExportFormat;
  tab: DouyinColorReportTab;
}

export const douyinColorReportApi = {
  getOutfitRankings(accountId: number, params: DouyinColorRankingParams) {
    return unwrapDouyinColorAnalytics(request.get<DouyinColorRankingResult>(`${basePath}/accounts/${accountId}/report/outfit`, { params }));
  },
  getTopRankings(accountId: number, params: DouyinColorRankingParams) {
    return unwrapDouyinColorAnalytics(request.get<DouyinColorRankingResult>(`${basePath}/accounts/${accountId}/report/top`, { params }));
  },
  getBottomRankings(accountId: number, params: DouyinColorRankingParams) {
    return unwrapDouyinColorAnalytics(request.get<DouyinColorRankingResult>(`${basePath}/accounts/${accountId}/report/bottom`, { params }));
  },
  exportReport(accountId: number, params: { format: DouyinColorExportFormat; tab: DouyinColorReportTab }) {
    return unwrapDouyinColorAnalytics(request.post<DouyinColorExportResult>(`${basePath}/accounts/${accountId}/report/export`, params));
  },
};

// ====== Task 19: 健康与发布阶段管理 API ======
export type DouyinColorReleaseStage = "A" | "B" | "C" | "D";

export interface DouyinColorCollectorStatus {
  account_id: number;
  current_status: string;
  queued_batch_count: number;
  queued_bytes: number;
  script_version: string | null;
  last_heartbeat_at: string | null;
}

export interface DouyinColorQueueCapacity {
  queued_jobs: number;
}

export interface DouyinColorFeatureFlags {
  color_analysis_enabled: boolean;
  annotation_review_enabled: boolean;
}

export interface DouyinColorHealth {
  collector_status: DouyinColorCollectorStatus[];
  queue_capacity: DouyinColorQueueCapacity;
  feature_flags: DouyinColorFeatureFlags;
}

export interface DouyinColorActiveToken {
  token_prefix: string;
  expires_at: string | null;
  is_active: boolean;
}

export interface DouyinColorTokenRotateResult {
  upload_token: string;
  expires_at: string;
  revoked_count: number;
}

export interface DouyinColorReleaseStageInfo {
  current_stage: DouyinColorReleaseStage;
  bounce_report_enabled: boolean;
  bounce_semantics_status: string;
  active_token: DouyinColorActiveToken | null;
}

export const douyinColorAdminApi = {
  getHealth() {
    return unwrapDouyinColorAnalytics(request.get<DouyinColorHealth>(`${basePath}/health`));
  },
  rotateToken(accountId: number) {
    return unwrapDouyinColorAnalytics(request.post<DouyinColorTokenRotateResult>(`${basePath}/accounts/${accountId}/upload-tokens/rotate`, {}));
  },
  getReleaseStage(accountId: number) {
    return unwrapDouyinColorAnalytics(request.get<DouyinColorReleaseStageInfo>(`${basePath}/accounts/${accountId}/release-stage`));
  },
  advanceStage(accountId: number, target_stage: string) {
    return unwrapDouyinColorAnalytics(request.post<DouyinColorReleaseStageInfo>(`${basePath}/accounts/${accountId}/release-stage/advance`, { target_stage }));
  },
  toggleBounceReport(accountId: number, enabled: boolean) {
    return unwrapDouyinColorAnalytics(request.post<DouyinColorReleaseStageInfo>(`${basePath}/accounts/${accountId}/release-stage/bounce-report`, { enabled }));
  },
};
