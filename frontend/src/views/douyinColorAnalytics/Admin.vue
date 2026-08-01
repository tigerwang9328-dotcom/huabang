<template>
  <section class="admin-page" v-loading="loading">
    <div class="page-head">
      <div>
        <p class="eyebrow">销售中心 · 线上销售</p>
        <h1>抖音视频分析</h1>
        <p>在这里查看采集是否正常，并为油猴脚本生成一次性上传令牌。</p>
      </div>
      <el-button :loading="loading" @click="loadAll">刷新</el-button>
    </div>

    <el-alert v-if="loadError" :title="loadError" type="warning" show-icon :closable="false" class="banner" />

    <el-card class="section-card" shadow="never">
      <template #header><h2>采集状态</h2></template>
      <el-descriptions v-if="context" :column="2" border>
        <el-descriptions-item label="当前账号">{{ context.account.display_name }}</el-descriptions-item>
        <el-descriptions-item label="抖音昵称">{{ context.account.observed_account_name || "尚未上报" }}</el-descriptions-item>
        <el-descriptions-item label="当前采集状态">
          <el-tag :type="statusTagType(activeCollector?.current_status)" effect="plain">{{ activeCollector?.current_status || "等待油猴心跳" }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="脚本最近心跳">{{ formatTime(context.account.last_heartbeat_at) }}</el-descriptions-item>
        <el-descriptions-item label="油猴脚本版本">{{ activeCollector?.script_version || "尚未上报" }}</el-descriptions-item>
        <el-descriptions-item label="本地待上传批次">{{ activeCollector?.queued_batch_count ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="本地待上传数据">{{ formatBytes(activeCollector?.queued_bytes ?? 0) }}</el-descriptions-item>
        <el-descriptions-item label="服务器计算队列">{{ health?.queue_capacity.queued_jobs ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="分析服务">{{ health?.feature_flags.color_analysis_enabled ? "已启用" : "未启用" }}</el-descriptions-item>
      </el-descriptions>
      <el-empty v-else description="尚未读取到启用的抖音账号" />
      <p class="hint">没有心跳时：确认油猴脚本已启用、已填写当前令牌，并在抖音创作服务平台保持登录。</p>
    </el-card>

    <el-card class="section-card" shadow="never">
      <template #header><h2>采集令牌</h2></template>
      <el-descriptions v-if="releaseStage" :column="2" border>
        <el-descriptions-item label="当前令牌前缀"><code>{{ releaseStage.active_token?.token_prefix || "—" }}</code></el-descriptions-item>
        <el-descriptions-item label="到期时间">{{ formatTime(releaseStage.active_token?.expires_at) }}</el-descriptions-item>
        <el-descriptions-item label="令牌状态"><el-tag :type="releaseStage.active_token?.is_active ? 'success' : 'info'" effect="plain">{{ releaseStage.active_token?.is_active ? "有效" : "无有效令牌" }}</el-tag></el-descriptions-item>
      </el-descriptions>
      <el-empty v-else description="令牌状态暂不可用" />
      <div class="card-actions" v-if="canManage">
        <el-button type="primary" :loading="rotating" :disabled="!context" @click="confirmRotate">生成新令牌</el-button>
        <span class="muted">生成后旧令牌立即失效。</span>
      </div>
      <p v-else class="hint">你可以查看采集状态；生成令牌需要抖音分析管理员权限。</p>
    </el-card>

    <el-card class="section-card" shadow="never">
      <template #header><h2>数据分析入口</h2></template>
      <div class="entry-actions">
        <el-button @click="router.push({ name: 'DouyinColorVideoList' })">视频列表</el-button>
        <el-button @click="router.push({ name: 'DouyinColorStyles' })">款式颜色</el-button>
        <el-button type="primary" @click="router.push({ name: 'DouyinColorReport' })">颜色报告</el-button>
      </div>
    </el-card>

    <el-collapse class="advanced" v-if="releaseStage">
      <el-collapse-item title="高级管理" name="advanced">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="发布阶段">{{ releaseStage.current_stage }}</el-descriptions-item>
          <el-descriptions-item label="弹回报告">{{ releaseStage.bounce_report_enabled ? "已开启" : "已关闭" }}</el-descriptions-item>
          <el-descriptions-item label="弹回语义状态">{{ releaseStage.bounce_semantics_status }}</el-descriptions-item>
        </el-descriptions>
      </el-collapse-item>
    </el-collapse>

    <el-dialog :model-value="Boolean(issuedToken)" title="请立即保存新的采集令牌" width="560px" :close-on-click-modal="false" :close-on-press-escape="false" @closed="clearIssuedToken">
      <el-alert title="该令牌只会在本窗口展示一次。关闭、刷新或离开页面后无法再次查看。" type="warning" :closable="false" show-icon />
      <el-input class="token-value" :model-value="issuedToken || ''" readonly>
        <template #append><el-button @click="copyIssuedToken">复制</el-button></template>
      </el-input>
      <template #footer><el-button type="primary" @click="clearIssuedToken">我已保存</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { onBeforeRouteLeave, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { douyinColorAnalyticsApi, douyinColorAdminApi, type DouyinAnnotationContext, type DouyinColorHealth, type DouyinColorReleaseStageInfo } from "@/api/douyinColorAnalytics";

const router = useRouter();
const auth = useAuthStore();
const loading = ref(false);
const rotating = ref(false);
const loadError = ref("");
const issuedToken = ref<string | null>(null);
const context = ref<DouyinAnnotationContext | null>(null);
const health = ref<DouyinColorHealth | null>(null);
const releaseStage = ref<DouyinColorReleaseStageInfo | null>(null);

const canManage = computed(() => auth.hasPermission("douyin.admin"));
const activeCollector = computed(() => health.value?.collector_status.find((item) => item.account_id === context.value?.account.id));

function formatTime(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-CN", { hour12: false });
}

function formatBytes(bytes: number) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let index = 0;
  let value = bytes;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value.toFixed(1)} ${units[index]}`;
}

function statusTagType(status?: string) {
  const value = (status || "").toLowerCase();
  if (value.includes("active") || value.includes("healthy") || value.includes("running")) return "success";
  if (value.includes("error") || value.includes("failed") || value.includes("offline")) return "danger";
  return "info";
}

function describeError(error: unknown) {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 401) return "登录已失效，请重新登录中台后再试。";
  if (status === 403) return "你没有查看该抖音账号采集状态的权限，请联系管理员授权。";
  if (status === 404) return "采集服务尚未启用，请联系管理员完成服务部署。";
  const response = (error as { response?: { data?: { detail?: string; message?: string } } })?.response?.data;
  return response?.detail || response?.message || "暂时无法读取采集状态，请稍后刷新。";
}

async function loadAll() {
  loading.value = true;
  loadError.value = "";
  try {
    context.value = (await douyinColorAnalyticsApi.getAnnotationContext()).data;
    const accountId = context.value.account.id;
    const [healthResult, stageResult] = await Promise.all([
      douyinColorAdminApi.getHealth(),
      douyinColorAdminApi.getReleaseStage(accountId),
    ]);
    health.value = healthResult.data;
    releaseStage.value = stageResult.data;
  } catch (error) {
    loadError.value = describeError(error);
  } finally {
    loading.value = false;
  }
}

async function confirmRotate() {
  if (!context.value) return;
  try {
    await ElMessageBox.confirm("生成新令牌会立即使旧令牌失效。油猴脚本需要改为使用新令牌，确认继续？", "确认生成新令牌", { type: "warning", confirmButtonText: "确认生成", cancelButtonText: "取消" });
  } catch { return; }
  rotating.value = true;
  try {
    const res = await douyinColorAdminApi.rotateToken(context.value.account.id);
    issuedToken.value = res.data.upload_token;
    releaseStage.value = (await douyinColorAdminApi.getReleaseStage(context.value.account.id)).data;
  } catch (error) {
    ElMessage.error(describeError(error));
  } finally {
    rotating.value = false;
  }
}

async function copyIssuedToken() {
  if (!issuedToken.value) return;
  try {
    await navigator.clipboard.writeText(issuedToken.value);
    ElMessage.success("已复制，请粘贴到油猴脚本配置中。");
  } catch {
    ElMessage.error("复制失败，请手动复制令牌。");
  }
}

function clearIssuedToken() { issuedToken.value = null; }

onBeforeRouteLeave(clearIssuedToken);
onBeforeUnmount(clearIssuedToken);
onMounted(loadAll);
</script>

<style scoped>
.admin-page { padding: 24px; }
.page-head { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 16px; }
.page-head h1 { margin: 5px 0; color: #172033; }
.page-head p { margin: 0; color: #667085; }
.eyebrow { font-size: 11px; font-weight: 800; letter-spacing: .09em; color: #5266a6 !important; }
.banner, .section-card { margin-bottom: 16px; }
.section-card h2 { margin: 0; font-size: 16px; color: #172033; }
.card-actions, .entry-actions { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
.hint, .muted { color: #667085; font-size: 12px; }
.advanced { margin-bottom: 16px; }
.token-value { margin-top: 16px; }
code { background: #f5f7fa; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
@media(max-width: 640px) { .admin-page { padding: 16px; } .page-head { flex-direction: column; } }
</style>
