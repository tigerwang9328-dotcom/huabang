<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">经营与财务</p>
        <h2>数据罗盘</h2>
        <p>关键指标钻取;按账簿展示收入/费用/净利润与科目余额概览。</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" :disabled="!bookId" @click="load">刷新</el-button>
        <router-link to="/app/finance-center/mumaren/ar-ap/receivable"><el-button :disabled="!bookId || isReadonly">记录回款</el-button></router-link>
        <router-link to="/app/finance-center/mumaren/reports/expense-detail"><el-button :disabled="!bookId || isReadonly">录入费用</el-button></router-link>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable>
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error || bookError" type="error" :title="error || bookError" :closable="false" show-icon />

    <el-empty v-else-if="!bookId" description="请先选择独立账簿" />

    <template v-else-if="isReadonly">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="金蝶迁移账簿只提供原始凭证、明细账与余额快照核对；未确认科目映射前，不展示收入、费用或利润指标。"
      />
      <div class="history-actions">
        <router-link to="/app/finance-center/mumaren/ledgers/detail"><el-button>查看明细账</el-button></router-link>
        <router-link to="/app/finance-center/mumaren/history/balance-snapshots"><el-button type="primary">余额快照核对</el-button></router-link>
      </div>
    </template>

    <template v-else>
      <el-row :gutter="16">
        <el-col v-for="card in metricCards" :key="card.label" :xs="12" :sm="12" :md="6">
          <el-card :class="['metric-card', card.cls]" shadow="hover">
            <div class="metric-label">{{ card.label }}</div>
            <div class="metric-value">{{ card.value }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-descriptions title="利润表摘要" :column="3" border>
        <el-descriptions-item label="收入">{{ money(profit.total_income) }}</el-descriptions-item>
        <el-descriptions-item label="费用">{{ money(profit.total_expense) }}</el-descriptions-item>
        <el-descriptions-item label="净利润">{{ money(profit.net_profit) }}</el-descriptions-item>
      </el-descriptions>

      <el-table :data="balanceSummary" empty-text="暂无试算平衡数据" stripe>
        <el-table-column prop="label" label="类别" width="200" />
        <el-table-column label="余额合计" align="right">
          <template #default="scope">{{ money(scope.row.amount) }}</template>
        </el-table-column>
      </el-table>
    </template>

    <section class="cash-safety" aria-label="现金安全经营预警">
      <div class="cash-safety-heading">
        <div><h3>现金安全</h3><p>经营预警，不替代银行对账或会计报表。</p></div>
        <el-button text :loading="cashSafetyLoading" @click="loadCashSafety">刷新预警</el-button>
      </div>
      <el-alert v-if="cashSafetyError" type="warning" :title="cashSafetyError" :closable="false" show-icon />
      <el-alert v-else-if="cashSafety?.status === 'pending_data'" type="info" :title="cashSafety.note" :closable="false" show-icon />
      <el-row v-else-if="cashSafety" :gutter="16">
        <el-col :xs="12" :sm="12" :md="6"><el-card shadow="never"><div class="metric-label">现金余额</div><div class="metric-value">{{ money(cashSafety.total_cash_balance) }}</div></el-card></el-col>
        <el-col :xs="12" :sm="12" :md="6"><el-card shadow="never"><div class="metric-label">近30天日均支出</div><div class="metric-value">{{ money(cashSafety.daily_avg_expense_30d) }}</div></el-card></el-col>
        <el-col :xs="12" :sm="12" :md="6"><el-card shadow="never"><div class="metric-label">现金安全天数</div><div class="metric-value">{{ cashSafety.cash_safety_days }} 天</div></el-card></el-col>
        <el-col :xs="12" :sm="12" :md="6"><el-card shadow="never"><div class="metric-label">风险等级</div><el-tag :type="cashRiskType">{{ cashRiskLabel }}</el-tag></el-card></el-col>
      </el-row>
    </section>
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { computed, onMounted, ref, watch } from "vue";
import {
  mumarenFinanceCenterApi,
  type MumarenCashSafety,
  type MumarenProfitStatement,
  type MumarenTrialBalanceRow,
} from "@/api/mumarenFinanceCenter";

const { books, bookId, isReadonly, loadBooks, error: bookError } = useMumarenFinanceBook();
const profit = ref<Partial<MumarenProfitStatement>>({});
const trialRows = ref<MumarenTrialBalanceRow[]>([]);
const error = ref("");
const loading = ref(false);
const booksLoaded = ref(false);
const requestVersion = ref(0);
const cashSafety = ref<MumarenCashSafety | null>(null);
const cashSafetyLoading = ref(false);
const cashSafetyError = ref("");

const money = (value?: number | null) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const metricCards = computed(() => {
  const netProfit = profit.value.net_profit || 0;
  return [
    { label: "总收入", value: money(profit.value.total_income), cls: "metric-income" },
    { label: "总费用", value: money(profit.value.total_expense), cls: "metric-expense" },
    { label: "净利润", value: money(netProfit), cls: netProfit >= 0 ? "metric-success" : "metric-danger" },
    { label: "科目数量", value: String(trialRows.value.length), cls: "metric-count" },
  ];
});
const cashRiskLabel = computed(() => ({ critical: "危险", warning: "预警", normal: "安全", unknown: "待接入" }[cashSafety.value?.risk_level || "unknown"]));
const cashRiskType = computed(() => cashSafety.value?.risk_level === "critical" ? "danger" : cashSafety.value?.risk_level === "warning" ? "warning" : cashSafety.value?.risk_level === "normal" ? "success" : "info");

const balanceSummary = computed(() => {
  const assets = trialRows.value
    .filter((r) => r.account_code.startsWith("1"))
    .reduce((sum, r) => sum + (r.closing_debit || 0), 0);
  const liabilities = trialRows.value
    .filter((r) => r.account_code.startsWith("2"))
    .reduce((sum, r) => sum + (r.closing_credit || 0), 0);
  return [
    { label: "资产合计", amount: assets },
    { label: "负债合计", amount: liabilities },
  ];
});

const load = async () => {
  const requestedBookId = bookId.value;
  const version = ++requestVersion.value;
  if (!requestedBookId) {
    loading.value = false;
    error.value = "";
    trialRows.value = [];
    profit.value = {};
    return;
  }
  if (isReadonly.value) {
    loading.value = false;
    error.value = "";
    trialRows.value = [];
    profit.value = {};
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const [trialResult, profitResult] = await Promise.all([
      mumarenFinanceCenterApi.getTrialBalance({ book_id: requestedBookId }),
      mumarenFinanceCenterApi.getProfitStatement({ book_id: requestedBookId }),
    ]);
    if (version !== requestVersion.value || requestedBookId !== bookId.value) return;
    trialRows.value = trialResult.data.data.rows || [];
    profit.value = profitResult.data.data;
  } catch {
    if (version === requestVersion.value && requestedBookId === bookId.value) {
      error.value = "无法加载独立当前账数据罗盘。";
    }
  } finally {
    if (version === requestVersion.value) loading.value = false;
  }
};

const loadCashSafety = async () => {
  cashSafetyLoading.value = true;
  cashSafetyError.value = "";
  try {
    cashSafety.value = (await mumarenFinanceCenterApi.getCashSafety()).data.data;
  } catch {
    cashSafetyError.value = "现金安全数据暂不可用；请检查现金与费用数据接入。";
  } finally {
    cashSafetyLoading.value = false;
  }
};

onMounted(async () => {
  await loadBooks();
  booksLoaded.value = true;
  await Promise.all([load(), loadCashSafety()]);
});

watch(bookId, () => {
  if (booksLoaded.value) void load();
});
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.heading-actions { display: flex; gap: 8px; }
.filters { display: flex; gap: 12px; }
.filters > * { max-width: 280px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
.metric-card { border-left: 4px solid #dcdfe6; }
.metric-card .metric-label { color: #5d6b7e; font-size: 13px; }
.metric-card .metric-value { margin-top: 8px; font-size: 22px; font-weight: 700; color: #2c3e50; }
.metric-income { border-left-color: #409eff; }
.metric-expense { border-left-color: #e6a23c; }
.metric-success { border-left-color: #67c23a; }
.metric-danger { border-left-color: #f56c6c; }
.metric-count { border-left-color: #909399; }
.history-actions { display: flex; flex-wrap: wrap; gap: 10px; }
.cash-safety { display: grid; gap: 12px; border-top: 1px solid #e1e7ef; padding-top: 16px; }.cash-safety-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }.cash-safety h3 { margin: 0; }.cash-safety p { margin: 4px 0 0; font-size: 13px; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
