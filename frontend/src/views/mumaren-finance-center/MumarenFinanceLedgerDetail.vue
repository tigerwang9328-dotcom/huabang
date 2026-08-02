<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">账簿查询</p>
        <h2>明细账</h2>
        <p>按科目逐笔展示实际已过账凭证分录；金蝶迁移账簿仅供只读查询。</p>
      </div>
      <div class="heading-actions"><el-button :loading="loading" :disabled="!bookId" @click="load">查询</el-button><el-button :loading="loading" :disabled="!hasMore" @click="loadMore">加载更多</el-button></div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
      <el-select v-model="accountId" placeholder="全部科目" clearable @change="load">
        <el-option v-for="account in accounts" :key="account.id" :label="`${account.account_code} ${account.account_name}`" :value="account.id" />
      </el-select>
    </div>

    <el-alert type="info" :closable="false" show-icon title="仅展示已过账分录；历史金蝶账簿不会出现录入、审核或过账操作。" />
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-empty v-else-if="!bookId" description="请先选择独立账簿" />
    <el-table v-else :data="rows" empty-text="暂无已过账分录" stripe>
      <el-table-column prop="voucher_date" label="日期" width="120" />
      <el-table-column prop="voucher_no" label="凭证号" min-width="130" />
      <el-table-column prop="account_code" label="科目编码" width="120" />
      <el-table-column prop="account_name" label="科目名称" min-width="150" />
      <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
      <el-table-column label="借方" width="140" align="right"><template #default="scope">{{ money(scope.row.debit_amount) }}</template></el-table-column>
      <el-table-column label="贷方" width="140" align="right"><template #default="scope">{{ money(scope.row.credit_amount) }}</template></el-table-column>
      <el-table-column label="分录累计余额" width="150" align="right"><template #default="scope">{{ money(scope.row.running_balance) }}</template></el-table-column>
    </el-table>
    <div v-if="bookId" class="table-footer"><span>已载入 {{ rows.length }} 条分录；分录累计余额按科目方向计算，不含余额快照期初。</span><el-button v-if="hasMore" :loading="loading" @click="loadMore">加载更多</el-button></div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { mumarenFinanceCenterApi, type MumarenFinanceAccount, type MumarenFinanceBook, type MumarenFinanceLedgerLine } from "@/api/mumarenFinanceCenter";

interface LedgerRow extends MumarenFinanceLedgerLine { summary: string }

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook } = useMumarenFinanceBook();
const accounts = ref<MumarenFinanceAccount[]>([]);
const accountId = ref<number>();
const rows = ref<LedgerRow[]>([]);
const offset = ref(0);
const hasMore = ref(false);
const error = ref("");
const loading = ref(false);
let loadRequestVersion = 0;

const money = (value?: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value) || 0);

const load = async (reset = true) => {
  const requestedBookId = bookId.value;
  const requestedAccountId = accountId.value;
  const requestedOffset = reset ? 0 : offset.value;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId) { rows.value = []; hasMore.value = false; loading.value = false; return; }
  if (reset) { offset.value = 0; rows.value = []; hasMore.value = false; }
  loading.value = true;
  error.value = "";
  try {
    const response = await mumarenFinanceCenterApi.getLedgerLines({ book_id: requestedBookId, account_id: requestedAccountId, offset: requestedOffset });
    if (requestVersion !== loadRequestVersion || requestedBookId !== bookId.value || requestedAccountId !== accountId.value || requestedOffset !== offset.value) return;
    const page = response.data.data;
    const mapped = page.rows.map((line) => ({ ...line, summary: line.line_summary || line.voucher_summary || "" }));
    rows.value = reset ? mapped : [...rows.value, ...mapped];
    offset.value = page.next_offset;
    hasMore.value = page.has_more;
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value && requestedAccountId === accountId.value) error.value = "无法加载独立账簿明细分录。";
  } finally {
    if (requestVersion === loadRequestVersion) loading.value = false;
  }
};

const loadMore = () => load(false);

const onBookChange = async () => {
  const requestedBookId = bookId.value;
  const requestVersion = ++loadRequestVersion;
  loading.value = true;
  accountId.value = undefined;
  accounts.value = [];
  rows.value = [];
  offset.value = 0;
  hasMore.value = false;
  error.value = "";
  if (!requestedBookId) { loading.value = false; return; }
  try {
    const response = await mumarenFinanceCenterApi.listAccounts(requestedBookId);
    if (requestVersion !== loadRequestVersion || requestedBookId !== bookId.value) return;
    accounts.value = response.data.data;
    await load();
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value) error.value = "无法加载独立科目体系。";
  } finally {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value) loading.value = false;
  }
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    initializeBook(books.value);
    await onBookChange();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.heading-actions, .table-footer { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.filters { display: flex; gap: 12px; }
.filters > * { max-width: 280px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
.table-footer { justify-content: space-between; color: #5d6b7e; font-size: 13px; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
