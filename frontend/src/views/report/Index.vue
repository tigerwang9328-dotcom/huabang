<template>
  <div class="report-page command-light-page" v-loading="loading">
    <header class="report-head">
      <div>
        <p class="eyebrow">经营管理 / 每日经营快照</p>
        <h1>经营日报</h1>
        <p>{{ report.ai_summary || "日报数据生成中" }}</p>
      </div>
      <div class="head-actions">
        <el-date-picker v-model="selectedDate" type="date" value-format="YYYY-MM-DD" :clearable="false" @change="loadReport" />
        <el-button type="primary" @click="loadReport">刷新</el-button>
      </div>
    </header>

    <section class="quality-band">
      <div><span>销售数据</span><strong>{{ freshness.sales?.business_date || selectedDate }}</strong></div>
      <div><span>库存快照</span><strong>{{ freshness.inventory?.snapshot_date || "待同步" }}</strong></div>
      <div><span>会员余额</span><strong>{{ shortTime(freshness.member?.updated_at) }}</strong></div>
      <div><span>成本</span><el-tag :type="report.is_cost_complete ? 'success' : 'warning'">{{ report.is_cost_complete ? "完整" : "预估" }}</el-tag></div>
      <div><span>费用</span><el-tag type="info">{{ report.is_finance_complete ? "完整" : "待接入" }}</el-tag></div>
    </section>

    <section class="metric-grid">
      <article v-for="item in metrics" :key="item.label">
        <span>{{ item.label }}</span><strong>{{ item.value }}</strong><small>{{ item.note }}</small>
      </article>
    </section>

    <section class="panel ai-advice-panel">
      <div class="panel-title">
        <div><h2>AI经营顾问</h2><span>{{ commandConclusion.executive_summary || "等待经营建议" }}</span></div>
        <div class="ai-meta"><el-tag :type="commandConclusion.mode === 'model' ? 'success' : 'info'">{{ commandConclusion.mode === "model" ? "大模型建议" : "确定性模板" }}</el-tag><span>{{ commandConclusion.model_used || report.ai_model_used || "deterministic_rules" }} · {{ shortTime(commandConclusion.generated_at || report.ai_generated_at) }}</span></div>
      </div>
      <div class="advice-grid">
        <div><h3>关键发现</h3><ul><li v-for="item in commandConclusion.key_findings || []" :key="item.title"><strong>{{ item.title }} · {{ confidenceLabel(item.confidence) }}</strong><p>{{ item.explanation }}</p><small v-for="ref in item.evidence_refs || []" :key="ref">{{ evidenceLabel(ref) }}</small></li></ul><el-empty v-if="!(commandConclusion.key_findings || []).length" description="暂无模型关键发现" :image-size="50" /></div>
        <div><h3>优先行动</h3><ul><li v-for="item in commandConclusion.recommendations || []" :key="item.title"><strong>{{ item.title }}</strong><p>{{ item.reason }} · {{ item.responsible_role || "待主管确认" }}</p><small v-for="ref in item.evidence_refs || []" :key="ref">{{ evidenceLabel(ref) }}</small></li></ul><el-empty v-if="!(commandConclusion.recommendations || []).length" description="暂无候选行动" :image-size="50" /></div>
        <div class="limitations"><h3>数据限制</h3><ul><li v-for="item in commandConclusion.limitations || []" :key="item">{{ item }}</li></ul><p v-if="commandConclusion.fallback_reason">回退原因：{{ commandConclusion.fallback_reason }}</p></div>
      </div>
    </section>

    <section class="report-grid">
      <div class="panel">
        <div class="panel-title"><h2>库存与会员资产</h2><span>外穿衣物 / 白名单10编码</span></div>
        <div class="asset-list">
          <div><span>库存金额</span><strong>{{ money(report.total_inventory_amount) }}</strong></div>
          <div><span>库存件数</span><strong>{{ number(report.inventory_total_qty) }}</strong></div>
          <div><span>90天以上库存</span><strong>{{ money(report.age_90_plus_amount) }}</strong></div>
          <div><span>180天以上库存</span><strong>{{ money(report.age_180_plus_amount) }}</strong></div>
          <div><span>库龄未知</span><strong>{{ number(report.inventory_age_unknown_qty) }} 件</strong></div>
          <div><span>VIP正余额</span><strong>{{ money(report.vip_balance) }}</strong></div>
          <div><span>VIP负余额人数</span><strong>{{ number(report.vip_negative_balance_count) }}</strong></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-title"><h2>数据完整性</h2><span>{{ report.report_date }}</span></div>
        <div class="status-list">
          <div v-for="(status, key) in statuses" :key="key"><span>{{ statusName(String(key)) }}</span><el-tag :type="tagType(String(status))">{{ statusLabel(String(status)) }}</el-tag></div>
        </div>
      </div>
    </section>

    <section class="panel history-panel">
      <div class="panel-title"><h2>近14日经营记录</h2><span>销售、效率、毛利与VIP · 点击行切换日报</span></div>
      <el-table :data="history" size="small" stripe class="history-table" @row-click="selectHistory">
        <el-table-column prop="report_date" label="日期" width="110" />
        <el-table-column label="销售额" width="116" align="right" header-align="right"><template #default="{ row }"><strong>{{ historyMoney(row.total_sales) }}</strong></template></el-table-column>
        <el-table-column label="实收金额" width="116" align="right" header-align="right"><template #default="{ row }">{{ historyMoney(row.actual_pay_amount) }}</template></el-table-column>
        <el-table-column label="订单" width="68" align="right" header-align="right"><template #default="{ row }">{{ historyNumber(row.order_count) }}</template></el-table-column>
        <el-table-column label="件数" width="68" align="right" header-align="right"><template #default="{ row }">{{ historyNumber(row.item_count) }}</template></el-table-column>
        <el-table-column label="客单价" width="94" align="right" header-align="right"><template #default="{ row }">{{ historyMoney(row.avg_order_value, 0) }}</template></el-table-column>
        <el-table-column label="连带率" width="80" align="right" header-align="right"><template #default="{ row }">{{ historyDecimal(row.items_per_order) }}</template></el-table-column>
        <el-table-column label="折扣率" width="80" align="right" header-align="right"><template #default="{ row }">{{ historyPercent(row.avg_discount_rate) }}</template></el-table-column>
        <el-table-column label="退货率" width="80" align="right" header-align="right"><template #default="{ row }">{{ historyPercent(row.return_rate) }}</template></el-table-column>
        <el-table-column label="毛利额" width="108" align="right" header-align="right"><template #default="{ row }">{{ historyMoney(row.gross_profit) }}</template></el-table-column>
        <el-table-column label="毛利率" width="80" align="right" header-align="right"><template #default="{ row }">{{ historyPercent(row.gross_margin) }}</template></el-table-column>
        <el-table-column label="VIP销售" width="108" align="right" header-align="right"><template #default="{ row }">{{ historyMoney(row.vip_sales_amount) }}</template></el-table-column>
        <el-table-column label="成本状态" width="100"><template #default="{ row }"><el-tag :type="row.is_cost_complete ? 'success' : 'warning'" size="small">{{ row.is_cost_complete ? "已就绪" : "预估" }}</el-tag></template></el-table-column>
        <el-table-column label="数据状态" width="100"><template #default="{ row }"><el-tag :type="dataStatusType(row.data_quality_status)" size="small">{{ dataStatusLabel(row.data_quality_status) }}</el-tag></template></el-table-column>
      </el-table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { dashboardApi } from "@/api/dashboard";

const loading = ref(false);
const report = ref<any>({});
const history = ref<any[]>([]);
const yesterday = new Date();
yesterday.setDate(yesterday.getDate() - 1);
const selectedDate = ref(yesterday.toISOString().slice(0, 10));
const freshness = computed(() => report.value.source_freshness || {});
const statuses = computed(() => report.value.metric_status || {});
const commandConclusion = computed(() => report.value.command_conclusion || {});

function money(value: any) { const n = Number(value || 0); return `¥${n.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`; }
function number(value: any) { return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 2 }); }
function percent(value: any) { return `${(Number(value || 0) * 100).toFixed(1)}%`; }
function hasValue(value: any) { return value !== null && value !== undefined && value !== ""; }
function historyMoney(value: any, digits = 2) { return hasValue(value) ? `¥${Number(value).toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}` : "--"; }
function historyNumber(value: any) { return hasValue(value) ? Number(value).toLocaleString("zh-CN") : "--"; }
function historyDecimal(value: any) { return hasValue(value) ? Number(value).toFixed(2) : "--"; }
function historyPercent(value: any) { return hasValue(value) ? `${(Number(value) * 100).toFixed(1)}%` : "--"; }
function shortTime(value: any) { return value ? String(value).replace("T", " ").slice(0, 16) : "待同步"; }
function statusLabel(value: string) { return ({ ready: "已就绪", estimated: "预估", pending_data: "待接入", stale: "数据陈旧" } as any)[value] || value; }
function tagType(value: string) { return ({ ready: "success", estimated: "warning", pending_data: "info", stale: "danger" } as any)[value] || "info"; }
function dataStatusLabel(value: string) { return ({ normal: "完整", warning: "需关注" } as any)[value] || "需关注"; }
function dataStatusType(value: string) { return value === "normal" ? "success" : "warning"; }
function statusName(key: string) { return ({ sales: "销售", actual_pay: "实收", gross_profit: "毛利", online_sales: "线上销售", inventory: "库存", vip_balance: "VIP余额", operating_profit: "经营利润" } as any)[key] || key; }
function confidenceLabel(value: string) { return ({ high: "高置信", medium: "中置信", low: "低置信" } as any)[value] || "待核验"; }
function evidenceLabel(ref: string) {
  const fact = (commandConclusion.value.facts || []).find((item: any) => item.fact_id === ref);
  if (fact) return `${fact.label}：${fact.value}（${fact.status}）`;
  const risk = (commandConclusion.value.risks || []).find((item: any) => item.rule_id === ref);
  return risk ? `${risk.title}（${risk.source}）` : ref;
}

const metrics = computed(() => [
  { label: "销售额", value: money(report.value.total_sales), note: "固定7家销售门店" },
  { label: "实收金额", value: money(report.value.actual_pay_amount), note: "支付明细口径" },
  { label: "订单数", value: number(report.value.order_count), note: "有效小票" },
  { label: "销售件数", value: number(report.value.item_count), note: "净销售件数" },
  { label: "客单价", value: money(report.value.avg_order_value), note: "销售额 / 订单" },
  { label: "连带率", value: number(report.value.items_per_order), note: "件数 / 订单" },
  { label: "毛利额", value: money(report.value.gross_profit), note: report.value.is_cost_complete ? "已就绪" : "预估" },
  { label: "毛利率", value: percent(report.value.gross_margin), note: report.value.is_cost_complete ? "已就绪" : "预估" },
  { label: "VIP销售", value: money(report.value.vip_sales_amount), note: `占比 ${percent(report.value.vip_sales_ratio)}` },
  { label: "退货金额", value: money(report.value.return_amount), note: `退货率 ${percent(report.value.return_rate)}` },
]);

async function loadReport() {
  loading.value = true;
  try {
    const { data } = await dashboardApi.getBossDaily(selectedDate.value);
    report.value = data?.data || {};
  } catch (_) { ElMessage.error("经营日报加载失败"); }
  finally { loading.value = false; }
}
async function loadHistory() {
  const { data } = await dashboardApi.listBossDaily({ days: 14 });
  history.value = data?.data?.items || [];
}
function selectHistory(row: any) { selectedDate.value = row.report_date; loadReport(); }
onMounted(async () => { await Promise.all([loadReport(), loadHistory()]); });
</script>

<style scoped>
.report-page { padding:24px; background:#F5F7FA; min-height:100%; color:#111827; }
.report-head { display:flex; justify-content:space-between; align-items:flex-end; gap:20px; padding-bottom:18px; border-bottom:1px solid #DDE3EA; }
.eyebrow { margin:0 0 5px; color:#B7791F; font-size:11px; font-weight:800; letter-spacing:.14em; }
h1 { margin:0; font-size:28px; } .report-head p:last-child { margin:8px 0 0; color:#5F6B7A; }
.head-actions { display:flex; gap:8px; }
.quality-band { display:grid; grid-template-columns:repeat(5,1fr); background:#fff; color:#334155; border:1px solid #E5EAF2; border-radius:8px; margin-top:16px; overflow:hidden; }
.quality-band div { padding:13px 16px; border-right:1px solid #EEF2F7; display:flex; align-items:center; justify-content:space-between; gap:10px; }
.quality-band span { color:#64748B; font-size:12px; } .quality-band strong { font-size:13px; color:#334155; }
.metric-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin-top:14px; }
.metric-grid article { background:#fff; border:1px solid #E1E6EC; border-radius:6px; padding:14px; min-height:92px; }
.metric-grid span,.metric-grid small { display:block; color:#7A8797; font-size:12px; }.metric-grid strong { display:block; margin:8px 0; font-size:21px; }
.report-grid { display:grid; grid-template-columns:1.4fr 1fr; gap:14px; }
.panel { margin-top:14px; background:#fff; border:1px solid #E1E6EC; border-radius:6px; padding:16px; }
.panel-title { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }.panel-title h2 { margin:0; font-size:16px; }.panel-title span { color:#8A96A5; font-size:12px; }
.ai-advice-panel .panel-title>div:first-child span { display:block; margin-top:6px; max-width:760px; color:#475569; line-height:1.6; }
.ai-meta { display:flex; align-items:center; gap:8px; white-space:nowrap; }
.advice-grid { display:grid; grid-template-columns:1fr 1fr .8fr; gap:12px; }.advice-grid>div { border:1px solid #e5eaf2; border-radius:6px; padding:14px; background:#f8fafc; }.advice-grid .limitations { background:#fffbeb; border-color:#fde68a; }.advice-grid h3 { margin:0 0 10px; font-size:14px; }.advice-grid ul { margin:0; padding-left:18px; color:#475569; font-size:13px; line-height:1.6; }.advice-grid li+li { margin-top:9px; }.advice-grid p { margin:3px 0; }.advice-grid small { display:block; color:#8b5e34; }
.asset-list { display:grid; grid-template-columns:repeat(3,1fr); border:1px solid #EEF1F4; }.asset-list div { padding:15px; border-right:1px solid #EEF1F4; border-bottom:1px solid #EEF1F4; }.asset-list span,.status-list span { color:#718096; font-size:12px; }.asset-list strong { display:block; margin-top:7px; font-size:17px; }
.status-list { display:grid; gap:10px; }.status-list div { display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #EEF1F4; padding-bottom:9px; }
.history-table { --el-table-header-bg-color:#F7F9FC; --el-table-row-hover-bg-color:#FFF8ED; }
.history-panel :deep(.el-table__row) { cursor:pointer; }
.history-panel :deep(.el-table__cell) { padding:7px 0; }
.history-panel :deep(.el-table .cell) { white-space:nowrap; }
.history-panel :deep(th.el-table__cell) { color:#5F6B7A; font-size:12px; font-weight:700; }
.history-panel :deep(td.el-table__cell) { color:#344054; font-variant-numeric:tabular-nums; }
.history-panel :deep(td.el-table__cell strong) { color:#111827; font-weight:700; }
@media(max-width:1100px){.quality-band,.metric-grid{grid-template-columns:repeat(2,1fr)}.report-grid,.advice-grid{grid-template-columns:1fr}.asset-list{grid-template-columns:repeat(2,1fr)}}
@media(max-width:700px){.report-head,.panel-title{align-items:flex-start;flex-direction:column}.quality-band,.metric-grid{grid-template-columns:1fr}.quality-band div{border-bottom:1px solid #EEF2F7}.report-page{padding:14px}.ai-meta{white-space:normal;flex-wrap:wrap}}
</style>
