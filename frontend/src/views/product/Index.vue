<template>
  <div class="analysis-page command-light-page">
    <div class="page-header">
      <h2 class="page-title">商品分析</h2>
      <span class="page-desc">动销分析、商品主档、SKU档案、条码质量</span>
    </div>

    <div class="summary-row">
      <div class="summary-card" v-for="s in summaryCards" :key="s.label" :class="{ warning: s.warning }">
        <div class="s-num">{{ s.value }}</div>
        <div class="s-label">{{ s.label }}</div>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="analysis-tabs">
      <!-- Tab 1: 商品经营分析 -->
      <el-tab-pane label="商品经营分析" name="biz">
        <div class="empty-block">
          <el-icon size="28"><TrendCharts /></el-icon>
          <span>商品主档与 SKU 档案已接入库存、近7天销售和质量建议，后续可继续扩展爆款/滞销专题分析。</span>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 商品主档 -->
      <el-tab-pane label="商品主档" name="products">
        <div class="toolbar">
          <div class="filters">
            <el-input v-model="pf.keyword" placeholder="款号/商品名称" clearable style="width:170px" @keyup.enter="fetchProducts" />
            <el-select v-model="pf.brand_name" placeholder="品牌" clearable filterable style="width:110px">
              <el-option v-for="b in pOpts.brands" :key="b" :label="b" :value="b" />
            </el-select>
            <el-select v-model="pf.category_name" placeholder="品类" clearable filterable style="width:120px">
              <el-option v-for="c in pOpts.categories" :key="c" :label="c" :value="c" />
            </el-select>
            <el-select v-model="pf.status" placeholder="状态" clearable style="width:90px">
              <el-option label="启用" value="active" /><el-option label="停用" value="disabled" />
            </el-select>
            <el-checkbox v-model="pf.onlyPositive" @change="handleProductFilterChange">隐藏0库存</el-checkbox>
            <el-button type="primary" @click="fetchProducts">搜索</el-button>
            <el-button @click="resetProducts">重置</el-button>
          </div>
          <span class="sync-info" v-if="pLastSync">最后同步：{{ pLastSync }}</span>
        </div>
        <el-table :data="productList" v-loading="pLoading" border stripe size="small" @sort-change="handleProductSortChange">
          <el-table-column prop="product_code" label="款号" width="110" fixed />
          <el-table-column prop="product_name" label="商品名称" min-width="150" show-overflow-tooltip />
          <el-table-column prop="category_name" label="品类" width="90" />
          <el-table-column prop="brand_name" label="品牌" width="80" />
          <el-table-column prop="year" label="年份" width="60" />
          <el-table-column prop="season" label="季节" width="60" />
          <el-table-column prop="tag_price" label="吊牌价" width="80" />
          <el-table-column label="状态" width="70">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ row.status === 'active' ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="成本" width="76">
            <template #default="{ row }">
              <el-tag :type="row.has_cost ? 'success' : 'warning'" size="small">{{ row.has_cost ? "已维护" : "缺成本" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="inventory_qty" label="库存" width="76" align="right" sortable="custom" />
          <el-table-column prop="sales_qty" label="7天销量" width="82" align="right" sortable="custom" />
          <el-table-column prop="sales_amount" label="7天销售额" width="96" align="right" sortable="custom">
            <template #default="{ row }">{{ formatAmount(row.sales_amount) }}</template>
          </el-table-column>
          <el-table-column prop="inventory_amount" label="库存金额" width="105" align="right">
            <template #default="{ row }">{{ formatAmount(row.inventory_amount) }}</template>
          </el-table-column>
          <el-table-column prop="gross_profit" label="7天毛利" width="96" align="right">
            <template #default="{ row }">{{ row.gross_profit == null ? '-' : formatAmount(row.gross_profit) }}</template>
          </el-table-column>
          <el-table-column prop="gross_margin" label="毛利率" width="86" align="right">
            <template #default="{ row }">{{ row.gross_margin == null ? '-' : formatRate(row.gross_margin) }}</template>
          </el-table-column>
          <el-table-column prop="sell_through_rate" label="售罄率" width="86" align="right">
            <template #default="{ row }">{{ formatRate(row.sell_through_rate) }}</template>
          </el-table-column>
          <el-table-column label="经营建议" width="100">
            <template #default="{ row }">
              <el-tooltip :content="row.decision?.reason || '-'" placement="top">
                <el-tag :type="decisionType(row.decision?.action)" size="small">{{ row.decision?.action_label || "-" }}</el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="source_system" label="来源" width="70" />
          <el-table-column label="同步时间" width="150">
            <template #default="{ row }">{{ fmtTs(row.synced_at) }}</template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination background layout="total, sizes, prev, pager, next, jumper"
            :total="pTotal" :current-page="pPage" :page-size="pSize"
            :page-sizes="[20, 50, 100]" @current-change="onPPage" @size-change="onPSize" />
        </div>
      </el-tab-pane>

      <!-- Tab 3: SKU档案 -->
      <el-tab-pane label="SKU档案" name="skus">
        <div class="toolbar">
          <div class="filters">
            <el-input v-model="sf.keyword" placeholder="SKU/条码/款号" clearable style="width:170px" @keyup.enter="fetchSkus" />
            <el-select v-model="sf.brand_name" placeholder="品牌" clearable filterable style="width:100px">
              <el-option v-for="b in sOpts.brands" :key="b" :label="b" :value="b" />
            </el-select>
            <el-select v-model="sf.status" placeholder="状态" clearable style="width:90px">
              <el-option label="启用" value="active" /><el-option label="停用" value="disabled" />
            </el-select>
            <el-checkbox v-model="sf.onlyPositive" @change="handleSkuFilterChange">隐藏0库存</el-checkbox>
            <el-button type="primary" @click="fetchSkus">搜索</el-button>
            <el-button @click="resetSkus">重置</el-button>
          </div>
          <span class="sync-info" v-if="sLastSync">最后同步：{{ sLastSync }}</span>
        </div>
        <el-table :data="skuList" v-loading="sLoading" border stripe size="small" @sort-change="handleSkuSortChange">
          <el-table-column prop="sku_code" label="SKU编码" width="140" fixed show-overflow-tooltip />
          <el-table-column prop="product_code" label="款号" width="100" />
          <el-table-column prop="product_name" label="商品名称" min-width="130" show-overflow-tooltip />
          <el-table-column prop="barcode" label="条码" width="110" />
          <el-table-column prop="color_name" label="颜色" width="90" />
          <el-table-column prop="size_name" label="尺码" width="70" />
          <el-table-column prop="brand_name" label="品牌" width="70" />
          <el-table-column prop="tag_price" label="吊牌价" width="80" />
          <el-table-column label="状态" width="70">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ row.status === 'active' ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="成本" width="76">
            <template #default="{ row }">
              <el-tag :type="row.has_cost ? 'success' : 'warning'" size="small">{{ row.has_cost ? "已维护" : "缺成本" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="inventory_qty" label="库存" width="76" align="right" sortable="custom" />
          <el-table-column prop="sales_qty" label="7天销量" width="82" align="right" sortable="custom" />
          <el-table-column prop="sales_amount" label="销售额" width="90" align="right" sortable="custom">
            <template #default="{ row }">{{ formatAmount(row.sales_amount) }}</template>
          </el-table-column>
          <el-table-column label="AI建议" width="90">
            <template #default="{ row }">
              <el-tag :type="suggestionType(row.ai_suggestion)" size="small">{{ row.ai_suggestion || "-" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="同步时间" width="150">
            <template #default="{ row }">{{ fmtTs(row.synced_at) }}</template>
          </el-table-column>
        </el-table>
        <div class="pager">
          <el-pagination background layout="total, sizes, prev, pager, next, jumper"
            :total="sTotal" :current-page="sPage" :page-size="sSize"
            :page-sizes="[20, 50, 100]" @current-change="onSPage" @size-change="onSSize" />
        </div>
      </el-tab-pane>

      <!-- Tab 4: 条码质量 -->
      <el-tab-pane label="条码质量" name="barcode">
        <div class="barcode-stats">
          <div class="barcode-card ok">
            <div class="bc-num">{{ barcodeStats.withBarcode }}</div>
            <div class="bc-label">有条码 SKU</div>
          </div>
          <div class="barcode-card warn">
            <div class="bc-num">{{ barcodeStats.noBarcode }}</div>
            <div class="bc-label">无条码 SKU</div>
          </div>
          <div class="barcode-card info">
            <div class="bc-num">{{ barcodeStats.barcodeRate }}%</div>
            <div class="bc-label">条码覆盖率</div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import { productApi } from "@/api/product";

const activeTab = ref("products");

const summaryCards = ref([
  { label: "商品款数", value: "—", warning: false },
  { label: "SKU数", value: "—", warning: false },
  { label: "商品缺成本", value: "—", warning: true },
  { label: "SKU缺成本", value: "—", warning: true },
  { label: "SKU缺条码", value: "—", warning: true },
  { label: "有库存SKU", value: "—", warning: false },
  { label: "7天动销SKU", value: "—", warning: false },
  { label: "库存金额", value: "—", warning: false },
]);

// 商品主档
const pLoading = ref(false); const productList = ref<any[]>([]);
const pTotal = ref(0); const pPage = ref(1); const pSize = ref(20);
const pLastSync = ref("");
const pSort = reactive({ prop: "", order: "" });
const pf = reactive({ keyword: "", brand_name: "", category_name: "", year: "", season: "", status: "", onlyPositive: true });
const pOpts = reactive<{ brands: string[]; categories: string[]; years: any[]; seasons: string[] }>({ brands: [], categories: [], years: [], seasons: [] });

// SKU
const sLoading = ref(false); const skuList = ref<any[]>([]);
const sTotal = ref(0); const sPage = ref(1); const sSize = ref(20);
const sLastSync = ref("");
const sSort = reactive({ prop: "", order: "" });
const sf = reactive({ keyword: "", product_code: "", brand_name: "", color_name: "", size_name: "", season_name: "", status: "", onlyPositive: true });
const sOpts = reactive<{ brands: string[]; colors: string[]; sizes: string[]; seasons: string[] }>({ brands: [], colors: [], sizes: [], seasons: [] });

const barcodeStats = ref({ withBarcode: 0, noBarcode: 0, barcodeRate: 0 });

function fmtTs(t: any) { if (!t) return "-"; return String(t).replace("T", " ").slice(0, 19); }
function formatNum(v: any) { return Number(v || 0).toLocaleString("zh-CN"); }
function formatAmount(v: any) {
  return Number(v || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function formatRate(v: any) { return `${(Number(v || 0) * 100).toFixed(1)}%`; }
function decisionType(text: string) {
  return ({ replenish: "success", transfer: "warning", clearance: "danger", continue_sale: "info" } as any)[text] || "info";
}
function suggestionType(text: string) {
  if (text === "正常") return "success";
  if (text === "持续跟进") return "primary";
  if (text === "补条码" || text === "补成本" || text === "关注补货") return "warning";
  return "info";
}

async function fetchQualitySummary() {
  try {
    const { data } = await productApi.getQualitySummary();
    if (!data?.success) return;
    const q = data.data || {};
    summaryCards.value = [
      { label: "商品款数", value: formatNum(q.product_count), warning: false },
      { label: "SKU数", value: formatNum(q.sku_count), warning: false },
      { label: "商品缺成本", value: formatNum(q.product_missing_cost_count), warning: true },
      { label: "SKU缺成本", value: formatNum(q.sku_missing_cost_count), warning: true },
      { label: "SKU缺条码", value: formatNum(q.sku_missing_barcode_count), warning: true },
      { label: "有库存SKU", value: formatNum(q.inv_sku_count), warning: false },
      { label: "7天动销SKU", value: formatNum(q.sale_sku_count), warning: false },
      { label: "库存金额", value: "¥" + formatAmount(q.inventory_amount), warning: false },
    ];
    barcodeStats.value.withBarcode = Number(q.sku_barcode_ready_count || 0);
    barcodeStats.value.noBarcode = Number(q.sku_missing_barcode_count || 0);
    barcodeStats.value.barcodeRate = Number(q.sku_barcode_rate || 0);
  } catch (_) {}
}

// 商品主档
async function fetchProducts() {
  pLoading.value = true;
  try {
    const params: any = { page: pPage.value, page_size: pSize.value };
    Object.entries(pf).forEach(([k, v]) => {
      if (k === "onlyPositive") {
        if (v) params.only_positive = 1;
      } else if (v !== "" && v != null) {
        params[k] = v;
      }
    });
    if (pSort.prop) {
      params.sort_by = pSort.prop;
      params.sort_order = pSort.order === "ascending" ? "asc" : "desc";
    }
    const { data } = await productApi.listProducts(params);
    if (data?.success) {
      productList.value = data.data.items || [];
      pTotal.value = data.data.total || 0;
      const times = productList.value.map((x: any) => x.synced_at).filter(Boolean).sort();
      if (times.length) pLastSync.value = fmtTs(times[times.length - 1]);
    }
  } catch (e: any) { ElMessage.error("查询失败"); }
  finally { pLoading.value = false; }
}
async function loadPOpts() {
  try {
    const { data } = await productApi.listProducts({ page: 1, page_size: 200 });
    const items = data?.data?.items || [];
    pOpts.brands = [...new Set(items.map((x: any) => x.brand_name).filter(Boolean))] as string[];
    pOpts.categories = [...new Set(items.map((x: any) => x.category_name).filter(Boolean))] as string[];
    pOpts.years = [...new Set(items.map((x: any) => x.year).filter((v: any) => v != null))].sort();
    pOpts.seasons = [...new Set(items.map((x: any) => x.season).filter(Boolean))] as string[];
  } catch (_) {}
}
function resetProducts() { pf.keyword = ""; pf.brand_name = ""; pf.category_name = ""; pf.year = ""; pf.season = ""; pf.status = ""; pf.onlyPositive = true; pPage.value = 1; fetchProducts(); }
function handleProductFilterChange() { pPage.value = 1; fetchProducts(); }
function handleProductSortChange({ prop, order }: any) {
  pSort.prop = order ? prop : "";
  pSort.order = order || "";
  pPage.value = 1;
  fetchProducts();
}
function onPPage(p: number) { pPage.value = p; fetchProducts(); }
function onPSize(s: number) { pSize.value = s; pPage.value = 1; fetchProducts(); }

// SKU
async function fetchSkus() {
  sLoading.value = true;
  try {
    const params: any = { page: sPage.value, page_size: sSize.value };
    Object.entries(sf).forEach(([k, v]) => {
      if (k === "onlyPositive") {
        if (v) params.only_positive = 1;
      } else if (v) {
        params[k] = v;
      }
    });
    if (sSort.prop) {
      params.sort_by = sSort.prop;
      params.sort_order = sSort.order === "ascending" ? "asc" : "desc";
    }
    const { data } = await productApi.listSkus(params);
    if (data?.success) {
      skuList.value = data.data.items || [];
      sTotal.value = data.data.total || 0;
      const times = skuList.value.map((x: any) => x.synced_at).filter(Boolean).sort();
      if (times.length) sLastSync.value = fmtTs(times[times.length - 1]);
    }
  } catch (e: any) { ElMessage.error("查询失败"); }
  finally { sLoading.value = false; }
}
async function loadSOpts() {
  try {
    const { data } = await productApi.listSkus({ page: 1, page_size: 200 });
    const items = data?.data?.items || [];
    sOpts.brands = [...new Set(items.map((x: any) => x.brand_name).filter(Boolean))] as string[];
    sOpts.colors = [...new Set(items.map((x: any) => x.color_name).filter(Boolean))] as string[];
    sOpts.sizes = [...new Set(items.map((x: any) => x.size_name).filter(Boolean))] as string[];
    sOpts.seasons = [...new Set(items.map((x: any) => x.season_name).filter(Boolean))] as string[];
  } catch (_) {}
}
function resetSkus() { Object.keys(sf).forEach(k => (sf as any)[k] = ""); sf.onlyPositive = true; sPage.value = 1; fetchSkus(); }
function handleSkuFilterChange() { sPage.value = 1; fetchSkus(); }
function handleSkuSortChange({ prop, order }: any) {
  sSort.prop = order ? prop : "";
  sSort.order = order || "";
  sPage.value = 1;
  fetchSkus();
}
function onSPage(p: number) { sPage.value = p; fetchSkus(); }
function onSSize(s: number) { sSize.value = s; sPage.value = 1; fetchSkus(); }

onMounted(() => {
  fetchQualitySummary();
  loadPOpts(); fetchProducts();
  loadSOpts(); fetchSkus();
});
</script>

<style scoped>
.analysis-page { display: flex; flex-direction: column; gap: 14px; width: 100%; min-width: 0; overflow: hidden; }
.page-header { display: flex; align-items: baseline; gap: 10px; }
.page-title { font-size: 20px; font-weight: 700; color: #111827; margin: 0; }
.page-desc { font-size: 12px; color: #9CA3AF; }
.summary-row { display: grid; grid-template-columns: repeat(8, 1fr); gap: 10px; }
.summary-card {
  background: #FFFFFF; border-radius: 10px; padding: 14px; text-align: center;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05); border-top: 3px solid #16A34A;
}
.summary-card.warning { border-top-color: #D97706; }
.s-num { font-size: 22px; font-weight: 700; color: #111827; }
.s-label { font-size: 11px; color: #9CA3AF; margin-top: 4px; }
.analysis-tabs { background: #FFFFFF; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.analysis-page :deep(.el-table th .cell) { display: inline-flex; align-items: center; justify-content: center; gap: 3px; white-space: nowrap; }
.analysis-page :deep(.el-table th .caret-wrapper) { flex: 0 0 auto; height: 20px; margin-left: 0; }
.sync-info { color: #909399; font-size: 12px; }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
.empty-block { display: flex; align-items: center; justify-content: center; gap: 10px; padding: 48px 0; color: #D1D5DB; font-size: 13px; }
.barcode-stats { display: flex; gap: 16px; justify-content: center; padding: 32px 0; }
.barcode-card { padding: 28px 40px; border-radius: 10px; text-align: center; }
.barcode-card.ok { background: #F0FDF4; border: 2px solid #BBF7D0; }
.barcode-card.warn { background: #FFF7ED; border: 2px solid #FED7AA; }
.barcode-card.info { background: #EFF6FF; border: 2px solid #BFDBFE; }
.bc-num { font-size: 32px; font-weight: 700; }
.barcode-card.ok .bc-num { color: #16A34A; }
.barcode-card.warn .bc-num { color: #D97706; }
.barcode-card.info .bc-num { color: #1E5EFF; }
.bc-label { font-size: 13px; color: #6B7280; margin-top: 4px; }
@media (max-width: 1200px) { .summary-row { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 760px) {
  .page-header { align-items: flex-start; flex-direction: column; gap: 4px; }
  .summary-row { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .summary-card { min-width: 0; padding: 12px 8px; }
  .s-num { font-size: 18px; overflow-wrap: anywhere; }
  .analysis-tabs { padding: 12px; overflow: hidden; }
}
</style>
