<template>
  <div class="lux-dashboard-wrapper" :class="{ ready: !loading }">

    <!-- ====== 极简大牌 Header ====== -->
    <div class="lux-clean-header">
      <div class="header-left-brand">
        <h1 class="lux-brand-title">
          <span class="brand-en">REARE</span>
          <span class="brand-divider"></span>
          <span class="brand-zh">经营概览</span>
        </h1>
        <p class="lux-brand-subtitle">基于百胜 ERP、库存、商品、门店数据驱动的零售决策看板</p>
      </div>
      <div class="header-right-meta">
        <span class="date-tag">
          <span class="live-dot"></span> 数据日期：{{ dataDate || '加载中...' }}
        </span>
        <button class="lux-btn-refresh" :class="{ spinning: loading }" @click="fetchData">
          <svg style="width:15px;height:15px" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6M23 20v-6h-6"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
        </button>
      </div>
    </div>

    <!-- ====== 数据资产总览 ====== -->
    <div class="lux-section-title">
      <span class="title-decor"></span> 数据资产总览
    </div>
    <div class="lux-grid-5">
      <div v-for="(a, idx) in assetCards" :key="a.label" class="lux-crypto-card" :style="{ animationDelay: (idx * 60) + 'ms' }">
        <div class="card-inner">
          <div class="card-icon" v-html="a.icon"></div>
          <div class="card-info">
            <span class="card-label">{{ a.label }}</span>
            <h2 class="card-value" :class="{ 'highlight-gold': idx === 0, 'highlight-orange': idx === 4 }">
              {{ a.value }}<span class="unit" v-if="a.unit">{{ a.unit }}</span>
            </h2>
          </div>
        </div>
        <div class="card-progress-bar" :class="{ 'bar-gold': idx === 0, 'bar-orange': idx === 4 }"></div>
      </div>
    </div>

    <!-- ====== 左右分栏 ====== -->
    <div class="lux-main-split">

      <!-- 左栏 -->
      <div class="lux-split-left">

        <div class="lux-section-title">
          <span class="title-decor"></span> 核心经营关键指标
        </div>
        <div class="lux-grid-4">
          <div class="lux-metric-card" v-for="m in bizMetricCards" :key="m.label">
            <div class="metric-header">
              <span class="metric-label">{{ m.label }}</span>
              <span class="metric-status-dot" :class="{ active: !m.isPending }"></span>
            </div>
            <div class="metric-body">
              <template v-if="!m.isPending">
                <span class="metric-num">{{ m.value }}</span>
              </template>
              <template v-else>
                <div class="lux-shimmer-loader">
                  <span class="shimmer-txt">--,--</span>
                  <span class="shimmer-sub">数据正同步</span>
                </div>
              </template>
            </div>
          </div>
        </div>

        <div class="lux-section-title">
          <span class="title-decor alert"></span> 实时库存风险监控
        </div>
        <div class="lux-grid-3">
          <div class="lux-risk-card" v-for="r in riskCards" :key="r.label">
            <div class="risk-meta">
              <span class="risk-label">{{ r.label }}</span>
            </div>
            <div class="risk-data">
              <template v-if="!r.isPending">
                <span class="risk-num" :class="{ 'text-alert': r.label.includes('缺货') || r.label.includes('高库存') }">{{ r.value }}</span>
              </template>
              <template v-else>
                <div class="lux-shimmer-loader alert-shimmer">
                  <span class="shimmer-txt">--</span>
                  <span class="shimmer-sub">智能审计中</span>
                </div>
              </template>
            </div>
          </div>
        </div>

      </div>

      <!-- 右栏 -->
      <div class="lux-split-right">

        <div class="lux-section-title">
          <span class="title-decor dynamic"></span> 近7天销售趋势洞察
        </div>
        <div class="lux-chart-box">
          <div class="lux-chart-stage">
            <v-chart :option="trendOption" autoresize class="echarts-canvas" />
          </div>
          <div class="lux-blur-overlay">
            <div class="overlay-content">
              <div class="pulse-radar"></div>
              <h3>销售明细尚未接入</h3>
              <p>系统已就绪，正等待百胜 ERP 流水数据管线握手连通</p>
            </div>
          </div>
        </div>

        <div class="lux-section-title">
          <span class="title-decor task"></span> 协同任务执行
        </div>
        <div class="lux-task-board">
          <div class="task-col" v-for="t in taskCards" :key="t.label" :class="{ urgent: t.isWarning, success: !t.isWarning && !t.isDanger }">
            <span class="task-num" :class="{ 'danger-num': t.isDanger }">{{ t.value }}</span>
            <span class="task-tit">{{ t.label }}</span>
          </div>
        </div>

      </div>
    </div>

    <!-- ====== 底部技术诊断面板 ====== -->
    <div class="lux-developer-drawer">
      <details class="lux-details">
        <summary class="lux-summary">
          核心数据底层资产链路健康度审计 (仅技术可见) &mdash; {{ pendingFields.length }} 项待接入
        </summary>
        <div class="drawer-inner-table" v-if="pendingFields.length">
          <div class="table-row header">
            <span>底层数据模型关键字段</span>
            <span>当前接入捕获状态</span>
          </div>
          <div class="table-row" v-for="pf in pendingFields" :key="pf.field">
            <code class="code-field">{{ pf.group }}.{{ pf.field }}</code>
            <span class="status-badge waiting">Awaiting Pipeline Feed &mdash; {{ pf.reason }}</span>
          </div>
        </div>
        <div class="drawer-inner-table" v-else>
          <div style="text-align:center;padding:12px;color:#16A34A">所有数据已全部接入</div>
        </div>
      </details>
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
const storeRank = ref<any[]>([]);
const taskSummary = ref<any>({});
const rawOverview = ref<any>({});

function getMetricVal(metrics: any, key: string): { val: string; isPending: boolean } {
  const m = metrics?.[key];
  if (!m || m.status === "pending_data") return { val: "--", isPending: true };
  return { val: m.display || String(m.value ?? "--"), isPending: false };
}

function formatBigNum(v: any): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (n >= 10000) return (n / 10000).toFixed(1) + "万";
  return String(Math.round(n));
}

function fmtMoney(v: any): string {
  if (v === null || v === undefined) return "--";
  const n = Number(v);
  if (Math.abs(n) >= 10000) return "¥" + (n / 10000).toFixed(2) + "万";
  return "¥" + n.toFixed(0);
}

const ico = (d: string) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="' + d + '"/></svg>';

const assetCards = computed(() => {
  const a = rawOverview.value?.data_assets || {};
  return [
    { label: "运营门店数", value: a.store_count?.value ?? "--", unit: "家", icon: ico("M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22V12h6v10") },
    { label: "商品总款数", value: a.product_count?.value ?? "--", unit: "款", icon: ico("M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z M3 6h18 M16 10a4 4 0 0 1-8 0") },
    { label: "活跃 SKU 数", value: a.sku_count?.value ?? "--", unit: "个", icon: ico("M4 7V4h16v3 M9 20h6 M12 4v16") },
    { label: "覆盖仓库数", value: a.warehouse_count?.value ?? "--", unit: "个", icon: ico("M3 21h18 M3 10h18 M5 6l7-3 7 3 M4 10v11 M20 10v11 M8 14v3 M12 14v3 M16 14v3") },
    { label: "在库物理记录", value: formatBigNum(a.inventory_record_count?.value), unit: "条", icon: ico("M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4") },
  ];
});

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
    { label: "缺货 SKU 数", ...getMetricVal(m, "low_stock_sku_count") },
    { label: "高库存 SKU 数", ...getMetricVal(m, "high_stock_sku_count") },
    { label: "无条码 SKU 数", ...getMetricVal(m, "no_barcode_sku_count") },
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
  grid: { left: 4, right: 4, top: 12, bottom: 28, containLabel: true },
  xAxis: {
    type: "category",
    data: trend.value.map((t: any) => (t.date || "").slice(5)),
    axisLabel: { color: "#94A3B8", fontSize: 11 },
  },
  yAxis: {
    type: "value",
    axisLabel: {
      color: "#94A3B8", fontSize: 11,
      formatter: (v: number) => v >= 10000 ? (v / 10000).toFixed(0) + "万" : String(v),
    },
    splitLine: { lineStyle: { color: "#F1F5F9" } },
  },
  series: [
    {
      name: "销售额", type: "line", data: trend.value.map((t: any) => t.total_sales || 0),
      smooth: true, symbol: "circle", symbolSize: 6,
      lineStyle: { color: "#FF6A00", width: 3 },
      itemStyle: { color: "#FF6A00", borderWidth: 2, borderColor: "#fff" },
      areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: "rgba(255,106,0,0.18)" }, { offset: 1, color: "rgba(255,106,0,0)" }] } },
    },
    {
      name: "订单数", type: "line", data: trend.value.map((t: any) => t.order_count || 0),
      smooth: true, symbol: "circle", symbolSize: 5,
      lineStyle: { color: "#1E293B", width: 2, type: "dashed" },
      itemStyle: { color: "#1E293B" },
      areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: "rgba(15,23,42,0.1)" }, { offset: 1, color: "rgba(15,23,42,0)" }] } },
    },
  ],
}));

async function fetchData() {
  loading.value = true;
  try {
    const [r1, r2, r3, r4] = await Promise.all([
      dashboardApi.getOverview(),
      dashboardApi.getSalesTrend({ days: 7 }),
      dashboardApi.getStoreRank({ top_n: 10 }),
      dashboardApi.getTaskSummary(),
    ]);
    rawOverview.value = r1.data.data || {};
    dataDate.value = rawOverview.value.stat_date || "";
    pendingFields.value = rawOverview.value.pending_fields || [];
    trend.value = r2.data.data?.trend || [];
    storeRank.value = r3.data.data?.rank || [];
    taskSummary.value = r4.data.data || {};
  } catch (e) {
    console.error("驾驶舱数据加载失败", e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => { fetchData(); });
</script>

<style scoped>
.lux-dashboard-wrapper {
  background-color: #F8FAFC;
  padding: 0 24px 24px 24px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: #1E293B;
  min-height: 100vh;
  opacity: 0; transform: translateY(8px);
  transition: opacity 0.5s ease, transform 0.5s ease;
}
.lux-dashboard-wrapper.ready { opacity: 1; transform: translateY(0); }

.lux-clean-header {
  display: flex; justify-content: space-between; align-items: flex-end;
  padding: 28px 0 20px 0; margin-bottom: 24px;
  border-bottom: 1px solid #E2E8F0;
}
.header-right-meta { display: flex; align-items: center; gap: 12px; }
.lux-btn-refresh {
  width: 34px; height: 34px; border: none; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  color: #64748B; transition: all 0.2s;
}
.lux-btn-refresh:hover { color: #0F172A; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.lux-btn-refresh.spinning svg { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.lux-brand-title { display: flex; align-items: center; margin: 0 0 6px 0; }
.brand-en { font-size: 28px; font-weight: 800; letter-spacing: 5px; color: #0F172A; }
.brand-divider { width: 2px; height: 22px; background-color: #FF6A00; margin: 0 16px; }
.brand-zh { font-size: 22px; font-weight: 600; letter-spacing: 2px; color: #334155; }
.lux-brand-subtitle { margin: 0; color: #64748B; font-size: 13px; }
.date-tag {
  background: #FFFFFF; padding: 8px 16px; border-radius: 6px;
  font-size: 13px; color: #475569; font-weight: 500;
  box-shadow: 0 1px 3px rgba(0,0,0,0.02); border: 1px solid #E2E8F0;
  display: flex; align-items: center;
}
.live-dot { width: 6px; height: 6px; background-color: #10B981; border-radius: 50%; margin-right: 8px; box-shadow: 0 0 6px #10B981; }

.lux-section-title { font-size: 15px; font-weight: 700; display: flex; align-items: center; margin: 28px 0 16px 0; color: #0F172A; letter-spacing: 0.5px; }
.title-decor { width: 4px; height: 15px; background-color: #D4AF37; border-radius: 2px; margin-right: 8px; }
.title-decor.alert { background-color: #EF4444; }
.title-decor.dynamic { background-color: #FF6A00; }
.title-decor.task { background-color: #8B5CF6; }

.lux-grid-5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; }
.lux-grid-4 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.lux-grid-3 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }

.lux-main-split { display: grid; grid-template-columns: 1.55fr 1fr; gap: 24px; margin-top: 8px; }

.lux-crypto-card {
  background: #FFFFFF; border-radius: 8px; padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.02), 0 4px 12px rgba(15,23,42,0.01);
  position: relative; overflow: hidden; transition: all 0.3s ease;
  border: 1px solid rgba(226,232,240,0.7);
  animation: fadeUp 0.5s ease both;
}
@keyframes fadeUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
.lux-crypto-card:hover { transform: translateY(-2px); box-shadow: 0 10px 20px -5px rgba(15,23,42,0.06); border-color: #CBD5E1; }
.card-inner { display: flex; align-items: center; }
.card-icon {
  width: 42px; height: 42px; border-radius: 8px; background-color: #F8FAFC;
  margin-right: 14px; opacity: 0.65; display: flex; align-items: center; justify-content: center; color: #94A3B8;
}
.card-icon :deep(svg) { width: 22px; height: 22px; }
.lux-crypto-card:hover .card-icon { color: #FF6A00; opacity: 1; }
.card-info { display: flex; flex-direction: column; }
.card-label { font-size: 13px; color: #64748B; margin-bottom: 4px; }
.card-value { font-size: 24px; font-weight: 700; margin: 0; color: #0F172A; }
.card-value .unit { font-size: 12px; font-weight: 400; color: #94A3B8; margin-left: 2px; }
.highlight-gold { color: #B45309; }
.highlight-orange { color: #EA580C; }
.card-progress-bar { position: absolute; bottom: 0; left: 0; width: 100%; height: 3px; background-color: #F1F5F9; }
.card-progress-bar.bar-gold { background-color: #D4AF37; }
.card-progress-bar.bar-orange { background-color: #FF6A00; }

.lux-metric-card, .lux-risk-card {
  background: #FFFFFF; border-radius: 8px; padding: 20px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.01); transition: all 0.2s;
  border: 1px solid rgba(226,232,240,0.7);
}
.lux-metric-card:hover, .lux-risk-card:hover { border-color: #CBD5E1; background-color: #FAFBFD; }
.metric-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.metric-label, .risk-label { font-size: 13px; color: #475569; font-weight: 500; }
.risk-meta { margin-bottom: 8px; }
.metric-status-dot { width: 6px; height: 6px; border-radius: 50%; background-color: #CBD5E1; }
.metric-status-dot.active { background-color: #10B981; box-shadow: 0 0 8px #10B981; }
.metric-num, .risk-num { font-size: 24px; font-weight: 700; color: #0F172A; letter-spacing: -0.5px; }
.text-alert { color: #EF4444; }

.lux-shimmer-loader { display: flex; flex-direction: column; }
.shimmer-txt {
  font-size: 22px; font-weight: 700; color: #E2E8F0; position: relative;
  overflow: hidden; display: inline-block; width: max-content;
}
.shimmer-txt::after {
  content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.6), transparent);
  transform: translateX(-100%); animation: luxLoadingShimmer 1.6s infinite;
}
.shimmer-sub { font-size: 11px; color: #94A3B8; margin-top: 6px; display: flex; align-items: center; }
.shimmer-sub::before { content: ""; width: 4px; height: 4px; border-radius: 50%; background-color: #FF6A00; margin-right: 6px; animation: luxPulse 2s infinite; }
.alert-shimmer .shimmer-sub::before { background-color: #94A3B8; animation: none; }

.lux-chart-box {
  background: #FFFFFF; border-radius: 8px; padding: 0;
  position: relative; overflow: hidden;
  border: 1px solid rgba(226,232,240,0.7); height: 280px;
}
.lux-chart-stage { width: 100%; height: 280px; }
.echarts-canvas { width: 100% !important; height: 280px !important; }
.lux-blur-overlay {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(255,255,255,0.75); backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; text-align: center;
}
.overlay-content h3 { font-size: 15px; font-weight: 700; color: #0F172A; margin: 0 0 6px 0; }
.overlay-content p { font-size: 12px; color: #64748B; margin: 0; padding: 0 16px; line-height: 1.4; }
.pulse-radar {
  width: 10px; height: 10px; background-color: #FF6A00; border-radius: 50%;
  margin: 0 auto 12px auto; position: relative;
}
.pulse-radar::after {
  content: ""; position: absolute; width: 100%; height: 100%; top: 0; left: 0;
  border-radius: 50%; border: 2px solid #FF6A00; animation: luxRadarExpand 2s infinite ease-out;
}

.lux-task-board {
  background: #FFFFFF; border-radius: 8px; padding: 24px;
  display: flex; justify-content: space-around;
  border: 1px solid rgba(226,232,240,0.7); height: 102px; box-sizing: border-box;
}
.task-col { display: flex; flex-direction: column; align-items: center; }
.task-num { font-size: 28px; font-weight: 800; color: #475569; line-height: 1; margin-bottom: 6px; }
.task-num.danger-num { color: #EF4444; }
.task-tit { font-size: 12px; color: #94A3B8; }
.task-col.success .task-num { color: #10B981; }
.task-col.urgent .task-num { color: #D97706; }

.lux-developer-drawer { margin-top: 40px; }
.lux-details { background: #F1F5F9; border-radius: 6px; overflow: hidden; }
.lux-summary { padding: 12px 16px; font-size: 12px; color: #64748B; cursor: pointer; user-select: none; }
.lux-summary:hover { background: #E2E8F0; color: #334155; }
.drawer-inner-table { padding: 16px; background: #FAFBFD; border-top: 1px solid #E2E8F0; }
.table-row { display: flex; justify-content: space-between; padding: 8px 12px; font-size: 12px; border-bottom: 1px solid #F1F5F9; }
.table-row.header { font-weight: 600; color: #475569; border-bottom: 1px solid #E2E8F0; }
.code-field { font-family: monospace; color: #0F172A; background: #E2E8F0; padding: 2px 6px; border-radius: 4px; }
.status-badge.waiting { color: #94A3B8; font-style: italic; }

@keyframes luxLoadingShimmer { 100% { transform: translateX(100%); } }
@keyframes luxPulse { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }
@keyframes luxRadarExpand { 0% { transform: scale(1); opacity: 1; } 100% { transform: scale(3); opacity: 0; } }

@media (max-width: 1200px) {
  .lux-main-split { grid-template-columns: 1fr; }
  .lux-grid-5 { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 768px) {
  .lux-grid-5, .lux-grid-4, .lux-grid-3 { grid-template-columns: 1fr 1fr; }
  .lux-clean-header { flex-direction: column; align-items: flex-start; gap: 12px; }
}
</style>