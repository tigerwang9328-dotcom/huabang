<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">账簿查询</p>
        <h2>明细账</h2>
        <p>按科目逐笔展示凭证分录明细;前端派生展示。</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" :disabled="!bookId" @click="load">查询</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
      <el-select v-model="accountId" placeholder="选择科目" clearable @change="load">
        <el-option
          v-for="acc in accounts"
          :key="acc.id"
          :label="`${acc.account_code} ${acc.account_name}`"
          :value="acc.id"
        />
      </el-select>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="凭证分录明细接口待后端补,当前以凭证头展示并按科目名称模糊匹配"
    />

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-empty v-else-if="!bookId" description="请先选择独立账簿" />

    <el-table v-else :data="ledgerRows" empty-text="暂无凭证明细" stripe>
      <el-table-column prop="voucher_date" label="日期" width="120" />
      <el-table-column prop="voucher_no" label="凭证号" min-width="130" />
      <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
      <el-table-column label="借方" width="140" align="right">
        <template #default="scope">{{ money(scope.row.total_debit) }}</template>
      </el-table-column>
      <el-table-column label="贷方" width="140" align="right">
        <template #default="scope">{{ money(scope.row.total_credit) }}</template>
      </el-table-column>
      <el-table-column label="累计余额" width="150" align="right">
        <template #default="scope">{{ money(scope.row.balance) }}</template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  mumarenFinanceCenterApi,
  type MumarenFinanceAccount,
  type MumarenFinanceBook,
  type MumarenFinanceVoucher,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const bookId = ref<number>();
const accounts = ref<MumarenFinanceAccount[]>([]);
const accountId = ref<number>();
const vouchers = ref<MumarenFinanceVoucher[]>([]);
const error = ref("");
const loading = ref(false);

const money = (value?: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const selectedAccount = computed(() => accounts.value.find((a) => a.id === accountId.value));

interface LedgerRow extends MumarenFinanceVoucher {
  balance: number;
}

const ledgerRows = computed<LedgerRow[]>(() => {
  const acc = selectedAccount.value;
  let list = [...vouchers.value];
  if (acc) {
    const keyword = acc.account_name || "";
    list = list.filter(
      (v) =>
        (v.summary && v.summary.includes(keyword)) ||
        (v.voucher_no && v.voucher_no.includes(keyword)),
    );
  }
  list.sort((a, b) =>
    a.voucher_date < b.voucher_date ? -1 : a.voucher_date > b.voucher_date ? 1 : a.id - b.id,
  );
  let cumulative = 0;
  return list.map((v) => {
    cumulative += (v.total_debit || 0) - (v.total_credit || 0);
    return { ...v, balance: cumulative };
  });
});

const onBookChange = async () => {
  accountId.value = undefined;
  accounts.value = [];
  vouchers.value = [];
  error.value = "";
  if (!bookId.value) return;
  try {
    accounts.value = (await mumarenFinanceCenterApi.listAccounts(bookId.value)).data.data;
  } catch {
    error.value = "无法加载独立科目体系。";
  }
};

const load = async () => {
  if (!bookId.value) {
    vouchers.value = [];
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    vouchers.value = (await mumarenFinanceCenterApi.listVouchers({ book_id: bookId.value })).data.data;
  } catch {
    error.value = "无法加载独立当前账凭证。";
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
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
