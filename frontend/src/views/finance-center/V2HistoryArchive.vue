<template>
  <div v-loading="loading" class="history-archive">
    <el-alert
      title="只展示已校验并发布到 fin_history 的历史金蝶凭证；历史数据不可编辑，也不参与 V2 当前账制单或过账。"
      type="warning"
      :closable="false"
      show-icon
    />
    <el-alert v-if="loadError" class="history-error" :title="`历史存档读取失败：${loadError}`" type="error" :closable="false" show-icon />

    <div class="toolbar">
      <span>已发布历史凭证</span>
      <el-button text type="primary" :loading="loading" @click="loadVouchers">刷新</el-button>
    </div>
    <el-table :data="vouchers" max-height="560" empty-text="尚未发布可查询的历史金蝶凭证">
      <el-table-column prop="voucher_date" label="日期" min-width="110" />
      <el-table-column prop="voucher_no" label="凭证号" min-width="110" />
      <el-table-column prop="voucher_group" label="字" min-width="70" />
      <el-table-column prop="fiscal_period" label="期间" min-width="80" />
      <el-table-column prop="total_debit" label="借方合计" min-width="110" />
      <el-table-column prop="total_credit" label="贷方合计" min-width="110" />
      <el-table-column prop="source_database" label="来源账套" min-width="150" />
      <el-table-column label="数据标记" min-width="100">
        <template #default="{ row }"><el-tag :type="row.historical_marker ? 'info' : 'danger'" effect="plain">{{ row.historical_marker ? "历史数据" : "标记异常" }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }"><el-button text type="primary" @click="viewVoucher(row)">查看分录</el-button></template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="drawerOpen" title="历史凭证分录（只读）" size="min(760px, 92vw)">
      <el-alert title="分录来自已发布 fin_history 视图，不提供编辑、删除、重过账或写回金蝶操作。" type="info" :closable="false" show-icon />
      <el-descriptions v-if="selectedVoucher" :column="2" border class="voucher-summary">
        <el-descriptions-item label="凭证号">{{ selectedVoucher.voucher_no }}</el-descriptions-item>
        <el-descriptions-item label="日期">{{ selectedVoucher.voucher_date }}</el-descriptions-item>
        <el-descriptions-item label="来源账套">{{ selectedVoucher.source_database }}</el-descriptions-item>
        <el-descriptions-item label="标记">{{ selectedVoucher.historical_marker ? "历史数据" : "标记异常" }}</el-descriptions-item>
      </el-descriptions>
      <el-table v-loading="lineLoading" :data="lines" max-height="480" class="line-table">
        <el-table-column prop="line_no" label="行号" width="72" />
        <el-table-column prop="account_code" label="科目" min-width="120" />
        <el-table-column prop="summary" label="摘要" min-width="180" />
        <el-table-column prop="debit_amount" label="借方" min-width="110" />
        <el-table-column prop="credit_amount" label="贷方" min-width="110" />
        <el-table-column prop="currency_code" label="币种" width="80" />
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  financeV2Api,
  type FinanceV2HistoryVoucher,
  type FinanceV2HistoryVoucherLine,
} from "@/api/financeV2";

const loading = ref(false);
const lineLoading = ref(false);
const loadError = ref("");
const vouchers = ref<FinanceV2HistoryVoucher[]>([]);
const lines = ref<FinanceV2HistoryVoucherLine[]>([]);
const selectedVoucher = ref<FinanceV2HistoryVoucher>();
const drawerOpen = ref(false);

async function loadVouchers() {
  loading.value = true;
  loadError.value = "";
  try {
    const pageSize = 200;
    const published: FinanceV2HistoryVoucher[] = [];
    for (let offset = 0; offset < 10_000; offset += pageSize) {
      const response = await financeV2Api.listHistoryVouchers({ limit: pageSize, offset });
      const page = response.data || [];
      published.push(...page);
      if (page.length < pageSize) break;
    }
    vouchers.value = published;
  } catch (error) {
    vouchers.value = [];
    loadError.value = error instanceof Error ? error.message : "请求失败";
  } finally {
    loading.value = false;
  }
}

async function viewVoucher(voucher: FinanceV2HistoryVoucher) {
  selectedVoucher.value = voucher;
  lines.value = [];
  drawerOpen.value = true;
  lineLoading.value = true;
  try {
    const response = await financeV2Api.listHistoryVoucherLines(voucher.id, { limit: 500 });
    lines.value = response.data || [];
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "历史凭证分录读取失败");
  } finally {
    lineLoading.value = false;
  }
}

onMounted(loadVouchers);
</script>

<style scoped>
.history-archive { min-width: 0; }
.toolbar { display: flex; align-items: center; justify-content: space-between; margin: 14px 0 8px; font-weight: 600; }
.history-error, .voucher-summary, .line-table { margin-top: 12px; }
</style>
