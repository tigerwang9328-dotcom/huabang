<template>
  <div class="size-wall-page">
    <header class="page-head">
      <div>
        <p class="eyebrow">SIZE WALL OPERATIONS</p>
        <h1>断码尺码墙</h1>
        <span>分析日期 {{ overview.analysis_date || "--" }} · 销售覆盖 {{ coverageText }}</span>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
    </header>

    <section class="filter-band">
      <el-select v-model="filters.store_code" placeholder="全部门店/仓库" clearable filterable @change="applyFilters">
        <el-option v-for="row in locationOptions" :key="row.code" :label="row.label" :value="row.code" />
      </el-select>
      <el-select v-model="filters.year" placeholder="年份" clearable @change="applyCandidateFilters">
        <el-option v-for="y in eligibleYears" :key="y" :label="`${y}年`" :value="y" />
      </el-select>
      <el-select v-model="filters.size_group" placeholder="尺码组" clearable @change="handleFilterGroupChange">
        <el-option v-for="g in sizeGroups" :key="g.code" :label="g.label" :value="g.code" />
      </el-select>
      <el-select v-model="filters.normalized_size_code" placeholder="全部尺码" clearable filterable @change="applyCandidateFilters">
        <el-option v-for="s in filterSizeOptions" :key="s" :label="displaySize(s)" :value="s" />
      </el-select>
      <el-select v-model="filters.category_name" placeholder="品类" clearable filterable @change="applyCandidateFilters">
        <el-option v-for="x in categoryOptions" :key="x" :label="x" :value="x" />
      </el-select>
      <el-select v-model="filters.price_band" placeholder="价格段" clearable @change="applyCandidateFilters">
        <el-option v-for="x in priceOptions" :key="x" :label="x" :value="x" />
      </el-select>
      <el-select v-model="filters.min_score" placeholder="最低评分" clearable @change="applyCandidateFilters">
        <el-option label="60分" :value="60" /><el-option label="75分" :value="75" /><el-option label="90分" :value="90" />
      </el-select>
      <el-select v-model="filters.suggested_action" placeholder="处理建议" clearable @change="applyCandidateFilters">
        <el-option v-for="x in actionOptions" :key="x" :label="x" :value="x" />
      </el-select>
      <el-button @click="resetFilters">重置</el-button>
    </section>

    <el-alert v-for="warning in overview.warnings || []" :key="warning" class="warning-line" type="warning" :closable="false" show-icon :title="warning" />

    <section class="size-group-bar">
      <el-radio-group v-model="activeSizeGroup" @change="handleOverviewGroupChange">
        <el-radio-button v-for="g in sizeGroups" :key="g.code" :value="g.code">{{ g.label }}（{{ g.sizes.length }}）</el-radio-button>
      </el-radio-group>
    </section>

    <section class="size-strip" v-loading="loading">
      <article v-for="row in selectedSizeSummary" :key="row.size_code" class="size-stat" :class="statusClass(row.status)">
        <div class="size-number">{{ row.display_size }}</div>
        <div class="size-metrics">
          <strong>{{ formatQty(row.qty) }}件</strong>
          <span>{{ row.style_colors }}个款色 · {{ money(row.inventory_amount) }}</span>
        </div>
        <el-tag :type="statusType(row.status)" effect="plain">{{ row.status }}</el-tag>
      </article>
    </section>

    <section class="data-section matrix-section">
      <div class="section-head">
        <div><p>STORE × SIZE</p><h2>门店尺码矩阵</h2></div>
        <span>显示可进入尺码墙的候选库存</span>
      </div>
      <el-table :data="matrixRows" border stripe size="small" empty-text="暂无候选库存">
        <el-table-column prop="store_name" label="门店" min-width="210" fixed />
        <el-table-column v-for="size in selectedGroupSizes" :key="size" :label="displaySize(size)" min-width="125" align="center">
          <template #default="{ row }">
            <div class="matrix-cell">
              <strong>{{ formatQty(row.sizes[size]?.qty) }}件</strong>
              <el-tag size="small" :type="statusType(row.sizes[size]?.status)" effect="plain">{{ row.sizes[size]?.status || "断货" }}</el-tag>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="insight-grid">
      <div class="data-section compact-section">
        <div class="section-head"><div><p>MERCHANDISING</p><h2>陈列建议</h2></div></div>
        <ol><li v-for="x in overview.display_advice || []" :key="x">{{ x }}</li></ol>
      </div>
      <div class="data-section compact-section">
        <div class="section-head"><div><p>SALES TALK</p><h2>销售话术</h2></div></div>
        <ol><li v-for="x in overview.sales_scripts || []" :key="x">{{ x }}</li></ol>
      </div>
      <div class="data-section compact-section">
        <div class="section-head"><div><p>AI INSIGHTS</p><h2>结构提醒</h2></div></div>
        <ol><li v-for="x in overview.insights || []" :key="x">{{ x }}</li></ol>
      </div>
    </section>

    <section class="data-section baseline-section">
      <div class="section-head">
        <div><p>BASELINE</p><h2>候选销售基线</h2></div>
        <el-tag type="info" effect="plain">非实际上墙效果</el-tag>
      </div>
      <div class="baseline-metrics">
        <div><span>候选款色</span><strong>{{ formatQty(coverage.candidate_style_colors) }}</strong></div>
        <div><span>候选件数</span><strong>{{ formatQty(coverage.candidate_qty) }}</strong></div>
        <div><span>库存金额</span><strong>{{ money(coverage.candidate_amount) }}</strong></div>
        <div><span>覆盖期销量</span><strong>{{ formatQty(coverage.baseline_sales_qty) }}</strong></div>
        <div><span>覆盖期销售额</span><strong>{{ money(coverage.baseline_sales_amount) }}</strong></div>
      </div>
    </section>

    <section class="data-section candidate-section">
      <div class="section-head">
        <div><p>CANDIDATE LIST</p><h2>尺码墙候选明细</h2></div>
        <span>共 {{ candidateTotal }} 条位置库存记录</span>
      </div>
      <el-table :data="candidates" v-loading="candidateLoading" border stripe size="small" empty-text="当前条件没有候选商品">
        <el-table-column label="图片" width="64" fixed align="center">
          <template #default="{ row }">
            <div class="candidate-thumb-cell">
              <el-image v-if="row.image_url" class="candidate-thumb" :src="row.image_url"
                :preview-src-list="[row.image_url]" fit="cover" preview-teleported
                hide-on-click-modal loading="lazy" />
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="store_name" label="门店/仓库" width="180" fixed show-overflow-tooltip />
        <el-table-column prop="product_code" label="款号" width="120" fixed />
        <el-table-column prop="product_name" label="商品" min-width="150" show-overflow-tooltip />
        <el-table-column prop="color_name" label="颜色" width="90" />
        <el-table-column label="标准尺码" width="88" align="center"><template #default="{ row }"><strong>{{ displaySize(row.normalized_size_code) }}</strong></template></el-table-column>
        <el-table-column label="百胜原码" width="88" align="center"><template #default="{ row }">{{ row.raw_size_code }}</template></el-table-column>
        <el-table-column prop="product_year" label="年份" width="70" />
        <el-table-column prop="category_name" label="品类" width="100" show-overflow-tooltip />
        <el-table-column prop="price_band" label="价格段" width="105" />
        <el-table-column label="库存" width="75" align="right"><template #default="{ row }">{{ formatQty(row.inventory_qty) }}</template></el-table-column>
        <el-table-column label="30日销量" width="90" align="right"><template #default="{ row }">{{ formatQty(row.sales_qty_30d) }}</template></el-table-column>
        <el-table-column label="尺码结构" width="110"><template #default="{ row }">{{ row.remaining_size_count }}/{{ row.listed_size_count }}</template></el-table-column>
        <el-table-column label="评分" width="76" align="center"><template #default="{ row }"><el-tag :type="row.score >= 75 ? 'danger' : 'warning'">{{ row.score }}</el-tag></template></el-table-column>
        <el-table-column label="入选原因" min-width="230"><template #default="{ row }"><div class="reason-list"><span v-for="x in row.score_reasons || []" :key="x">{{ x }}</span></div></template></el-table-column>
        <el-table-column prop="suggested_action" label="处理建议" width="120"><template #default="{ row }"><el-tag effect="plain">{{ row.suggested_action }}</el-tag></template></el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination background layout="total, sizes, prev, pager, next" :total="candidateTotal" :current-page="page" :page-size="pageSize"
          :page-sizes="[20, 50, 100]" @current-change="changePage" @size-change="changePageSize" />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { productApi } from "@/api/product";

const priceOptions = ["300元以下", "300-499元", "500-799元", "800-1199元", "1200元以上"];
const actionOptions = ["集中调拨", "集中清仓", "VIP定向推荐", "集中陈列", "搭配销售"];
const loading = ref(false); const candidateLoading = ref(false);
const overview = ref<any>({ size_summary: [], store_matrix: [], data_coverage: {}, warnings: [] });
const candidates = ref<any[]>([]); const candidateTotal = ref(0);
const page = ref(1); const pageSize = ref(20);
const activeSizeGroup = ref("");
const filters = reactive<any>({ store_code: "", year: null, size_group: "", normalized_size_code: "", category_name: "", price_band: "", min_score: 60, suggested_action: "" });
const coverage = computed(() => overview.value.data_coverage || {});
const coverageText = computed(() => coverage.value.coverage_start ? `${coverage.value.coverage_start} 至 ${coverage.value.coverage_end}（${coverage.value.coverage_days}天）` : "--");
const matrixRows = computed(() => overview.value.store_matrix || []);
const sizeGroups = computed<any[]>(() => overview.value.size_groups || []);
const selectedGroupSizes = computed<string[]>(() => sizeGroups.value.find((g: any) => g.code === activeSizeGroup.value)?.sizes || []);
const selectedSizeSummary = computed<any[]>(() => (overview.value.size_summary || []).filter((x: any) => x.size_group === activeSizeGroup.value));
const filterSizeOptions = computed<string[]>(() => {
  if (!filters.size_group) return (overview.value.size_summary || []).map((x: any) => x.size_code);
  return sizeGroups.value.find((g: any) => g.code === filters.size_group)?.sizes || [];
});
const categoryOptions = computed(() => (overview.value.category_distribution || []).map((x: any) => x.name).filter(Boolean));
const eligibleYears = computed(() => overview.value.eligible_years || []);
const locationOptions = computed(() => (overview.value.location_options || []).map((x: any) => ({
  code: x.store_code,
  label: `${x.store_code} ${x.store_name || x.store_code}`,
})));

const formatQty = (value: any) => Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
const money = (value: any) => `¥${Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
const statusType = (status: string) => status === "断货" ? "danger" : status === "偏少" ? "warning" : status === "偏多" ? "primary" : "success";
const statusClass = (status: string) => `status-${status || "normal"}`;
const displaySize = (size: any) => String(size || "").replace(/Y$/, "");

function params(includeCandidate = false) {
  const data: any = {};
  Object.entries(filters).forEach(([key, value]) => { if (value !== "" && value !== null && value !== undefined) data[key] = value; });
  if (!includeCandidate) Object.keys(data).forEach((key) => { if (key !== "store_code") delete data[key]; });
  return data;
}
async function fetchOverview() {
  loading.value = true;
  try {
    const { data } = await productApi.getSizeWallOverview(params(false));
    if (data?.success) {
      overview.value = data.data || {};
      if (!sizeGroups.value.some((g: any) => g.code === activeSizeGroup.value)) activeSizeGroup.value = sizeGroups.value[0]?.code || "";
    }
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "尺码墙概览加载失败"); }
  finally { loading.value = false; }
}
async function fetchCandidates() {
  candidateLoading.value = true;
  try {
    const { data } = await productApi.getSizeWallCandidates({ ...params(true), page: page.value, page_size: pageSize.value });
    if (data?.success) { candidates.value = data.data.items || []; candidateTotal.value = data.data.total || 0; }
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "候选明细加载失败"); }
  finally { candidateLoading.value = false; }
}
async function loadAll() { await Promise.all([fetchOverview(), fetchCandidates()]); }
async function applyFilters() { page.value = 1; await loadAll(); }
async function applyCandidateFilters() { page.value = 1; await fetchCandidates(); }
function handleOverviewGroupChange() { /* 只切换概览与矩阵，不改变候选筛选 */ }
function handleFilterGroupChange() { filters.normalized_size_code = ""; applyCandidateFilters(); }
function resetFilters() { Object.assign(filters, { store_code: "", year: null, size_group: "", normalized_size_code: "", category_name: "", price_band: "", min_score: 60, suggested_action: "" }); page.value = 1; loadAll(); }
function changePage(value: number) { page.value = value; fetchCandidates(); }
function changePageSize(value: number) { pageSize.value = value; page.value = 1; fetchCandidates(); }
onMounted(loadAll);
</script>

<style scoped>
.size-wall-page { min-height: 100vh; padding: 26px 30px 44px; background: #f5f7fa; color: #172033; }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding-bottom: 20px; border-bottom: 1px solid #dfe4ea; }
.eyebrow, .section-head p { margin: 0 0 7px; color: #b36a21; font-size: 11px; font-weight: 800; letter-spacing: 0; }
.page-head h1 { margin: 0 0 7px; font-size: 30px; line-height: 1.2; }
.page-head span, .section-head span { color: #697386; font-size: 13px; }
.filter-band { display: flex; flex-wrap: wrap; gap: 9px; padding: 18px 0; }
.filter-band :deep(.el-select) { width: 132px; }
.filter-band :deep(.el-select:first-child) { width: 210px; }
.warning-line { margin-bottom: 10px; }
.size-group-bar { overflow-x: auto; padding: 2px 0 12px; white-space: nowrap; }
.size-group-bar :deep(.el-radio-group) { flex-wrap: nowrap; }
.size-strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); border: 1px solid #dfe4ea; background: white; }
.size-stat { min-height: 104px; display: grid; grid-template-columns: 56px 1fr auto; gap: 14px; align-items: center; padding: 17px 19px; border-right: 1px solid #e7ebf0; }
.size-stat:last-child { border-right: 0; }
.size-number { font-size: 36px; font-weight: 800; color: #152d4f; }
.size-metrics { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.size-metrics strong { font-size: 20px; white-space: nowrap; }.size-metrics span { color: #788397; font-size: 12px; }
.data-section { margin-top: 18px; padding: 18px 20px; border: 1px solid #dfe4ea; background: white; }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 15px; }
.section-head h2 { margin: 0; font-size: 18px; }
.matrix-cell { display: flex; justify-content: center; align-items: center; gap: 10px; }.matrix-cell strong { min-width: 46px; text-align: right; }
.insight-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }.compact-section { margin-top: 14px; }
.compact-section ol { margin: 0; padding-left: 20px; color: #3f4a5d; font-size: 13px; line-height: 1.8; }
.baseline-metrics { display: grid; grid-template-columns: repeat(5, 1fr); border-top: 1px solid #edf0f3; }
.baseline-metrics div { padding: 16px 14px 4px; border-right: 1px solid #edf0f3; }.baseline-metrics div:last-child { border-right: 0; }
.baseline-metrics span { display: block; margin-bottom: 7px; color: #788397; font-size: 12px; }.baseline-metrics strong { font-size: 20px; }
.reason-list { display: flex; flex-wrap: wrap; gap: 4px; }.reason-list span { padding: 2px 6px; background: #f0f3f7; color: #46536a; font-size: 11px; }
.candidate-thumb-cell { width: 48px; height: 48px; margin: 0 auto; background: #f2f4f7; }
.candidate-thumb { width: 48px; height: 48px; cursor: zoom-in; }
.pager { display: flex; justify-content: flex-end; padding-top: 16px; }
@media (max-width: 1180px) { .size-strip { grid-template-columns: repeat(2, 1fr); }.size-stat:nth-child(2) { border-right: 0; }.size-stat { border-bottom: 1px solid #e7ebf0; }.insight-grid { grid-template-columns: 1fr; }.baseline-metrics { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 900px) { .size-strip { grid-template-columns: 1fr; }.size-stat { border-right: 0; } }
@media (max-width: 720px) { .size-wall-page { padding: 18px 14px 36px; }.page-head { align-items: flex-start; }.page-head h1 { font-size: 25px; }.size-strip { grid-template-columns: 1fr; }.size-stat { border-right: 0; }.baseline-metrics { grid-template-columns: repeat(2, 1fr); }.filter-band :deep(.el-select), .filter-band :deep(.el-select:first-child) { width: calc(50% - 5px); } }
</style>
