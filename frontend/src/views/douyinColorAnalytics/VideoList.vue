<template>
  <section class="douyin-video-list" v-loading="loading">
    <div class="page-head">
      <div>
        <p class="eyebrow">DOUYIN COLOR ANALYTICS</p>
        <h1>视频片段标注</h1>
        <p>每个片段标注一套清晰可见的穿搭；为套内每件衣物选择真实款号与可选 SKU，多套重点或无法判断只保留质量记录，不进入排名。</p>
      </div>
      <div class="head-actions">
        <el-tag v-if="context" type="info" effect="plain">账号：{{ context.account.display_name }}<span v-if="context.account.observed_account_name">（{{ context.account.observed_account_name }}）</span></el-tag>
        <el-button @click="openStyles">款号与颜色</el-button>
        <el-button type="primary" :loading="loading" @click="load">刷新视频</el-button>
      </div>
    </div>

    <el-alert
      v-if="loadError"
      title="标注数据读取失败"
      :description="loadError"
      type="error"
      show-icon
      :closable="false"
      class="load-error"
    />
    <el-alert
      v-else
      title="审核与权限说明"
      description="页面不自行判断敏感操作权限；创建、提交、审核、删除和恢复均由服务端记录账号、操作人、版本与审计事件。"
      type="info"
      show-icon
      :closable="false"
      class="load-error"
    />

    <el-table :data="videos" stripe class="video-table" empty-text="当前账号暂无可标注视频">
      <el-table-column prop="title" label="作品" min-width="240">
        <template #default="{ row }">
          <strong>{{ row.title || "未命名作品" }}</strong>
          <small>{{ row.video_id_string }}</small>
        </template>
      </el-table-column>
      <el-table-column prop="published_at" label="发布时间" width="170">
        <template #default="{ row }">{{ formatTime(row.published_at) }}</template>
      </el-table-column>
      <el-table-column prop="duration_ms" label="时长" width="100">
        <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
      </el-table-column>
      <el-table-column prop="collection_status" label="采集状态" width="120">
        <template #default="{ row }"><el-tag effect="plain">{{ row.collection_status }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }"><el-button type="primary" text @click="annotate(row)">维护片段</el-button></template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { douyinColorAnalyticsApi, type DouyinAnnotationContext, type DouyinVideo } from "@/api/douyinColorAnalytics";

const router = useRouter();
const loading = ref(false);
const loadError = ref("");
const context = ref<DouyinAnnotationContext | null>(null);
const videos = ref<DouyinVideo[]>([]);

const formatTime = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
const sortVideosForAnnotation = (items: DouyinVideo[]) => [...items].sort((left, right) => {
  if (left.published_at == null && right.published_at == null) return 0;
  if (left.published_at == null) return 1;
  if (right.published_at == null) return -1;
  return Date.parse(right.published_at) - Date.parse(left.published_at);
});
const formatDuration = (milliseconds: number) => {
  const seconds = Math.max(0, Math.round(milliseconds / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
};

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    const contextResponse = await douyinColorAnalyticsApi.getAnnotationContext();
    context.value = contextResponse.data;
    const response = await douyinColorAnalyticsApi.listVideos({ account_id: context.value.account.id, limit: 200 });
    videos.value = sortVideosForAnnotation(response.data.items || []);
  } catch (error) {
    videos.value = [];
    loadError.value = describeError(error);
  } finally {
    loading.value = false;
  }
}

function annotate(video: DouyinVideo) {
  router.push({ name: "DouyinColorAnnotation", params: { videoId: video.video_id_string } });
}

function openStyles() {
  router.push({ name: "DouyinColorStyles" });
}

function describeError(error: unknown) {
  const response = (error as { response?: { data?: { detail?: string; message?: string } } })?.response?.data;
  return response?.detail || response?.message || (error instanceof Error ? error.message : "请求失败，请稍后重试");
}

onMounted(load);
</script>

<style scoped>
.douyin-video-list { min-width: 0; padding: 24px; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 16px; }
.page-head h1 { margin: 5px 0 8px; color: #172033; }
.page-head p { margin: 0; color: #667085; }
.eyebrow { font-size: 11px; font-weight: 800; letter-spacing: .09em; color: #5266a6 !important; }
.head-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.load-error { margin-bottom: 16px; }
.video-table strong, .video-table small { display: block; }
.video-table small { margin-top: 4px; color: #7b8494; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
@media (max-width: 760px) { .douyin-video-list { padding: 16px; } .page-head { flex-direction: column; } .head-actions { justify-content: flex-start; } }
</style>
