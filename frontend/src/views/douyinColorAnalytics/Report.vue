<template>
  <section class="report-page" v-loading="loading">
    <div class="page-head">
      <div>
        <el-button text @click="router.push({ name: 'DouyinColorVideoList' })">← 返回视频</el-button>
        <p class="eyebrow">COLOR RETENTION REPORT</p>
        <h1>颜色留存报告</h1>
        <p>按穿搭层级聚合的颜色留存排名，基于已审核片段的观察窗口曲线计算。</p>
      </div>
      <div class="head-actions">
        <el-select v-model="filters.observation_window" placeholder="观察窗口" style="width: 150px" @change="loadActiveTab">
          <el-option label="T+2（前天发布）" value="t2" />
          <el-option label="T+7（7天前发布）" value="t7" />
          <el-option label="T+30（30天前发布）" value="t30" />
          <el-option label="临时采集" value="ad_hoc" />
        </el-select>
        <el-select v-model="filters.position_segment" placeholder="位置段" style="width: 150px" @change="loadActiveTab">
          <el-option label="全部位置" value="all" />
          <el-option label="前段" value="front" />
          <el-option label="中段" value="middle" />
          <el-option label="后段" value="rear" />
        </el-select>
        <el-button :loading="loading" @click="loadActiveTab">刷新</el-button>
        <el-dropdown split-button type="primary" @click="handleExport('xlsx')" @command="handleExport">
          导出报告
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="xlsx">导出 XLSX</el-dropdown-item>
              <el-dropdown-item command="csv">导出 CSV</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <el-alert
      title="免责声明：历史关联，不是因果"
      description="本报告展示的是历史关联关系，不是因果关系。颜色留存差异可能受拍摄、选品、受众、时段等多重因素影响，请结合业务语境审慎解读。"
      type="warning"
      show-icon
      :closable="false"
      class="banner"
    />

    <el-alert v-if="loadError" :title="loadError" type="error" show-icon :closable="false" class="banner" />

    <el-alert
      title="样本门槛说明"
      description="样本数 < 3 的组合不显示平均排名；样本数 < 5 的组合不显示稳定性排名。请结合样本量审慎解读小样本组合。"
      type="info"
      show-icon
      :closable="false"
      class="banner"
    />

    <el-card v-if="context" class="section-card" shadow="never">
      <template #header><h2>当前账号</h2></template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="管理员名称">{{ context.account.display_name }}</el-descriptions-item>
        <el-descriptions-item label="抖音昵称">
          <span v-if="context.account.observed_account_name">{{ context.account.observed_account_name }}</span>
          <span v-else class="muted">暂无（采集器未上报）</span>
        </el-descriptions-item>
        <el-descriptions-item label="账号标识">
          <code>{{ context.account.account_key }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="最近心跳">{{ formatTime(context.account.last_heartbeat_at) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="整套穿搭" name="outfit" />
      <el-tab-pane label="上衣（outer+top）" name="top" />
      <el-tab-pane label="裤子（bottom）" name="bottom" />
    </el-tabs>

    <el-table :data="currentRows" stripe empty-text="当前筛选条件下暂无排名数据">
      <el-table-column type="index" label="#" width="60" />
      <el-table-column prop="combination_key" label="组合键" min-width="200" show-overflow-tooltip />
      <el-table-column label="平均留存" width="130">
        <template #default="{ row }">
          <span v-if="row.avg_retention != null">{{ formatPercent(row.avg_retention) }}</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="平均排名" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.sample_count >= 3 && row.avg_rank != null" type="info" effect="plain">{{ row.avg_rank }}</el-tag>
          <span v-else class="muted" title="样本数 <3 不显示">—</span>
        </template>
      </el-table-column>
      <el-table-column label="稳定性排名" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.sample_count >= 5 && row.stability_rank != null" type="warning" effect="plain">{{ row.stability_rank }}</el-tag>
          <span v-else class="muted" title="样本数 <5 不显示">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="sample_count" label="样本数" width="90" sortable />
      <el-table-column prop="position_segment" label="位置段" width="100">
        <template #default="{ row }"><el-tag effect="plain">{{ row.position_segment }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="observation_window" label="观察窗口" width="120" />
      <el-table-column label="参考颜色" width="160">
        <template #default="{ row }">
          <span v-if="row.sku_color_code || row.sku_color_name" class="color-ref">
            <span class="color-chip" :style="{ background: colorToCss(row.sku_color_code, row.sku_color_name) }" />
            <span>{{ row.sku_color_name || row.sku_color_code }}</span>
          </span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";
import {
  douyinColorAnalyticsApi,
  douyinColorReportApi,
  type DouyinAnnotationContext,
  type DouyinColorRankingRow,
  type DouyinColorReportTab,
  type DouyinColorExportFormat,
} from "@/api/douyinColorAnalytics";

const router = useRouter();
const loading = ref(false);
const loadError = ref("");
const context = ref<DouyinAnnotationContext | null>(null);
const activeTab = ref<DouyinColorReportTab>("outfit");
const filters = ref({ observation_window: "t2", position_segment: "all" });

const outfitRows = ref<DouyinColorRankingRow[]>([]);
const topRows = ref<DouyinColorRankingRow[]>([]);
const bottomRows = ref<DouyinColorRankingRow[]>([]);

const tabLoaded = ref<Record<DouyinColorReportTab, boolean>>({ outfit: false, top: false, bottom: false });

const currentRows = computed(() => {
  if (activeTab.value === "outfit") return outfitRows.value;
  if (activeTab.value === "top") return topRows.value;
  return bottomRows.value;
});

const formatPercent = (value: number) => {
  const pct = value <= 1 ? value * 100 : value;
  return `${pct.toFixed(1)}%`;
};

const formatTime = (value: string | null | undefined) => {
  if (!value) return "—";
  try { return new Date(value).toLocaleString("zh-CN", { hour12: false }); }
  catch { return value; }
};

const colorToCss = (code: string | null, name: string | null): string => {
  const keyword = `${code || ""} ${name || ""}`.toLowerCase();
  const map: Array<[string, string]> = [
    ["black", "#1a1a1a"], ["white", "#f0f0f0"], ["red", "#e74c3c"],
    ["blue", "#3498db"], ["green", "#27ae60"], ["yellow", "#f1c40f"],
    ["pink", "#fd79a8"], ["gray", "#95a5a6"], ["grey", "#95a5a6"],
    ["brown", "#8b6914"], ["orange", "#e67e22"], ["purple", "#9b59b6"],
    ["navy", "#2c3e50"], ["beige", "#e8d8c4"], ["khaki", "#c3b091"],
    ["cream", "#f5e6d3"], ["burgundy", "#7c1f2c"], ["olive", "#708238"],
  ];
  for (const [name, css] of map) {
    if (keyword.includes(name)) return css;
  }
  if (code && /^#[0-9a-f]{6}$/i.test(code)) return code;
  return "#cccccc";
};

function describeError(error: unknown) {
  const response = (error as { response?: { data?: { detail?: string; message?: string } } })?.response?.data;
  return response?.detail || response?.message || (error instanceof Error ? error.message : "请求失败");
}

async function loadContext() {
  if (context.value) return;
  context.value = (await douyinColorAnalyticsApi.getAnnotationContext()).data;
}

async function loadTab(tab: DouyinColorReportTab) {
  if (!context.value) return;
  const accountId = context.value.account.id;
  const params = { observation_window: filters.value.observation_window, position_segment: filters.value.position_segment };
  if (tab === "outfit") {
    outfitRows.value = (await douyinColorReportApi.getOutfitRankings(accountId, params)).data.items || [];
  } else if (tab === "top") {
    topRows.value = (await douyinColorReportApi.getTopRankings(accountId, params)).data.items || [];
  } else {
    bottomRows.value = (await douyinColorReportApi.getBottomRankings(accountId, params)).data.items || [];
  }
  tabLoaded.value[tab] = true;
}

async function loadActiveTab() {
  loading.value = true;
  loadError.value = "";
  try {
    await loadContext();
    await loadTab(activeTab.value);
  } catch (error) {
    loadError.value = describeError(error);
  } finally {
    loading.value = false;
  }
}

async function onTabChange(name: string | number) {
  const tab = String(name) as DouyinColorReportTab;
  activeTab.value = tab;
  if (!tabLoaded.value[tab]) {
    await loadActiveTab();
  }
}

async function handleExport(format: string | number | object) {
  const fmt = String(format) as DouyinColorExportFormat;
  if (!context.value) {
    ElMessage.warning("账号上下文未加载");
    return;
  }
  loading.value = true;
  try {
    const res = await douyinColorReportApi.exportReport(context.value.account.id, { format: fmt, tab: activeTab.value });
    const url = res.data.download_url;
    if (url) {
      window.open(url, "_blank");
      ElMessage.success(`已触发 ${fmt.toUpperCase()} 导出，当前 Tab：${activeTab.value}`);
    } else {
      ElMessage.success(`导出请求已提交（${fmt.toUpperCase()} / ${activeTab.value}），服务端生成中`);
    }
  } catch (error) {
    ElMessage.error(describeError(error));
  } finally {
    loading.value = false;
  }
}

onMounted(loadActiveTab);
</script>

<style scoped>
.report-page { padding: 24px; }
.page-head { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 16px; }
.page-head h1 { margin: 5px 0; color: #172033; }
.page-head p { margin: 0; color: #667085; }
.eyebrow { font-size: 11px; font-weight: 800; letter-spacing: .09em; color: #5266a6 !important; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.banner { margin-bottom: 12px; }
.muted { color: #c0c4cc; }
.color-ref { display: inline-flex; align-items: center; gap: 6px; }
.color-chip { display: inline-block; width: 14px; height: 14px; border-radius: 3px; border: 1px solid #dcdfe6; vertical-align: middle; }
@media(max-width: 640px) { .report-page { padding: 16px; } .page-head { flex-direction: column; } }
</style>
