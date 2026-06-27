<template>
  <div class="analysis-page">
    <div class="page-header">
      <h2 class="page-title">门店分析</h2>
      <span class="page-desc">门店经营排行、基础档案、异常监控</span>
    </div>

    <!-- 顶部指标 -->
    <div class="summary-row">
      <div class="summary-card" v-for="s in summaryCards" :key="s.label" :class="{ pending: s.isPending }">
        <div class="s-num" v-if="!s.isPending">{{ s.value }}</div>
        <el-tag v-else type="info" size="small">待接入</el-tag>
        <div class="s-label">{{ s.label }}</div>
      </div>
    </div>

    <!-- Tab 页 -->
    <el-tabs v-model="activeTab" class="analysis-tabs">
      <el-tab-pane label="门店经营排行" name="rank">
        <div class="empty-block">
          <el-icon size="28"><TrendCharts /></el-icon>
          <span>销售明细尚未接入，门店经营排行暂不可用。请先接入百胜销售数据。</span>
        </div>
      </el-tab-pane>

      <el-tab-pane label="门店基础档案" name="list">
        <!-- 工具栏 -->
        <div class="toolbar">
          <div class="filters">
            <el-input v-model="filters.keyword" placeholder="店铺代码/名称" clearable style="width:180px" @keyup.enter="search" />
            <el-select v-model="filters.region_name" placeholder="区域" clearable filterable style="width:130px">
              <el-option v-for="a in options.regions" :key="a" :label="a" :value="a" />
            </el-select>
            <el-select v-model="filters.store_type" placeholder="店铺性质" clearable style="width:120px">
              <el-option v-for="t in options.storeTypes" :key="t" :label="t" :value="t" />
            </el-select>
            <el-select v-model="filters.status" placeholder="状态" clearable style="width:100px">
              <el-option label="营业" value="营业" /><el-option label="停用" value="停用" />
            </el-select>
            <el-button type="primary" @click="search">搜索</el-button>
            <el-button @click="reset">重置</el-button>
          </div>
          <span class="sync-info" v-if="lastSync">最后同步：{{ lastSync }}</span>
        </div>
        <el-table :data="list" v-loading="loading" border stripe size="small">
          <el-table-column prop="store_code" label="店铺代码" width="100" fixed />
          <el-table-column prop="store_name" label="店铺名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="region_name" label="区域" width="100" />
          <el-table-column prop="store_type" label="店铺性质" width="90" />
          <el-table-column prop="business_type" label="线上/线下" width="90" />
          <el-table-column prop="province" label="省" width="70" />
          <el-table-column prop="city" label="市" width="80" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === '营业' ? 'success' : 'info'" size="small">{{ row.status || '-' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="source_system" label="来源系统" width="90" />
          <el-table-column label="同步时间" width="160">
            <template #default="{ row }">{{ fmtTs(row.synced_at) }}</template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination background layout="total, sizes, prev, pager, next, jumper"
            :total="total" :current-page="page" :page-size="pageSize"
            :page-sizes="[20, 50, 100]" @current-change="onPage" @size-change="onSize" />
        </div>
      </el-tab-pane>

      <el-tab-pane label="异常门店" name="anomaly">
        <div class="empty-block">
          <el-icon size="28"><Warning /></el-icon>
          <span>暂无真实销售/库存异常数据，异常门店监控待数据接入后启用。</span>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, reactive, computed } from "vue";
import { ElMessage } from "element-plus";
import { storeApi } from "@/api/store";
import { dashboardApi } from "@/api/dashboard";

const activeTab = ref("list");
const loading = ref(false);
const list = ref<any[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const lastSync = ref("");
const filters = reactive({ keyword: "", region_name: "", store_type: "", business_type: "", status: "" });
const options = reactive<{ regions: string[]; storeTypes: string[]; bizTypes: string[] }>({ regions: [], storeTypes: [], bizTypes: [] });

const summaryCards = ref([
  { label: "门店总数", value: "—", isPending: false },
  { label: "启用门店", value: "—", isPending: false },
  { label: "停用门店", value: "—", isPending: false },
  { label: "区域数", value: "—", isPending: false },
  { label: "今日销售额", value: "待接入", isPending: true },
  { label: "今日订单数", value: "待接入", isPending: true },
  { label: "今日件数", value: "待接入", isPending: true },
]);

function fmtTs(t: any) { if (!t) return "-"; return String(t).replace("T", " ").slice(0, 19); }

async function fetchOverview() {
  try {
    const { data } = await dashboardApi.getOverview();
    const assets = data?.data?.data_assets || {};
    if (assets.store_count?.value) summaryCards.value[0].value = String(assets.store_count.value);
    // 从门店列表中统计启用/停用
  } catch (_) {}
}

async function fetchList() {
  loading.value = true;
  try {
    const params: any = { page: page.value, page_size: pageSize.value };
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    const { data } = await storeApi.listStores(params);
    if (data?.success) {
      list.value = data.data.items || [];
      total.value = data.data.total || 0;
      const times = list.value.map((x: any) => x.synced_at).filter(Boolean).sort();
      if (times.length) lastSync.value = fmtTs(times[times.length - 1]);
      // 统计启用/停用
      const active = list.value.filter((x: any) => x.status === "营业").length;
      summaryCards.value[1].value = String(active);
      summaryCards.value[2].value = String(total.value - active);
    }
  } catch (e: any) { ElMessage.error("查询失败"); }
  finally { loading.value = false; }
}

async function loadOptions() {
  try {
    const { data } = await storeApi.listStores({ page: 1, page_size: 200 });
    const items = data?.data?.items || [];
    options.regions = [...new Set(items.map((x: any) => x.region_name).filter(Boolean))] as string[];
    options.storeTypes = [...new Set(items.map((x: any) => x.store_type).filter(Boolean))] as string[];
    options.bizTypes = [...new Set(items.map((x: any) => x.business_type).filter(Boolean))] as string[];
    const regions = [...new Set(items.map((x: any) => x.region_name).filter(Boolean))];
    summaryCards.value[3].value = String(regions.length);
  } catch (_) {}
}

function search() { page.value = 1; fetchList(); }
function reset() { filters.keyword = ""; filters.region_name = ""; filters.store_type = ""; filters.business_type = ""; filters.status = ""; page.value = 1; fetchList(); }
function onPage(p: number) { page.value = p; fetchList(); }
function onSize(s: number) { pageSize.value = s; page.value = 1; fetchList(); }

onMounted(() => { fetchOverview(); loadOptions(); fetchList(); });
</script>

<style scoped>
.analysis-page { display: flex; flex-direction: column; gap: 14px; }
.page-header { display: flex; align-items: baseline; gap: 10px; }
.page-title { font-size: 20px; font-weight: 700; color: #111827; margin: 0; }
.page-desc { font-size: 12px; color: #9CA3AF; }
.summary-row { display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; }
.summary-card {
  background: #FFFFFF; border-radius: 10px; padding: 14px; text-align: center;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05); border-top: 3px solid #1E5EFF;
}
.summary-card.pending { opacity: 0.6; border-top-color: #D1D5DB; }
.s-num { font-size: 22px; font-weight: 700; color: #111827; }
.s-label { font-size: 11px; color: #9CA3AF; margin-top: 4px; }
.analysis-tabs { background: #FFFFFF; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.sync-info { color: #909399; font-size: 12px; }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
.empty-block { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 48px 0; color: #D1D5DB; font-size: 13px; }
@media (max-width: 1200px) { .summary-row { grid-template-columns: repeat(4, 1fr); } }
</style>
