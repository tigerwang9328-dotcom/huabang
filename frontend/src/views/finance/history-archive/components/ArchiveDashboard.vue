<template>
  <section v-loading="loading" class="dashboard-wrap">
    <div class="metric-grid">
      <article><span>累计文件数量</span><strong>{{ summary.total_files.toLocaleString() }}</strong><small>正常数据资产</small></article>
      <article><span>累计存储容量</span><strong>{{ formatSize(summary.total_size) }}</strong><small>不含回收站统计</small></article>
      <article><span>数据覆盖年份</span><strong>{{ summary.covered_year_count }}</strong><small>{{ yearText }}</small></article>
      <article><span>数据分类数量</span><strong>{{ summary.category_count }}</strong><small>含一、二、三级分类</small></article>
    </div>
    <div class="dashboard-grid">
      <article class="panel distribution">
        <header><b>一级分类资产分布</b><small>按正常文件统计</small></header>
        <div v-if="summary.category_distribution.length" class="bars">
          <div v-for="item in summary.category_distribution" :key="item.category_id" class="bar-row">
            <span>{{ item.name }}</span><i><em :style="{ width: `${Math.max(2, item.file_count / maxCount * 100)}%` }" /></i><b>{{ item.file_count }}</b>
          </div>
        </div>
        <el-empty v-else description="暂无分类数据" :image-size="58" />
      </article>
      <article class="panel">
        <header><b>最近上传</b><small>最新 5 条</small></header>
        <div v-if="summary.recent_uploads.length" class="activity-list">
          <div v-for="item in summary.recent_uploads" :key="item.id">
            <span><b>{{ item.data_name }}</b><small>{{ item.uploader_name || "未知" }} · {{ formatDate(item.created_at) }}</small></span>
            <em>{{ formatSize(item.file_size) }}</em>
          </div>
        </div>
        <el-empty v-else description="暂无上传记录" :image-size="58" />
      </article>
      <article class="panel">
        <header><b>最近下载</b><small>最新 5 条</small></header>
        <div v-if="summary.recent_downloads.length" class="activity-list">
          <div v-for="item in summary.recent_downloads" :key="`${item.file_id}-${item.operation_time}`">
            <span><b>{{ item.data_name }}</b><small>{{ item.user_name || "未知" }} · {{ formatDate(item.operation_time) }}</small></span>
          </div>
        </div>
        <el-empty v-else description="暂无下载记录" :image-size="58" />
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue"
import type { ArchiveSummary } from "@/api/historyArchive"

const props = defineProps<{ summary: ArchiveSummary; loading: boolean }>()
const maxCount = computed(() => Math.max(1, ...props.summary.category_distribution.map(item => item.file_count)))
const yearText = computed(() => props.summary.covered_years.length ? props.summary.covered_years.join("、") : "暂无数据")
function formatSize(bytes: number) {
  if (!bytes) return "0 B"
  const units = ["B", "KB", "MB", "GB", "TB"]
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`
}
function formatDate(value?: string | null) { return value ? value.replace("T", " ").slice(0, 16) : "-" }
</script>

<style scoped>
.dashboard-wrap{display:flex;flex-direction:column;gap:14px}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric-grid article,.panel{border:1px solid #e5e9f0;border-radius:12px;background:#fff}.metric-grid article{padding:17px 19px}.metric-grid span,.metric-grid small{display:block;color:#667085;font-size:12px}.metric-grid strong{display:block;margin:5px 0 2px;color:#17243b;font-size:26px}.dashboard-grid{display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:12px}.panel{min-height:218px;padding:17px 19px}.panel header{display:flex;justify-content:space-between;margin-bottom:15px}.panel header small{color:#98a2b3}.bars,.activity-list{display:flex;flex-direction:column;gap:11px}.bar-row{display:grid;grid-template-columns:72px 1fr 28px;align-items:center;gap:8px;font-size:12px}.bar-row i{height:7px;overflow:hidden;border-radius:5px;background:#eef1f5}.bar-row em{display:block;height:100%;border-radius:5px;background:#316bd8}.activity-list>div{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid #f0f2f5}.activity-list span,.activity-list b,.activity-list small{display:block;min-width:0}.activity-list b{max-width:210px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.activity-list small,.activity-list em{margin-top:3px;color:#98a2b3;font-size:10px;font-style:normal}@media(max-width:1100px){.metric-grid{grid-template-columns:repeat(2,1fr)}.dashboard-grid{grid-template-columns:1fr}.panel{min-height:auto}}@media(max-width:640px){.metric-grid{grid-template-columns:1fr}}
</style>
