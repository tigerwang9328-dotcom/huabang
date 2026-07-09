<template>
  <div class="ops-dashboard" :class="{ ready: !loading }">
    <section class="ops-hero">
      <div>
        <p class="eyebrow">HUABANG BUSINESS COMMAND CENTER</p>
        <h1>经营总览</h1>
        <p class="hero-sub">销售、库存、人力与AI诊断统一看板。所有已接入数据保持原接口口径，未接入项明确标识。</p>
      </div>
      <div class="hero-actions">
        <el-date-picker
          v-model="selectedDate"
          type="date"
          value-format="YYYY-MM-DD"
          :clearable="false"
          placeholder="选择日期"
          style="width: 160px"
          @change="onDateChange"
        />
        <span class="date-pill"><span class="live-dot"></span>数据日期：{{ dataDate || '加载中' }}</span>
        <button class="refresh-btn" :class="{ spinning: loading }" @click="fetchData" aria-label="刷新经营概览">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6M23 20v-6h-6"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
        </button>
      </div>
    </section>

    <section class="module-card api-panel">
      <div class="module-head">
        <div>
          <p class="module-kicker">API METRICS</p>
          <h2>公司经营核心 API 卡片</h2>
        </div>
        <span class="module-note">固定成本未接入前，纯利润按“待财务成本接入”处理</span>
      </div>
      <div class="api-grid">
        <div v-for="card in apiCards" :key="card.label" class="api-card" :class="card.tone">
          <span class="api-label">{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
          <small>{{ card.note }}</small>
        </div>
      </div>
    </section>

    <section class="module-card sales-panel">
      <div class="module-head">
        <div>
          <p class="module-kicker">SALES</p>
          <h2>销售模块</h2>
        </div>
        <span class="module-note">按线上 / 线下 / 门店三个维度看昨日经营</span>
      </div>
      <div class="sales-layout">
        <div class="channel-grid">
          <div v-for="item in channelCards" :key="item.label" class="channel-card">
            <span>{{ item.label }}</span>
            <strong>{{ item.amount }}</strong>
            <small>{{ item.meta }}</small>
          </div>
        </div>
        <div class="trend-box">
          <v-chart :option="trendOption" autoresize class="trend-chart" />
        </div>
      </div>

      <div class="store-section">
        <div class="subhead">
          <h3>线下门店昨日经营明细</h3>
          <span>{{ storeRank.length }} 家门店有销售流水</span>
        </div>
        <div class="store-table">
          <div class="store-row store-header">
            <span>排名</span><span>门店</span><span>销售额</span><span>实收</span><span>订单</span><span>客单价</span><span>件单数</span>
          </div>
          <div v-for="row in storeRows" :key="row.store_code" class="store-row">
            <span class="rank">{{ row.rank }}</span>
            <span class="store-name">{{ row.store_name || row.store_code }}</span>
            <span>{{ fmtMoney(row.net_sales) }}</span>
            <span>{{ fmtMoney(row.actual_pay_amount) }}</span>
            <span>{{ row.order_count || 0 }}</span>
            <span>{{ fmtMoney(row.avg_order_value) }}</span>
            <span>{{ formatDecimal(row.items_per_order) }}</span>
          </div>
          <div v-if="!storeRows.length" class="empty-row">暂无门店销售流水</div>
        </div>
      </div>
    </section>

    <section class="module-grid two-col">
      <div class="module-card inventory-panel">
        <div class="module-head compact">
          <div>
            <p class="module-kicker">INVENTORY</p>
            <h2>库存模块</h2>
          </div>
        </div>
        <div class="inventory-kpis">
          <div class="mini-kpi"><span>库存数量</span><strong>{{ metricDisplay('inventory_risk', 'total_inventory_qty') }}</strong></div>
          <div class="mini-kpi"><span>库存金额</span><strong>{{ moneyMetric('inventory_risk', 'inventory_amount') }}</strong></div>
          <div class="mini-kpi"><span>缺货SKU</span><strong>{{ metricDisplay('inventory_risk', 'low_stock_sku_count') }}</strong></div>
          <div class="mini-kpi"><span>高库存SKU</span><strong>{{ metricDisplay('inventory_risk', 'high_stock_sku_count') }}</strong></div>
        </div>
        <div class="category-list">
          <div class="subhead"><h3>按品类库存数量</h3><span>Top {{ inventoryCategories.length }}</span></div>
          <div v-for="cat in inventoryCategories" :key="cat.category_name" class="category-row">
            <div class="category-meta"><span>{{ cat.category_name }}</span><strong>{{ formatBigNum(cat.qty) }}件</strong></div>
            <div class="bar-track"><i :style="{ width: cat.percent + '%' }"></i></div>
          </div>
          <div v-if="!inventoryCategories.length" class="empty-row">暂无品类库存汇总</div>
        </div>
      </div>

      <div class="module-card hr-panel">
        <div class="module-head compact">
          <div>
            <p class="module-kicker">HUMAN RESOURCE</p>
            <h2>人力资源</h2>
          </div>
        </div>
        <div class="hr-grid">
          <div class="hr-card"><span>今日待处理任务</span><strong>{{ taskCards[0]?.value ?? 0 }}</strong><small>来自任务闭环</small></div>
          <div class="hr-card"><span>逾期任务</span><strong class="danger">{{ taskCards[1]?.value ?? 0 }}</strong><small>需主管复查</small></div>
          <div class="hr-card pending"><span>在岗人数</span><strong>待接入</strong><small>需钉钉组织/考勤口径</small></div>
          <div class="hr-card pending"><span>人效分析</span><strong>规划中</strong><small>销售额 / 工时 / 人员</small></div>
        </div>
        <div class="module-tip">补充建议：人力资源模块后续应接入“员工档案、考勤、排班、导购归属、人效排行”，才能支撑单店人效判断。</div>
      </div>
    </section>

    <section class="module-card ai-panel">
      <div class="module-head">
        <div>
          <p class="module-kicker">AI DIAGNOSIS</p>
          <h2>AI经营诊断</h2>
        </div>
        <router-link to="/app/ai-diagnosis" class="diagnosis-link">进入总体经营诊断</router-link>
      </div>
      <div class="diagnosis-grid">
        <div v-for="d in diagnosisCards" :key="d.title" class="diagnosis-card" :class="d.level">
          <span>{{ d.scope }}</span>
          <strong>{{ d.title }}</strong>
          <p>{{ d.desc }}</p>
        </div>
      </div>
    </section>

    <section class="module-card governance-panel">
      <details>
        <summary>数据治理与待接入清单 · {{ pendingFields.length }} 项</summary>
        <div class="pending-table" v-if="pendingFields.length">
          <div v-for="pf in pendingFields" :key="pf.field" class="pending-row">
            <code>{{ pf.group }}.{{ pf.field }}</code>
            <span>{{ pf.reason }}</span>
          </div>
        </div>
        <div v-else class="empty-row">当前经营概览核心字段已接入</div>
      </details>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";
import VChart from "vue-echarts";
import { dashboardApi } from "@/api/dashboard";

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const loading = ref(true);
const dataDate = ref("");
const pendingFields = ref<any[]>([]);
const trend = ref<any[]>([]);
const storeRank = ref<any[]>([]);
const rawOverview = ref<any>({});

const yesterday = new Date();
yesterday.setDate(yesterday.getDate() - 1);
const selectedDate = ref(yesterday.toISOString().slice(0, 10));

function onDateChange() { fetchData(); }

function metric(group: string, key: string) { return rawOverview.value?.[group]?.[key]; }
function isPendingValue(v: any) { return !v || v.status === "pending_data" || v.value === null || v.value === undefined; }
function metricDisplay(group: string, key: string) {
  const m = metric(group, key);
  if (isPendingValue(m)) return "待接入";
  return m.display || String(m.value ?? "--");
}
function numberMetric(group: string, key: string) {
  const m = metric(group, key);
  return isPendingValue(m) ? null : Number(m.value);
}
function fmtMoney(v: any): string {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (!Number.isFinite(n)) return "--";
  if (Math.abs(n) >= 10000) return "¥" + (n / 10000).toFixed(2) + "万";
  return "¥" + n.toFixed(0);
}
function moneyMetric(group: string, key: string) {
  const n = numberMetric(group, key);
  return n === null ? "待接入" : fmtMoney(n);
}
function formatBigNum(v: any): string {
  if (v === null || v === undefined || v === "") return "--";
  const n = Number(v);
  if (!Number.isFinite(n)) return "--";
  if (Math.abs(n) >= 10000) return (n / 10000).toFixed(1) + "万";
  return String(Math.round(n));
}
function formatDecimal(v: any): string {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : "--";
}

const goodsCost = computed(() => {
  const sales = numberMetric("business_metrics", "yesterday_sales");
  const grossProfit = numberMetric("business_metrics", "gross_profit");
  if (sales === null || grossProfit === null) return null;
  return Math.max(0, sales - grossProfit);
});

const apiCards = computed(() => [
  { label: "销售额", value: moneyMetric("business_metrics", "yesterday_sales"), note: "公司全渠道当前以百胜小票口径为准", tone: "orange" },
  { label: "实收金额", value: moneyMetric("business_metrics", "yesterday_actual_pay_amount"), note: "收钱吧/现金/线上/充值-退款口径", tone: "blue" },
  { label: "销售量", value: metricDisplay("business_metrics", "yesterday_items"), note: "昨日销售件数，按小票商品明细汇总", tone: "green" },
  { label: "商品成本", value: goodsCost.value === null ? "待接入" : fmtMoney(goodsCost.value), note: "销售额 - 毛利额，成本缺失时为预估", tone: "slate" },
  { label: "固定成本", value: "待接入", note: "房租 / 水电 / 人员工资需财务接入", tone: "muted" },
  { label: "利润率", value: metricDisplay("business_metrics", "gross_margin") + "%", note: "当前为毛利率，待固定成本后切净利率", tone: "gold" },
  { label: "纯利润", value: "待接入", note: "需商品成本 + 固定成本完整接入", tone: "muted" },
]);

const currentTrend = computed(() => trend.value[trend.value.length - 1] || {});
const channelCards = computed(() => {
  const c = currentTrend.value;
  const total = Number(c.total_sales || 0);
  const offline = Number(c.offline_sales || 0);
  const online = Number(c.online_sales || 0);
  return [
    { label: "线下销售", amount: fmtMoney(offline), meta: `${total ? ((offline / total) * 100).toFixed(1) : 0}% · ${c.order_count || 0} 单` },
    { label: "线上销售", amount: fmtMoney(online), meta: online > 0 ? `${((online / total) * 100).toFixed(1)}%` : "线上平台待接入" },
    { label: "销售件数", amount: formatBigNum(c.item_count || numberMetric("business_metrics", "yesterday_items")), meta: "昨日销售量" },
  ];
});

function storeDisplayName(s: any): string {
  const code = String(s.store_code || "");
  const rawName = String(s.store_name || "").trim();
  const name = code ? rawName.replace(new RegExp(`^${code}[\\s\\-_/｜|]*`), "").trim() : rawName;
  return name ? `${name} ${code}` : `门店 ${code}`;
}

const storeRows = computed(() => storeRank.value.map((s: any) => ({ ...s, store_name: storeDisplayName(s) })));

const inventoryCategories = computed(() => {
  const rows = rawOverview.value?.inventory_by_category || [];
  const max = Math.max(...rows.map((r: any) => Math.abs(Number(r.qty || 0))), 1);
  return rows.map((r: any) => ({ ...r, percent: Math.min(100, Math.round(Math.abs(Number(r.qty || 0)) / max * 100)) }));
});

const taskCards = computed(() => {
  const m = rawOverview.value?.task_execution || {};
  return [
    { label: "待处理", value: m.pending_task_count?.value ?? 0 },
    { label: "已逾期", value: m.overdue_task_count?.value ?? 0 },
    { label: "已完成", value: m.completed_task_count?.value ?? 0 },
  ];
});

const diagnosisCards = computed(() => {
  const sales = numberMetric("business_metrics", "yesterday_sales") || 0;
  const orders = numberMetric("business_metrics", "yesterday_orders") || 0;
  const lowStock = numberMetric("inventory_risk", "low_stock_sku_count") || 0;
  const fixedCostPending = true;
  return [
    { scope: "总体", title: sales > 0 ? "经营数据已形成闭环" : "销售流水偏弱或未同步", desc: sales > 0 ? `昨日销售 ${fmtMoney(sales)}，订单 ${orders} 单，可进入门店复盘。` : "请检查百胜小票同步与门店开单情况。", level: sales > 0 ? "ok" : "warn" },
    { scope: "销售", title: orders <= 3 ? "订单数偏低，需看门店明细" : "订单量正常波动", desc: "建议结合线下门店明细查看是否集中在单店。", level: orders <= 3 ? "warn" : "ok" },
    { scope: "库存", title: lowStock > 0 ? "存在缺货SKU风险" : "库存风险较低", desc: `当前缺货SKU ${formatBigNum(lowStock)}，建议优先补齐爆款核心尺码。`, level: lowStock > 0 ? "danger" : "ok" },
    { scope: "财务", title: fixedCostPending ? "固定成本未接入" : "利润口径完整", desc: "房租、水电、人员工资接入后才能输出纯利润与净利率。", level: "warn" },
  ];
});

const trendOption = computed(() => ({
  tooltip: { trigger: "axis" },
  legend: { top: 8, right: 12, textStyle: { color: "#64748B" } },
  grid: { left: 8, right: 16, top: 42, bottom: 18, containLabel: true },
  xAxis: { type: "category", data: trend.value.map((t: any) => (t.date || "").slice(5)), axisLabel: { color: "#94A3B8" } },
  yAxis: { type: "value", axisLabel: { color: "#94A3B8", formatter: (v: number) => v >= 10000 ? (v / 10000).toFixed(0) + "万" : String(v) }, splitLine: { lineStyle: { color: "#EEF2F7" } } },
  series: [
    { name: "线下", type: "line", smooth: true, data: trend.value.map((t: any) => t.offline_sales || 0), lineStyle: { color: "#FF6A00", width: 3 }, itemStyle: { color: "#FF6A00" }, areaStyle: { color: "rgba(255,106,0,0.12)" } },
    { name: "线上", type: "line", smooth: true, data: trend.value.map((t: any) => t.online_sales || 0), lineStyle: { color: "#2563EB", width: 2 }, itemStyle: { color: "#2563EB" } },
  ],
}));

async function fetchData() {
  loading.value = true;
  try {
    const [r1, r2, r3] = await Promise.all([
      dashboardApi.getOverview({ stat_date: selectedDate.value }),
      dashboardApi.getSalesTrend({ days: 7, end_date: selectedDate.value }),
      dashboardApi.getStoreRank({ stat_date: selectedDate.value, top_n: 20 }),
    ]);
    rawOverview.value = r1.data.data || {};
    dataDate.value = rawOverview.value.stat_date || "";
    pendingFields.value = rawOverview.value.pending_fields || [];
    trend.value = r2.data.data?.trend || [];
    storeRank.value = r3.data.data?.rank || [];
  } catch (e) {
    console.error("经营概览数据加载失败", e);
  } finally {
    loading.value = false;
  }
}

onMounted(fetchData);
</script>

<style scoped>
.ops-dashboard { min-height: 100vh; padding: 0 24px 28px; background: #F6F8FB; color: #0F172A; opacity: 0; transform: translateY(8px); transition: .35s ease; }
.ops-dashboard.ready { opacity: 1; transform: translateY(0); }
.ops-hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; padding: 28px 0 22px; border-bottom: 1px solid #E2E8F0; }
.eyebrow, .module-kicker { margin: 0 0 6px; font-size: 11px; letter-spacing: .16em; color: #C0762A; font-weight: 800; }
.ops-hero h1 { margin: 0; font-size: 30px; letter-spacing: .08em; }
.hero-sub { margin: 8px 0 0; color: #64748B; font-size: 13px; }
.hero-actions { display: flex; align-items: center; gap: 12px; }
.date-pill { background: #fff; border: 1px solid #E2E8F0; border-radius: 999px; padding: 8px 14px; font-size: 13px; color: #475569; display: inline-flex; align-items: center; gap: 8px; }
.live-dot { width: 7px; height: 7px; background: #10B981; border-radius: 50%; box-shadow: 0 0 8px #10B981; }
.refresh-btn { width: 36px; height: 36px; border-radius: 50%; border: 0; background: #fff; color: #64748B; display: grid; place-items: center; cursor: pointer; box-shadow: 0 1px 4px rgba(15,23,42,.08); }
.refresh-btn svg { width: 16px; height: 16px; }
.refresh-btn.spinning svg { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.module-card { background: #fff; border: 1px solid #E2E8F0; border-radius: 16px; padding: 22px; margin-top: 22px; box-shadow: 0 12px 32px rgba(15,23,42,.04); }
.module-head { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; margin-bottom: 18px; }
.module-head.compact { margin-bottom: 14px; }
.module-head h2 { margin: 0; font-size: 20px; }
.module-note { color: #94A3B8; font-size: 12px; }
.api-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 14px; }
.api-card { border-radius: 14px; padding: 16px; min-height: 112px; background: #F8FAFC; border: 1px solid #EEF2F7; }
.api-card span, .channel-card span, .mini-kpi span, .hr-card span { display:block; color:#64748B; font-size:12px; margin-bottom:8px; }
.api-card strong { display:block; font-size:22px; margin-bottom:8px; }
.api-card small, .channel-card small, .hr-card small { color:#94A3B8; font-size:11px; line-height:1.45; }
.api-card.orange { background:#FFF7ED; border-color:#FED7AA; } .api-card.blue { background:#EFF6FF; border-color:#BFDBFE; } .api-card.green { background:#F0FDF4; border-color:#BBF7D0; } .api-card.gold { background:#FEFCE8; border-color:#FDE68A; } .api-card.slate { background:#F8FAFC; } .api-card.muted { opacity:.78; }
.sales-layout { display:grid; grid-template-columns: 340px 1fr; gap:18px; }
.channel-grid { display:grid; gap:12px; }
.channel-card { border:1px solid #EEF2F7; border-radius:14px; padding:18px; background:#FAFBFD; }
.channel-card strong { font-size:24px; }
.trend-box { height: 286px; border:1px solid #EEF2F7; border-radius:14px; overflow:hidden; }
.trend-chart { width:100%; height:286px; }
.store-section { margin-top:20px; }
.subhead { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
.subhead h3 { margin:0; font-size:15px; } .subhead span { color:#94A3B8; font-size:12px; }
.store-table { border:1px solid #EEF2F7; border-radius:14px; overflow:hidden; }
.store-row { display:grid; grid-template-columns: 60px 1.4fr repeat(5, 1fr); gap:12px; padding:12px 14px; border-bottom:1px solid #F1F5F9; font-size:13px; align-items:center; }
.store-row:last-child { border-bottom:0; } .store-header { background:#F8FAFC; color:#64748B; font-weight:700; } .rank { font-weight:800; color:#C0762A; } .store-name { font-weight:700; }
.module-grid.two-col { display:grid; grid-template-columns: 1.15fr .85fr; gap:22px; }
.inventory-kpis, .hr-grid { display:grid; grid-template-columns: repeat(2,1fr); gap:12px; }
.mini-kpi, .hr-card { background:#F8FAFC; border:1px solid #EEF2F7; border-radius:14px; padding:16px; }
.mini-kpi strong, .hr-card strong { font-size:22px; } .hr-card strong.danger { color:#EF4444; } .hr-card.pending strong { color:#94A3B8; font-size:18px; }
.category-list { margin-top:18px; }
.category-row { margin-top:12px; }
.category-meta { display:flex; justify-content:space-between; font-size:13px; margin-bottom:7px; }
.category-meta strong { color:#0F172A; }
.bar-track { height:8px; background:#EEF2F7; border-radius:999px; overflow:hidden; } .bar-track i { display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,#D4AF37,#FF6A00); }
.module-tip { margin-top:14px; padding:12px; border-radius:12px; background:#FFFBEB; color:#92400E; font-size:12px; line-height:1.6; }
.diagnosis-link { color:#C05621; font-size:13px; font-weight:700; text-decoration:none; }
.diagnosis-grid { display:grid; grid-template-columns: repeat(4,1fr); gap:14px; }
.diagnosis-card { border-radius:14px; padding:16px; border:1px solid #E2E8F0; background:#FAFBFD; }
.diagnosis-card span { color:#94A3B8; font-size:12px; } .diagnosis-card strong { display:block; margin:8px 0; font-size:16px; } .diagnosis-card p { margin:0; color:#64748B; font-size:12px; line-height:1.55; }
.diagnosis-card.ok { border-color:#BBF7D0; background:#F0FDF4; } .diagnosis-card.warn { border-color:#FDE68A; background:#FFFBEB; } .diagnosis-card.danger { border-color:#FECACA; background:#FEF2F2; }
.governance-panel { margin-bottom:20px; } details summary { cursor:pointer; color:#64748B; font-size:13px; font-weight:700; } .pending-table { margin-top:14px; border-top:1px solid #EEF2F7; } .pending-row { display:flex; justify-content:space-between; gap:16px; padding:10px 0; border-bottom:1px solid #F1F5F9; font-size:12px; } code { background:#F1F5F9; padding:2px 6px; border-radius:6px; color:#0F172A; }
.empty-row { padding:18px; color:#94A3B8; text-align:center; font-size:13px; }
@media (max-width: 1440px) { .api-grid { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 1280px) { .api-grid { grid-template-columns: repeat(3, 1fr); } .sales-layout, .module-grid.two-col { grid-template-columns: 1fr; } .diagnosis-grid { grid-template-columns: repeat(2,1fr); } }
@media (max-width: 760px) { .ops-hero, .module-head { flex-direction:column; align-items:flex-start; } .hero-actions { flex-wrap:wrap; } .api-grid, .inventory-kpis, .hr-grid, .diagnosis-grid { grid-template-columns:1fr; } .store-row { grid-template-columns: 44px 1fr; } .store-row span:nth-child(n+3) { display:none; } }
</style>
