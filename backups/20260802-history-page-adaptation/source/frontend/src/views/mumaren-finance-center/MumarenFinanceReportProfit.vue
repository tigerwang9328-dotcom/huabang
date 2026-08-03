<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">报表</p>
        <h2>利润表</h2>
        <p>按独立当前账已过账凭证计算损益;不混入历史归档。</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" :disabled="!bookId || isHistoricalBook" @click="load">查询</el-button>
        <el-button :disabled="!bookId || isHistoricalBook" @click="printReport">打印</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
      <el-input v-model="period" placeholder="2026-07(可选)" />
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-alert v-else-if="isHistoricalBook" type="warning" :closable="false" show-icon title="金蝶迁移账簿的利润表科目待映射；请使用科目余额表和明细账核对原始已过账数据。" />

    <el-descriptions v-else title="利润表" :column="3" border>
      <el-descriptions-item label="收入">{{ money(profit.total_income) }}</el-descriptions-item>
      <el-descriptions-item label="费用">{{ money(profit.total_expense) }}</el-descriptions-item>
      <el-descriptions-item label="净利润">{{ money(profit.net_profit) }}</el-descriptions-item>
    </el-descriptions>
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { computed, onMounted, ref } from "vue";
import {
  mumarenFinanceCenterApi,
  type MumarenFinanceBook,
  type MumarenProfitStatement,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook, isReadonly } = useMumarenFinanceBook();
const period = ref("");
const profit = ref<Partial<MumarenProfitStatement>>({});
const error = ref("");
const loading = ref(false);
const isHistoricalBook = computed(() =>
  isReadonly.value || Boolean(books.value.find((book) => book.id === bookId.value)?.is_readonly),
);

const money = (value?: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
const printReport = () => window.print();

const load = async () => {
  if (!bookId.value || isHistoricalBook.value) return;
  loading.value = true;
  error.value = "";
  try {
    const result = await mumarenFinanceCenterApi.getProfitStatement({
      book_id: bookId.value,
      period: period.value || undefined,
    });
    profit.value = result.data.data;
  } catch {
    error.value = "无法加载独立当前账利润表。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = async () => {
  if (bookId.value) {
    await load();
  } else {
    profit.value = {};
  }
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    initializeBook(books.value);
    // 自动加载第一个账簿
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
