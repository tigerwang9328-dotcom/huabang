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
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable>
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error || bookError" type="error" :title="error || bookError" :closable="false" show-icon />

    <el-empty v-else-if="!bookId" description="请先选择独立账簿" />

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
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { computed, onMounted, ref, watch } from "vue";
import {
  mumarenFinanceCenterApi,
  type MumarenProfitStatement,
  type MumarenTrialBalanceRow,
} from "@/api/mumarenFinanceCenter";

const { books, bookId, loadBooks, error: bookError } = useMumarenFinanceBook();
const profit = ref<Partial<MumarenProfitStatement>>({});
const trialRows = ref<MumarenTrialBalanceRow[]>([]);
const error = ref("");
const loading = ref(false);
const booksLoaded = ref(false);
const requestVersion = ref(0);

const money = (value?: number) =>
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

onMounted(async () => {
  await loadBooks();
  booksLoaded.value = true;
  await load();
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
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
