<template>
  <div class="ai-diagnosis-page">
    <section class="hero">
      <div>
        <p>AI BUSINESS DIAGNOSIS</p>
        <h1>{{ currentModule.label }}</h1>
        <span>不是普通报表，而是回答：哪里出问题、谁处理、几点前处理、明天怎么复查。</span>
      </div>
      <div class="filters">
        <el-date-picker v-model="filters.stat_date" type="date" value-format="YYYY-MM-DD" placeholder="诊断日期" clearable />
        <el-input v-model="filters.store_code" placeholder="门店编码（可选）" clearable />
        <el-select v-model="filters.level" placeholder="风险等级" clearable>
          <el-option label="高风险" value="high" />
          <el-option label="中风险" value="medium" />
          <el-option label="低风险" value="low" />
        </el-select>
        <el-button type="primary" :loading="loading" @click="loadData">刷新诊断</el-button>
      </div>
    </section>


    <el-alert
      v-if="qualityWarnings.length"
      class="quality-alert"
      type="warning"
      :closable="false"
      show-icon
      :title="qualityWarnings.join('；')"
    />

    <section class="score-grid">
      <div class="score-card main-score">
        <small>经营健康分</small>
        <strong>{{ summary.health_score ?? "--" }}</strong>
        <span>{{ summary.stat_date || "等待数据" }}</span>
      </div>
      <div v-for="card in metricCards" :key="card.label" class="score-card">
        <small>{{ card.label }}</small>
        <strong>{{ card.value }}</strong>
        <span>{{ card.desc }}</span>
      </div>
    </section>

    <section class="summary-card">
      <div class="section-title">
        <div>
          <p>AI DIAGNOSIS SUMMARY</p>
          <h2>AI诊断摘要</h2>
        </div>
        <el-tag :type="dataQuality.is_complete ? 'success' : 'warning'">{{ dataQuality.is_complete ? "数据完整" : "数据需补齐" }}</el-tag>
      </div>
      <p class="summary-text">{{ summary.ai_summary || fallbackSummary }}</p>
      <div class="source-line">数据来源：{{ (dataQuality.source_tables || []).join(" / ") || "规则诊断服务" }}</div>
    </section>

    <section v-if="moduleKey === 'overview'" class="focus-grid">
      <div class="panel">
        <div class="section-title"><div><p>TOP 3 ACTIONS</p><h2>今日最应该抓的三件事</h2></div></div>
        <div v-if="diagnoses.length" class="focus-list">
          <article v-for="d in diagnoses.slice(0, 3)" :key="d.id" class="focus-item" :class="d.level">
            <el-tag :type="levelType(d.level)">{{ d.level_label }}风险</el-tag>
            <h3>{{ d.title }}</h3>
            <p>{{ d.description }}</p>
            <ul>
              <li><b>可能原因：</b>{{ d.possible_reason }}</li>
              <li><b>建议动作：</b>{{ d.suggested_action }}</li>
              <li><b>责任人：</b>{{ d.suggested_owner_role }}</li>
              <li><b>截止时间：</b>{{ d.deadline_suggestion }}</li>
              <li><b>复查指标：</b>{{ d.review_metric }}</li>
            </ul>
          </article>
        </div>
        <el-empty v-else description="暂无高优先级诊断，或数据尚未同步" />
      </div>
      <div class="panel">
        <div class="section-title"><div><p>RISK RADAR</p><h2>风险雷达</h2></div></div>
        <div class="risk-radar">
          <div v-for="r in risks" :key="r.name" class="risk-pill" :class="r.level">
            <span>{{ r.name }}</span>
            <strong>{{ r.value }}</strong>
          </div>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <div>
          <p>DIAGNOSIS LIST</p>
          <h2>{{ currentModule.label }}明细</h2>
        </div>
        <el-button v-if="moduleKey !== 'overview'" @click="generateTasks" :loading="generating">生成建议任务</el-button>
      </div>
      <el-table :data="filteredDiagnoses" v-loading="loading" empty-text="暂无诊断数据，或当前模块数据未接入" border>
        <el-table-column label="等级" width="90">
          <template #default="{ row }"><el-tag :type="levelType(row.level)">{{ row.level_label }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="title" label="问题类型" min-width="180" />
        <el-table-column prop="description" label="问题描述" min-width="260" show-overflow-tooltip />
        <el-table-column label="数据依据" min-width="240">
          <template #default="{ row }">
            <div class="evidence"><span v-for="e in row.evidence || []" :key="e">{{ e }}</span></div>
          </template>
        </el-table-column>
        <el-table-column prop="possible_reason" label="可能原因" min-width="220" show-overflow-tooltip />
        <el-table-column prop="suggested_action" label="建议动作" min-width="260" show-overflow-tooltip />
        <el-table-column prop="suggested_owner_role" label="责任人建议" width="150" />
        <el-table-column prop="deadline_suggestion" label="截止时间" width="140" />
        <el-table-column prop="review_metric" label="复查指标" min-width="220" show-overflow-tooltip />
      </el-table>
    </section>

    <section class="panel">
      <div class="section-title"><div><p>ACTION LOOP</p><h2>行动建议 / 闭环任务</h2></div></div>
      <el-table :data="actions" empty-text="暂无行动建议" border>
        <el-table-column prop="task_no" label="任务编号" width="150" />
        <el-table-column prop="problem_type" label="问题类型" min-width="180" />
        <el-table-column prop="today_action" label="今日动作" min-width="260" show-overflow-tooltip />
        <el-table-column prop="owner" label="责任人" width="150" />
        <el-table-column prop="deadline" label="截止时间" width="150" />
        <el-table-column prop="priority" label="优先级" width="100" />
        <el-table-column prop="feedback_requirement" label="反馈要求" min-width="260" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column prop="review_metric" label="复查指标" min-width="220" show-overflow-tooltip />
      </el-table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { aiDiagnosisApi } from "@/api/ai";

const route = useRoute();
const modules = [
  { key: "overview", label: "AI经营诊断总览" },
  { key: "sales", label: "销售诊断" },
  { key: "products", label: "商品诊断" },
  { key: "inventory", label: "库存诊断" },
  { key: "hr", label: "人力诊断" },
  { key: "finance", label: "财务诊断" },
  { key: "members", label: "会员诊断" },
  { key: "audit", label: "异常稽核" },
  { key: "actions", label: "行动闭环" },
];

const routeModuleKey = computed(() => String(route.params.module || "overview"));
const moduleKey = computed(() => routeModuleKey.value === "action-tasks" ? "actions" : routeModuleKey.value);
const apiModuleKey = computed(() => moduleKey.value === "actions" ? "action-tasks" : moduleKey.value);
const currentModule = computed(() => modules.find((m) => m.key === moduleKey.value) || modules[0]);
const filters = reactive({ stat_date: "", store_code: "", level: "" });
const loading = ref(false);
const generating = ref(false);
const payload = ref<any>({ summary: {}, risks: [], diagnoses: [], action_suggestions: [], data_quality: {} });

const summary = computed(() => payload.value.summary || {});
const risks = computed(() => payload.value.risks || []);
const diagnoses = computed(() => payload.value.diagnoses || []);
const actions = computed(() => payload.value.action_suggestions || []);
const dataQuality = computed(() => payload.value.data_quality || {});
const qualityWarnings = computed(() => [...(dataQuality.value.warnings || []), ...(dataQuality.value.missing_fields || []).map((x: string) => `缺失：${x}`)]);
const fallbackSummary = "当前模块将优先基于真实销售、商品、库存、财务、任务数据生成诊断；数据不足时会降级显示，不会编造结论。";

const filteredDiagnoses = computed(() => {
  if (!filters.level) return diagnoses.value;
  return diagnoses.value.filter((d: any) => d.level === filters.level);
});

const money = (v: any) => {
  const n = Number(v || 0);
  if (Math.abs(n) >= 10000) return `¥${(n / 10000).toFixed(2)}万`;
  return `¥${n.toFixed(0)}`;
};
const num = (v: any, suffix = "") => (v === null || v === undefined || Number.isNaN(Number(v)) ? "未接入" : `${Number(v).toFixed(0)}${suffix}`);
const pct = (v: any) => {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "未接入";
  const n = Math.abs(Number(v)) <= 1 ? Number(v) * 100 : Number(v);
  return `${n.toFixed(1)}%`;
};

const metricCards = computed(() => {
  const s = summary.value;
  const common: any[] = [
    { label: "净销售额", value: money(s.net_sales), desc: "百胜销售净额口径" },
    { label: "订单数", value: num(s.order_count, "单"), desc: "成交规模" },
    { label: "毛利率", value: pct(s.gross_margin), desc: "成本缺失时为预估" },
  ];
  const byModule: Record<string, any[]> = {
    overview: [
      { label: "销售健康", value: s.sales_health || "--", desc: "销售风险等级" },
      { label: "库存健康", value: s.inventory_health || "--", desc: "库存风险等级" },
      { label: "财务健康", value: s.finance_health || "--", desc: "利润现金风险" },
    ],
    sales: [
      { label: "销售件数", value: num(s.item_count, "件"), desc: "净销售件数" },
      { label: "客单价", value: money(s.avg_order_value), desc: "成交质量" },
      { label: "连带率", value: Number(s.items_per_order || 0).toFixed(2), desc: "搭配销售能力" },
      { label: "退货率", value: pct(s.return_rate), desc: "销售质量" },
    ],
    products: [
      { label: "商品数", value: num(s.product_count, "款"), desc: "参与诊断商品" },
      { label: "近7日销量", value: num(s.sales_qty_7d, "件"), desc: "动销表现" },
      { label: "爆款缺货", value: num(s.hot_low_stock_count, "款"), desc: "补货/调拨优先" },
      { label: "慢款滞销", value: num(s.slow_product_count, "款"), desc: "清仓风险" },
    ],
    inventory: [
      { label: "库存数量", value: num(s.total_inventory_qty, "件"), desc: `库存快照 ${s.inventory_stat_date || "--"}` },
      { label: "库存金额", value: money(s.inventory_amount), desc: "资金占用" },
      { label: "90天以上", value: money(s.age_90_amount), desc: "老库存金额" },
      { label: "负库存SKU", value: num(s.negative_sku_count, "个"), desc: "仓库复核" },
    ],
    hr: [
      { label: "员工数", value: num(s.employee_count, "人"), desc: "钉钉在职员工" },
      { label: "人均销售", value: money(s.avg_sales_per_employee), desc: "销售额 / 在职员工" },
      { label: "今日出勤", value: num(s.attendance_employee_count, "人"), desc: `考勤 ${s.attendance_stat_date || "--"}` },
      { label: "考勤异常", value: num(s.attendance_abnormal_count, "人"), desc: "缺卡/迟到/早退" },
    ],
    finance: [
      { label: "销售成本", value: money(s.cost_of_goods), desc: "商品成本" },
      { label: "预估毛利", value: money(s.gross_profit), desc: "非最终财报" },
      { label: "费用", value: money(s.total_expense), desc: "固定成本/费用" },
      { label: "预估利润", value: money(s.operating_profit), desc: "需财务核准" },
    ],
    members: [
      { label: "会员订单", value: num(s.member_order_count, "单"), desc: "小票会员字段" },
      { label: "活跃会员", value: num(s.active_member_count, "人"), desc: "当日去重成交" },
      { label: "会员销售", value: money(s.member_sales_amount), desc: "会员成交金额" },
      { label: "会员订单占比", value: pct(s.member_order_ratio), desc: "会员经营质量" },
      { label: "待回访", value: num(s.pending_visit_count, "人"), desc: `回访清单 ${s.visit_stat_date || "--"}` },
    ],
    audit: [
      { label: "异常数量", value: num(s.audit_count, "项"), desc: "需复核" },
      { label: "高危异常", value: num(s.high_count, "项"), desc: "优先处理" },
    ],
    "actions": [
      { label: "建议任务", value: num(s.suggestion_count, "项"), desc: "需人工确认" },
      { label: "正式任务", value: num(s.existing_task_count, "项"), desc: "任务系统记录" },
      { label: "逾期任务", value: num(s.overdue_count, "项"), desc: "突出跟进" },
    ],
  };
  return moduleKey.value === "overview" ? byModule.overview : [...common, ...(byModule[moduleKey.value] || [])].slice(0, 7);
});

const levelType = (level: string) => (level === "high" ? "danger" : level === "medium" ? "warning" : "success");

const loadData = async () => {
  loading.value = true;
  try {
    const params: any = {};
    if (filters.stat_date) params.stat_date = filters.stat_date;
    if (filters.store_code) params.store_code = filters.store_code;
    const res = await aiDiagnosisApi.getModule(apiModuleKey.value, params);
    payload.value = res.data.data || {};
  } catch (e: any) {
    payload.value = { summary: {}, risks: [], diagnoses: [], action_suggestions: [], data_quality: { warnings: [e?.message || "AI诊断接口暂时不可用"] } };
  } finally {
    loading.value = false;
  }
};

const generateTasks = async () => {
  generating.value = true;
  try {
    const res = await aiDiagnosisApi.generateTasks({ module: apiModuleKey.value, stat_date: filters.stat_date, store_code: filters.store_code });
    payload.value.action_suggestions = res.data.data?.tasks || [];
    ElMessage.success("已生成建议任务，当前阶段需人工确认后派发");
  } finally {
    generating.value = false;
  }
};

watch(moduleKey, loadData);
onMounted(loadData);
</script>

<style scoped>
.ai-diagnosis-page { min-height: 100vh; padding: 28px 32px 44px; background: #f6f8fb; color: #0f172a; }
.hero { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; padding-bottom: 22px; border-bottom: 1px solid #e2e8f0; }
.hero p, .section-title p { margin: 0 0 8px; color: #c0762a; font-size: 11px; letter-spacing: .18em; font-weight: 900; }
.hero h1 { margin: 0 0 8px; font-size: 34px; letter-spacing: .02em; }
.hero span { color: #64748b; font-size: 14px; }
.filters { display: grid; grid-template-columns: 170px 180px 130px 100px; gap: 10px; align-items: center; }
.quality-alert { margin: 12px 0; }
.score-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 14px; margin: 18px 0; }
.score-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 18px; box-shadow: 0 12px 32px rgba(15,23,42,.05); min-height: 106px; }
.score-card small { display: block; color: #64748b; font-weight: 800; margin-bottom: 10px; }
.score-card strong { display: block; font-size: 25px; line-height: 1.15; letter-spacing: -.03em; }
.score-card span { display: block; margin-top: 9px; color: #94a3b8; font-size: 12px; line-height: 1.5; }
.main-score { background: linear-gradient(135deg, #0f172a, #1e293b); color: #fff; border-color: transparent; }
.main-score small, .main-score span { color: rgba(255,255,255,.72); }
.main-score strong { font-size: 42px; color: #f8d36d; }
.summary-card, .panel { background: #fff; border: 1px solid #e2e8f0; border-radius: 20px; padding: 22px; box-shadow: 0 12px 32px rgba(15,23,42,.05); margin-bottom: 18px; }
.section-title { display: flex; justify-content: space-between; gap: 16px; align-items: center; margin-bottom: 16px; }
.section-title h2 { margin: 0; font-size: 21px; }
.summary-text { color: #334155; line-height: 1.9; font-size: 15px; margin: 0; }
.source-line { margin-top: 12px; color: #94a3b8; font-size: 12px; }
.focus-grid { display: grid; grid-template-columns: 1.4fr .8fr; gap: 18px; }
.focus-list { display: grid; gap: 12px; }
.focus-item { border: 1px solid #e2e8f0; border-radius: 16px; padding: 16px; background: #f8fafc; }
.focus-item.high { background: #fff7f7; border-color: #fecaca; }
.focus-item.medium { background: #fffbeb; border-color: #fde68a; }
.focus-item h3 { margin: 10px 0 8px; font-size: 18px; }
.focus-item p { margin: 0 0 10px; color: #475569; line-height: 1.7; }
.focus-item ul { margin: 0; padding-left: 18px; color: #475569; line-height: 1.8; font-size: 13px; }
.risk-radar { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.risk-pill { border: 1px solid #e2e8f0; background: #f8fafc; border-radius: 14px; padding: 14px; }
.risk-pill span { display: block; color: #64748b; font-size: 12px; margin-bottom: 8px; }
.risk-pill strong { font-size: 24px; }
.risk-pill.high { background: #fff7f7; border-color: #fecaca; }
.risk-pill.medium { background: #fffbeb; border-color: #fde68a; }
.evidence { display: flex; flex-wrap: wrap; gap: 6px; }
.evidence span { background: #f1f5f9; color: #475569; border-radius: 999px; padding: 4px 8px; font-size: 12px; }
@media (max-width: 1280px) { .score-grid { grid-template-columns: repeat(3, 1fr); } .focus-grid { grid-template-columns: 1fr; } .filters { grid-template-columns: 1fr 1fr; } }
@media (max-width: 760px) { .ai-diagnosis-page { padding: 20px 14px; } .hero { display: block; } .filters { grid-template-columns: 1fr; margin-top: 16px; } .score-grid { grid-template-columns: 1fr; } .risk-radar { grid-template-columns: 1fr; } }
</style>
