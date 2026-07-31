<template>
  <section class="admin-page" v-loading="loading">
    <div class="page-head">
      <div>
        <el-button text @click="router.push({ name: 'DouyinColorVideoList' })">← 返回视频</el-button>
        <p class="eyebrow">DOUYIN COLOR ADMIN</p>
        <h1>管理与健康</h1>
        <p>采集器状态、队列容量、令牌轮换与发布阶段开关；敏感操作由服务端权限校验。</p>
      </div>
      <el-button :loading="loading" @click="loadAll">刷新</el-button>
    </div>

    <el-alert v-if="loadError" :title="loadError" type="error" show-icon :closable="false" class="banner" />

    <!-- 健康页区域 -->
    <el-card class="section-card" shadow="never">
      <template #header><h2>采集器状态与队列</h2></template>
      <el-descriptions v-if="health" :column="2" border>
        <el-descriptions-item label="当前状态">
          <el-tag :type="statusTagType(health.collector_status.current_status)" effect="plain">
            {{ health.collector_status.current_status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="队列批次">{{ health.collector_status.queued_batch_count }}</el-descriptions-item>
        <el-descriptions-item label="队列字节">{{ formatBytes(health.collector_status.queued_bytes) }}</el-descriptions-item>
        <el-descriptions-item label="最近心跳">{{ formatTime(health.collector_status.last_heartbeat_at) }}</el-descriptions-item>
        <el-descriptions-item label="计算任务排队">
          {{ health.queue_capacity.calculation_job_queued }} / {{ health.queue_capacity.calculation_job_capacity }}
        </el-descriptions-item>
        <el-descriptions-item label="当前阶段">
          <el-tag type="success">{{ health.feature_flags.current_stage }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="弹回报告">
          <el-tag :type="health.feature_flags.bounce_report_enabled ? 'success' : 'info'" effect="plain">
            {{ health.feature_flags.bounce_report_enabled ? '已开启' : '已关闭' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="弹回语义状态">{{ health.feature_flags.bounce_semantics_status }}</el-descriptions-item>
      </el-descriptions>
      <el-empty v-else description="暂无健康数据" />
    </el-card>

    <!-- 权限区域 -->
    <el-card class="section-card" shadow="never">
      <template #header><h2>当前权限</h2></template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="用户角色">
          <el-tag v-for="role in auth.roles" :key="role" class="role-tag" effect="plain">{{ role }}</el-tag>
          <span v-if="auth.roles.length === 0" class="muted">未分配角色</span>
        </el-descriptions-item>
        <el-descriptions-item label="是否管理员">
          <el-tag :type="auth.isAdmin ? 'danger' : 'info'" effect="plain">{{ auth.isAdmin ? '是' : '否' }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="可执行操作">
          <el-tag v-if="canManage" type="success" effect="plain">可管理（令牌轮换、阶段前进）</el-tag>
          <el-tag v-else type="info" effect="plain">只读查看</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="数据范围">{{ auth.dataScope }}</el-descriptions-item>
      </el-descriptions>
      <p class="hint">权限说明：admin 可见全部功能；viewer 仅只读。角色与权限由服务端 JWT 控制，前端不做绕过。</p>
    </el-card>

    <!-- 令牌轮换区域 -->
    <el-card class="section-card" shadow="never">
      <template #header><h2>上传令牌</h2></template>
      <el-descriptions v-if="releaseStage" :column="2" border>
        <el-descriptions-item label="当前令牌前缀">
          <code>{{ releaseStage.active_token?.token_prefix || '—' }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="到期时间">
          {{ formatTime(releaseStage.active_token?.expires_at || null) }}
        </el-descriptions-item>
        <el-descriptions-item label="令牌状态">
          <el-tag v-if="releaseStage.active_token?.is_active" type="success" effect="plain">active</el-tag>
          <el-tag v-else type="info" effect="plain">无活跃令牌</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <div class="card-actions">
        <el-button type="danger" :disabled="!canManage" :loading="rotating" @click="confirmRotate">轮换令牌</el-button>
        <span v-if="!canManage" class="muted">需要管理权限</span>
      </div>
    </el-card>

    <!-- A/B/C/D 阶段开关区域 -->
    <el-card class="section-card" shadow="never">
      <template #header><h2>发布阶段</h2></template>
      <el-descriptions v-if="releaseStage" :column="1" border>
        <el-descriptions-item label="当前阶段">
          <el-steps :active="stageIndex" finish-status="success" class="stage-steps">
            <el-step title="A" description="内测" />
            <el-step title="B" description="灰度" />
            <el-step title="C" description="扩大" />
            <el-step title="D" description="全量" />
          </el-steps>
        </el-descriptions-item>
        <el-descriptions-item label="弹回报告开关">
          <div class="bounce-row">
            <el-switch
              :model-value="releaseStage.bounce_report_enabled"
              :disabled="!canToggleBounce || !canManage"
              :loading="togglingBounce"
              @change="onToggleBounce"
            />
            <span v-if="!canToggleBounce" class="muted">弹回语义状态未达到 verified_*_is_better，暂不可开启。</span>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="弹回语义状态">{{ releaseStage.bounce_semantics_status }}</el-descriptions-item>
      </el-descriptions>
      <div class="card-actions">
        <el-button type="primary" :disabled="!canManage || !canAdvance" :loading="advancing" @click="confirmAdvance">
          前进到下一阶段（{{ nextStage }}）
        </el-button>
        <span v-if="!canAdvance" class="muted">已是最终阶段 D</span>
        <span v-if="!canManage" class="muted">需要管理权限</span>
      </div>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import {
  douyinColorAnalyticsApi,
  douyinColorAdminApi,
  type DouyinAnnotationContext,
  type DouyinColorHealth,
  type DouyinColorReleaseStageInfo,
  type DouyinColorReleaseStage,
} from "@/api/douyinColorAnalytics";

const router = useRouter();
const auth = useAuthStore();
const loading = ref(false);
const rotating = ref(false);
const advancing = ref(false);
const togglingBounce = ref(false);
const loadError = ref("");

const context = ref<DouyinAnnotationContext | null>(null);
const health = ref<DouyinColorHealth | null>(null);
const releaseStage = ref<DouyinColorReleaseStageInfo | null>(null);

const STAGE_ORDER: DouyinColorReleaseStage[] = ["A", "B", "C", "D"];

const stageIndex = computed(() => {
  if (!releaseStage.value) return 0;
  const idx = STAGE_ORDER.indexOf(releaseStage.value.current_stage);
  return idx < 0 ? 0 : idx;
});

const canAdvance = computed(() => {
  if (!releaseStage.value) return false;
  return STAGE_ORDER.indexOf(releaseStage.value.current_stage) < STAGE_ORDER.length - 1;
});

const nextStage = computed(() => {
  if (!releaseStage.value || !canAdvance.value) return "—";
  const idx = STAGE_ORDER.indexOf(releaseStage.value.current_stage);
  return STAGE_ORDER[idx + 1] || "—";
});

const canManage = computed(() => auth.isAdmin || auth.hasRole("admin") || auth.hasPermission("douyin:admin") || auth.hasPermission("douyin.color:admin"));

const canToggleBounce = computed(() => {
  if (!releaseStage.value) return false;
  const status = releaseStage.value.bounce_semantics_status || "";
  return status.startsWith("verified_") && status.endsWith("_is_better");
});

function formatTime(value: string | null) {
  if (!value) return "—";
  try { return new Date(value).toLocaleString("zh-CN", { hour12: false }); }
  catch { return value; }
}

function formatBytes(bytes: number) {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let idx = 0;
  let val = bytes;
  while (val >= 1024 && idx < units.length - 1) { val /= 1024; idx++; }
  return `${val.toFixed(1)} ${units[idx]}`;
}

function statusTagType(status: string) {
  const s = (status || "").toLowerCase();
  if (s.includes("running") || s.includes("ok") || s.includes("healthy") || s.includes("active")) return "success";
  if (s.includes("idle") || s.includes("waiting") || s.includes("paused")) return "info";
  if (s.includes("error") || s.includes("down") || s.includes("failed")) return "danger";
  return "warning";
}

function describeError(error: unknown) {
  const response = (error as { response?: { data?: { detail?: string; message?: string } } })?.response?.data;
  return response?.detail || response?.message || (error instanceof Error ? error.message : "请求失败");
}

async function loadContext() {
  if (context.value) return;
  context.value = (await douyinColorAnalyticsApi.getAnnotationContext()).data;
}

async function loadHealth() {
  health.value = (await douyinColorAdminApi.getHealth()).data;
}

async function loadReleaseStage() {
  if (!context.value) return;
  releaseStage.value = (await douyinColorAdminApi.getReleaseStage(context.value.account.id)).data;
}

async function loadAll() {
  loading.value = true;
  loadError.value = "";
  try {
    await loadContext();
    await Promise.all([loadHealth(), loadReleaseStage()]);
  } catch (error) {
    loadError.value = describeError(error);
  } finally {
    loading.value = false;
  }
}

async function confirmRotate() {
  if (!context.value) return;
  try {
    await ElMessageBox.confirm(
      "轮换将立即吊销当前活跃令牌，已使用旧令牌的采集器需要更新配置。确认继续？",
      "确认轮换令牌",
      { type: "warning", confirmButtonText: "确认轮换", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  rotating.value = true;
  try {
    const res = await douyinColorAdminApi.rotateToken(context.value.account.id);
    await loadReleaseStage();
    ElMessage.success(`令牌已轮换，新令牌前缀：${res.data.token_prefix}`);
  } catch (error) {
    ElMessage.error(describeError(error));
  } finally {
    rotating.value = false;
  }
}

async function confirmAdvance() {
  if (!context.value || !canAdvance.value) return;
  const target = nextStage.value;
  try {
    await ElMessageBox.confirm(
      `确认将发布阶段从 ${releaseStage.value?.current_stage} 前进到 ${target}？此操作不可回退。`,
      `确认前进到阶段 ${target}`,
      { type: "warning", confirmButtonText: `前进到 ${target}`, cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  advancing.value = true;
  try {
    await douyinColorAdminApi.advanceStage(context.value.account.id, target);
    await loadAll();
    ElMessage.success(`已前进到阶段 ${target}`);
  } catch (error) {
    ElMessage.error(describeError(error));
  } finally {
    advancing.value = false;
  }
}

async function onToggleBounce(val: string | number | boolean) {
  if (!context.value) return;
  const enabled = Boolean(val);
  togglingBounce.value = true;
  try {
    await douyinColorAdminApi.toggleBounceReport(context.value.account.id, enabled);
    await loadReleaseStage();
    ElMessage.success(enabled ? "弹回报告已开启" : "弹回报告已关闭");
  } catch (error) {
    ElMessage.error(describeError(error));
  } finally {
    togglingBounce.value = false;
  }
}

onMounted(loadAll);
</script>

<style scoped>
.admin-page { padding: 24px; }
.page-head { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 16px; }
.page-head h1 { margin: 5px 0; color: #172033; }
.page-head p { margin: 0; color: #667085; }
.eyebrow { font-size: 11px; font-weight: 800; letter-spacing: .09em; color: #5266a6 !important; }
.banner { margin-bottom: 16px; }
.section-card { margin-bottom: 16px; }
.section-card h2 { margin: 0; font-size: 16px; color: #172033; }
.role-tag { margin-right: 6px; }
.card-actions { margin-top: 12px; display: flex; gap: 12px; align-items: center; }
.bounce-row { display: flex; align-items: center; gap: 12px; }
.stage-steps { padding: 8px 0; }
.hint { margin: 8px 0 0; color: #667085; font-size: 12px; }
.muted { color: #c0c4cc; font-size: 12px; }
code { background: #f5f7fa; padding: 2px 6px; border-radius: 3px; font-family: monospace; }
@media(max-width: 640px) { .admin-page { padding: 16px; } .page-head { flex-direction: column; } }
</style>
