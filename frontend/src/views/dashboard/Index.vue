<template>
  <div class="ops-dashboard command-light-page" :class="{ ready: !loading }">
    <section class="ops-hero">
      <div>
        <p class="eyebrow">经营管理 / 公司经营总览</p>
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

    <section class="decision-strip" v-if="commandCenter.available">
      <div>
        <p class="module-kicker">昨日经营结论</p>
        <strong>{{ commandCenter.decision_summary }}</strong>
        <div class="freshness-line">
          <span v-for="item in freshnessItems" :key="item.label">{{ item.label }} {{ item.value }}</span>
        </div>
      </div>
      <el-button type="primary" plain @click="router.push('/app/report')">查看经营日报</el-button>
    </section>

    <section class="module-card api-panel">
      <div class="module-head">
        <div>
          <p class="module-kicker">核心指标</p>
          <h2>公司经营核心指标</h2>
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
          <p class="module-kicker">销售经营</p>
          <h2>销售分析</h2>
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
            <p class="module-kicker">库存经营</p>
            <h2>库存分析</h2>
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
            <p class="module-kicker">任务与人效</p>
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

    <section class="decision-grid" v-if="commandCenter.available">
      <div class="module-card risk-panel">
        <div class="module-head compact">
          <div><p class="module-kicker">经营风险</p><h2>重大异常</h2></div>
          <el-tag type="danger" effect="plain">{{ commandCenter.major_risks?.length || 0 }} 项</el-tag>
        </div>
        <div v-if="commandCenter.major_risks?.length" class="decision-list">
          <button v-for="risk in commandCenter.major_risks" :key="`${risk.exception_type}-${risk.id}`" class="decision-item" @click="openRisk(risk)">
            <el-tag :type="risk.severity === 'critical' ? 'danger' : 'warning'" size="small">{{ risk.severity === 'critical' ? '紧急' : '风险' }}</el-tag>
            <span><strong>{{ risk.description }}</strong><small>{{ risk.store_code || '公司' }} · {{ risk.product_code || risk.sku_code || risk.exception_type }}</small></span>
          </button>
        </div>
        <el-empty v-else description="当前没有重大异常" :image-size="54" />
      </div>
      <div class="module-card action-panel">
        <div class="module-head compact">
          <div><p class="module-kicker">任务闭环</p><h2>今日行动清单</h2></div>
          <el-button text type="primary" @click="router.push('/app/task')">全部任务</el-button>
        </div>
        <div v-if="commandCenter.today_actions?.length" class="decision-list">
          <button v-for="task in commandCenter.today_actions" :key="task.id" class="decision-item" @click="router.push(`/app/task/${task.id}`)">
            <el-tag :type="task.status === 'overdue' ? 'danger' : 'info'" size="small">{{ taskStatus(task.status) }}</el-tag>
            <span><strong>{{ task.title }}</strong><small>{{ task.assignee_name || roleName(task.assignee_role) }} · 截止 {{ task.due_date || '待确认' }}</small></span>
          </button>
        </div>
        <el-empty v-else description="今日暂无待办" :image-size="54" />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
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
const commandCenter = ref<any>({});
const router = useRouter();

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

function ccMetric(key: string) { return commandCenter.value?.core_metrics?.[key]; }
function ccDisplay(key: string, type: "money" | "count" | "percent" = "count") {
  const item = ccMetric(key);
  if (!item || item.value === null || item.status === "pending_data") return "待接入";
  if (type === "money") return fmtMoney(item.value);
  if (type === "percent") return `${(Number(item.value) * 100).toFixed(1)}%`;
  return Number(item.value).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}
function metricNote(key: string, fallback: string) {
  const item = ccMetric(key);
  const labels: Record<string, string> = { ready: "已就绪", estimated: "预估", pending_data: "待接入", stale: "数据陈旧" };
  return item ? `${labels[item.status] || item.status} · ${item.source}` : fallback;
}
const apiCards = computed(() => [
  { label: "销售额", value: ccDisplay("sales", "money"), note: metricNote("sales", "百胜小票"), tone: "orange" },
  { label: "线下销售", value: moneyMetric("business_metrics", "yesterday_offline_sales"), note: "百胜非011结算", tone: "orange" },
  { label: "线上销售", value: moneyMetric("business_metrics", "yesterday_online_sales"), note: "百胜011线上支付", tone: "blue" },
  { label: "实收金额", value: ccDisplay("actual_pay", "money"), note: metricNote("actual_pay", "支付明细"), tone: "blue" },
  { label: "订单数", value: ccDisplay("orders"), note: metricNote("orders", "百胜小票"), tone: "green" },
  { label: "销售件数", value: ccDisplay("items"), note: metricNote("items", "百胜小票"), tone: "slate" },
  { label: "客单价", value: ccDisplay("avg_order_value", "money"), note: metricNote("avg_order_value", "百胜小票"), tone: "gold" },
  { label: "连带率", value: ccDisplay("items_per_order"), note: metricNote("items_per_order", "百胜小票"), tone: "slate" },
  { label: "毛利额", value: ccDisplay("gross_profit", "money"), note: metricNote("gross_profit", "百胜成本"), tone: "orange" },
  { label: "毛利率", value: ccDisplay("gross_margin", "percent"), note: metricNote("gross_margin", "百胜成本"), tone: "gold" },
  { label: "库存金额", value: ccDisplay("inventory_amount", "money"), note: metricNote("inventory_amount", "外穿衣物库存"), tone: "blue" },
  { label: "90天以上库存", value: ccDisplay("age_90_amount", "money"), note: metricNote("age_90_amount", "FIFO库龄"), tone: "muted" },
  { label: "VIP余额", value: ccDisplay("vip_balance", "money"), note: metricNote("vip_balance", "CZ_DQJE"), tone: "green" },
  { label: "VIP销售", value: ccDisplay("vip_sales", "money"), note: metricNote("vip_sales", "百胜会员小票"), tone: "slate" },
]);

const freshnessItems = computed(() => {
  const sources = commandCenter.value?.data_quality?.source_freshness || {};
  return [
    { label: "销售", value: sources.sales?.business_date || "-" },
    { label: "库存", value: sources.inventory?.snapshot_date || "-" },
    { label: "会员", value: String(sources.member?.updated_at || "-").replace("T", " ").slice(0, 16) },
  ];
});

function taskStatus(status: string) { return ({ draft: "待确认", pending: "待处理", processing: "处理中", overdue: "已逾期" } as any)[status] || status; }
function roleName(role: string) { return ({ store_manager: "店长", operation: "运营" } as any)[role] || role || "待定责任人"; }
function openRisk(risk: any) {
  if (String(risk.exception_type || "").startsWith("inventory_")) router.push("/app/inventory?tab=warning");
  else router.push("/app/warning");
}

const currentTrend = computed(() => trend.value[trend.value.length - 1] || {});
const channelCards = computed(() => {
  const c = currentTrend.value;
  const offline = Number(numberMetric("business_metrics", "yesterday_offline_sales") ?? 0);
  const online = Number(numberMetric("business_metrics", "yesterday_online_sales") ?? 0);
  const total = offline + online;
  return [
    { label: "线下销售", amount: fmtMoney(offline), meta: `${total ? ((offline / total) * 100).toFixed(2) : "0.00"}% · 百胜非011结算` },
    { label: "线上销售", amount: fmtMoney(online), meta: `${total ? ((online / total) * 100).toFixed(2) : "0.00"}% · 百胜011线上支付` },
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
    commandCenter.value = rawOverview.value.command_center || {};
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
.ops-dashboard { min-height: 100vh; padding: 0 24px 28px; background: #F6F8FB; color: #0F172A; }
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
.decision-strip { margin-top:18px; padding:16px 18px; background:#FFFBEB; color:#78350F; border:1px solid #FDE7B2; border-left:4px solid #F59E0B; border-radius:8px; display:flex; align-items:center; justify-content:space-between; gap:20px; }
.decision-strip strong { font-size:17px; line-height:1.7; }
.freshness-line { display:flex; gap:18px; margin-top:8px; color:#92704A; font-size:12px; }
.module-card { background: #fff; border: 1px solid #E2E8F0; border-radius: 8px; padding: 22px; margin-top: 22px; box-shadow: 0 8px 24px rgba(15,23,42,.04); }
.module-head { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; margin-bottom: 18px; }
.module-head.compact { margin-bottom: 14px; }
.module-head h2 { margin: 0; font-size: 20px; }
.module-note { color: #94A3B8; font-size: 12px; }
.api-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
.api-card { border-radius: 6px; padding: 14px; min-height: 96px; background: #F8FAFC; border: 1px solid #EEF2F7; }
.api-card span, .channel-card span, .mini-kpi span, .hr-card span { display:block; color:#64748B; font-size:12px; margin-bottom:8px; }
.api-card strong { display:block; font-size:22px; margin-bottom:8px; }
.api-card small, .channel-card small, .hr-card small { color:#94A3B8; font-size:11px; line-height:1.45; }
.api-card.orange { background:#FFF7ED; border-color:#FED7AA; } .api-card.blue { background:#EFF6FF; border-color:#BFDBFE; } .api-card.green { background:#F0FDF4; border-color:#BBF7D0; } .api-card.gold { background:#FEFCE8; border-color:#FDE68A; } .api-card.slate { background:#F8FAFC; } .api-card.muted { opacity:.78; }
.decision-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
.decision-list { display:grid; gap:8px; }
.decision-item { width:100%; display:grid; grid-template-columns:58px 1fr; align-items:start; gap:10px; padding:10px 0; background:transparent; border:0; border-bottom:1px solid #EEF2F7; text-align:left; cursor:pointer; }
.decision-item:last-child { border-bottom:0; }
.decision-item span { min-width:0; }
.decision-item strong { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#0F172A; font-size:13px; }
.decision-item small { display:block; margin-top:5px; color:#94A3B8; font-size:11px; }
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
.governance-panel { margin-bottom:20px; } details summary { cursor:pointer; color:#64748B; font-size:13px; font-weight:700; } .pending-table { margin-top:14px; border-top:1px solid #EEF2F7; } .pending-row { display:flex; justify-content:space-between; gap:16px; padding:10px 0; border-bottom:1px solid #F1F5F9; font-size:12px; } code { background:#F1F5F9; padding:2px 6px; border-radius:6px; color:#0F172A; }
.empty-row { padding:18px; color:#94A3B8; text-align:center; font-size:13px; }
@media (max-width: 1440px) { .api-grid { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 1280px) { .api-grid { grid-template-columns: repeat(3, 1fr); } .sales-layout, .module-grid.two-col, .decision-grid { grid-template-columns: 1fr; } }
@media (max-width: 760px) { .ops-dashboard { padding:0 0 20px; } .ops-hero, .module-head, .decision-strip { flex-direction:column; align-items:flex-start; } .hero-actions, .freshness-line { width:100%; flex-wrap:wrap; } .hero-actions .el-date-editor { flex:1; min-width:150px; } .date-pill { max-width:100%; } .api-grid, .inventory-kpis, .hr-grid { grid-template-columns:1fr; } .module-card { padding:16px; } .store-row { grid-template-columns: 44px 1fr; } .store-row span:nth-child(n+3) { display:none; } }
</style>
