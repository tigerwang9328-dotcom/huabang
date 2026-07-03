<template>
  <div class="sku-archive">
    <div class="page-header">
      <h2>SKU档案</h2>
      <p class="page-desc">华邦标准 SKU 维（dim_sku），当前数据来源：百胜 E3ERP，已接入条码/成本质量、库存与近7天销售。</p>
    </div>

    <div class="quality-grid" v-loading="qualityLoading">
      <div class="quality-card">
        <span>SKU总数</span>
        <strong>{{ formatNumber(quality.sku_count) }}</strong>
      </div>
      <div class="quality-card warning">
        <span>SKU缺成本</span>
        <strong>{{ formatNumber(quality.sku_missing_cost_count) }}</strong>
      </div>
      <div class="quality-card warning">
        <span>SKU缺条码</span>
        <strong>{{ formatNumber(quality.sku_missing_barcode_count) }}</strong>
      </div>
      <div class="quality-card">
        <span>条码覆盖率</span>
        <strong>{{ Number(quality.sku_barcode_rate || 0).toFixed(1) }}%</strong>
      </div>
      <div class="quality-card">
        <span>有库存SKU</span>
        <strong>{{ formatNumber(quality.inv_sku_count) }}</strong>
      </div>
      <div class="quality-card">
        <span>近7天动销SKU</span>
        <strong>{{ formatNumber(quality.sale_sku_count) }}</strong>
      </div>
    </div>

    <div class="toolbar">
      <div class="filters">
        <el-input v-model="filters.keyword" placeholder="SKU/条码/款号/商品名" clearable style="width:200px" @keyup.enter="handleSearch" />
        <el-input v-model="filters.product_code" placeholder="款号精确" clearable style="width:130px" @keyup.enter="handleSearch" />
        <el-select v-model="filters.brand_name" placeholder="品牌" clearable filterable style="width:110px">
          <el-option v-for="b in options.brands" :key="b" :label="b" :value="b" />
        </el-select>
        <el-select v-model="filters.color_name" placeholder="颜色" clearable filterable style="width:110px">
          <el-option v-for="c in options.colors" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="filters.size_name" placeholder="尺码" clearable filterable style="width:100px">
          <el-option v-for="z in options.sizes" :key="z" :label="z" :value="z" />
        </el-select>
        <el-select v-model="filters.season_name" placeholder="季节" clearable style="width:100px">
          <el-option v-for="s in options.seasons" :key="s" :label="s" :value="s" />
        </el-select>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>
      <div class="actions">
        <span class="last-sync" v-if="lastSyncedAt">最后同步：{{ formatTime(lastSyncedAt) }}</span>
        <el-button type="success" :loading="syncing" @click="handleSync">
          <el-icon style="margin-right:4px"><Refresh /></el-icon>同步SKU档案
        </el-button>
      </div>
    </div>

    <el-table :data="list" v-loading="loading" border stripe size="small" style="width:100%">
      <el-table-column prop="sku_code" label="SKU编码" width="150" fixed show-overflow-tooltip />
      <el-table-column prop="product_code" label="款号" width="110" />
      <el-table-column prop="product_name" label="商品名称" min-width="140" show-overflow-tooltip />
      <el-table-column prop="barcode" label="条码" width="120" show-overflow-tooltip />
      <el-table-column prop="color_name" label="颜色" width="100" />
      <el-table-column prop="size_name" label="尺码" width="80" />
      <el-table-column prop="brand_name" label="品牌" width="80" />
      <el-table-column prop="season_name" label="季节" width="70" />
      <el-table-column prop="tag_price" label="吊牌价" width="90" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ row.status === 'active' ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="成本" width="80">
        <template #default="{ row }">
          <el-tag :type="row.has_cost ? 'success' : 'warning'" size="small">{{ row.has_cost ? "已维护" : "缺成本" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="inventory_qty" label="当前库存" width="90" align="right" />
      <el-table-column prop="sales_qty" label="近7天销量" width="95" align="right" />
      <el-table-column label="销售额" width="95" align="right">
        <template #default="{ row }">{{ formatAmount(row.sales_amount) }}</template>
      </el-table-column>
      <el-table-column label="AI建议" width="95">
        <template #default="{ row }">
          <el-tag :type="suggestionType(row.ai_suggestion)" size="small">{{ row.ai_suggestion || "-" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="source_system" label="来源系统" width="90" />
      <el-table-column label="同步时间" width="160"><template #default="{ row }">{{ formatTime(row.synced_at) }}</template></el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination background layout="total, sizes, prev, pager, next, jumper"
        :total="total" :current-page="page" :page-size="page_size" :page-sizes="[20, 50, 100]"
        @current-change="handlePageChange" @size-change="handleSizeChange" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import { productApi } from "@/api/product";

const loading = ref(false);
const qualityLoading = ref(false);
const syncing = ref(false);
const list = ref<any[]>([]);
const total = ref(0);
const page = ref(1);
const page_size = ref(20);
const lastSyncedAt = ref<string | null>(null);
const quality = ref<any>({});
const filters = reactive<any>({ keyword: "", product_code: "", brand_name: "", color_name: "", size_name: "", season_name: "", status: "" });
const options = reactive<{ brands: string[]; colors: string[]; sizes: string[]; seasons: string[] }>({ brands: [], colors: [], sizes: [], seasons: [] });

function formatTime(t: string | null) {
  if (!t) return "-";
  return String(t).replace("T", " ").slice(0, 19);
}

function formatNumber(v: any) {
  return Number(v || 0).toLocaleString("zh-CN");
}

function formatAmount(v: any) {
  return Number(v || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function suggestionType(text: string) {
  if (text === "正常") return "success";
  if (text === "补条码" || text === "补成本" || text === "关注补货") return "warning";
  return "info";
}

async function fetchQuality() {
  qualityLoading.value = true;
  try {
    const { data } = await productApi.getQualitySummary();
    if (data && data.success) quality.value = data.data || {};
  } catch (_) {
    /* 概览失败不阻塞列表 */
  } finally {
    qualityLoading.value = false;
  }
}

async function fetchList() {
  loading.value = true;
  try {
    const params: any = { page: page.value, page_size: page_size.value };
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    const { data } = await productApi.listSkus(params);
    if (data && data.success) {
      list.value = data.data.items || [];
      total.value = data.data.total || 0;
      const times = list.value.map((x) => x.synced_at).filter(Boolean).sort();
      if (times.length) lastSyncedAt.value = times[times.length - 1];
    } else {
      ElMessage.error((data && data.message) || "查询失败");
    }
  } catch (e: any) {
    ElMessage.error((e && e.message) || "查询失败");
  } finally {
    loading.value = false;
  }
}

async function loadOptions() {
  try {
    const { data } = await productApi.listSkus({ page: 1, page_size: 200 });
    const items = (data && data.data && data.data.items) || [];
    options.brands = [...new Set(items.map((x: any) => x.brand_name).filter(Boolean))] as string[];
    options.colors = [...new Set(items.map((x: any) => x.color_name).filter(Boolean))] as string[];
    options.sizes = [...new Set(items.map((x: any) => x.size_name).filter(Boolean))] as string[];
    options.seasons = [...new Set(items.map((x: any) => x.season_name).filter(Boolean))] as string[];
  } catch (_) { /* 忽略 */ }
}

function handleSearch() { page.value = 1; fetchList(); }
function handleReset() {
  Object.keys(filters).forEach((k) => (filters[k] = ""));
  page.value = 1; fetchList();
}
function handlePageChange(p: number) { page.value = p; fetchList(); }
function handleSizeChange(s: number) { page_size.value = s; page.value = 1; fetchList(); }

async function handleSync() {
  syncing.value = true;
  try {
    const { data } = await productApi.syncSkus({ full_sync: true, page_size: 20 });
    if (data && data.success) {
      ElMessage.success(data.message || "SKU 同步已在后台启动，稍后刷新查看");
      setTimeout(() => { fetchQuality(); fetchList(); }, 1500);
    } else {
      ElMessage.error((data && data.message) || "同步失败");
    }
  } catch (e: any) {
    ElMessage.error((e && e.message) || "同步失败");
  } finally {
    syncing.value = false;
  }
}

onMounted(() => { fetchQuality(); loadOptions(); fetchList(); });
</script>

<style scoped>
.sku-archive { padding: 16px; }
.page-header { margin-bottom: 12px; }
.page-header h2 { font-size: 18px; color: #333; margin-bottom: 4px; }
.page-desc { color: #999; font-size: 13px; }
.quality-grid { display:grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap:12px; margin-bottom:12px; }
.quality-card { background:#fff; border:1px solid #ebeef5; border-radius:6px; padding:12px 14px; min-height:70px; display:flex; flex-direction:column; justify-content:center; box-shadow:0 1px 2px rgba(0,0,0,.03); }
.quality-card span { color:#909399; font-size:12px; margin-bottom:8px; }
.quality-card strong { color:#172033; font-size:22px; line-height:1; }
.quality-card.warning strong { color:#d97706; }
.toolbar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:12px; }
.filters { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.actions { display:flex; align-items:center; gap:12px; }
.last-sync { color:#909399; font-size:13px; }
.pager { margin-top:12px; display:flex; justify-content:flex-end; }
@media (max-width: 1200px) {
  .quality-grid { grid-template-columns: repeat(3, minmax(120px, 1fr)); }
}
@media (max-width: 760px) {
  .quality-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
}
</style>
