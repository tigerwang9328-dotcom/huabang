<template>
  <div class="store-sales-page">
    <section class="store-header">
      <div>
        <div class="eyebrow">门店管理 / 独立门店销售数据</div>
        <h1>独立门店销售数据</h1>
        <p>基于百胜小票流水汇总门店销售、订单、件数、折扣与动销指标。</p>
      </div>
      <div class="header-meta">
        <el-tag type="success" effect="light" round>
          <span class="live-dot"></span>
          数据正常对接
        </el-tag>
        <span>最新销售日期：{{ latestSalesDate || "-" }}</span>
        <span>同步时间：{{ formatTime(updatedAt) }}</span>
      </div>
    </section>

    <section class="filter-band">
      <div class="filter-left">
        <el-radio-group v-model="preset" size="small" @change="applyPreset">
          <el-radio-button label="today">最新日</el-radio-button>
          <el-radio-button label="yesterday">前一日</el-radio-button>
          <el-radio-button label="last7">近7天</el-radio-button>
          <el-radio-button label="last30">近30天</el-radio-button>
          <el-radio-button label="custom">自定义</el-radio-button>
        </el-radio-group>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          range-separator="至"
          :clearable="false"
          :disabled="preset !== 'custom'"
          size="small"
          @change="handleDateChange"
        />
        <el-input
          v-model="keyword"
          clearable
          size="small"
          class="keyword-input"
          placeholder="搜索门店代码/名称"
          @keyup.enter="fetchData"
          @clear="fetchData"
        />
      </div>
      <div class="filter-actions">
        <el-button size="small" :icon="Search" type="primary" @click="fetchData">查询</el-button>
        <el-button size="small" :icon="Refresh" :loading="loading" @click="refresh">刷新</el-button>
      </div>
    </section>

    <section class="summary-grid" v-loading="loading">
      <div class="metric-card" v-for="card in metricCards" :key="card.label">
        <div class="metric-label">{{ card.label }}</div>
        <div class="metric-value">{{ card.value }}</div>
        <div class="metric-sub">{{ card.sub }}</div>
      </div>
    </section>

    <section class="content-grid">
      <div class="rank-panel">
        <div class="panel-head">
          <div>
            <h2>门店销售排行</h2>
            <span>{{ dateRange[0] }} 至 {{ dateRange[1] }}</span>
          </div>
          <el-tag size="small" type="info">{{ filteredStores.length }} 家门店</el-tag>
        </div>

        <el-table
          :data="filteredStores"
          v-loading="loading"
          border
          stripe
          size="small"
          class="rank-table"
          :default-sort="{ prop: 'sales_amount', order: 'descending' }"
        >
          <el-table-column prop="rank" label="排名" width="64" fixed align="center">
            <template #default="{ row }">
              <span class="rank-badge" :class="{ top: row.rank <= 3 }">{{ row.rank }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="store_code" label="门店代码" width="96" />
          <el-table-column prop="store_name" label="门店名称" min-width="190" show-overflow-tooltip />
          <el-table-column prop="sales_amount" label="销售额" width="118" sortable align="right">
            <template #default="{ row }">{{ formatMoney(row.sales_amount) }}</template>
          </el-table-column>
          <el-table-column prop="actual_pay_amount" label="实收金额" width="118" sortable align="right">
            <template #default="{ row }">{{ formatMoney(row.actual_pay_amount) }}</template>
          </el-table-column>
          <el-table-column prop="recharge_amount" label="充值金额" width="118" sortable align="right">
            <template #default="{ row }">{{ formatMoney(row.recharge_amount) }}</template>
          </el-table-column>
          <el-table-column prop="refund_amount" label="退款金额" width="118" sortable align="right">
            <template #default="{ row }">{{ formatMoney(row.refund_amount) }}</template>
          </el-table-column>
          <el-table-column prop="orders" label="订单数" width="88" sortable align="right" />
          <el-table-column prop="sales_qty" label="件数" width="82" sortable align="right">
            <template #default="{ row }">{{ formatQty(row.sales_qty) }}</template>
          </el-table-column>
          <el-table-column prop="customer_average_price" label="客单价" width="96" sortable align="right">
            <template #default="{ row }">{{ formatMoney(row.customer_average_price) }}</template>
          </el-table-column>
          <el-table-column prop="attach_rate" label="连带率" width="86" sortable align="right">
            <template #default="{ row }">{{ formatDecimal(row.attach_rate) }}</template>
          </el-table-column>
          <el-table-column prop="discount_rate" label="折扣" width="82" sortable align="right">
            <template #default="{ row }">{{ formatPercent(row.discount_rate) }}</template>
          </el-table-column>
          <el-table-column prop="product_count" label="动销款" width="86" sortable align="right" />
          <el-table-column prop="sku_count" label="动销SKU" width="96" sortable align="right" />
        </el-table>
      </div>

      <div class="chart-stack">
        <div class="chart-panel">
          <div class="panel-head compact">
            <h2>门店销售额对比</h2>
            <span>按销售额降序</span>
          </div>
          <v-chart :option="barOption" autoresize class="chart-canvas" />
        </div>
        <div class="chart-panel">
          <div class="panel-head compact">
            <h2>日期趋势</h2>
            <span>销售额 / 订单数</span>
          </div>
          <v-chart :option="trendOption" autoresize class="trend-canvas" />
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { Refresh, Search } from "@element-plus/icons-vue";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import VChart from "vue-echarts";
import { storeApi } from "@/api/store";

use([CanvasRenderer, BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent]);

type Preset = "today" | "yesterday" | "last7" | "last30" | "custom";

const loading = ref(false);
const preset = ref<Preset>("today");
const keyword = ref("");
const latestSalesDate = ref("");
const updatedAt = ref("");
const dateRange = ref<[string, string]>(["", ""]);
const summary = ref<any>({});
const stores = ref<any[]>([]);
const trend = ref<any[]>([]);

function parseDate(value: string) {
  const d = new Date(`${value}T00:00:00`);
  return Number.isNaN(d.getTime()) ? new Date() : d;
}

function toDateString(d: Date) {
  const copy = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return copy.toISOString().slice(0, 10);
}

function shiftDate(value: string, days: number) {
  const d = parseDate(value);
  d.setDate(d.getDate() + days);
  return toDateString(d);
}

function formatMoney(value: any) {
  const n = Number(value || 0);
  if (Math.abs(n) >= 10000) return `¥${(n / 10000).toFixed(2)}万`;
  return `¥${Math.round(n).toLocaleString("zh-CN")}`;
}

function formatQty(value: any) {
  const n = Number(value || 0);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function formatDecimal(value: any) {
  const n = Number(value || 0);
  return n ? n.toFixed(2) : "0";
}

function formatPercent(value: any) {
  const n = Number(value || 0);
  return n ? `${(n * 100).toFixed(1)}%` : "0%";
}

function formatTime(t: any) {
  if (!t) return "-";
  return String(t).replace("T", " ").slice(0, 19);
}

function applyPreset() {
  const anchor = latestSalesDate.value || toDateString(new Date());
  if (preset.value === "today") dateRange.value = [anchor, anchor];
  if (preset.value === "yesterday") {
    const y = shiftDate(anchor, -1);
    dateRange.value = [y, y];
  }
  if (preset.value === "last7") dateRange.value = [shiftDate(anchor, -6), anchor];
  if (preset.value === "last30") dateRange.value = [shiftDate(anchor, -29), anchor];
  if (preset.value !== "custom") fetchData();
}

function handleDateChange() {
  if (preset.value === "custom") fetchData();
}

async function fetchData() {
  loading.value = true;
  try {
    const params: any = {};
    if (dateRange.value[0]) params.start_date = dateRange.value[0];
    if (dateRange.value[1]) params.end_date = dateRange.value[1];
    if (keyword.value.trim()) params.keyword = keyword.value.trim();
    const { data } = await storeApi.getSalesAnalysis(params);
    if (!data?.success) {
      ElMessage.error(data?.message || "查询失败");
      return;
    }
    const payload = data.data || {};
    latestSalesDate.value = payload.latest_sales_date || latestSalesDate.value;
    updatedAt.value = payload.updated_at || "";
    summary.value = payload.summary || {};
    stores.value = payload.stores || [];
    trend.value = payload.trend || [];
    if (payload.date_range?.start_date && payload.date_range?.end_date) {
      dateRange.value = [payload.date_range.start_date, payload.date_range.end_date];
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "门店销售数据加载失败");
  } finally {
    loading.value = false;
  }
}

async function refresh() {
  await fetchData();
}

const filteredStores = computed(() => stores.value || []);

const metricCards = computed(() => [
  { label: "销售额", value: formatMoney(summary.value.total_sales_amount), sub: "VIP/收钱吧/五月前储值/现金/线上" },
  { label: "实收金额", value: formatMoney(summary.value.total_actual_pay_amount), sub: "收钱吧/现金/线上+充值-退款" },
  { label: "订单数", value: Number(summary.value.total_orders || 0).toLocaleString("zh-CN"), sub: `${summary.value.active_stores_count || 0} 家有销售` },
  { label: "销售件数", value: formatQty(summary.value.total_sales_qty), sub: `连带率 ${formatDecimal(summary.value.attach_rate)}` },
  { label: "客单价", value: formatMoney(summary.value.customer_average_price), sub: `平均折扣 ${formatPercent(summary.value.discount_rate)}` },
  { label: "活跃门店", value: `${summary.value.active_stores_count || 0}`, sub: "白名单销售门店" },
]);

const barOption = computed(() => {
  const rows = [...filteredStores.value].sort((a, b) => Number(b.sales_amount) - Number(a.sales_amount)).slice(0, 10).reverse();
  return {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v: any) => formatMoney(v) },
    grid: { left: 90, right: 18, top: 12, bottom: 24 },
    xAxis: { type: "value", axisLabel: { formatter: (v: number) => (v >= 10000 ? `${v / 10000}万` : v) }, splitLine: { lineStyle: { color: "#eef2f7" } } },
    yAxis: { type: "category", data: rows.map((x) => x.store_code), axisTick: { show: false } },
    series: [{
      type: "bar",
      data: rows.map((x) => Number(x.sales_amount || 0)),
      barWidth: 14,
      itemStyle: { color: "#2563eb", borderRadius: [0, 4, 4, 0] },
    }],
  };
});

const trendOption = computed(() => ({
  tooltip: { trigger: "axis" },
  legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 10 },
  grid: { left: 42, right: 28, top: 34, bottom: 28 },
  xAxis: { type: "category", data: trend.value.map((x) => String(x.biz_date).slice(5)), axisTick: { show: false } },
  yAxis: [
    { type: "value", axisLabel: { formatter: (v: number) => (v >= 10000 ? `${v / 10000}万` : v) }, splitLine: { lineStyle: { color: "#eef2f7" } } },
    { type: "value", axisLabel: { formatter: "{value}" }, splitLine: { show: false } },
  ],
  series: [
    {
      name: "销售额",
      type: "line",
      smooth: true,
      data: trend.value.map((x) => Number(x.sales_amount || 0)),
      lineStyle: { width: 3, color: "#2563eb" },
      itemStyle: { color: "#2563eb" },
      areaStyle: { color: "rgba(37, 99, 235, .12)" },
    },
    {
      name: "订单数",
      type: "bar",
      yAxisIndex: 1,
      data: trend.value.map((x) => Number(x.orders || 0)),
      barWidth: 10,
      itemStyle: { color: "#94a3b8", borderRadius: [4, 4, 0, 0] },
    },
  ],
}));

onMounted(async () => {
  await fetchData();
  if (!dateRange.value[0] && latestSalesDate.value) applyPreset();
});
</script>

<style scoped>
.store-sales-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  color: #111827;
}

.store-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e5e7eb;
}

.eyebrow {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}

.store-header h1 {
  margin: 0;
  font-size: 22px;
  line-height: 1.2;
  font-weight: 800;
  letter-spacing: 0;
}

.store-header p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}

.header-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  color: #64748b;
  font-size: 12px;
  white-space: nowrap;
}

.live-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-right: 6px;
  border-radius: 999px;
  background: #22c55e;
}

.filter-band {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.filter-left {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.keyword-input {
  width: 190px;
}

.filter-actions {
  display: flex;
  gap: 8px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.metric-card {
  min-height: 92px;
  padding: 14px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.metric-label {
  font-size: 12px;
  color: #64748b;
}

.metric-value {
  margin-top: 8px;
  font-size: 22px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.1;
}

.metric-sub {
  margin-top: 7px;
  color: #94a3b8;
  font-size: 12px;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(360px, .85fr);
  gap: 14px;
  align-items: stretch;
}

.rank-panel,
.chart-panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px;
  min-width: 0;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-head h2 {
  margin: 0;
  font-size: 15px;
  line-height: 1.2;
}

.panel-head span {
  display: block;
  margin-top: 4px;
  color: #94a3b8;
  font-size: 12px;
}

.panel-head.compact {
  align-items: baseline;
}

.chart-stack {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: 14px;
  min-width: 0;
}

.rank-table {
  width: 100%;
}

.rank-badge {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: 26px;
  height: 22px;
  border-radius: 999px;
  color: #64748b;
  background: #f1f5f9;
  font-weight: 700;
}

.rank-badge.top {
  color: #fff;
  background: #2563eb;
}

.chart-canvas,
.trend-canvas {
  width: 100% !important;
  height: 270px !important;
}

@media (max-width: 1280px) {
  .summary-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .content-grid {
    grid-template-columns: 1fr;
  }

  .chart-stack {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    grid-template-rows: none;
  }
}

@media (max-width: 760px) {
  .store-sales-page {
    padding: 12px;
  }

  .store-header,
  .filter-band {
    flex-direction: column;
    align-items: stretch;
  }

  .header-meta {
    align-items: flex-start;
    white-space: normal;
  }

  .summary-grid,
  .chart-stack {
    grid-template-columns: 1fr;
  }

  .keyword-input {
    width: 100%;
  }
}
</style>
