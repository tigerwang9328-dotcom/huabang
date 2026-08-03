<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">金蝶迁移数据</p>
        <h2>余额快照核对</h2>
        <p>只读来源证据，不计入当前账报表，供与金蝶期末余额核对。</p>
      </div>
      <el-button :loading="loading" :disabled="!bookId || !isHistoricalBook" @click="load">刷新</el-button>
    </div>
    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="load">
        <el-option v-for="book in books" :key="book.id" :label="bookLabel(book)" :value="book.id" />
      </el-select>
      <el-input v-model="period" placeholder="期间，如 2026-07" @change="load" />
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-empty v-else-if="!bookId" description="请选择金蝶迁移账簿" />
    <el-empty v-else-if="!isHistoricalBook" description="当前账簿没有金蝶迁移余额快照；请选择金蝶迁移账簿核对历史余额。" />
    <el-table v-else :data="rows" empty-text="该账簿暂无余额快照" stripe>
      <el-table-column prop="period_code" label="期间" width="110" />
      <el-table-column prop="account_code" label="科目编码" width="130" />
      <el-table-column prop="account_name" label="科目名称" min-width="180" />
      <el-table-column label="期初" align="right"><template #default="s">{{ money(s.row.opening_amount) }}</template></el-table-column>
      <el-table-column label="本期借方" align="right"><template #default="s">{{ money(s.row.period_debit) }}</template></el-table-column>
      <el-table-column label="本期贷方" align="right"><template #default="s">{{ money(s.row.period_credit) }}</template></el-table-column>
      <el-table-column label="期末" align="right"><template #default="s">{{ money(s.row.closing_amount) }}</template></el-table-column>
    </el-table>
    <div v-if="bookId && isHistoricalBook" class="table-footer">
      <span>已载入 {{ rows.length }} 条余额快照。</span>
      <el-button v-if="hasMore" :loading="loading" @click="loadMore">加载更多</el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { mumarenFinanceCenterApi, type MumarenFinanceBalanceSnapshot, type MumarenFinanceBook } from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook } = useMumarenFinanceBook();
const rows = ref<MumarenFinanceBalanceSnapshot[]>([]);
const period = ref("");
const loading = ref(false);
const error = ref("");
const offset = ref(0);
const hasMore = ref(false);
const pageSize = 500;
let loadRequestVersion = 0;

const selectedBook = computed(() => books.value.find((book) => book.id === bookId.value));
const isHistoricalBook = computed(() => Boolean(selectedBook.value?.is_readonly));
const bookLabel = (book: MumarenFinanceBook) =>
  book.is_readonly ? book.book_name : `${book.book_name}（非金蝶账簿）`;
const money = (value: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value) || 0);

const load = async (reset = true) => {
  const requestedBookId = bookId.value;
  const requestedPeriod = period.value;
  const requestedOffset = reset ? 0 : offset.value;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId || !isHistoricalBook.value) {
    rows.value = [];
    hasMore.value = false;
    loading.value = false;
    return;
  }
  if (reset) {
    rows.value = [];
    offset.value = 0;
    hasMore.value = false;
  }
  loading.value = true;
  error.value = "";
  try {
    const response = await mumarenFinanceCenterApi.getHistoryBalanceSnapshots({
      book_id: requestedBookId,
      period: requestedPeriod || undefined,
      limit: pageSize,
      offset: requestedOffset,
    });
    if (requestVersion !== loadRequestVersion || requestedBookId !== bookId.value || requestedPeriod !== period.value) return;
    const page = response.data.data;
    rows.value = reset ? page : [...rows.value, ...page];
    offset.value = requestedOffset + page.length;
    hasMore.value = page.length === pageSize;
  } catch {
    if (requestVersion === loadRequestVersion) error.value = "无法加载金蝶余额快照。";
  } finally {
    if (requestVersion === loadRequestVersion) loading.value = false;
  }
};

const loadMore = () => load(false);

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    initializeBook(books.value);
    await load();
  } catch {
    error.value = "无法加载金蝶迁移账簿。";
  }
});
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading, .table-footer { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.filters { display: flex; gap: 12px; }
.filters > * { max-width: 280px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; }
h2 { margin: 8px 0; }
p, .table-footer { color: #5d6b7e; }
.table-footer { align-items: center; font-size: 13px; }
@media (max-width: 640px) { .heading, .filters, .table-footer { flex-direction: column; } .filters > * { max-width: none; } }
</style>
