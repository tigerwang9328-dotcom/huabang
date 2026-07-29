<template>
  <section class="workspace">
    <el-card shadow="never" class="hero">
      <template #header>
        <div class="title-row">
          <div>
            <p class="eyebrow">财务中心 / V2.0</p>
            <h1>会计工作台</h1>
          </div>
          <el-tag type="warning" effect="light">当前为只读验收阶段</el-tag>
        </div>
      </template>
      <p>
        新账采用“草稿 → 财务人员审核 → 人工过账”。历史金蝶数据与当前账严格隔离；在最终切换 Gate 通过前，不开放 V2 制单、审核或过账。
      </p>
      <el-alert
        :title="gateMessage"
        :type="books.length ? 'warning' : 'info'"
        :closable="false"
        show-icon
      />
    </el-card>

    <el-card shadow="never" class="book-card">
      <template #header>
        <div class="title-row">
          <strong>当前账账簿</strong>
          <el-button :loading="loading" text type="primary" @click="loadBooks">刷新</el-button>
        </div>
      </template>
      <el-table v-loading="loading" :data="books" empty-text="尚未建立 V2 当前账账簿">
        <el-table-column prop="book_code" label="账簿编码" min-width="140" />
        <el-table-column prop="book_name" label="账簿名称" min-width="220" />
        <el-table-column prop="status" label="状态" min-width="120" />
        <el-table-column label="正式报表">
          <template #default="{ row }">
            <el-tag :type="row.formal_report_blocked ? 'danger' : 'success'" effect="plain">
              {{ row.formal_report_blocked ? "已阻断" : "可出具" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="books.length" class="workspace-filter">
        <el-select v-model="selectedBookId" aria-label="选择 V2 当前账账簿" @change="loadWorkspace">
          <el-option v-for="book in books" :key="book.id" :label="`${book.book_code} · ${book.book_name}`" :value="book.id" />
        </el-select>
        <el-button :loading="workspaceLoading" text type="primary" @click="loadWorkspace">刷新账期与凭证</el-button>
      </div>
    </el-card>

    <el-card v-loading="historyLoading" shadow="never" class="history-card">
      <template #header>
        <div class="title-row">
          <div>
            <strong>历史金蝶凭证（只读存档）</strong>
            <p class="subtle">仅展示已完成校验并发布的 fin_history 数据，不参与 V2 当前账制单或过账。</p>
          </div>
          <el-button :loading="historyLoading" text type="primary" @click="loadHistoryVouchers">刷新</el-button>
        </div>
      </template>
      <el-alert
        title="每条凭证及其分录均带“历史数据”标记；原始金蝶账套只读保留，导入失败或未发布批次不会出现在这里。"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-alert v-if="historyLoadError" class="history-error" :title="`历史凭证读取失败：${historyLoadError}`" type="error" :closable="false" show-icon />
      <el-table :data="historyVouchers" max-height="360" empty-text="尚未发布可查询的历史金蝶凭证">
        <el-table-column prop="voucher_date" label="日期" min-width="110" />
        <el-table-column prop="voucher_no" label="凭证号" min-width="110" />
        <el-table-column prop="voucher_group" label="字" min-width="70" />
        <el-table-column prop="fiscal_period" label="期间" min-width="80" />
        <el-table-column prop="total_debit" label="借方合计" min-width="110" />
        <el-table-column prop="total_credit" label="贷方合计" min-width="110" />
        <el-table-column prop="source_database" label="来源账套" min-width="150" />
        <el-table-column label="数据标记" min-width="100">
          <template #default="{ row }"><el-tag :type="row.historical_marker ? 'info' : 'danger'" effect="plain">{{ row.historical_marker ? "历史数据" : "标记异常" }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }"><el-button text type="primary" @click="viewHistoryVoucher(row)">查看分录</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="selectedBookId" v-loading="workspaceLoading" shadow="never">
      <template #header><strong>当前账工作区（只读）</strong></template>
      <el-alert title="这里展示的是 fin_current 的账期、可制单科目和凭证状态；写入仍受后端 Gate 强制控制。" type="info" :closable="false" show-icon />
      <el-alert
        class="gate-alert"
        :title="writeGateMessage"
        :type="draftEnabled || reviewEnabled || postEnabled ? 'warning' : 'info'"
        :closable="false"
        show-icon
      />
      <section v-if="draftEnabled" class="draft-section">
        <div class="section-head"><h2>人工凭证草稿</h2><span>保存后仍需提交、审核和人工过账</span></div>
        <div class="draft-meta">
          <el-select v-model="draft.period_id" placeholder="选择开放期间">
            <el-option v-for="period in openPeriods" :key="period.id" :label="period.period_code" :value="period.id" />
          </el-select>
          <el-date-picker v-model="draft.voucher_date" type="date" value-format="YYYY-MM-DD" :clearable="false" />
          <el-button type="primary" :loading="draftSaving" @click="saveDraft">保存草稿</el-button>
        </div>
        <el-table :data="draft.entries" max-height="260" empty-text="请至少保留两条分录">
          <el-table-column label="科目" min-width="220"><template #default="{ row }"><el-select v-model="row.account_version_id" filterable placeholder="选择可制单科目"><el-option v-for="account in accounts" :key="account.id" :label="`${account.account_code} · ${account.account_name}`" :value="account.id" /></el-select></template></el-table-column>
          <el-table-column label="摘要" min-width="160"><template #default="{ row }"><el-input v-model="row.summary" maxlength="512" /></template></el-table-column>
          <el-table-column label="借方" width="150"><template #default="{ row }"><el-input-number v-model="row.debit_amount" :min="0" :precision="2" controls-position="right" /></template></el-table-column>
          <el-table-column label="贷方" width="150"><template #default="{ row }"><el-input-number v-model="row.credit_amount" :min="0" :precision="2" controls-position="right" /></template></el-table-column>
          <el-table-column width="80"><template #default="{ $index }"><el-button text type="danger" :disabled="draft.entries.length <= 2" @click="removeDraftLine($index)">删除</el-button></template></el-table-column>
        </el-table>
        <el-button text type="primary" @click="addDraftLine">添加分录</el-button>
      </section>
      <div class="workspace-grid">
        <section>
          <h2>会计期间</h2>
          <el-table :data="periods" max-height="240" empty-text="当前账尚无会计期间">
            <el-table-column prop="period_code" label="期间" min-width="100" />
            <el-table-column prop="status" label="状态" min-width="90" />
            <el-table-column prop="start_date" label="开始" min-width="110" />
            <el-table-column prop="end_date" label="结束" min-width="110" />
            <el-table-column label="结账" width="100" fixed="right"><template #default="{ row }"><el-button text type="primary" @click="viewPeriodCloseReadiness(row)">检查</el-button></template></el-table-column>
          </el-table>
        </section>
        <section>
          <h2>可制单科目</h2>
          <el-table :data="accounts" max-height="240" empty-text="当前账尚无可制单科目">
            <el-table-column prop="account_code" label="编码" min-width="100" />
            <el-table-column prop="account_name" label="科目" min-width="150" />
            <el-table-column prop="normal_balance" label="余额方向" min-width="90" />
          </el-table>
        </section>
      </div>
      <section class="voucher-section">
        <h2>凭证工作流</h2>
        <el-table :data="vouchers" max-height="300" empty-text="当前账尚无凭证">
          <el-table-column prop="voucher_date" label="日期" min-width="110" />
          <el-table-column prop="voucher_no" label="凭证号" min-width="110"><template #default="{ row }">{{ row.voucher_no || "待人工过账编号" }}</template></el-table-column>
          <el-table-column prop="status" label="状态" min-width="100" />
          <el-table-column prop="total_debit" label="借方合计" min-width="110" />
          <el-table-column prop="total_credit" label="贷方合计" min-width="110" />
          <el-table-column prop="prepared_by" label="制单人" min-width="100" />
          <el-table-column prop="reviewer_id" label="审核人" min-width="100" />
          <el-table-column prop="posted_by" label="过账人" min-width="100" />
          <el-table-column label="操作" min-width="250" fixed="right">
            <template #default="{ row }">
              <el-button v-for="action in availableActions(row)" :key="action" size="small" text type="primary" :loading="commandLoading === `${row.id}:${action}`" @click="runCommand(row, action)">{{ actionLabel(action) }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </el-card>

    <el-drawer v-model="historyDrawerOpen" :title="`历史凭证分录${selectedHistoryVoucher ? ` · ${selectedHistoryVoucher.voucher_no}` : ''}`" size="760px">
      <el-alert title="分录来自已发布的历史导入批次，仅供核对；不能在此修改、审核或过账。" type="info" :closable="false" show-icon />
      <el-table v-loading="historyLineLoading" :data="historyVoucherLines" max-height="620" empty-text="该历史凭证没有可查询分录">
        <el-table-column prop="line_no" label="行号" width="70" />
        <el-table-column prop="account_code" label="科目编码" min-width="110" />
        <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
        <el-table-column prop="debit_amount" label="借方" min-width="110" />
        <el-table-column prop="credit_amount" label="贷方" min-width="110" />
        <el-table-column prop="currency_code" label="币种" width="80" />
        <el-table-column label="数据标记" width="100"><template #default="{ row }"><el-tag :type="row.historical_marker ? 'info' : 'danger'" effect="plain">{{ row.historical_marker ? "历史数据" : "标记异常" }}</el-tag></template></el-table-column>
      </el-table>
    </el-drawer>

    <el-drawer v-model="periodCloseDrawerOpen" :title="`结账检查${selectedClosePeriod ? ` · ${selectedClosePeriod.period_code}` : ''}`" size="720px">
      <el-alert title="结账前必须全部通过未过账、借贷平衡、来源异常和余额重算检查；人工操作仍受独立 period_close Gate 控制。" type="warning" :closable="false" show-icon />
      <template v-if="periodCloseReadiness">
        <el-descriptions class="close-summary" :column="2" border>
          <el-descriptions-item label="期间状态">{{ periodCloseReadiness.status }}</el-descriptions-item>
          <el-descriptions-item label="可开始结账">{{ periodCloseReadiness.ready_to_start_close ? "是" : "否" }}</el-descriptions-item>
          <el-descriptions-item label="未过账凭证">{{ periodCloseReadiness.checks.unposted_voucher_count }}</el-descriptions-item>
          <el-descriptions-item label="借贷不平凭证">{{ periodCloseReadiness.checks.unbalanced_voucher_count }}</el-descriptions-item>
          <el-descriptions-item label="来源异常">{{ periodCloseReadiness.checks.source_exception_count }}</el-descriptions-item>
          <el-descriptions-item label="余额差异">{{ periodCloseReadiness.checks.ledger_difference_count }}</el-descriptions-item>
          <el-descriptions-item label="已过账借贷">{{ periodCloseReadiness.checks.posted_debit }} / {{ periodCloseReadiness.checks.posted_credit }}</el-descriptions-item>
          <el-descriptions-item label="余额表借贷">{{ periodCloseReadiness.checks.ledger_debit }} / {{ periodCloseReadiness.checks.ledger_credit }}</el-descriptions-item>
        </el-descriptions>
        <p class="close-note">来源异常口径：{{ periodCloseReadiness.checks.source_exception_scope }}</p>
        <el-button text type="primary" :loading="trialBalanceLoading" @click="loadTrialBalance">查看 V2 当前账试算表</el-button>
        <el-alert v-if="trialBalance" class="history-error" :title="trialBalance.formal_report_message" type="info" :closable="false" show-icon />
        <el-table v-if="trialBalance" :data="trialBalance.rows" max-height="300" empty-text="当前期间暂无已重建余额">
          <el-table-column prop="account_code" label="科目编码" min-width="110" /><el-table-column prop="account_name" label="科目名称" min-width="160" />
          <el-table-column prop="opening_debit" label="期初借" min-width="100" /><el-table-column prop="opening_credit" label="期初贷" min-width="100" />
          <el-table-column prop="period_debit" label="本期借" min-width="100" /><el-table-column prop="period_credit" label="本期贷" min-width="100" />
          <el-table-column prop="closing_debit" label="期末借" min-width="100" /><el-table-column prop="closing_credit" label="期末贷" min-width="100" />
        </el-table>
        <div v-if="periodCloseEnabled" class="close-actions">
          <el-button v-for="action in availablePeriodActions()" :key="action" type="primary" :loading="periodCommandLoading === action" @click="runPeriodCommand(action)">{{ periodActionLabel(action) }}</el-button>
        </div>
        <el-alert v-else class="history-error" :title="writeReadiness?.commands.period_close.reason || '结账写入 Gate 未开启'" type="info" :closable="false" show-icon />
      </template>
      <el-skeleton v-else-if="periodCloseLoading" :rows="5" animated />
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  financeV2Api,
  type FinanceV2Account,
  type FinanceV2Book,
  type FinanceV2HistoryVoucher,
  type FinanceV2HistoryVoucherLine,
  type FinanceV2PeriodCloseReadiness,
  type FinanceV2TrialBalance,
  type FinanceV2Period,
  type FinanceV2Voucher,
  type FinanceV2VoucherLineInput,
  type FinanceV2WriteReadiness,
} from "@/api/financeV2";

const books = ref<FinanceV2Book[]>([]);
const selectedBookId = ref<number>();
const periods = ref<FinanceV2Period[]>([]);
const accounts = ref<FinanceV2Account[]>([]);
const vouchers = ref<FinanceV2Voucher[]>([]);
const historyVouchers = ref<FinanceV2HistoryVoucher[]>([]);
const historyVoucherLines = ref<FinanceV2HistoryVoucherLine[]>([]);
const selectedHistoryVoucher = ref<FinanceV2HistoryVoucher>();
const selectedClosePeriod = ref<FinanceV2Period>();
const writeReadiness = ref<FinanceV2WriteReadiness>();
const periodCloseReadiness = ref<FinanceV2PeriodCloseReadiness>();
const trialBalance = ref<FinanceV2TrialBalance>();
const loading = ref(false);
const historyLoading = ref(false);
const historyLineLoading = ref(false);
const periodCloseLoading = ref(false);
const trialBalanceLoading = ref(false);
const workspaceLoading = ref(false);
const draftSaving = ref(false);
const commandLoading = ref("");
const periodCommandLoading = ref("");
const loadError = ref("");
const historyLoadError = ref("");
const historyDrawerOpen = ref(false);
const periodCloseDrawerOpen = ref(false);
const today = () => new Date().toISOString().slice(0, 10);
const newRequestId = () => globalThis.crypto?.randomUUID?.() || `finance-v2-${Date.now()}-${Math.random().toString(36).slice(2)}`;
const draft = reactive({ book_id: 0, period_id: 0, voucher_date: today(), request_id: newRequestId(), entries: [] as FinanceV2VoucherLineInput[] });

const draftEnabled = computed(() => Boolean(writeReadiness.value?.commands.draft.enabled));
const reviewEnabled = computed(() => Boolean(writeReadiness.value?.commands.review.enabled));
const postEnabled = computed(() => Boolean(writeReadiness.value?.commands.post.enabled));
const periodCloseEnabled = computed(() => Boolean(writeReadiness.value?.commands.period_close.enabled));
const openPeriods = computed(() => periods.value.filter((period) => period.status === "open"));
const writeGateMessage = computed(() => {
  if (!writeReadiness.value) return "正在读取服务器写入 Gate；未确认前不显示可写操作。";
  const disabled = Object.entries(writeReadiness.value.commands).filter(([, value]) => !value.enabled).map(([command]) => command);
  return disabled.length ? `当前禁用：${disabled.join("、")}。实际写入仍由后端再次校验。` : "已按当前用户和账簿确认 Gate；每次写入仍由后端强制复核。";
});

const gateMessage = computed(() => {
  if (loadError.value) return `无法读取 V2 账簿：${loadError.value}`;
  if (!books.value.length) return "尚未导入或批准 V2 当前账数据；这不是零余额，也不代表可开始制单。";
  return "生产写入开关仍应保持关闭，直至历史核对、最终期初、旧入口冻结与人工验收全部通过。";
});

async function loadBooks() {
  loading.value = true;
  loadError.value = "";
  try {
    const response = await financeV2Api.listBooks();
    books.value = response.data || [];
    if (!selectedBookId.value && books.value.length) selectedBookId.value = books.value[0].id;
    await Promise.all([loadWorkspace(), loadHistoryVouchers()]);
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "请求失败";
  } finally {
    loading.value = false;
  }
}

async function loadHistoryVouchers() {
  historyLoading.value = true;
  historyLoadError.value = "";
  try {
    const response = await financeV2Api.listHistoryVouchers({ limit: 100 });
    historyVouchers.value = response.data || [];
  } catch (error) {
    historyVouchers.value = [];
    historyLoadError.value = error instanceof Error ? error.message : "请求失败";
  } finally {
    historyLoading.value = false;
  }
}

async function viewHistoryVoucher(voucher: FinanceV2HistoryVoucher) {
  selectedHistoryVoucher.value = voucher;
  historyVoucherLines.value = [];
  historyDrawerOpen.value = true;
  historyLineLoading.value = true;
  try {
    const response = await financeV2Api.listHistoryVoucherLines(voucher.id, { limit: 500 });
    historyVoucherLines.value = response.data || [];
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "历史凭证分录读取失败");
  } finally {
    historyLineLoading.value = false;
  }
}

async function viewPeriodCloseReadiness(period: FinanceV2Period) {
  if (!selectedBookId.value) return;
  selectedClosePeriod.value = period;
  periodCloseReadiness.value = undefined;
  trialBalance.value = undefined;
  periodCloseDrawerOpen.value = true;
  periodCloseLoading.value = true;
  try {
    const response = await financeV2Api.getPeriodCloseReadiness(selectedBookId.value, period.id);
    periodCloseReadiness.value = response.data;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "结账检查读取失败");
  } finally {
    periodCloseLoading.value = false;
  }
}

async function loadTrialBalance() {
  if (!selectedBookId.value || !selectedClosePeriod.value) return;
  trialBalanceLoading.value = true;
  try {
    const response = await financeV2Api.getTrialBalance(selectedBookId.value, selectedClosePeriod.value.id);
    trialBalance.value = response.data;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "试算表读取失败");
  } finally {
    trialBalanceLoading.value = false;
  }
}

async function loadWorkspace() {
  if (!selectedBookId.value) {
    periods.value = [];
    accounts.value = [];
    vouchers.value = [];
    writeReadiness.value = undefined;
    return;
  }
  workspaceLoading.value = true;
  try {
    const [periodResponse, accountResponse, voucherResponse, readinessResponse] = await Promise.all([
      financeV2Api.listPeriods(selectedBookId.value),
      financeV2Api.listAccounts(selectedBookId.value),
      financeV2Api.listVouchers(selectedBookId.value),
      financeV2Api.getWriteReadiness(selectedBookId.value),
    ]);
    periods.value = periodResponse.data || [];
    accounts.value = accountResponse.data || [];
    vouchers.value = voucherResponse.data || [];
    writeReadiness.value = readinessResponse.data;
    draft.book_id = selectedBookId.value;
    if (!openPeriods.value.some((period) => period.id === draft.period_id)) draft.period_id = openPeriods.value[0]?.id || 0;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "工作区读取失败";
  } finally {
    workspaceLoading.value = false;
  }
}

function addDraftLine() {
  draft.entries.push({ account_version_id: 0, summary: "", debit_amount: 0, credit_amount: 0 });
}

function removeDraftLine(index: number) {
  draft.entries.splice(index, 1);
}

function resetDraft() {
  draft.request_id = newRequestId();
  draft.voucher_date = today();
  draft.entries.splice(0, draft.entries.length, ...[0, 1].map(() => ({ account_version_id: 0, summary: "", debit_amount: 0, credit_amount: 0 })));
}

async function saveDraft() {
  if (!draft.book_id || !draft.period_id) return ElMessage.warning("请选择账簿和开放期间");
  draftSaving.value = true;
  try {
    await financeV2Api.createDraft({ ...draft, entries: draft.entries.map((entry) => ({ ...entry })) });
    ElMessage.success("凭证草稿已保存");
    resetDraft();
    await loadWorkspace();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存草稿失败");
  } finally {
    draftSaving.value = false;
  }
}

const actionLabel = (action: string) => ({ submit: "提交", start_review: "领取审核", approve: "批准", reject: "驳回", reopen: "重新打开", withdraw: "撤回", cancel: "取消", post: "人工过账" } as Record<string, string>)[action] || action;
const actionGate = (action: string) => action === "post" ? postEnabled.value : ["start_review", "approve", "reject"].includes(action) ? reviewEnabled.value : draftEnabled.value;
function availableActions(voucher: FinanceV2Voucher) {
  const candidates: Record<string, string[]> = { draft: ["submit", "cancel"], submitted: ["start_review", "cancel"], reviewing: ["approve", "reject", "cancel"], rejected: ["reopen"], approved: ["withdraw", "cancel", "post"] };
  return (candidates[voucher.status] || []).filter(actionGate);
}

const periodActionLabel = (action: string) => ({ start_close: "开始结账", complete_close: "完成结账", request_reopen: "申请反结账", approve_reopen: "批准反结账" } as Record<string, string>)[action] || action;
function availablePeriodActions() {
  const status = periodCloseReadiness.value?.status;
  if (status === "open" && periodCloseReadiness.value?.ready_to_start_close) return ["start_close"];
  if (status === "closing") return ["complete_close"];
  if (status === "closed") return ["request_reopen"];
  if (status === "reopening") return ["approve_reopen"];
  return [];
}

async function runPeriodCommand(action: string) {
  if (!selectedBookId.value || !selectedClosePeriod.value || !periodCloseReadiness.value) return;
  const reasonRequired = ["request_reopen", "approve_reopen"].includes(action);
  let reason: string | undefined;
  if (reasonRequired) {
    try {
      const response = await ElMessageBox.prompt(`${periodActionLabel(action)}原因将写入不可变审计记录。`, periodActionLabel(action), { inputPattern: /\S+/, inputErrorMessage: "必须填写原因", confirmButtonText: "确认", cancelButtonText: "取消" });
      reason = response.value;
    } catch {
      return;
    }
  }
  periodCommandLoading.value = action;
  try {
    await financeV2Api.executePeriodCommand(selectedBookId.value, selectedClosePeriod.value.id, {
      action,
      command_id: newRequestId(),
      expected_version: periodCloseReadiness.value.version,
      reason,
    });
    ElMessage.success(`${periodActionLabel(action)}已提交`);
    await loadWorkspace();
    const refreshed = periods.value.find((period) => period.id === selectedClosePeriod.value?.id);
    if (refreshed) await viewPeriodCloseReadiness(refreshed);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : `${periodActionLabel(action)}失败，请刷新后确认状态`);
  } finally {
    periodCommandLoading.value = "";
  }
}

async function runCommand(voucher: FinanceV2Voucher, action: string) {
  const reasonRequired = ["reject", "reopen", "withdraw", "cancel", "post"].includes(action);
  let reason: string | undefined;
  if (reasonRequired) {
    try {
      const response = await ElMessageBox.prompt(`${actionLabel(action)}原因将写入审计记录。`, actionLabel(action), { inputPattern: /\S+/, inputErrorMessage: "必须填写原因", confirmButtonText: "确认", cancelButtonText: "取消" });
      reason = response.value;
    } catch {
      return;
    }
  }
  const key = `${voucher.id}:${action}`;
  commandLoading.value = key;
  try {
    await financeV2Api.executeCommand(voucher.id, { action, command_id: newRequestId(), expected_version: voucher.version, reason });
    ElMessage.success(`${actionLabel(action)}已提交`);
    await loadWorkspace();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : `${actionLabel(action)}失败，请刷新后确认凭证状态`);
  } finally {
    commandLoading.value = "";
  }
}

onMounted(loadBooks);
</script>

<style scoped>
.workspace { display: grid; gap: 16px; }
.hero p { margin: 0 0 16px; color: var(--el-text-color-regular); line-height: 1.7; }
.title-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.title-row h1 { margin: 2px 0 0; font-size: 22px; }
.eyebrow { margin: 0; color: var(--el-color-primary); font-size: 12px; font-weight: 600; }
.book-card { min-height: 260px; }
.history-card { min-height: 260px; }
.subtle { margin: 6px 0 0; color: var(--el-text-color-secondary); font-size: 12px; }
.history-error { margin-top: 12px; }
.close-summary { margin-top: 16px; }
.close-note { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; }
.close-actions { display: flex; gap: 10px; margin-top: 16px; }
.workspace-filter { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.gate-alert { margin-top: 16px; }
.draft-section { margin-top: 20px; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.section-head h2 { margin: 0; font-size: 15px; }.section-head span { color: var(--el-text-color-secondary); font-size: 12px; }
.draft-meta { display: flex; gap: 12px; margin-bottom: 12px; }
.workspace-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }
.workspace-grid h2, .voucher-section h2 { margin: 0 0 10px; font-size: 15px; }
.voucher-section { margin-top: 20px; }
@media (max-width: 900px) { .workspace-grid { grid-template-columns: 1fr; } .draft-meta { flex-direction: column; } }
</style>
