<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">报表</p>
        <h2>税金明细表</h2>
        <p>按独立账簿展示税务记录明细;只读。</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" :disabled="!bookId" @click="load">查询</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <template v-else-if="loaded">
      <el-table :data="records" empty-text="暂无独立税务记录" stripe>
        <el-table-column prop="tax_name" label="税种" min-width="160" />
        <el-table-column prop="period" label="期间" width="120" />
        <el-table-column label="应缴" width="140" align="right">
          <template #default="scope">{{ money(scope.row.tax_amount) }}</template>
        </el-table-column>
        <el-table-column label="已缴" width="140" align="right">
          <template #default="scope">{{ money(scope.row.paid_amount) }}</template>
        </el-table-column>
        <el-table-column label="未缴" width="140" align="right">
          <template #default="scope">
            <span :class="Number(scope.row.unpaid_amount) > 0 ? 'text-danger' : 'text-ok'">{{ money(scope.row.unpaid_amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'paid' ? 'success' : ''" size="small">{{ statusLabel(scope.row.status) }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </template>
    <el-empty v-else description="请选择独立账簿后查询税务明细" />
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { onMounted, ref } from "vue";
import {
  mumarenFinanceCenterApi,
  type MumarenFinanceBook,
  type MumarenTaxRecord,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook } = useMumarenFinanceBook();
const records = ref<MumarenTaxRecord[]>([]);
const error = ref("");
const loading = ref(false);
const loaded = ref(false);

const money = (value: number | undefined) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

// 状态展示契约:pending → "未缴",paid → "已缴"
const statusLabel = (s: string) => (s === "paid" ? "已缴" : "未缴");

const load = async () => {
  if (!bookId.value) {
    loaded.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    records.value = (await mumarenFinanceCenterApi.listTaxRecords({ book_id: bookId.value })).data.data;
    loaded.value = true;
  } catch {
    error.value = "无法加载独立税务明细。";
    loaded.value = false;
  } finally {
    loading.value = false;
  }
};

const onBookChange = () => {
  // 切换账簿时清空已加载数据,必须由用户主动点击"查询"
  loaded.value = false;
  records.value = [];
};

onMounted(async () => {
  // 仅加载账簿列表,不自动选择账簿,不自动请求税务接口。
  // 用户必须主动选择独立账簿后才能查询税务明细(沿用 Tax.vue 约定)。
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    initializeBook(books.value);
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
.text-danger { color: #f56c6c; font-weight: 600; }
.text-ok { color: #67c23a; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
