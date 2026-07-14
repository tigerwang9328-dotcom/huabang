<template>
  <div class="analysis-page command-light-page">
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
        <div class="toolbar">
          <div class="filters">
            <el-select v-model="warningFilters.warning_level" placeholder="等级" clearable style="width:110px" @change="fetchWarnings">
              <el-option label="紧急" value="critical" /><el-option label="风险" value="risk" /><el-option label="预警" value="warning" />
            </el-select>
            <el-select v-model="warningFilters.warning_type" placeholder="类型" clearable style="width:150px" @change="fetchWarnings">
              <el-option label="负库存" value="negative" /><el-option label="90天库龄" value="age_90" /><el-option label="180天库龄" value="age_180" />
              <el-option label="低可售天数" value="low_sellable_days" /><el-option label="高库存" value="overstock" />
            </el-select>
            <el-input v-model="warningFilters.store_code" placeholder="门店/仓库编码" clearable style="width:140px" @keyup.enter="fetchWarnings" />
            <el-select v-model="warningFilters.task_status" placeholder="任务状态" clearable style="width:120px" @change="fetchWarnings">
              <el-option label="未转任务" value="unconverted" /><el-option label="已转任务" value="converted" />
            </el-select>
            <el-button type="primary" @click="fetchWarnings">查询</el-button>
          </div>
          <span class="sync-info">预警日期：{{ warningDate || "-" }}</span>
        </div>
        <el-table :data="warningRows" v-loading="warningLoading" border stripe size="small">
          <el-table-column label="等级" width="82"><template #default="{ row }"><el-tag :type="warningTag(row.warning_level)" size="small">{{ warningLevel(row.warning_level) }}</el-tag></template></el-table-column>
          <el-table-column prop="store_code" label="仓店" width="90" />
          <el-table-column prop="store_name" label="仓店名称" min-width="145" show-overflow-tooltip />
          <el-table-column prop="product_code" label="款号" width="110" />
          <el-table-column prop="product_name" label="商品" min-width="150" show-overflow-tooltip />
          <el-table-column label="类型" width="105"><template #default="{ row }">{{ warningType(row.warning_type) }}</template></el-table-column>
          <el-table-column prop="current_quantity" label="库存" width="78" align="right" />
          <el-table-column label="金额" width="105" align="right"><template #default="{ row }">{{ formatMoney(row.current_cost_amount) }}</template></el-table-column>
          <el-table-column prop="age_days" label="库龄" width="76" align="right" />
          <el-table-column prop="sellable_days" label="可售天数" width="88" align="right" />
          <el-table-column prop="description" label="建议" min-width="230" show-overflow-tooltip />
          <el-table-column label="任务" width="112" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!row.is_converted_to_task" text type="primary" size="small" @click="createWarningTask(row)">转任务</el-button>
              <el-button v-else text type="success" size="small" @click="openTask(row.task_id)">查看任务</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pager"><el-pagination background layout="total, sizes, prev, pager, next" :total="warningTotal" v-model:current-page="warningPage" v-model:page-size="warningSize" :page-sizes="[20,50,100]" @current-change="fetchWarnings" @size-change="onWarningSize" /></div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";
import { inventoryApi } from "@/api/inventory";

const activeTab = ref("overview");
const router = useRouter();

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

const warningLoading = ref(false); const warningRows = ref<any[]>([]); const warningTotal = ref(0);
const warningPage = ref(1); const warningSize = ref(20); const warningDate = ref("");
const warningFilters = reactive({ warning_level: "", warning_type: "", store_code: "", task_status: "" });
async function fetchWarnings() {
  warningLoading.value = true;
  try {
    const params: any = { page: warningPage.value, page_size: warningSize.value };
    Object.entries(warningFilters).forEach(([k, v]) => { if (v) params[k] = v; });
    const { data } = await inventoryApi.listWarnings(params);
    warningRows.value = data?.data?.items || [];
    warningTotal.value = data?.data?.total || 0;
    warningDate.value = data?.data?.warning_date || "";
    summaryCards.value[6] = { label: "当前预警", value: String(warningTotal.value), isPending: false };
  } catch (_) { ElMessage.error("库存预警加载失败"); }
  finally { warningLoading.value = false; }
}
async function createWarningTask(row: any) {
  try {
    const { data } = await inventoryApi.createWarningTask(row.id);
    if (!data?.success) return ElMessage.error(data?.message || "任务草稿创建失败");
    ElMessage.success(data.message || "任务草稿已创建");
    await fetchWarnings();
  } catch (_) { ElMessage.error("任务草稿创建失败"); }
}
function openTask(taskId: number) { if (taskId) router.push(`/app/task/${taskId}`); }
function onWarningSize() { warningPage.value = 1; fetchWarnings(); }
function warningTag(level: string) { return ({ critical: "danger", risk: "warning", warning: "warning" } as any)[level] || "info"; }
function warningLevel(level: string) { return ({ critical: "紧急", risk: "风险", warning: "预警", info: "提示" } as any)[level] || level; }
function warningType(kind: string) { return ({ negative: "负库存", age_90: "90天库龄", age_180: "180天库龄", low_sellable_days: "低可售天数", overstock: "高库存" } as any)[kind] || kind; }

function fmtTs(t: any) { if (!t) return "-"; return String(t).replace("T", " ").slice(0, 19); }
function formatMoney(v: any) {
  const n = Number(v || 0);
  return `¥${n.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}

onMounted(() => {
  if (new URLSearchParams(window.location.search).get("tab") === "warning") activeTab.value = "warning";
  fetchOverview();
  loadWOpts(); fetchWarehouses();
  fetchBalance();
  fetchWarnings();
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
@media (max-width: 760px) {
  .inventory-page { gap: 12px; }
  .summary-row { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
  .summary-card { min-width: 0; padding: 12px 8px; }
  .s-num { font-size: clamp(16px, 5vw, 20px); overflow-wrap: anywhere; }
  .analysis-tabs { padding: 12px; }
  .toolbar { align-items: flex-start; }
  .filters { width: 100%; }
}
</style>
