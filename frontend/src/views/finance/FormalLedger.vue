<template>
  <div class="formal-ledger">
    <header class="page-header">
      <div>
        <h1>正式账簿</h1>
        <p>可写财务凭证与月度报表</p>
      </div>
      <el-tag :type="statusType" effect="plain">{{ statusText }}</el-tag>
    </header>

    <section class="action-grid">
      <div class="panel">
        <h2>金蝶历史写入</h2>
        <div class="form-row">
          <el-input v-model="importAccountSet" placeholder="账套编码 AIS..." clearable />
          <el-button type="primary" :icon="Upload" :loading="loading.import" @click="importHistory">写入账簿</el-button>
        </div>
      </div>

      <div class="panel">
        <h2>期间</h2>
        <div class="form-row compact">
          <el-input-number v-model="bookId" :min="1" controls-position="right" />
          <el-input v-model="period" placeholder="2026-02" />
          <el-button :icon="Unlock" :loading="loading.period" @click="openPeriod">打开</el-button>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <h2>凭证</h2>
        <div class="button-row">
          <el-button :icon="DocumentAdd" type="primary" :loading="loading.voucher" @click="createVoucher">创建草稿</el-button>
          <el-button :icon="CircleCheck" :loading="loading.post" @click="postVoucher">过账</el-button>
          <el-button :icon="RefreshLeft" :loading="loading.reverse" @click="reverseVoucher">冲销</el-button>
        </div>
      </div>
      <div class="voucher-grid">
        <el-input-number v-model="voucher.book_id" :min="1" controls-position="right" />
        <el-input v-model="voucher.period" placeholder="期间" />
        <el-input v-model="voucher.voucher_no" placeholder="凭证号" />
        <el-date-picker v-model="voucher.voucher_date" type="date" value-format="YYYY-MM-DD" placeholder="凭证日期" />
        <el-input-number v-model="voucherId" :min="1" controls-position="right" />
        <el-input v-model="voucher.reason" placeholder="原因" />
      </div>
      <el-table :data="voucher.entries" stripe>
        <el-table-column label="科目ID" width="120">
          <template #default="scope"><el-input-number v-model="scope.row.account_id" :min="1" controls-position="right" /></template>
        </el-table-column>
        <el-table-column label="摘要" min-width="180">
          <template #default="scope"><el-input v-model="scope.row.summary" /></template>
        </el-table-column>
        <el-table-column label="借方" width="150" align="right">
          <template #default="scope"><el-input-number v-model="scope.row.debit_amount" :min="0" :precision="2" controls-position="right" /></template>
        </el-table-column>
        <el-table-column label="贷方" width="150" align="right">
          <template #default="scope"><el-input-number v-model="scope.row.credit_amount" :min="0" :precision="2" controls-position="right" /></template>
        </el-table-column>
      </el-table>
    </section>

    <section class="panel">
      <div class="section-head">
        <h2>月度报表</h2>
        <el-button :icon="DataAnalysis" type="primary" :loading="loading.statement" @click="generateStatement">生成</el-button>
      </div>
      <div class="form-row compact">
        <el-input-number v-model="statement.book_id" :min="1" controls-position="right" />
        <el-input v-model="statement.period" placeholder="2026-01" />
        <el-select v-model="statement.statement_type">
          <el-option label="资产负债表" value="balance_sheet" />
          <el-option label="利润表" value="income_statement" />
          <el-option label="现金流量表" value="cashflow" />
        </el-select>
      </div>
      <el-alert v-if="statementResult.status !== 'ready'" :title="statementAlert" :closable="false" show-icon :type="statementResult.status === 'pending_mapping' ? 'warning' : 'info'" />
      <el-table :data="statementResult.items" stripe>
        <el-table-column prop="line_code" label="行项目" width="140" />
        <el-table-column prop="line_name" label="名称" min-width="220" />
        <el-table-column label="本期金额" width="180" align="right">
          <template #default="scope">{{ money(scope.row.current_amount) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="130" />
      </el-table>
    </section>

    <section class="panel">
      <h2>最近结果</h2>
      <pre>{{ JSON.stringify(lastResult, null, 2) }}</pre>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { CircleCheck, DataAnalysis, DocumentAdd, RefreshLeft, Unlock, Upload } from "@element-plus/icons-vue";
import { financeCenterApi, type StatementGeneratePayload, type StatementGenerateResult, type VoucherCreatePayload } from "@/api/financeCenter";

const loading = reactive({ import: false, period: false, voucher: false, post: false, reverse: false, statement: false });
const importAccountSet = ref("");
const bookId = ref(1);
const period = ref("2026-02");
const voucherId = ref(1);
const lastResult = ref<Record<string, unknown>>({});
const voucher = reactive<VoucherCreatePayload>({
  book_id: 1,
  period: "2026-02",
  voucher_no: "",
  voucher_date: new Date().toISOString().slice(0, 10),
  reason: "",
  entries: [
    { account_id: 1, summary: "", debit_amount: 0, credit_amount: 0 },
    { account_id: 2, summary: "", debit_amount: 0, credit_amount: 0 },
  ],
});
const statement = reactive<StatementGeneratePayload>({ book_id: 1, period: "2026-01", statement_type: "income_statement" });
const statementResult = ref<StatementGenerateResult>({ status: "pending_data", items: [], issues: [] });
const statusType = computed(() => statementResult.value.status === "ready" ? "success" : statementResult.value.status === "pending_mapping" ? "warning" : "info");
const statusText = computed(() => statementResult.value.status === "ready" ? "报表可用" : statementResult.value.status === "pending_mapping" ? "映射待确认" : "待生成");
const statementAlert = computed(() => statementResult.value.status === "pending_mapping" ? "存在未确认科目映射，不能展示为完整报表。" : "当前期间暂无可生成报表数据。");
const unwrap = <T,>(response: { data: { data: T } }) => response.data.data;
const money = (value: number | null | undefined) => value == null ? "-" : new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);

const run = async (key: keyof typeof loading, action: () => Promise<Record<string, unknown>>, message: string) => {
  loading[key] = true;
  try {
    lastResult.value = await action();
    ElMessage.success(message);
  } finally {
    loading[key] = false;
  }
};

const importHistory = () => run("import", async () => unwrap(await financeCenterApi.importKingdeeHistory(importAccountSet.value)), "写入任务完成");
const openPeriod = () => run("period", async () => unwrap(await financeCenterApi.openPeriod({ book_id: bookId.value, period: period.value })), "期间已打开");
const createVoucher = () => run("voucher", async () => unwrap(await financeCenterApi.createVoucher(voucher)), "凭证草稿已创建");
const postVoucher = () => run("post", async () => unwrap(await financeCenterApi.postVoucher(voucherId.value, voucher.reason || "reviewed")), "凭证已过账");
const reverseVoucher = () => run("reverse", async () => unwrap(await financeCenterApi.reverseVoucher(voucherId.value, { voucher_no: `REV-${voucherId.value}`, reason: voucher.reason || "approved reversal" })), "冲销凭证已生成");
const generateStatement = async () => run("statement", async () => {
  const result = unwrap(await financeCenterApi.generateStatement(statement));
  statementResult.value = result;
  return result as unknown as Record<string, unknown>;
}, "报表生成完成");
</script>

<style scoped>
.formal-ledger { min-width: 0; color: #1f2937; }
.page-header, .section-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.page-header h1, .panel h2 { margin: 0; letter-spacing: 0; }
.page-header h1 { font-size: 24px; line-height: 1.3; }
.page-header p { margin: 4px 0 0; color: #6b7280; font-size: 13px; }
.action-grid { display: grid; grid-template-columns: repeat(2, minmax(260px, 1fr)); gap: 14px; margin-bottom: 14px; }
.panel { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin-bottom: 14px; }
.panel h2 { font-size: 16px; }
.form-row { display: grid; grid-template-columns: minmax(180px, 1fr) auto; gap: 10px; align-items: center; margin-top: 12px; }
.form-row.compact { grid-template-columns: 120px 140px minmax(150px, 1fr); }
.button-row { display: flex; gap: 8px; flex-wrap: wrap; }
.voucher-grid { display: grid; grid-template-columns: 120px 120px minmax(140px, 1fr) 160px 120px minmax(180px, 1fr); gap: 10px; margin-bottom: 12px; }
pre { max-height: 220px; overflow: auto; margin: 0; padding: 12px; background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 6px; font-size: 12px; }
@media (max-width: 900px) {
  .action-grid, .voucher-grid, .form-row, .form-row.compact { grid-template-columns: 1fr; }
  .section-head { align-items: flex-start; flex-direction: column; }
}
</style>
