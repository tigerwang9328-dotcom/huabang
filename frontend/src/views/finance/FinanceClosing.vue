<template>
  <div class="fc-closing">
    <div class="page-header">
      <h2>期末处理</h2>
    </div>

    <el-row :gutter="16" class="kpi-row">
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: #eef2ff;"><el-icon :size="22" color="#2563eb"><Calendar /></el-icon></div>
            <div class="kpi-text">
              <span class="kpi-label">当前期间</span>
              <b class="kpi-value">{{ currentPeriod || "--" }}</b>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: #f0fdf4;"><el-icon :size="22" color="#16a34a"><CircleCheck /></el-icon></div>
            <div class="kpi-text">
              <span class="kpi-label">期间状态</span>
              <b class="kpi-value">
                <el-tag :type="periodStatus === 'open' ? 'warning' : 'success'" size="small">{{ periodStatus || "--" }}</el-tag>
              </b>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: #fffbeb;"><el-icon :size="22" color="#ca8a04"><Document /></el-icon></div>
            <div class="kpi-text">
              <span class="kpi-label">凭证总数</span>
              <b class="kpi-value">{{ voucherTotal }}</b>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: #fef2f2;"><el-icon :size="22" color="#dc2626"><Select /></el-icon></div>
            <div class="kpi-text">
              <span class="kpi-label">已过账数</span>
              <b class="kpi-value">{{ postedVoucherCount }}</b>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <div class="filter-bar">
      <el-select v-model="selectedBookId" placeholder="选择账套" filterable @change="onBookChange">
        <el-option v-for="b in books" :key="b.id" :label="b.company_name" :value="b.id" />
      </el-select>
    </div>

    <el-table :data="periods" stripe size="small" v-loading="loading">
      <el-table-column prop="company_name" label="账套" min-width="160" />
      <el-table-column prop="period" label="期间" width="110" />
      <el-table-column prop="fiscal_year" label="会计年度" width="100" align="center" />
      <el-table-column prop="fiscal_period" label="会计月份" width="100" align="center" />
      <el-table-column prop="start_date" label="开始日期" width="110" />
      <el-table-column prop="end_date" label="结束日期" width="110" />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'open' ? 'warning' : 'success'" size="small">
            {{ row.status === 'open' ? '打开' : '已结账' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'open'"
            link
            type="primary"
            size="small"
            @click="openAction(row, 'close')"
          >结账</el-button>
          <el-button
            v-if="row.status === 'closed'"
            link
            type="warning"
            size="small"
            @click="openAction(row, 'reopen')"
          >反结账</el-button>
          <el-button
            link
            type="success"
            size="small"
            @click="openAction(row, 'profit_loss')"
          >损益结转</el-button>
          <el-button
            v-if="row.status !== 'open'"
            link
            type="info"
            size="small"
            @click="openAction(row, 'open')"
          >打开期间</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 操作确认弹窗 -->
    <el-dialog v-model="showActionDialog" :title="actionTitle" width="440px" :close-on-click-modal="false">
      <el-form :model="actionForm" label-width="80px">
        <el-form-item label="期间">
          <span>{{ actionTarget?.period }}</span>
        </el-form-item>
        <el-form-item label="操作">
          <el-tag>{{ actionTitle }}</el-tag>
        </el-form-item>
        <el-form-item label="原因" required>
          <el-input v-model="actionForm.reason" type="textarea" :rows="3" placeholder="请输入操作原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showActionDialog = false">取消</el-button>
        <el-button type="primary" :loading="actionLoading" @click="handleAction">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Calendar, CircleCheck, Document, Select } from "@element-plus/icons-vue";
import { financeCenterApi, type FinBook, type FinPeriod } from "@/api/financeCenter";

const selectedBookId = ref<number | null>(null);
const books = ref<FinBook[]>([]);
const periods = ref<(FinPeriod & { company_name?: string })[]>([]);
const loading = ref(false);

const currentPeriod = ref("");
const periodStatus = ref("");
const voucherTotal = ref(0);
const postedVoucherCount = ref(0);

const showActionDialog = ref(false);
const actionType = ref<"open" | "close" | "reopen" | "profit_loss">("close");
const actionTarget = ref<(FinPeriod & { company_name?: string }) | null>(null);
const actionLoading = ref(false);
const actionForm = ref({ reason: "" });

const actionTitleMap: Record<string, string> = {
  open: "打开期间",
  close: "结账",
  reopen: "反结账",
  profit_loss: "损益结转",
};

const actionTitle = ref("");

const loadBooks = async () => {
  try {
    const res = await financeCenterApi.listBooks();
    books.value = res.data.data || [];
    if (books.value.length > 0 && !selectedBookId.value) {
      selectedBookId.value = books.value[0].id;
      onBookChange();
    }
  } catch { /* ignore */ }
};

const onBookChange = async () => {
  if (!selectedBookId.value) return;
  loading.value = true;
  try {
    const [periodsRes, vouchersRes] = await Promise.all([
      financeCenterApi.listPeriods({ book_id: selectedBookId.value }),
      financeCenterApi.listVouchers({ book_id: selectedBookId.value, ...{ page_size: 9999 } }),
    ]);
    const allPeriods = periodsRes.data.data || [];
    const book = books.value.find((b) => b.id === selectedBookId.value);
    periods.value = allPeriods.map((p) => ({
      ...p,
      company_name: book?.company_name || "",
    }));

    const openPeriod = allPeriods.find((p) => p.status === "open");
    currentPeriod.value = openPeriod?.period || allPeriods[allPeriods.length - 1]?.period || "";
    periodStatus.value = openPeriod?.status || (allPeriods.length > 0 ? allPeriods[allPeriods.length - 1].status : "");

    const vData = vouchersRes.data.data;
    const vouchers = vData?.items || [];
    voucherTotal.value = vouchers.length;
    postedVoucherCount.value = vouchers.filter((v) => v.status === "posted").length;
  } catch { /* ignore */ }
  loading.value = false;
};

const openAction = (row: FinPeriod & { company_name?: string }, type: "open" | "close" | "reopen" | "profit_loss") => {
  actionTarget.value = row;
  actionType.value = type;
  actionTitle.value = actionTitleMap[type];
  actionForm.value = { reason: "" };
  showActionDialog.value = true;
};

const handleAction = async () => {
  if (!actionTarget.value || !actionForm.value.reason) {
    ElMessage.warning("请填写操作原因");
    return;
  }
  actionLoading.value = true;
  try {
    const payload = {
      book_id: selectedBookId.value!,
      period: actionTarget.value.period,
      reason: actionForm.value.reason,
    };
    switch (actionType.value) {
      case "open":
        await financeCenterApi.openPeriod({ book_id: payload.book_id, period: payload.period });
        break;
      case "close":
        await financeCenterApi.closePeriod(payload);
        break;
      case "reopen":
        await financeCenterApi.reopenPeriod(payload);
        break;
      case "profit_loss":
        await financeCenterApi.profitLossCarryover(payload);
        break;
    }
    ElMessage.success(`${actionTitle.value}成功`);
    showActionDialog.value = false;
    onBookChange();
  } catch { ElMessage.error(`${actionTitle.value}失败`); }
  actionLoading.value = false;
};

onMounted(() => {
  loadBooks();
});
</script>

<script lang="ts">
export default { name: "FinanceClosing" };
</script>

<style scoped>
.fc-closing { padding: 0; }
.page-header { margin-bottom: 20px; }
.page-header h2 { font-size: 20px; color: #1f2937; margin: 0; }
.kpi-row { margin-bottom: 20px; }
.kpi-card { border-radius: 8px; border: 1px solid #e5e7eb; }
.kpi-card :deep(.el-card__body) { padding: 16px 20px; }
.kpi-content { display: flex; align-items: center; gap: 12px; }
.kpi-icon { width: 42px; height: 42px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.kpi-text { display: flex; flex-direction: column; gap: 4px; }
.kpi-label { font-size: 12px; color: #6b7280; }
.kpi-value { font-size: 22px; color: #111827; font-weight: 700; }
.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
</style>