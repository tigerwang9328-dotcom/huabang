<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">钉钉同步数据</p>
        <h2>费用分析</h2>
        <p>仅查看钉钉审批同步的报销与付款申请，不会生成、审核或过账凭证。</p>
      </div>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-alert type="info" :closable="false" show-icon title="只读来源：钉钉 finance_expense_records；数据以钉钉同步状态为准。" />

    <div class="filters">
      <el-radio-group v-model="category" @change="resetAndLoad">
        <el-radio-button label="">全部</el-radio-button>
        <el-radio-button label="reimbursement">报销</el-radio-button>
        <el-radio-button label="payment">付款申请</el-radio-button>
      </el-radio-group>
      <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" @change="resetAndLoad" />
      <el-input v-model.trim="approvalStatus" clearable placeholder="审批状态" @keyup.enter="resetAndLoad" @clear="resetAndLoad" />
      <el-button @click="resetAndLoad">查询</el-button>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-table v-else :data="items" v-loading="loading" empty-text="暂无钉钉费用单据" stripe>
      <el-table-column prop="expense_date" label="日期" width="120" />
      <el-table-column prop="category" label="类型" width="110"><template #default="scope">{{ categoryLabel(scope.row.category) }}</template></el-table-column>
      <el-table-column prop="applicant_name" label="申请人" min-width="110" />
      <el-table-column prop="department_name" label="部门" min-width="130" />
      <el-table-column prop="expense_type" label="事项" min-width="180" />
      <el-table-column label="金额" min-width="120" align="right"><template #default="scope">{{ money(scope.row.amount) }}</template></el-table-column>
      <el-table-column prop="approval_status" label="审批状态" min-width="120" />
      <el-table-column label="付款状态" min-width="110"><template #default="scope">{{ paymentLabel(scope.row.payment_status) }}</template></el-table-column>
    </el-table>
    <div class="pager" v-if="total > pageSize"><el-pagination v-model:current-page="page" layout="prev, pager, next" :page-size="pageSize" :total="total" @current-change="load" /></div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { mumarenFinanceCenterApi, type DingtalkExpenseCategory, type MumarenDingtalkExpense } from "@/api/mumarenFinanceCenter";

const category = ref<"" | DingtalkExpenseCategory>("");
const dateRange = ref<[string, string] | null>(null);
const approvalStatus = ref("");
const items = ref<MumarenDingtalkExpense[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const loading = ref(false);
const error = ref("");
const money = (value: number) => new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(value || 0);
const categoryLabel = (value: DingtalkExpenseCategory | null) => value === "reimbursement" ? "报销" : value === "payment" ? "付款申请" : "未分类";
const paymentLabel = (value: string | null) => value === "paid" ? "已付款" : value === "unpaid" ? "未付款" : value || "待同步";
const load = async () => {
  loading.value = true;
  error.value = "";
  try {
    const result = await mumarenFinanceCenterApi.listDingtalkExpenses({
      category: category.value || undefined,
      start_date: dateRange.value?.[0], end_date: dateRange.value?.[1],
      approval_status: approvalStatus.value || undefined,
      page: page.value, page_size: pageSize,
    });
    items.value = result.data.data.items;
    total.value = result.data.data.total;
  } catch {
    error.value = "无法读取钉钉费用数据，请检查同步状态后重试。";
  } finally {
    loading.value = false;
  }
};
const resetAndLoad = () => { page.value = 1; void load(); };
onMounted(() => void load());
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading, .filters { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
.heading > div { margin-right: auto; }.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; } h2 { margin: 8px 0; } p { color: #5d6b7e; }.pager { display: flex; justify-content: flex-end; }
@media (max-width: 640px) { .filters > * { width: 100%; }.filters :deep(.el-radio-group) { width: auto; } }
</style>
