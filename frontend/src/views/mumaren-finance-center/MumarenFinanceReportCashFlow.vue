<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">财务报表</p>
        <h2>现金流量表</h2>
        <p>按现金类科目派生经营/投资/筹资活动现金流。</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" :disabled="!bookId" @click="load">查询</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="load">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <template v-else-if="bookId">
      <el-table :data="activities" empty-text="暂无现金类科目数据" stripe size="small">
        <el-table-column prop="category" label="活动类别" min-width="140" />
        <el-table-column label="现金流入" align="right">
          <template #default="scope">{{ money(scope.row.inflow) }}</template>
        </el-table-column>
        <el-table-column label="现金流出" align="right">
          <template #default="scope">{{ money(scope.row.outflow) }}</template>
        </el-table-column>
        <el-table-column label="净额" align="right">
          <template #default="scope">{{ money(scope.row.net) }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="200" />
      </el-table>

      <el-descriptions :column="1" border>
        <el-descriptions-item label="现金净增加合计">{{ money(cashNetIncrease) }}</el-descriptions-item>
      </el-descriptions>
      <p class="gap-note">注:投资/筹资活动现金流待后端补独立接口,当前仅由现金类科目(1001 库存现金 / 1002 银行存款 / 1012 其他货币资金)派生经营活动净额与现金净增加。</p>
    </template>

    <el-empty v-else description="请选择独立账簿后查看现金流量表" />
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { computed, onMounted, ref } from "vue";
import { mumarenFinanceCenterApi, type MumarenFinanceBook, type MumarenTrialBalanceRow } from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook } = useMumarenFinanceBook();
const rows = ref<MumarenTrialBalanceRow[]>([]);
const error = ref("");
const loading = ref(false);

const money = (value?: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const isCashCode = (code: string, prefixes: string[]) => {
  const c = (code || "").trim();
  return prefixes.some((p) => c.startsWith(p));
};

// 经营活动:1001 库存现金、1002 银行存款。
const operatingRows = computed(() =>
  rows.value.filter((r) => isCashCode(r.account_code, ["1001", "1002"])),
);
// 现金类科目(含 1012 其他货币资金),用于现金净增加合计。
const cashRows = computed(() =>
  rows.value.filter((r) => isCashCode(r.account_code, ["1001", "1002", "1012"])),
);

const operatingInflow = computed(() => operatingRows.value.reduce((s, r) => s + Number(r.debit_amount), 0));
const operatingOutflow = computed(() => operatingRows.value.reduce((s, r) => s + Number(r.credit_amount), 0));
const operatingNet = computed(() => operatingInflow.value - operatingOutflow.value);

// 现金净增加 = 现金类科目期末 (借方 - 贷方) 合计。
const cashNetIncrease = computed(() =>
  cashRows.value.reduce((s, r) => s + (Number(r.closing_debit) - Number(r.closing_credit)), 0),
);

const activities = computed(() => [
  { category: "经营活动", inflow: operatingInflow.value, outflow: operatingOutflow.value, net: operatingNet.value, note: "" },
  { category: "投资活动", inflow: 0, outflow: 0, net: 0, note: "投资活动现金流待后端补" },
  { category: "筹资活动", inflow: 0, outflow: 0, net: 0, note: "筹资活动现金流待后端补" },
]);

const load = async () => {
  if (!bookId.value) {
    rows.value = [];
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const result = await mumarenFinanceCenterApi.getTrialBalance({ book_id: bookId.value });
    rows.value = result.data.data.rows || [];
  } catch {
    error.value = "无法加载现金流量表数据。";
    rows.value = [];
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
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
.gap-note { color: #9b5b00; font-size: 12px; line-height: 1.6; margin: 4px 0 0; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
