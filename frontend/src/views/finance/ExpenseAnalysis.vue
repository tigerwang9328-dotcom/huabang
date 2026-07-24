<template>
  <div class="expense-analysis page">
    <div class="page-header"><h2 class="page-title">费用分析</h2><span class="page-sub">全部费用记录（报销 + 付款）</span></div>
    <div v-if="expenseState === 'loading'" class="sec state-panel" v-loading="true" />
    <el-alert v-else-if="expenseState === 'error'" :title="expenseError" type="error" :closable="false" />
    <el-empty v-else-if="expenseState === 'empty'" description="暂无费用数据，待钉钉审批数据接入后展示" :image-size="90" />
    <div v-else-if="expenseState === 'ready'" class="sec">
      <el-table :data="items" size="small" stripe>
        <el-table-column prop="applicant_name" label="申请人" min-width="100" />
        <el-table-column prop="department_name" label="部门" min-width="120" />
        <el-table-column prop="expense_type" label="事项" min-width="150" />
        <el-table-column label="金额" min-width="110"><template #default="{ row }">{{ fmtMoney(row.amount) }}</template></el-table-column>
        <el-table-column label="分类" width="90"><template #default="{ row }"><el-tag size="small" :type="row.category === 'payment' ? 'warning' : 'success'">{{ row.category === 'payment' ? '付款' : '报销' }}</el-tag></template></el-table-column>
        <el-table-column prop="expense_date" label="日期" min-width="110" />
      </el-table>
      <div class="pager" v-if="total > pageSize"><el-pagination layout="prev, pager, next" :total="total" :page-size="pageSize" :current-page="page" @current-change="onPage" /></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { financeApi, type FinanceExpenseRecord } from "@/api/finance";
type ExpenseState = "loading" | "error" | "empty" | "ready";
const expenseState = ref<ExpenseState>("loading");
const expenseError = ref("");
const items = ref<FinanceExpenseRecord[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const fmtMoney = (value: number) => value >= 10000 ? "¥" + (value / 10000).toFixed(2) + "万" : "¥" + value.toFixed(0);
const load = async () => {
  expenseState.value = "loading";
  expenseError.value = "";
  items.value = [];
  total.value = 0;
  try {
    const data = (await financeApi.getExpenses({ page: page.value, page_size: pageSize })).data.data;
    items.value = data.items;
    total.value = data.total;
    expenseState.value = data.items.length ? "ready" : "empty";
  } catch {
    expenseError.value = "费用数据加载失败，请稍后重试";
    expenseState.value = "error";
  }
};
const onPage = (nextPage: number) => { page.value = nextPage; void load(); };
onMounted(load);
</script>

<style scoped>
.expense-analysis.page { display: flex; flex-direction: column; gap: 18px; }
.page-header { display: flex; align-items: baseline; gap: 10px; }
.page-title { font-size: 20px; font-weight: 700; color: #111827; margin: 0; }
.page-sub { font-size: 13px; color: #9CA3AF; }
.sec { background: #fff; border-radius: 8px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.state-panel { min-height: 180px; }
.pager { margin-top: 14px; display: flex; justify-content: flex-end; }
@media (max-width: 768px) { .page-header { align-items: flex-start; flex-wrap: wrap; } .page-sub { flex-basis: 100%; } }
</style>
