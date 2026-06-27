<template>
  <div class="dashboard-v2">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="page-header-left">
        <h2 class="page-title">华邦AI中台 · 经营概览</h2>
        <span class="page-subtitle">基于百胜ERP、库存、商品、门店数据的经营指挥看板</span>
      </div>
      <div class="page-header-right">
        <span class="data-date" v-if="dataDate">
          <el-icon><Calendar /></el-icon> 数据日期：{{ dataDate }}
        </span>
        <el-button size="small" :loading="loading" @click="fetchData" class="refresh-btn">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
    </div>

    <!-- 第一行：数据资产 -->
    <div class="section-label">📊 数据资产</div>
    <div class="asset-row">
      <div class="asset-card" v-for="a in assetCards" :key="a.label">
        <div class="asset-num">{{ a.value }}</div>
        <div class="asset-label">{{ a.label }}</div>
      </div>
    </div>

    <!-- 第二行：经营指标 -->
    <div class="section-label">📈 经营关键指标</div>
    <div class="metric-row">
      <div class="metric-card" v-for="m in bizMetricCards" :key="m.label" :class="{ pending: m.isPending }">
        <div class="metric-label">{{ m.label }}</div>
        <div class="metric-value" v-if="!m.isPending">{{ m.value }}</div>
        <el-tag v-else type="info" size="small" class="pending-tag">待接入</el-tag>
      </div>
    </div>

    <!-- 第三行：库存风险 + 任务执行 -->
    <div class="two-col">
      <div class="panel">
        <div class="section-label">⚠️ 库存风险</div>
        <div class="metric-row small">
          <div class="metric-card" v-for="r in riskCards" :key="r.label" :class="{ pending: r.isPending }">
            <div class="metric-label">{{ r.label }}</div>
            <div class="metric-value" v-if="!r.isPending">{{ r.value }}</div>
            <el-tag v-else type="info" size="small" class="pending-tag">待接入</el-tag>
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="section-label">📋 任务执行</div>
        <div class="metric-row small">
          <div class="metric-card" v-for="t in taskCards" :key="t.label" :class="{ warning: t.isWarning, danger: t.isDanger }">
            <div class="metric-label">{{ t.label }}</div>
            <div class="metric-value" :class="{ 'danger-val': t.isDanger }">{{ t.value }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 趋势图（无数据时简化） -->
    <div class="panel trend-panel">
      <div class="section-label">📉 近7天销售趋势</div>
      <div v-if="!trend.length || !trend.some(t => t.total_sales)" class="empty-hint">
        <el-icon><TrendCharts /></el-icon>
        <span>销售明细尚未接入，趋势图待数据接入后展示</span>
      </div>
      <div v-else class="trend-chart-wrap">
        <v-chart :option="trendOption" autoresize class="echarts-trend" />
      </div>
    </div>

    <!-- 待接入字段清单 -->
    <div class="panel pending-panel" v-if="pendingFields.length">
      <div class="section-label">⏳ 待接入数据</div>
      <div class="pending-list">
        <el-tag v-for="pf in pendingFields" :key="pf.field" type="info" size="small" effect="plain">
          {{ pf.group }} / {{ pf.field }}：{{ pf.reason }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import VChart from "vue-echarts";
import { dashboardApi } from "@/api/dashboard";

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent]);

const loading = ref(true);
const dataDate = ref("");
const pendingFields = ref<any[]>([]);
const trend = ref<any[]>([]);

// 从 overview 解析的原始数据
const rawOverview = ref<any>({});

function getMetricVal(metrics: any, key: string): { val: string; isPending: boolean } {
  const m = metrics?.[key];
  if (!m || m.status === "pending_data") return { val: "待接入", isPending: true };
  return { val: m.display || String(m.value ?? "—"), isPending: false };
}

const assetCards = computed(() => {
  const a = rawOverview.value?.data_assets || {};
  return [
    { label: "门店数", value: a.store_count?.value ?? "—" },
    { label: "商品款数", value: a.product_count?.value ?? "—" },
    { label: "SKU数", value: a.sku_count?.value ?? "—" },
    { label: "仓库数", value: a.warehouse_count?.value ?? "—" },
    { label: "库存记录", value: formatBigNum(a.inventory_record_count?.value) },
  ];
});

function formatBigNum(v: any): string {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (n >= 10000) return (n / 10000).toFixed(1) + "万";
  return String(n);
}

const bizMetricCards = computed(() => {
  const m = rawOverview.value?.business_metrics || {};
  const cards = [
    { key: "yesterday_sales", label: "昨日销售额" },
    { key: "yesterday_orders", label: "昨日订单数" },
    { key: "yesterday_items", label: "昨日销售件数" },
    { key: "gross_profit", label: "毛利额" },
    { key: "gross_margin", label: "毛利率" },
    { key: "discount_rate", label: "折扣率" },
    { key: "avg_order_value", label: "客单价" },
    { key: "items_per_order", label: "连带率" },
  ];
  return cards.map(c => {
    const r = getMetricVal(m, c.key);
    return { label: c.label, value: r.val, isPending: r.isPending };
  });
});

const riskCards = computed(() => {
  const m = rawOverview.value?.inventory_risk || {};
  return [
    { label: "库存件数", ...getMetricVal(m, "total_inventory_qty") },
    { label: "库存金额", ...getMetricVal(m, "inventory_amount") },
    { label: "缺货SKU", ...getMetricVal(m, "low_stock_sku_count") },
    { label: "高库存SKU", ...getMetricVal(m, "high_stock_sku_count") },
    { label: "无条码SKU", ...getMetricVal(m, "no_barcode_sku_count") },
    { label: "90天+库存金额", ...getMetricVal(m, "age_90_plus_amount") },
  ];
});

const taskCards = computed(() => {
  const m = rawOverview.value?.task_execution || {};
  const pending = m.pending_task_count?.value ?? 0;
  const overdue = m.overdue_task_count?.value ?? 0;
  return [
    { label: "待处理", value: pending, isWarning: pending > 0, isDanger: false },
    { label: "已逾期", value: overdue, isWarning: false, isDanger: overdue > 0 },
    { label: "已完成", value: m.completed_task_count?.value ?? 0, isWarning: false, isDanger: false },
  ];
});

const trendOption = computed(() => ({
  tooltip: { trigger: "axis" },
  grid: { left: 4, right: 4, top: 12, bottom: 0, containLabel: true },
  xAxis: {
    type: "category",
    data: trend.value.map((t: any) => (t.date || "").slice(5)),
    axisLabel: { color: "#9CA3AF", fontSize: 11 },
  },
  yAxis: {
    type: "value",
    axisLabel: {
      color: "#9CA3AF", fontSize: 11,
      formatter: (v: number) => v >= 10000 ? (v / 10000).toFixed(0) + "万" : String(v),
    },
    splitLine: { lineStyle: { color: "#F3F4F6" } },
  },
  series: [{
    type: "line", data: trend.value.map((t: any) => t.total_sales || 0),
    smooth: true, symbol: "circle", symbolSize: 4,
    lineStyle: { color: "#1E5EFF", width: 2 },
    itemStyle: { color: "#1E5EFF" },
    areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
      colorStops: [{ offset: 0, color: "rgba(30,94,255,0.1)" }, { offset: 1, color: "rgba(30,94,255,0)" }] } },
  }],
}));

async function fetchData() {
  loading.value = true;
  try {
    const [r1, r2] = await Promise.all([
      dashboardApi.getOverview(),
      dashboardApi.getSalesTrend({ days: 7 }),
    ]);
    rawOverview.value = r1.data.data || {};
    dataDate.value = rawOverview.value.stat_date || "";
    pendingFields.value = rawOverview.value.pending_fields || [];
    trend.value = r2.data.data?.trend || [];
  } catch (e) {
    console.error("加载概览失败", e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => { fetchData(); });
</script>

<style scoped>
.dashboard-v2 { display: flex; flex-direction: column; gap: 16px; }
.page-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.page-header-left { display: flex; align-items: baseline; gap: 12px; }
.page-title { font-size: 20px; font-weight: 700; color: #111827; margin: 0; }
.page-subtitle { font-size: 12px; color: #9CA3AF; }
.page-header-right { display: flex; align-items: center; gap: 10px; }
.data-date { display: flex; align-items: center; gap: 5px; font-size: 12px; color: #6B7280; }
.refresh-btn { border-color: #E5E7EB; color: #374151; background: #fff; }

.section-label { font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 2px; }

/* 数据资产 */
.asset-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.asset-card {
  background: #FFFFFF; border-radius: 10px; padding: 18px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center;
  border-top: 3px solid #1E5EFF;
}
.asset-num { font-size: 28px; font-weight: 700; color: #111827; line-height: 1.2; }
.asset-label { font-size: 12px; color: #9CA3AF; margin-top: 4px; }

/* 指标卡片 */
.metric-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.metric-row.small { grid-template-columns: repeat(3, 1fr); }
.metric-card {
  background: #FFFFFF; border-radius: 10px; padding: 14px 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.metric-card.pending { opacity: 0.7; }
.metric-card.warning { border-left: 3px solid #F59E0B; }
.metric-card.danger { border-left: 3px solid #DC2626; }
.metric-label { font-size: 12px; color: #9CA3AF; margin-bottom: 6px; }
.metric-value { font-size: 22px; font-weight: 700; color: #111827; }
.metric-value.danger-val { color: #DC2626; }
.pending-tag { margin-top: 2px; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.panel { background: #FFFFFF; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }

.trend-panel { }
.trend-chart-wrap { width: 100%; }
.echarts-trend { width: 100%; height: 200px; }

.empty-hint { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 24px 0; color: #D1D5DB; font-size: 13px; }

.pending-panel { }
.pending-list { display: flex; flex-wrap: wrap; gap: 6px; }

@media (max-width: 1100px) {
  .asset-row { grid-template-columns: repeat(3, 1fr); }
  .metric-row { grid-template-columns: repeat(2, 1fr); }
  .two-col { grid-template-columns: 1fr; }
}
</style>
