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
        <el-button :disabled="!bookId" @click="printReport">打印</el-button>
        <el-button :disabled="!bookId" @click="exportStatement">导出</el-button>
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
        <el-descriptions-item label="现金流入合计">{{ money(statement.total_inflow) }}</el-descriptions-item>
        <el-descriptions-item label="现金流出合计">{{ money(statement.total_outflow) }}</el-descriptions-item>
        <el-descriptions-item label="现金流净额">{{ money(statement.total_net) }}</el-descriptions-item>
        <el-descriptions-item label="现金净增加（已过账凭证）">{{ money(statement.cash_net_increase) }}</el-descriptions-item>
      </el-descriptions>
      <p class="gap-note">报表仅汇总当前独立账簿中已过账资金流水；未过账草稿不进入报表。现金净增加另按已过账凭证的现金类科目计算，用于核对。</p>
    </template>

    <el-empty v-else description="请选择独立账簿后查看现金流量表" />
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { computed, onMounted, ref } from "vue";
import { mumarenFinanceCenterApi, type MumarenCashFlowStatement, type MumarenFinanceBook } from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook } = useMumarenFinanceBook();
const statement = ref<MumarenCashFlowStatement>({
  sections: {
    operating: { inflow: 0, outflow: 0, net: 0 },
    investing: { inflow: 0, outflow: 0, net: 0 },
    financing: { inflow: 0, outflow: 0, net: 0 },
  },
  total_inflow: 0,
  total_outflow: 0,
  total_net: 0,
  cash_net_increase: 0,
});
const error = ref("");
const loading = ref(false);

const money = (value?: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const activities = computed(() => [
  { category: "经营活动", ...statement.value.sections.operating, note: "已过账经营类资金流水" },
  { category: "投资活动", ...statement.value.sections.investing, note: "已过账投资类资金流水" },
  { category: "筹资活动", ...statement.value.sections.financing, note: "已过账筹资类资金流水" },
]);

const load = async () => {
  if (!bookId.value) {
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    statement.value = (await mumarenFinanceCenterApi.getCashFlowStatement({ book_id: bookId.value })).data.data;
  } catch {
    error.value = "无法加载现金流量表数据。";
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

const printReport = () => window.print();

const exportStatement = () => {
  const rows = [
    ["活动类别", "现金流入", "现金流出", "净额", "备注"],
    ...activities.value.map((row) => [row.category, money(row.inflow), money(row.outflow), money(row.net), row.note]),
    ["现金流入合计", money(statement.value.total_inflow), "", "", ""],
    ["现金流出合计", "", money(statement.value.total_outflow), "", ""],
    ["现金流净额", "", "", money(statement.value.total_net), ""],
    ["现金净增加（已过账凭证）", "", "", money(statement.value.cash_net_increase), ""],
  ];
  const quote = (value: string) => `"${value.replace(/"/g, '""')}"`;
  const blob = new Blob([`\uFEFF${rows.map((row) => row.map(quote).join(",")).join("\r\n")}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `独立财务现金流量表-${bookId.value}.csv`;
  link.click();
  URL.revokeObjectURL(url);
};
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
