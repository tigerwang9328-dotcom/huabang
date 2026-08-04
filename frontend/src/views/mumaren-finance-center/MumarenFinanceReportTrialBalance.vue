<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">报表</p>
        <h2>科目余额表</h2>
        <p>按独立当前账已过账凭证计算科目余额;不混入历史归档。</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" :disabled="!bookId" @click="load">查询</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
      <el-input v-model="period" placeholder="2026-07(可选)" />
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-alert v-if="hasPendingHistoricalMapping" type="warning" :closable="false" show-icon :title="mappingWarning" />

    <el-table v-if="!error" :data="trialRows" empty-text="暂无已过账数据" stripe>
      <el-table-column prop="account_code" label="科目编码" />
      <el-table-column prop="account_name" label="科目名称" min-width="180" />
      <el-table-column label="借方" align="right">
        <template #default="scope">{{ money(scope.row.debit_amount) }}</template>
      </el-table-column>
      <el-table-column label="贷方" align="right">
        <template #default="scope">{{ money(scope.row.credit_amount) }}</template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { computed, onMounted, ref } from "vue";
import {
  mumarenFinanceCenterApi,
  type MumarenFinanceBook,
  type MumarenTrialBalanceRow,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook, isReadonly } = useMumarenFinanceBook();
const period = ref("");
const trialRows = ref<MumarenTrialBalanceRow[]>([]);
const error = ref("");
const loading = ref(false);
const unclassifiedAccountCount = ref(0);
let loadRequestVersion = 0;
const isHistoricalBook = computed(() =>
  isReadonly.value || Boolean(books.value.find((book) => book.id === bookId.value)?.is_readonly),
);
const hasPendingHistoricalMapping = computed(() =>
  isHistoricalBook.value && unclassifiedAccountCount.value > 0,
);
const mappingWarning = computed(() =>
  `该金蝶历史账簿有 ${unclassifiedAccountCount.value} 个科目待会计分类映射；科目余额可继续核对，但正式三表的 0.00 不代表历史业务为零。`,
);

const money = (value?: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const load = async () => {
  const requestedBookId = bookId.value;
  const requestedPeriod = period.value || undefined;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId) {
    trialRows.value = [];
    unclassifiedAccountCount.value = 0;
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const result = await mumarenFinanceCenterApi.getTrialBalance({
      book_id: requestedBookId,
      period: requestedPeriod,
    });
    if (requestVersion !== loadRequestVersion || requestedBookId !== bookId.value || requestedPeriod !== (period.value || undefined)) return;
    trialRows.value = result.data.data.rows || [];
    unclassifiedAccountCount.value = Number(result.data.data.unclassified_account_count || 0);
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value && requestedPeriod === (period.value || undefined)) error.value = "无法加载独立账簿科目余额表。";
  } finally {
    if (requestVersion === loadRequestVersion) loading.value = false;
  }
};

const onBookChange = async () => {
  await load();
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    initializeBook(books.value);
    if (bookId.value) await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
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
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
