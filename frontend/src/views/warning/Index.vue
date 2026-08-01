<template>
  <div class="command-light-page audit-page">
    <header class="page-heading">
      <div>
        <div class="eyebrow">经营管理 / 异常稽核</div>
        <h1>异常稽核</h1>
        <p>每条异常保留规则版本、阈值、原始证据和来源时间；来源不足时明确显示待接入。</p>
      </div>
      <el-button :loading="loading" @click="loadData">
        <el-icon><Refresh /></el-icon>刷新
      </el-button>
    </header>

    <section class="summary-grid">
      <div class="summary-card">
        <span>当日异常</span><strong>{{ total }}</strong><small>{{ query.business_date || latestDate || "最新业务日" }}</small>
      </div>
      <div class="summary-card critical">
        <span>重大异常</span><strong>{{ criticalCount }}</strong><small>紧急 / 风险</small>
      </div>
      <div class="summary-card warning">
        <span>待转任务</span><strong>{{ unconvertedCount }}</strong><small>仍需人工确认责任人</small>
      </div>
      <div class="summary-card pending">
        <span>待接入来源</span><strong>{{ pendingSources.length }}</strong><small>不按零值参与判断</small>
      </div>
    </section>

    <section class="surface source-status" v-if="pendingSources.length">
      <div class="section-title-row">
        <div><h2>数据源状态</h2><p>下列来源尚不足以生成确定性异常。</p></div>
      </div>
      <div class="status-list">
        <el-tag v-for="item in pendingSources" :key="item.key" type="info" effect="plain">
          {{ sourceLabel(item.key) }} · 待接入
          <el-tooltip :content="item.reason" placement="top"><span class="status-help">?</span></el-tooltip>
        </el-tag>
      </div>
    </section>

    <section class="surface attribution-status">
      <div class="section-title-row attribution-title-row">
        <div>
          <h2>业绩归属数据门禁</h2>
          <p>抖音来源、交易、会员归属、排班、改单、跨店和退款七类证据全部就绪后，才允许生成归属建议。</p>
        </div>
        <el-tag :type="attributionAllReady ? 'success' : 'warning'" effect="light">
          {{ attributionAllReady ? "来源已齐全" : "来源不足时不自动归责" }}
        </el-tag>
      </div>
      <div class="attribution-source-grid">
        <div v-for="item in attributionSources" :key="item.key" class="attribution-source-item">
          <div>
            <strong>{{ sourceLabel(item.key) }}</strong>
            <small>{{ item.source || "来源待确认" }}</small>
          </div>
          <el-tag :type="item.status === 'ready' ? 'success' : 'info'" effect="plain">
            {{ item.status === "ready" ? "已就绪" : "待接入" }}
          </el-tag>
          <p>{{ item.reason || `更新时间 ${formatTime(item.updated_at)}` }}</p>
        </div>
      </div>
    </section>

    <section class="surface">
      <div class="filter-bar">
        <el-date-picker v-model="query.business_date" type="date" value-format="YYYY-MM-DD" placeholder="业务日期" clearable />
        <el-input v-model="query.keyword" placeholder="对象、单号或说明" clearable @keyup.enter="search" />
        <el-input v-model="query.store_code" placeholder="门店/仓库编码" clearable @keyup.enter="search" />
        <el-select v-model="query.severity" placeholder="异常等级" clearable>
          <el-option label="紧急" value="critical" /><el-option label="风险" value="risk" />
          <el-option label="预警" value="warning" /><el-option label="提示" value="info" />
        </el-select>
        <el-select v-model="query.metric_status" placeholder="数据状态" clearable>
          <el-option label="已就绪" value="ready" /><el-option label="预估" value="estimated" />
          <el-option label="待接入" value="pending_data" /><el-option label="已过期" value="stale" />
        </el-select>
        <el-select v-model="query.task_status" placeholder="任务状态" clearable>
          <el-option label="已转任务" value="converted" /><el-option label="待转任务" value="unconverted" />
        </el-select>
        <el-button type="primary" @click="search"><el-icon><Search /></el-icon>查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <el-table :data="items" v-loading="loading" stripe row-key="id" empty-text="当前筛选条件下暂无异常">
        <el-table-column prop="id" label="ID" width="74" />
        <el-table-column label="等级" width="82">
          <template #default="{ row }"><el-tag :type="severityType(row.severity)" effect="light">{{ severityLabel(row.severity) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="audit_date" label="业务日期" width="112" />
        <el-table-column label="规则" min-width="150">
          <template #default="{ row }"><div class="primary-cell">{{ row.rule_code || row.exception_type }}</div><small>{{ row.rule_version || "legacy" }}</small></template>
        </el-table-column>
        <el-table-column label="对象" min-width="170">
          <template #default="{ row }"><div class="primary-cell">{{ row.subject_id || "公司" }}</div><small>{{ row.store_name || row.subject_type }}</small></template>
        </el-table-column>
        <el-table-column prop="description" label="异常说明" min-width="300" show-overflow-tooltip />
        <el-table-column label="证据来源" min-width="190">
          <template #default="{ row }"><div class="primary-cell">{{ row.source_name || "未标注" }}</div><small>来源时间 {{ formatTime(row.source_updated_at) }}</small><small>生成时间 {{ formatTime(row.generated_at) }}</small></template>
        </el-table-column>
        <el-table-column label="任务" width="100">
          <template #default="{ row }"><el-tag :type="row.is_converted_to_task ? 'success' : 'info'" effect="plain">{{ row.is_converted_to_task ? row.task_status || "已创建" : "待确认" }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="126" fixed="right">
          <template #default="{ row }"><el-button link type="primary" @click="openDetail(row.id)">证据明细</el-button></template>
        </el-table-column>
      </el-table>

      <div class="pagination-row">
        <span>共 {{ total }} 条</span>
        <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[20, 50, 100]" layout="sizes, prev, pager, next" @size-change="loadData" @current-change="loadData" />
      </div>
    </section>

    <el-drawer v-model="drawerVisible" title="异常证据" size="min(720px, 92vw)">
      <div v-if="detail" class="evidence-drawer">
        <div class="detail-heading">
          <el-tag :type="severityType(detail.severity)">{{ severityLabel(detail.severity) }}</el-tag>
          <h2>{{ detail.description }}</h2>
          <p>{{ detail.rule_code }} · 规则版本 {{ detail.rule_version }}</p>
        </div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="业务日期">{{ detail.audit_date }}</el-descriptions-item>
          <el-descriptions-item label="对象">{{ detail.subject_id }}</el-descriptions-item>
          <el-descriptions-item label="证据哈希"><span class="hash">{{ detail.evidence_hash }}</span></el-descriptions-item>
          <el-descriptions-item label="责任归属">{{ responsibilityLabel(detail.responsibility_status) }}</el-descriptions-item>
          <el-descriptions-item label="来源时间">{{ formatTime(detail.source_updated_at) }}</el-descriptions-item>
          <el-descriptions-item label="生成时间">{{ formatTime(detail.generated_at) }}</el-descriptions-item>
          <el-descriptions-item label="规则阈值"><code>{{ compactJson(detail.thresholds) }}</code></el-descriptions-item>
        </el-descriptions>

        <div class="drawer-section">
          <h3>证据明细</h3>
          <el-table :data="detail.evidence_records || []" border empty-text="暂无可追溯证据">
            <el-table-column prop="source_table" label="原始业务表" min-width="170" />
            <el-table-column prop="document_no" label="原始单号" min-width="130" />
            <el-table-column label="字段值" min-width="230" show-overflow-tooltip>
              <template #default="{ row }">{{ compactJson(row.source_fields) }}</template>
            </el-table-column>
            <el-table-column label="来源时间" min-width="150"><template #default="{ row }">{{ formatTime(row.source_updated_at || row.created_at) }}</template></el-table-column>
          </el-table>
        </div>

        <div v-if="detail.data_snapshot?.adjudication" class="drawer-section current-adjudication">
          <h3>当前人工裁决</h3>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="归属对象">
              {{ detail.data_snapshot.adjudication.selected_owner_id }}
              （{{ ownerTypeLabel(detail.data_snapshot.adjudication.selected_owner_type) }}）
            </el-descriptions-item>
            <el-descriptions-item label="裁决理由">{{ detail.data_snapshot.adjudication.reason }}</el-descriptions-item>
            <el-descriptions-item label="裁决证据"><code>{{ compactJson(detail.data_snapshot.adjudication.decision_evidence) }}</code></el-descriptions-item>
            <el-descriptions-item label="裁决时间">{{ formatTime(detail.data_snapshot.adjudication.decided_at) }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <div v-if="detail.exception_type === 'performance_attribution_conflict'" class="drawer-section adjudication-form">
          <h3>人工裁决</h3>
          <p class="form-help">裁决只记录归属结论、操作人和证据，不修改百胜交易、会员或退款原始数据。</p>
          <el-form label-position="top">
            <div class="adjudication-fields">
              <el-form-item label="归属对象编号" required>
                <el-input v-model="adjudication.selected_owner_id" placeholder="导购、门店或团队编号" />
              </el-form-item>
              <el-form-item label="归属对象类型" required>
                <el-select v-model="adjudication.selected_owner_type">
                  <el-option label="导购" value="guide" />
                  <el-option label="门店" value="store" />
                  <el-option label="团队" value="team" />
                </el-select>
              </el-form-item>
            </div>
            <el-form-item label="裁决理由" required>
              <el-input v-model="adjudication.reason" type="textarea" :rows="2" placeholder="说明选择该归属对象的业务依据" />
            </el-form-item>
            <el-form-item label="裁决证据（JSON）" required>
              <el-input v-model="adjudication.decision_evidence" type="textarea" :rows="4" placeholder='例如 {"排班记录":"2026-07-14早班","核对人":"店长"}' />
            </el-form-item>
            <el-button type="primary" :loading="adjudicating" @click="submitAdjudication">保存人工裁决</el-button>
          </el-form>
        </div>

        <div class="drawer-actions">
          <el-button type="primary" :disabled="!detail.drilldown?.route" @click="drilldown(detail)">下钻</el-button>
          <span v-if="detail.responsibility_status === 'pending_data'">责任人来源待接入，不自动归责。</span>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Refresh, Search } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { auditApi } from "@/api/audit";
import { parsePositiveIntegerQuery } from "@/utils/routeQuery.mjs";

const router = useRouter();
const route = useRoute();
const loading = ref(false);
const items = ref<any[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const latestDate = ref("");
const sourceStatuses = ref<Record<string, any>>({});
const attributionStatus = ref<any>({ sources: {}, all_sources_ready: false });
const drawerVisible = ref(false);
const detail = ref<any>(null);
const adjudicating = ref(false);
const adjudication = reactive({ selected_owner_id: "", selected_owner_type: "guide", reason: "", decision_evidence: "" });
const query = reactive({ business_date: "", keyword: "", store_code: "", severity: "", metric_status: "", task_status: "" });

const summary = ref({ major_count: 0, unconverted_count: 0 });
type AttributionSourceItem = { key: string; status?: string; source?: string; reason?: string; updated_at?: string };
const criticalCount = computed(() => summary.value.major_count);
const unconvertedCount = computed(() => summary.value.unconverted_count);
const pendingSources = computed(() => Object.entries(sourceStatuses.value).filter(([, value]) => value.status === "pending_data").map(([key, value]) => ({ key, ...value })));
const attributionSources = computed<AttributionSourceItem[]>(() => Object.entries(attributionStatus.value.sources || {}).map(([key, value]) => ({ key, ...(value as Omit<AttributionSourceItem, "key">) })));
const attributionAllReady = computed(() => Boolean(attributionStatus.value.all_sources_ready));

const sourceNames: Record<string, string> = {
  return: "退货", amendment: "改单", stocktake: "盘点", responsibility: "责任归属",
  douyin_source: "抖音订单来源", store_transaction: "门店交易", member_ownership: "会员归属",
  guide_schedule: "导购排班", amendment_log: "改单日志", cross_store_history: "跨店消费", refund_record: "退款记录",
};
const sourceLabel = (key: string) => sourceNames[key] || key;
const severityLabel = (value: string) => ({ critical: "紧急", risk: "风险", warning: "预警", info: "提示" }[value] || value || "提示");
const severityType = (value: string) => value === "critical" ? "danger" : value === "risk" ? "warning" : value === "warning" ? "warning" : "info";
const formatTime = (value?: string) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "待接入";
const compactJson = (value: unknown) => value ? JSON.stringify(value) : "-";
const responsibilityLabel = (value?: string) => value === "adjudicated" ? "已裁决" : value === "ready" ? "已确认" : "待确认";
const ownerTypeLabel = (value?: string) => ({ guide: "导购", store: "门店", team: "团队" }[value || ""] || value || "未知");

async function loadData() {
  loading.value = true;
  try {
    const params = Object.fromEntries(Object.entries(query).filter(([, value]) => value));
    const [listResponse, statusResponse, attributionResponse] = await Promise.all([
      auditApi.listExceptions({ ...params, page: page.value, page_size: pageSize.value }),
      auditApi.getRuleStatuses(),
      auditApi.getAttributionStatus(query.business_date || undefined),
    ]);
    const data = listResponse.data.data || {};
    items.value = data.items || [];
    total.value = data.total || 0;
    summary.value = data.summary || { major_count: 0, unconverted_count: 0 };
    latestDate.value = data.business_date || "";
    sourceStatuses.value = statusResponse.data.data || {};
    attributionStatus.value = attributionResponse.data.data || { sources: {}, all_sources_ready: false };
  } finally {
    loading.value = false;
  }
}

function search() { page.value = 1; loadData(); }
function reset() { Object.assign(query, { business_date: "", keyword: "", store_code: "", severity: "", metric_status: "", task_status: "" }); search(); }
async function openDetail(id: number, silentError = false) {
  detail.value = (await auditApi.getException(id, { silentError })).data.data;
  const current = detail.value?.data_snapshot?.adjudication;
  Object.assign(adjudication, {
    selected_owner_id: current?.selected_owner_id || "",
    selected_owner_type: current?.selected_owner_type || "guide",
    reason: current?.reason || "",
    decision_evidence: current?.decision_evidence ? JSON.stringify(current.decision_evidence, null, 2) : "",
  });
  drawerVisible.value = true;
}
async function submitAdjudication() {
  if (!detail.value?.id || !adjudication.selected_owner_id.trim() || adjudication.reason.trim().length < 2 || !adjudication.decision_evidence.trim()) {
    ElMessage.warning("请完整填写归属对象、裁决理由和裁决证据");
    return;
  }
  let decisionEvidence: Record<string, unknown>;
  try {
    decisionEvidence = JSON.parse(adjudication.decision_evidence);
    if (!decisionEvidence || Array.isArray(decisionEvidence) || typeof decisionEvidence !== "object" || !Object.keys(decisionEvidence).length) throw new Error("empty");
  } catch {
    ElMessage.warning("裁决证据必须是非空 JSON 对象");
    return;
  }
  adjudicating.value = true;
  try {
    await auditApi.adjudicateAttribution(detail.value.id, {
      selected_owner_id: adjudication.selected_owner_id.trim(),
      selected_owner_type: adjudication.selected_owner_type,
      reason: adjudication.reason.trim(),
      decision_evidence: decisionEvidence,
    });
    ElMessage.success("人工裁决已保存，原始业务数据未修改");
    await openDetail(detail.value.id);
    await loadData();
  } finally {
    adjudicating.value = false;
  }
}
function drilldown(row: any) { if (row.drilldown?.route) router.push({ path: row.drilldown.route, query: row.drilldown.params || {} }); }

async function initialize() {
  await loadData();
  const exceptionId = parsePositiveIntegerQuery(route.query.exception_id);
  if (exceptionId === null) return;
  try {
    await openDetail(exceptionId, true);
  } catch {
    ElMessage.warning("指定异常不存在或无权查看");
  }
}

onMounted(initialize);
</script>

<style scoped>
.audit-page { padding: 24px 28px 36px; background: #f5f7fa; min-height: 100%; color: #0f172a; }
.page-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 20px; }
.eyebrow { color: #b76b12; font-weight: 700; font-size: 12px; margin-bottom: 8px; }
.page-heading h1 { margin: 0; font-size: 30px; letter-spacing: 0; }
.page-heading p, .section-title-row p { color: #64748b; margin: 8px 0 0; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.summary-card, .surface { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0 3px 12px rgba(15, 23, 42, 0.04); }
.summary-card { min-height: 112px; padding: 18px 20px; border-top: 3px solid #3b82f6; }
.summary-card.critical { border-top-color: #ef4444; }.summary-card.warning { border-top-color: #f59e0b; }.summary-card.pending { border-top-color: #94a3b8; }
.summary-card span, .summary-card small { display: block; color: #64748b; }.summary-card strong { display: block; font-size: 28px; margin: 8px 0; }
.surface { padding: 18px 20px; margin-bottom: 14px; }
.section-title-row h2 { margin: 0; font-size: 18px; }.section-title-row p { font-size: 13px; }
.status-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }.status-help { margin-left: 5px; font-weight: 700; }
.attribution-title-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.attribution-source-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
.attribution-source-item { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 10px; padding: 12px; border: 1px solid #e2e8f0; border-radius: 6px; background: #f8fafc; }
.attribution-source-item strong, .attribution-source-item small { display: block; }.attribution-source-item small { color: #94a3b8; margin-top: 3px; }
.attribution-source-item p { grid-column: 1 / -1; margin: 4px 0 0; color: #64748b; font-size: 12px; line-height: 1.5; }
.filter-bar { display: grid; grid-template-columns: 150px minmax(180px, 1fr) 150px 130px 130px 130px auto auto; gap: 10px; margin-bottom: 16px; }
.filter-bar :deep(.el-date-editor.el-input) { width: 100%; }
.primary-cell { font-weight: 600; color: #1e293b; }.el-table small { display: block; color: #94a3b8; margin-top: 4px; }
.pagination-row { display: flex; justify-content: space-between; align-items: center; color: #64748b; margin-top: 16px; }
.detail-heading { margin-bottom: 18px; }.detail-heading h2 { margin: 12px 0 8px; font-size: 20px; }.detail-heading p { color: #64748b; }
.hash { font-family: Consolas, monospace; overflow-wrap: anywhere; }.drawer-section { margin-top: 24px; }.drawer-section h3 { margin-bottom: 12px; }
.current-adjudication, .adjudication-form { padding: 16px; border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc; }
.form-help { color: #64748b; font-size: 13px; margin: -4px 0 16px; }.adjudication-fields { display: grid; grid-template-columns: minmax(0, 1fr) 160px; gap: 12px; }
.adjudication-fields :deep(.el-select) { width: 100%; }
.drawer-actions { display: flex; align-items: center; gap: 12px; margin-top: 20px; color: #64748b; font-size: 13px; }
code { white-space: normal; word-break: break-all; }
@media (max-width: 1100px) { .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.filter-bar { grid-template-columns: repeat(3, minmax(0, 1fr)); }.attribution-source-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) { .audit-page { padding: 18px 12px 28px; }.page-heading, .attribution-title-row { align-items: flex-start; flex-direction: column; }.page-heading h1 { font-size: 26px; }.summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.summary-card { padding: 14px; min-height: 100px; }.filter-bar, .attribution-source-grid, .adjudication-fields { grid-template-columns: 1fr; }.pagination-row { align-items: flex-start; gap: 12px; flex-direction: column; overflow-x: auto; }.surface { padding: 14px; } }
</style>
