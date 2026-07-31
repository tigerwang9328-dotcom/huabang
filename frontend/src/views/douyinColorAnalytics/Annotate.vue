<template>
  <section class="annotation-page" v-loading="loading">
    <div class="page-head">
      <div>
        <el-button text @click="router.push({ name: 'DouyinColorVideoList' })">← 返回视频</el-button>
        <p class="eyebrow">ANNOTATION WORKSPACE</p>
        <h1>{{ video?.title || "视频片段标注" }}</h1>
        <p>{{ video?.video_id_string }} · 账号：{{ context?.account.display_name || "加载中" }}</p>
      </div>
      <div class="head-actions">
        <el-button @click="startNew">新增片段</el-button>
        <el-button type="primary" :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <el-alert v-if="loadError" title="标注工作区读取失败" :description="loadError" type="error" show-icon :closable="false" class="banner" />
    <el-alert v-else title="整套穿搭标注规则" description="clear_primary 表示整套穿搭清晰可见，至少 2 件衣物（衣物位 + 款号 + 可选 SKU）；multi_focus、unclear 会清空衣物且只记录质量状态，不参与排名。" type="warning" show-icon :closable="false" class="banner" />

    <div class="workspace">
      <article class="preview-panel">
        <div class="preview-head">
          <div><span>作品预览</span><small>安全 pathname 仅用于打开创作者中心原作品</small></div>
          <el-button text type="primary" :disabled="!safeCreatorPath" @click="openOriginalWork">打开原作品</el-button>
        </div>
        <img v-if="video_preview_url" :src="video_preview_url" class="cover" alt="作品封面预览" />
        <el-empty v-else description="未提供可展示封面；仍可维护时间片段" :image-size="100" />
        <dl v-if="video" class="video-meta">
          <div><dt>时长</dt><dd>{{ formatDuration(video.duration_ms) }}</dd></div>
          <div><dt>采集状态</dt><dd>{{ video.collection_status }}</dd></div>
          <div><dt>曲线快照</dt><dd>{{ snapshots.length }} 条</dd></div>
        </dl>
        <div class="curve-panel">
          <div class="curve-label"><span>留存曲线时间轴</span><small>{{ curveResolutionLabel }}</small></div>
          <div v-if="curvePoints.length" class="curve-bars" aria-label="留存曲线预览">
            <i v-for="point in curvePoints" :key="`${point.second}-${point.value}`" :style="{ height: `${Math.max(3, point.value * 100)}%` }" />
          </div>
          <el-empty v-else description="尚无质量合格曲线；可保存片段，服务端将校验曲线分辨率" :image-size="60" />
        </div>
      </article>

      <article class="editor-panel">
        <div class="panel-title"><div><span>片段维护</span><small>输入按整秒保存，服务端返回实际吸附边界</small></div><el-tag v-if="editor.id" effect="plain">编辑 #{{ editor.id }}</el-tag></div>
        <el-alert v-if="validationErrors.length" title="请先修正以下校验错误" type="error" :closable="false" class="validation-alert">
          <ul><li v-for="error in validationErrors" :key="error">{{ error }}</li></ul>
        </el-alert>
        <el-form label-position="top">
          <div class="time-row">
            <el-form-item label="开始秒"><el-input-number v-model="startSecond" :min="0" :max="maxSecond - 1" :step="1" :precision="0" /></el-form-item>
            <el-form-item label="结束秒"><el-input-number v-model="endSecond" :min="1" :max="maxSecond" :step="1" :precision="0" /></el-form-item>
          </div>
          <el-form-item label="主要分析衣物判断">
            <el-radio-group v-model="editor.focus_status">
              <el-radio value="clear_primary">整套穿搭清晰可见</el-radio>
              <el-radio value="multi_focus">多件重点，不进入排名</el-radio>
              <el-radio value="unclear">无法判断，不进入排名</el-radio>
            </el-radio-group>
          </el-form-item>
          <template v-if="editor.focus_status === 'clear_primary'">
            <el-form-item label="穿搭衣物（clear_primary 至少 2 件）">
              <div v-for="(part, index) in outfitParts" :key="index" class="outfit-row">
                <el-select v-model="part.position" placeholder="衣物位" class="position-select">
                  <el-option label="外套 outer" value="outer" />
                  <el-option label="上衣 top" value="top" />
                  <el-option label="裤子 bottom" value="bottom" />
                  <el-option label="其他 none" value="none" />
                </el-select>
                <el-select v-model="part.style_id" placeholder="选择款号" filterable class="style-select" @change="() => onStyleChange(index)">
                  <el-option v-for="style in styles" :key="style.id" :label="`${style.style_code} · ${style.style_name}`" :value="style.id" />
                </el-select>
                <el-select v-model="part.sku_code" placeholder="SKU（可选）" :disabled="!part.style_id" filterable clearable class="sku-select">
                  <el-option v-for="color in colorsByStyle[part.style_id || 0] || []" :key="color.id" :label="`${color.color_code} · ${color.color_name}`" :value="color.color_code" />
                </el-select>
                <el-button text type="danger" @click="removePart(index)">删除</el-button>
              </div>
              <el-button @click="addPart">添加衣物</el-button>
            </el-form-item>
          </template>
          <el-form-item label="标注说明（可选）"><el-input v-model="editor.focus_note" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="记录穿搭判断、切换原因或审核需要关注的事实" /></el-form-item>
        </el-form>
        <div class="save-row"><el-button @click="startNew">取消编辑</el-button><el-button type="primary" :loading="saving" @click="save">保存草稿</el-button></div>
      </article>
    </div>

    <article class="clip-panel">
      <div class="panel-title"><div><span>已维护片段</span><small>review status、版本和操作人来自服务端记录，冲突不会被页面静默覆盖。</small></div></div>
      <el-table :data="clips" empty-text="尚未维护片段">
        <el-table-column label="时间" width="150"><template #default="{ row }">{{ seconds(row.start_ms) }}s – {{ seconds(row.end_ms) }}s</template></el-table-column>
        <el-table-column label="判断" width="150"><template #default="{ row }"><el-tag :type="focusTag(row.focus_status)" effect="plain">{{ focusLabel(row.focus_status) }}</el-tag></template></el-table-column>
        <el-table-column label="审核状态" width="120"><template #default="{ row }"><el-tag effect="plain">{{ row.annotation_status }}</el-tag></template></el-table-column>
        <el-table-column label="重叠" width="150"><template #default="{ row }">{{ row.overlap_status || "not_required" }}</template></el-table-column>
        <el-table-column label="版本" width="72"><template #default="{ row }">v{{ row.version }}</template></el-table-column>
        <el-table-column label="操作人" min-width="130"><template #default="{ row }">{{ row.updated_by || row.created_by || "—" }}</template></el-table-column>
        <el-table-column label="重叠说明" min-width="160"><template #default="{ row }">{{ row.overlap_reason || "—" }}</template></el-table-column>
        <el-table-column label="操作" min-width="240" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" @click="editClip(row)">编辑</el-button>
            <el-button v-if="row.annotation_status === 'draft'" text type="primary" @click="runAction(row, 'submit')">提交</el-button>
            <el-button v-if="row.annotation_status === 'submitted'" text type="success" @click="runAction(row, 'approve')">审核通过</el-button>
            <el-button v-if="row.annotation_status === 'submitted'" text type="danger" @click="runAction(row, 'reject')">驳回</el-button>
            <el-button v-if="row.annotation_status !== 'deleted'" text type="danger" @click="removeClip(row)">删除</el-button>
            <el-button v-else text type="warning" @click="runAction(row, 'restore')">恢复</el-button>
          </template>
        </el-table-column>
      </el-table>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRoute, useRouter } from "vue-router";
import {
  douyinColorAnalyticsApi,
  type DouyinAnnotationContext,
  type DouyinFocusStatus,
  type DouyinGarmentColor,
  type DouyinGarmentStyle,
  type DouyinVideo,
  type DouyinVideoAnalysisSnapshot,
  type DouyinVideoClip,
  type GarmentPosition,
} from "@/api/douyinColorAnalytics";

const CREATOR_ORIGIN = "https://creator.douyin.com";
const route = useRoute();
const router = useRouter();
const loading = ref(false);
const saving = ref(false);
const loadError = ref("");
const validationErrors = ref<string[]>([]);
const context = ref<DouyinAnnotationContext | null>(null);
const video = ref<DouyinVideo | null>(null);
const snapshots = ref<DouyinVideoAnalysisSnapshot[]>([]);
const clips = ref<DouyinVideoClip[]>([]);
const styles = ref<DouyinGarmentStyle[]>([]);
const colorsByStyle = ref<Record<number, DouyinGarmentColor[]>>({});

interface OutfitPartEditor { position: GarmentPosition; style_id: number | null; sku_code: string | null }
const outfitParts = ref<OutfitPartEditor[]>([]);

const newEditor = () => ({ id: null as number | null, version: 0, input_start_ms: 0, input_end_ms: 1_000, focus_status: "clear_primary" as DouyinFocusStatus, focus_note: "" });
const editor = ref(newEditor());
const maxSecond = computed(() => Math.max(1, Math.ceil((video.value?.duration_ms || 1_000) / 1_000)));
const startSecond = computed({ get: () => Math.round(editor.value.input_start_ms / 1_000), set: (value: number | undefined) => { editor.value.input_start_ms = Math.max(0, Math.round(Number(value || 0)) * 1_000); } });
const endSecond = computed({ get: () => Math.round(editor.value.input_end_ms / 1_000), set: (value: number | undefined) => { editor.value.input_end_ms = Math.max(0, Math.round(Number(value || 0)) * 1_000); } });
const video_preview_url = computed(() => video.value?.cover_path || "");
const safeCreatorPath = computed(() => {
  const path = video.value?.creator_detail_path || "";
  return path.startsWith("/creator-micro/") && !path.includes("?") && !path.includes("#") ? path : "";
});
const curvePoints = computed(() => snapshots.value.find((item) => item.analysis_type === 1 && item.curve_quality_status === "valid")?.normalized_curve || []);
const curveResolutionLabel = computed(() => curvePoints.value.length ? `已加载 ${curvePoints.value.length} 个留存点` : "无可用留存点");

watch(() => editor.value.focus_status, (status) => { if (status !== "clear_primary") clearNonPrimaryOutfit(); });

async function load() {
  const videoId = String(route.params.videoId || "");
  if (!videoId) { loadError.value = "缺少作品 ID"; return; }
  loading.value = true;
  loadError.value = "";
  try {
    const contextResponse = await douyinColorAnalyticsApi.getAnnotationContext();
    context.value = contextResponse.data;
    const accountId = context.value.account.id;
    const videoResponse = await douyinColorAnalyticsApi.getVideo(videoId, accountId);
    const [snapshotResponse, clipResponse, styleResponse] = await Promise.all([
      douyinColorAnalyticsApi.listVideoAnalysisSnapshots(videoId, accountId),
      douyinColorAnalyticsApi.listVideoClips({ account_id: accountId, video_id: videoResponse.data.id, include_deleted: true }),
      douyinColorAnalyticsApi.listStyles(accountId),
    ]);
    video.value = videoResponse.data;
    snapshots.value = snapshotResponse.data || [];
    clips.value = clipResponse.data.items || [];
    styles.value = styleResponse.data.items || [];
  } catch (error) {
    loadError.value = describeError(error);
  } finally {
    loading.value = false;
  }
}

function clearNonPrimaryOutfit() { outfitParts.value = []; }
function addPart() { outfitParts.value.push({ position: "none", style_id: null, sku_code: null }); }
function removePart(index: number) { outfitParts.value.splice(index, 1); }
async function onStyleChange(index: number) {
  const part = outfitParts.value[index];
  if (!part) return;
  part.sku_code = null;
  if (!part.style_id || !context.value) return;
  if (!colorsByStyle.value[part.style_id]) {
    try { colorsByStyle.value[part.style_id] = (await douyinColorAnalyticsApi.listColors(part.style_id, context.value.account.id)).data.items || []; } catch (error) { ElMessage.error(describeError(error)); }
  }
}
function startNew() { validationErrors.value = []; editor.value = newEditor(); outfitParts.value = []; }
async function editClip(clip: DouyinVideoClip) {
  editor.value = { id: clip.id, version: clip.version, input_start_ms: clip.input_start_ms, input_end_ms: clip.input_end_ms, focus_status: clip.focus_status, focus_note: clip.focus_note || "" };
  outfitParts.value = (clip.outfit_parts_json || []).map((p) => ({ position: p.position, style_id: p.style_id, sku_code: p.sku_code }));
  if (context.value) {
    for (const part of outfitParts.value) {
      if (part.style_id && !colorsByStyle.value[part.style_id]) {
        try { colorsByStyle.value[part.style_id] = (await douyinColorAnalyticsApi.listColors(part.style_id, context.value.account.id)).data.items || []; } catch { /* ignore color load error on edit */ }
      }
    }
  }
}

function validate() {
  const errors: string[] = [];
  if (!video.value) errors.push("作品尚未加载完成");
  if (editor.value.input_start_ms < 0) errors.push("开始时间不能小于 0 秒");
  if (editor.value.input_end_ms <= editor.value.input_start_ms) errors.push("结束时间必须晚于开始时间");
  if (video.value && editor.value.input_end_ms > video.value.duration_ms) errors.push("结束时间不能超过作品时长");
  if (editor.value.focus_status === "clear_primary") {
    if (outfitParts.value.length < 2) errors.push("整套穿搭标注至少 2 件衣物");
    outfitParts.value.forEach((part, index) => {
      if (!part.position) errors.push(`第 ${index + 1} 件衣物未选择衣物位`);
      if (!part.style_id) errors.push(`第 ${index + 1} 件衣物未选择款号`);
    });
  }
  if (editor.value.focus_status !== "clear_primary" && outfitParts.value.length > 0) errors.push("非整套穿搭标注不得携带衣物信息");
  validationErrors.value = errors;
  return errors.length === 0;
}

async function save() {
  if (!context.value || !video.value || !validate()) return;
  saving.value = true;
  try {
    const outfit_parts_json = editor.value.focus_status === "clear_primary"
      ? outfitParts.value.map((p) => ({ position: p.position, style_id: p.style_id as number, sku_code: p.sku_code }))
      : [];
    const payload = { account_id: context.value.account.id, video_id: video.value.id, input_start_ms: editor.value.input_start_ms, input_end_ms: editor.value.input_end_ms, curve_resolution_ms: curveResolutionMs(), focus_status: editor.value.focus_status, outfit_parts_json, focus_note: editor.value.focus_note || null };
    const response = editor.value.id
      ? await douyinColorAnalyticsApi.updateVideoClip(editor.value.id, { ...payload, expected_version: editor.value.version })
      : await douyinColorAnalyticsApi.createVideoClip(payload);
    upsertClip(response.data);
    ElMessage.success("草稿已保存；请根据服务端返回的审核状态继续处理");
    startNew();
  } catch (error) {
    validationErrors.value = [describeError(error)];
  } finally { saving.value = false; }
}

async function runAction(clip: DouyinVideoClip, action: "submit" | "approve" | "reject" | "restore") {
  if (!context.value) return;
  try {
    const payload = { account_id: context.value.account.id, expected_version: clip.version };
    const response = action === "submit" ? await douyinColorAnalyticsApi.submitVideoClip(clip.id, payload)
      : action === "approve" ? await douyinColorAnalyticsApi.approveVideoClip(clip.id, payload)
      : action === "reject" ? await douyinColorAnalyticsApi.rejectVideoClip(clip.id, payload)
      : await douyinColorAnalyticsApi.restoreVideoClip(clip.id, payload);
    upsertClip(response.data);
    ElMessage.success("服务端已记录操作与审计信息");
  } catch (error) { if (String(error).includes("cancel")) return; ElMessage.error(describeError(error)); }
}

async function removeClip(clip: DouyinVideoClip) {
  if (!context.value) return;
  try {
    await ElMessageBox.confirm("删除会保留审计记录，可由服务端规则控制恢复。", "删除片段", { type: "warning" });
    const response = await douyinColorAnalyticsApi.deleteVideoClip(clip.id, { account_id: context.value.account.id, expected_version: clip.version });
    upsertClip(response.data);
    ElMessage.success("已请求删除，实际状态以服务端响应为准");
  } catch (error) { if (String(error).includes("cancel")) return; ElMessage.error(describeError(error)); }
}

function upsertClip(clip: DouyinVideoClip) { const index = clips.value.findIndex((item) => item.id === clip.id); if (index >= 0) clips.value.splice(index, 1, clip); else clips.value.unshift(clip); }
function curveResolutionMs() { if (curvePoints.value.length < 2) return 1_000; return Math.max(1_000, Math.round((curvePoints.value[1].second - curvePoints.value[0].second) * 1_000)); }
function openOriginalWork() { if (safeCreatorPath.value) window.open(`${CREATOR_ORIGIN}${safeCreatorPath.value}`, "_blank", "noopener,noreferrer"); }
function seconds(ms: number) { return Math.round(ms / 1_000); }
function formatDuration(ms: number) { return `${Math.floor(ms / 60_000)}:${String(Math.round(ms / 1_000) % 60).padStart(2, "0")}`; }
function focusLabel(status: DouyinFocusStatus) { return { clear_primary: "整套穿搭", multi_focus: "多件重点", unclear: "无法判断" }[status]; }
function focusTag(status: DouyinFocusStatus) { return status === "clear_primary" ? "success" : "warning"; }
function describeError(error: unknown) { const response = (error as { response?: { data?: { detail?: string; message?: string } } })?.response?.data; return response?.detail || response?.message || (error instanceof Error ? error.message : "请求失败"); }

onMounted(load);
</script>

<style scoped>
.annotation-page { padding: 24px; color: #172033; }
.page-head, .preview-head, .panel-title, .save-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-head h1 { margin: 4px 0; }.page-head p { margin: 0; color: #667085; }.eyebrow { font-size: 11px; font-weight: 800; letter-spacing: .09em; color: #5266a6 !important; }.head-actions { display: flex; gap: 8px; }.banner { margin: 16px 0; }
.workspace { display: grid; grid-template-columns: minmax(280px, .9fr) minmax(360px, 1.1fr); gap: 16px; }.preview-panel, .editor-panel, .clip-panel { border: 1px solid #e5eaf2; border-radius: 10px; background: #fff; padding: 18px; box-shadow: 0 1px 2px rgba(15, 23, 42, .04); }.preview-head span, .panel-title span { display: block; font-weight: 700; }.preview-head small, .panel-title small { color: #7b8494; font-size: 12px; }.cover { display: block; width: 100%; max-height: 320px; object-fit: cover; border-radius: 8px; margin: 16px 0; background: #f4f6f8; }.video-meta { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0; }.video-meta div { padding: 8px; background: #f7f8fb; }.video-meta dt { color: #7b8494; font-size: 12px; }.video-meta dd { margin: 4px 0 0; font-weight: 600; }.curve-panel { margin-top: 16px; }.curve-label { display: flex; justify-content: space-between; color: #667085; font-size: 12px; }.curve-bars { height: 80px; display: flex; align-items: end; gap: 2px; padding: 8px; margin-top: 8px; background: linear-gradient(#f8fafc, #eef3ff); border-radius: 6px; }.curve-bars i { flex: 1; min-width: 2px; background: #536fd6; opacity: .85; }.time-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }.full-width { width: 100%; }.validation-alert { margin-bottom: 12px; }.validation-alert ul { margin: 0; padding-left: 18px; }.clip-panel { margin-top: 16px; }.clip-panel .panel-title { margin-bottom: 10px; }
.outfit-row { display: grid; grid-template-columns: 1fr 1.5fr 1.5fr auto; gap: 8px; align-items: center; margin-bottom: 8px; }
.position-select, .style-select, .sku-select { width: 100%; }
@media (max-width: 900px) { .annotation-page { padding: 16px; }.page-head, .workspace { display: block; }.head-actions { margin-top: 12px; }.editor-panel { margin-top: 16px; }.outfit-row { grid-template-columns: 1fr; gap: 6px; } }
@media (max-width: 560px) { .time-row, .video-meta { grid-template-columns: 1fr; } }
</style>
