<template>
  <div class="fc-cockpit">
    <div class="page-header">
      <h2>数据罗盘</h2>
      <span class="page-desc">财务中心首页仪表盘</span>
    </div>

    <el-row :gutter="16" class="kpi-row">
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: #eef2ff;"><el-icon :size="24" color="#2563eb"><Collection /></el-icon></div>
            <div class="kpi-text">
              <span class="kpi-label">账套数量</span>
              <b class="kpi-value">{{ bookCount }}</b>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: #f0fdf4;"><el-icon :size="24" color="#16a34a"><CircleCheck /></el-icon></div>
            <div class="kpi-text">
              <span class="kpi-label">已结账期间数</span>
              <b class="kpi-value">{{ closedPeriodCount }}</b>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: #fffbeb;"><el-icon :size="24" color="#ca8a04"><Clock /></el-icon></div>
            <div class="kpi-text">
              <span class="kpi-label">待审核凭证数</span>
              <b class="kpi-value">{{ pendingVoucherCount }}</b>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: #fef2f2;"><el-icon :size="24" color="#dc2626"><Document /></el-icon></div>
            <div class="kpi-text">
              <span class="kpi-label">本月凭证数</span>
              <b class="kpi-value">{{ monthVoucherCount }}</b>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">最近操作日志</span></template>
      <el-table :data="logs" stripe size="small" v-loading="logLoading">
        <el-table-column prop="created_at" label="时间" width="170" />
        <el-table-column prop="actor_name" label="操作人" width="120" />
        <el-table-column prop="action" label="操作" min-width="140" />
        <el-table-column prop="target_type" label="目标类型" width="120" />
        <el-table-column prop="target_id" label="目标ID" width="100" />
        <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { Collection, CircleCheck, Clock, Document } from "@element-plus/icons-vue";
import { financeCenterApi, type FinBook, type FinPeriod, type FinVoucher, type FinOperationLog } from "@/api/financeCenter";

const money = (v: number | null | undefined) => v == null ? "--" : v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });

const books = ref<FinBook[]>([]);
const periods = ref<FinPeriod[]>([]);
const vouchers = ref<FinVoucher[]>([]);
const logs = ref<FinOperationLog[]>([]);
const logLoading = ref(false);

const bookCount = ref(0);
const closedPeriodCount = ref(0);
const pendingVoucherCount = ref(0);
const monthVoucherCount = ref(0);

const loadAll = async () => {
  try {
    const [booksRes] = await Promise.all([
      financeCenterApi.listBooks(),
    ]);
    books.value = booksRes.data.data || [];
    bookCount.value = books.value.length;

    if (books.value.length > 0) {
      const firstBook = books.value[0];
      const [periodsRes, vouchersRes] = await Promise.all([
        financeCenterApi.listPeriods({ book_id: firstBook.id }),
        financeCenterApi.listVouchers({ book_id: firstBook.id, ...{ page_size: 9999 } }),
      ]);
      periods.value = periodsRes.data.data || [];
      closedPeriodCount.value = periods.value.filter((p) => p.status === "closed").length;

      const vData = vouchersRes.data.data;
      vouchers.value = vData?.items || [];
      pendingVoucherCount.value = vouchers.value.filter((v) => v.status === "draft" || v.status === "pending_review").length;

      const now = new Date();
      const thisMonth = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}`;
      monthVoucherCount.value = vouchers.value.filter((v) => v.period && v.period.startsWith(thisMonth)).length;
    }

    const logsRes = await financeCenterApi.listOperationLogs({ book_id: books.value.length > 0 ? books.value[0].id : 0, page_size: 10 });
    logs.value = (logsRes.data.data as any)?.items || [];
  } catch {
    // silently handle
  }
};

onMounted(() => {
  loadAll();
});
</script>

<script lang="ts">
export default { name: "FinanceCockpit" };
</script>

<style scoped>
.fc-cockpit { padding: 0; }
.page-header { margin-bottom: 20px; }
.page-header h2 { font-size: 20px; color: #1f2937; margin: 0 0 4px; }
.page-desc { font-size: 13px; color: #9ca3af; }
.kpi-row { margin-bottom: 20px; }
.kpi-card { border-radius: 8px; border: 1px solid #e5e7eb; }
.kpi-card :deep(.el-card__body) { padding: 20px; }
.kpi-content { display: flex; align-items: center; gap: 14px; }
.kpi-icon { width: 48px; height: 48px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.kpi-text { display: flex; flex-direction: column; gap: 4px; }
.kpi-label { font-size: 13px; color: #6b7280; }
.kpi-value { font-size: 26px; color: #111827; font-weight: 700; }
.section-card { border-radius: 8px; border: 1px solid #e5e7eb; }
.section-card :deep(.el-card__header) { padding: 14px 20px; border-bottom: 1px solid #f3f4f6; }
.card-title { font-size: 15px; font-weight: 600; color: #1f2937; }
</style>