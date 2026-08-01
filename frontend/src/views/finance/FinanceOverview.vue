<template>
  <div class="finance-overview page">
    <div class="page-header">
      <div><h2 class="page-title">财务首页</h2><span class="page-sub">报销 / 付款 / 费用 汇总（来自钉钉审批同步）</span></div>
      <el-button size="small" :loading="overviewState === 'loading'" @click="load">刷新</el-button>
    </div>
    <div v-if="overviewState === 'loading'" class="state-panel" v-loading="true" />
    <el-alert v-else-if="overviewState === 'error'" :title="overviewError" type="error" :closable="false" />
    <el-empty v-else-if="overviewState === 'empty'" description="暂无费用数据，待钉钉审批数据接入后展示" :image-size="80" />
    <template v-else-if="overviewState === 'ready' && overview">
      <div class="cards">
        <div class="card" v-for="card in cards" :key="card.label">
          <div class="c-label">{{ card.label }}</div>
          <div class="c-val" :class="card.cls">{{ card.money ? fmtMoney(card.value) : card.value }}</div>
        </div>
      </div>
      <div class="sec">
        <div class="sec-title">最近费用记录</div>
        <el-table :data="overview.recent_records" size="small" stripe>
          <el-table-column prop="applicant_name" label="申请人" min-width="100" />
          <el-table-column prop="department_name" label="部门" min-width="120" />
          <el-table-column prop="expense_type" label="类型" min-width="140" />
          <el-table-column label="金额" min-width="110"><template #default="{ row }">{{ fmtMoney(row.amount) }}</template></el-table-column>
          <el-table-column label="分类" width="100"><template #default="{ row }"><el-tag size="small" :type="row.category === 'payment' ? 'warning' : 'success'">{{ row.category === 'payment' ? '付款' : '报销' }}</el-tag></template></el-table-column>
          <el-table-column prop="approval_status" label="审批" width="100" />
          <el-table-column prop="expense_date" label="日期" min-width="110" />
        </el-table>
      </div>
      <div class="sec">
        <div class="sec-title">本月部门费用排行</div>
        <el-table :data="overview.department_rank" size="small" stripe>
          <el-table-column type="index" label="#" width="56" />
          <el-table-column prop="department" label="部门" min-width="160" />
          <el-table-column label="费用合计" min-width="140"><template #default="{ row }">{{ fmtMoney(row.amount) }}</template></el-table-column>
        </el-table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { financeApi, type FinanceOverview } from "@/api/finance";
type OverviewState = "loading" | "error" | "empty" | "ready";
const overviewState = ref<OverviewState>("loading");
const overviewError = ref("");
const overview = ref<FinanceOverview | null>(null);
const cards = computed(() => {
  const data = overview.value;
  if (!data) return [];
  return [
    { label: "今日报销金额", value: data.today.reimbursement_amount, money: true },
    { label: "本月报销金额", value: data.month.reimbursement_amount, money: true },
    { label: "今日付款申请", value: data.today.payment_amount, money: true },
    { label: "本月付款申请", value: data.month.payment_amount, money: true },
    { label: "待审批", value: data.pending_count, money: false },
    { label: "已审批未付款", value: data.approved_unpaid_count, money: false, cls: "warn" },
  ];
});
const fmtMoney = (value: number) => value >= 10000 ? "¥" + (value / 10000).toFixed(2) + "万" : "¥" + value.toFixed(0);
const load = async () => {
  overviewState.value = "loading";
  overviewError.value = "";
  overview.value = null;
  try {
    const data = (await financeApi.getOverview()).data.data;
    overview.value = data;
    overviewState.value = data.recent_records.length || data.department_rank.length ? "ready" : "empty";
  } catch {
    overviewError.value = "财务概览加载失败，请稍后重试";
    overviewState.value = "error";
  }
};
onMounted(load);
</script>

<style scoped>
.finance-overview.page { display: flex; flex-direction: column; gap: 18px; }
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.page-title { font-size: 20px; font-weight: 700; color: #111827; margin: 0; }
.page-sub { font-size: 13px; color: #9CA3AF; margin-left: 10px; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.card, .sec { background: #fff; border-radius: 8px; padding: 16px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.c-label { font-size: 12px; color: #9CA3AF; margin-bottom: 8px; }
.c-val { font-size: 22px; font-weight: 700; color: #111827; }
.c-val.warn { color: #D97706; }
.sec-title { font-size: 14px; font-weight: 700; color: #111827; margin-bottom: 14px; }
.state-panel { min-height: 160px; background: #fff; border-radius: 8px; }
@media (max-width: 768px) { .page-header { align-items: flex-start; flex-wrap: wrap; } .page-sub { display: block; margin: 4px 0 0; } }
</style>
