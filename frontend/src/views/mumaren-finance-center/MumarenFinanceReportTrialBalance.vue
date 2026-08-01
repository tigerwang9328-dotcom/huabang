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

    <el-table v-else :data="trialRows" empty-text="暂无已过账数据" stripe>
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
import { onMounted, ref } from "vue";
import {
  mumarenFinanceCenterApi,
  type MumarenFinanceBook,
  type MumarenTrialBalanceRow,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const bookId = ref<number>();
const period = ref("");
const trialRows = ref<MumarenTrialBalanceRow[]>([]);
const error = ref("");
const loading = ref(false);

const money = (value?: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const load = async () => {
  if (!bookId.value) return;
  loading.value = true;
  error.value = "";
  try {
    const result = await mumarenFinanceCenterApi.getTrialBalance({
      book_id: bookId.value,
      period: period.value || undefined,
    });
    trialRows.value = result.data.data.rows || [];
  } catch {
    error.value = "无法加载独立当前账科目余额表。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = async () => {
  // 选择账簿后自动加载第一个账簿
  if (bookId.value) {
    await load();
  } else {
    trialRows.value = [];
  }
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    // 自动加载第一个账簿
    bookId.value = books.value[0]?.id;
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
