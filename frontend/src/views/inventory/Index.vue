<template>
  <div class="analysis-page">
    <div class="page-header">
      <h2 class="page-title">库存预警</h2>
      <span class="page-desc">库存总览、库存余额、仓库档案、预警监控</span>
    </div>

    <!-- 顶部指标 -->
    <div class="summary-row">
      <div class="summary-card" v-for="s in summaryCards" :key="s.label" :class="{ pending: s.isPending }">
        <div class="s-num" v-if="!s.isPending">{{ s.value }}</div>
        <el-tag v-else type="info" size="small">待接入</el-tag>
        <div class="s-label">{{ s.label }}</div>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="analysis-tabs">
      <!-- Tab 1: 库存总览 -->
      <el-tab-pane label="库存总览" name="overview">
        <el-table :data="whSummary" border stripe size="small" v-loading="ovLoading">
          <el-table-column prop="warehouse_code" label="仓库编码" width="110" />
          <el-table-column prop="warehouse_name" label="仓库名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="total_qty" label="库存总件数" width="120" align="right" />
          <el-table-column prop="sku_count" label="SKU数" width="100" align="right" />
          <el-table-column label="库存金额" width="120" align="right">
            <template #default="{ row }">{{ formatMoney(row.inventory_amount) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab 2: 库存余额 -->
      <el-tab-pane label="库存余额" name="balance">
        <div class="toolbar">
          <div class="filters">
            <el-input v-model="bf.keyword" placeholder="货号/SKU/条码" clearable style="width:170px" @keyup.enter="fetchBalance" />
            <el-input v-model="bf.warehouse_code" placeholder="仓库编码" clearable style="width:110px" @keyup.enter="fetchBalance" />
            <el-checkbox v-model="bf.onlyPositive" @change="fetchBalance" style="margin:0 4px">仅有货</el-checkbox>
            <el-button type="primary" @click="fetchBalance">搜索</el-button>
            <el-button @click="resetBalance">重置</el-button>
          </div>
          <span class="sync-info" v-if="bLastSync">最后同步：{{ bLastSync }}</span>
        </div>
        <el-table :data="balanceList" v-loading="bLoading" border stripe size="small">
          <el-table-column prop="warehouse_code" label="仓库" width="90" fixed />
          <el-table-column prop="warehouse_name" label="仓库名称" min-width="120" show-overflow-tooltip />
          <el-table-column prop="product_code" label="货号" width="100" />
          <el-table-column prop="sku_code" label="SKU" width="120" show-overflow-tooltip />
          <el-table-column prop="barcode" label="条码" width="110" />
          <el-table-column prop="goods_name" label="商品名称" min-width="120" show-overflow-tooltip />
          <el-table-column prop="color_name" label="颜色" width="80" />
          <el-table-column prop="size_name" label="尺码" width="60" />
          <el-table-column prop="qty" label="库存数量" width="90" align="right" />
          <el-table-column prop="lock_qty" label="占用" width="70" align="right" />
          <el-table-column prop="road_qty" label="在途" width="70" align="right" />
          <el-table-column prop="available_qty" label="可用" width="80" align="right">
            <template #default="{ row }"><span :class="{ neg: row.available_qty < 0 }">{{ row.available_qty }}</span></template>
          </el-table-column>
          <el-table-column label="库存金额" width="100" align="right">
            <template #default="{ row }">{{ row.inventory_amount == null ? "-" : formatMoney(row.inventory_amount) }}</template>
          </el-table-column>
          <el-table-column label="同步时间" width="150">
            <template #default="{ row }">{{ fmtTs(row.synced_at) }}</template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination background layout="total, sizes, prev, pager, next, jumper"
            :total="bTotal" :current-page="bPage" :page-size="bSize"
            :page-sizes="[20, 50, 100]" @current-change="onBPage" @size-change="onBSize" />
        </div>
      </el-tab-pane>

      <!-- Tab 3: 仓库档案 -->
      <el-tab-pane label="仓库档案" name="warehouses">
        <div class="toolbar">
          <div class="filters">
            <el-input v-model="wf.keyword" placeholder="仓库编码/名称" clearable style="width:170px" @keyup.enter="fetchWarehouses" />
            <el-select v-model="wf.region_name" placeholder="区域" clearable filterable style="width:120px">
              <el-option v-for="r in wOpts.regions" :key="r" :label="r" :value="r" />
            </el-select>
            <el-select v-model="wf.status" placeholder="状态" clearable style="width:100px">
              <el-option label="启用" value="active" /><el-option label="停用" value="disabled" />
            </el-select>
            <el-button type="primary" @click="fetchWarehouses">搜索</el-button>
            <el-button @click="resetWarehouses">重置</el-button>
          </div>
          <span class="sync-info" v-if="wLastSync">最后同步：{{ wLastSync }}</span>
        </div>
        <el-table :data="whList" v-loading="wLoading" border stripe size="small">
          <el-table-column prop="warehouse_code" label="仓库编码" width="110" fixed />
          <el-table-column prop="warehouse_name" label="仓库名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="warehouse_nature" label="仓库性质" width="80" />
          <el-table-column prop="warehouse_category_name" label="仓库类别" width="90" />
          <el-table-column prop="region_name" label="所属区域" width="100" />
          <el-table-column prop="default_location_name" label="默认库位" width="100" />
          <el-table-column label="状态" width="70">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : (row.status === 'disabled' ? 'info' : 'warning')" size="small">
                {{ row.status === 'active' ? '启用' : (row.status === 'disabled' ? '停用' : '未知') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="同步时间" width="150">
            <template #default="{ row }">{{ fmtTs(row.synced_at) }}</template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination background layout="total, sizes, prev, pager, next, jumper"
            :total="wTotal" v-model:current-page="wPage" v-model:page-size="wSize"
            :page-sizes="[20, 50, 100]" @current-change="onWPage" @size-change="onWSize" />
        </div>
      </el-tab-pane>

      <!-- Tab 4: 库存预警 -->
      <el-tab-pane label="库存预警" name="warning">
        <div class="empty-block">
          <el-icon size="28"><Warning /></el-icon>
          <span>库存预警规则待配置。低库存阈值、高库存阈值、库龄预警等规则配置后启用自动监控。</span>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import { inventoryApi } from "@/api/inventory";

const activeTab = ref("overview");

const summaryCards = ref([
  { label: "仓库数量", value: "—", isPending: false },
  { label: "启用仓库", value: "—", isPending: false },
  { label: "库存记录数", value: "—", isPending: false },
  { label: "库存总件数", value: "—", isPending: false },
  { label: "库存金额", value: "—", isPending: false },
  { label: "缺货SKU", value: "—", isPending: false },
  { label: "高库存SKU", value: "待配置", isPending: true },
]);

// Tab 1: 库存总览
const ovLoading = ref(false); const whSummary = ref<any[]>([]);
async function fetchOverview() {
  ovLoading.value = true;
  try {
    const [{ data: summaryRes }, { data: overviewRes }] = await Promise.all([
      inventoryApi.getSummary(),
      inventoryApi.getOverview(),
    ]);
    const summary = summaryRes?.data?.summary || {};
    summaryCards.value[0].value = summary.warehouse_count?.display || "0";
    summaryCards.value[1].value = summary.enabled_warehouses?.display || "0";
    summaryCards.value[2].value = summary.inventory_records?.display || "0";
    summaryCards.value[3].value = summary.total_inventory_qty?.display || "0";
    summaryCards.value[4].value = formatMoney(summary.inventory_amount?.value || 0);
    summaryCards.value[5].value = summary.out_of_stock_sku_count?.display || "0";
    whSummary.value = overviewRes?.data?.by_warehouse || [];
  } catch (_) { ElMessage.error("库存总览查询失败"); }
  finally { ovLoading.value = false; }
}

// Tab 2: 库存余额
const bLoading = ref(false); const balanceList = ref<any[]>([]);
const bTotal = ref(0); const bPage = ref(1); const bSize = ref(20); const bLastSync = ref("");
const bf = reactive({ keyword: "", warehouse_code: "", product_code: "", onlyPositive: true });
async function fetchBalance() {
  bLoading.value = true;
  try {
    const params: any = { page: bPage.value, page_size: bSize.value };
    if (bf.keyword) params.keyword = bf.keyword;
    if (bf.warehouse_code) params.warehouse_code = bf.warehouse_code;
    if (bf.product_code) params.product_code = bf.product_code;
    if (bf.onlyPositive) params.only_positive = 1;
    const { data } = await inventoryApi.listInventory(params);
    if (data?.success) {
      balanceList.value = data.data.items || [];
      bTotal.value = data.data.total || 0;
      const times = balanceList.value.map((x: any) => x.synced_at).filter(Boolean).sort();
      if (times.length) bLastSync.value = fmtTs(times[times.length - 1]);
    }
  } catch (e: any) { ElMessage.error("查询失败"); }
  finally { bLoading.value = false; }
}
function resetBalance() { bf.keyword = ""; bf.warehouse_code = ""; bf.product_code = ""; bf.onlyPositive = true; bPage.value = 1; fetchBalance(); }
function onBPage(p: number) { bPage.value = p; fetchBalance(); }
function onBSize(s: number) { bSize.value = s; bPage.value = 1; fetchBalance(); }

// Tab 3: 仓库档案
const wLoading = ref(false); const whList = ref<any[]>([]);
const wTotal = ref(0); const wPage = ref(1); const wSize = ref(20); const wLastSync = ref("");
const wf = reactive({ keyword: "", warehouse_nature: "", warehouse_category_name: "", region_name: "", status: "" });
const wOpts = reactive<{ regions: string[]; natures: string[]; categories: string[] }>({ regions: [], natures: [], categories: [] });
async function fetchWarehouses() {
  wLoading.value = true;
  try {
    const params: any = { page: wPage.value, page_size: wSize.value };
    Object.entries(wf).forEach(([k, v]) => { if (v) params[k] = v; });
    const { data } = await inventoryApi.listWarehouses(params);
    if (data?.success) {
      whList.value = data.data.items || [];
      wTotal.value = data.data.total || 0;
      const times = whList.value.map((x: any) => x.synced_at).filter(Boolean).sort();
      if (times.length) wLastSync.value = fmtTs(times[times.length - 1]);
      summaryCards.value[0].value = String(wTotal.value);
      const enabled = whList.value.filter((x: any) => x.is_enabled).length;
      summaryCards.value[1].value = String(enabled);
    }
  } catch (e: any) { ElMessage.error("查询失败"); }
  finally { wLoading.value = false; }
}
async function loadWOpts() {
  try {
    const { data } = await inventoryApi.listWarehouses({ page: 1, page_size: 200 });
    const items = data?.data?.items || [];
    wOpts.regions = [...new Set(items.map((x: any) => x.region_name).filter(Boolean))] as string[];
    wOpts.natures = [...new Set(items.map((x: any) => x.warehouse_nature).filter(Boolean))] as string[];
    wOpts.categories = [...new Set(items.map((x: any) => x.warehouse_category_name).filter(Boolean))] as string[];
  } catch (_) {}
}
function resetWarehouses() { Object.keys(wf).forEach(k => (wf as any)[k] = ""); wPage.value = 1; fetchWarehouses(); }
function onWPage(p: number) { wPage.value = p; fetchWarehouses(); }
function onWSize(s: number) { wSize.value = s; wPage.value = 1; fetchWarehouses(); }

function fmtTs(t: any) { if (!t) return "-"; return String(t).replace("T", " ").slice(0, 19); }
function formatMoney(v: any) {
  const n = Number(v || 0);
  return `¥${n.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}

onMounted(() => {
  fetchOverview();
  loadWOpts(); fetchWarehouses();
  fetchBalance();
});
</script>

<style scoped>
.analysis-page { display: flex; flex-direction: column; gap: 14px; }
.page-header { display: flex; align-items: baseline; gap: 10px; }
.page-title { font-size: 20px; font-weight: 700; color: #111827; margin: 0; }
.page-desc { font-size: 12px; color: #9CA3AF; }
.summary-row { display: grid; grid-template-columns: repeat(7, 1fr); gap: 10px; }
.summary-card {
  background: #FFFFFF; border-radius: 10px; padding: 14px; text-align: center;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05); border-top: 3px solid #F59E0B;
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
.neg { color: #f56c6c; }
@media (max-width: 1200px) { .summary-row { grid-template-columns: repeat(4, 1fr); } }
</style>
