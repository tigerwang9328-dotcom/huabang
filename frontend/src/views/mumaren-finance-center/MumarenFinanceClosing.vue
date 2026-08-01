<template>
  <section class="panel closing-workbench">
    <div class="heading">
      <div>
        <p class="panel-kicker">期末结账</p>
        <h2>结账</h2>
        <p>按独立账簿和会计期间完成预检、结转与结账；所有写入均保留审计记录。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <el-card shadow="never" class="context-card">
      <div class="context-grid">
        <div>
          <span class="context-label">独立账簿</span>
          <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
            <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
          </el-select>
        </div>
        <div>
          <span class="context-label">目标期间</span>
          <el-date-picker v-model="targetPeriod" type="month" value-format="YYYY-MM" placeholder="选择期间" :disabled="!bookId" />
        </div>
        <div class="context-fact"><span>当前期间</span><strong>{{ targetPeriod || "—" }}</strong></div>
        <div class="context-fact"><span>期间状态</span><el-tag v-if="selectedPeriod" :type="statusTagType(selectedPeriod.status)">{{ statusLabel(selectedPeriod.status) }}</el-tag><strong v-else>未初始化</strong></div>
      </div>
    </el-card>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-card shadow="never" class="operation-card">
      <template #header><div class="card-title"><span>结账操作</span><el-tag v-if="precheck" :type="precheck.can_close ? 'success' : 'danger'">{{ precheck.message }}</el-tag></div></template>
      <div class="operation-row">
        <el-button :disabled="!canOperate" :loading="acting === 'initialize'" @click="initialize">初始化期间</el-button>
        <el-button type="primary" plain :disabled="!canOperate" :loading="acting === 'precheck'" @click="runPrecheck">预检</el-button>
        <el-button type="success" plain :disabled="!canOperate" :loading="acting === 'carry'" @click="carryForward">结转损益</el-button>
        <el-button type="primary" :disabled="!canClose" :loading="acting === 'close'" @click="closePeriod">执行结账</el-button>
        <el-button v-if="selectedPeriod?.status === 'closed'" type="warning" plain :disabled="!canOperate" :loading="acting === 'reopen'" @click="reopenPeriod">重新开启</el-button>
      </div>
      <p class="operation-hint">执行结账前必须完成预检；警告项会提示但不阻止，阻断项会禁止结账。</p>
    </el-card>

    <el-card v-if="precheck" shadow="never" class="check-card">
      <template #header><div class="card-title"><span>结账预检</span><div class="check-summary"><el-tag type="danger">阻断 {{ precheck.blocking_count }}</el-tag><el-tag type="warning">警告 {{ precheck.warning_count }}</el-tag></div></div></template>
      <div class="checks">
        <div v-for="item in precheck.checks" :key="item.key" class="check-item" :class="`check-${item.severity}`">
          <div class="check-icon">{{ item.passed ? "✓" : item.severity === "error" ? "!" : "i" }}</div>
          <div class="check-body"><strong>{{ item.title }}</strong><span>{{ item.message }}</span></div>
          <span v-if="item.count" class="check-count">{{ item.count }}</span>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="period-card">
      <template #header><div class="card-title"><span>期间列表</span><span class="muted">共 {{ periods.length }} 个期间</span></div></template>
      <el-table v-loading="loading" :data="periods" empty-text="暂无结账期间" stripe>
        <el-table-column prop="period_code" label="会计期间" width="120" />
        <el-table-column label="起止日期" min-width="190"><template #default="{ row }">{{ row.start_date }} 至 {{ row.end_date }}</template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="closed_by" label="结账人" width="100" />
        <el-table-column prop="closed_at" label="结账时间" width="190"><template #default="{ row }">{{ row.closed_at || "—" }}</template></el-table-column>
        <el-table-column prop="source_system" label="来源" width="140"><template #default="{ row }">{{ row.source_system || "当前账簿" }}</template></el-table-column>
        <el-table-column label="操作" width="180" fixed="right"><template #default="{ row }"><el-button v-if="row.status === 'open'" link type="primary" size="small" @click="selectRow(row)">预检</el-button><el-button v-if="row.status === 'closed'" link type="warning" size="small" @click="selectRow(row)">查看</el-button></template></el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { mumarenFinanceCenterApi, periodsApi, type MumarenFinanceBook, type MumarenPeriod, type MumarenPeriodPrecheck } from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const bookId = ref<number>();
const periods = ref<MumarenPeriod[]>([]);
const targetPeriod = ref("");
const precheck = ref<MumarenPeriodPrecheck>();
const loading = ref(false);
const error = ref("");
const acting = ref<"initialize" | "precheck" | "carry" | "close" | "reopen">();

const selectedPeriod = computed(() => periods.value.find((row) => row.period_code === targetPeriod.value));
const canOperate = computed(() => Boolean(bookId.value && targetPeriod.value));
const canClose = computed(() => canOperate.value && Boolean(precheck.value?.can_close && selectedPeriod.value?.status === "open"));
const statusLabel = (status: string) => status === "open" ? "未结账" : status === "closed" ? "已结账" : status;
const statusTagType = (status: string): "info" | "success" | "warning" => status === "closed" ? "success" : status === "open" ? "info" : "warning";

const load = async () => {
  if (!bookId.value) return;
  loading.value = true; error.value = ""; precheck.value = undefined;
  try {
    periods.value = (await periodsApi.list({ book_id: bookId.value })).data.data;
    if (!targetPeriod.value) targetPeriod.value = periods.value[0]?.period_code || new Date().toISOString().slice(0, 7);
  } catch (e: any) { error.value = e?.response?.data?.detail || "无法加载结账期间。"; }
  finally { loading.value = false; }
};
const onBookChange = () => { periods.value = []; targetPeriod.value = ""; precheck.value = undefined; load(); };
const selectRow = (row: MumarenPeriod) => { targetPeriod.value = row.period_code; precheck.value = undefined; };
const confirmAction = (message: string) => ElMessageBox.confirm(message, "请确认操作", { type: "warning", confirmButtonText: "确认", cancelButtonText: "取消" });

const initialize = async () => { if (!canOperate.value || !bookId.value) return; await confirmAction(`确认初始化 ${targetPeriod.value} 期间吗？`); acting.value = "initialize"; try { await periodsApi.initialize(bookId.value, targetPeriod.value); ElMessage.success("期间已初始化"); await load(); } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "初始化失败"); } finally { acting.value = undefined; } };
const runPrecheck = async () => { if (!canOperate.value || !bookId.value) return; acting.value = "precheck"; try { precheck.value = (await periodsApi.precheck(bookId.value, targetPeriod.value)).data.data; } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "预检失败"); } finally { acting.value = undefined; } };
const carryForward = async () => { if (!canOperate.value || !bookId.value) return; await confirmAction(`确认生成 ${targetPeriod.value} 损益结转草稿吗？`); acting.value = "carry"; try { const result = (await periodsApi.carryForward(bookId.value, targetPeriod.value)).data.data; ElMessage.success(result.voucher_no ? `已生成凭证草稿 ${result.voucher_no}` : "本期无需结转"); await runPrecheck(); } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "结转失败"); } finally { acting.value = undefined; } };
const closePeriod = async () => { if (!canClose.value || !bookId.value || !selectedPeriod.value) return; await confirmAction(`确认结账 ${targetPeriod.value} 吗？结账后该期间将禁止重复结账。`); acting.value = "close"; try { await periodsApi.close(selectedPeriod.value.id, bookId.value); ElMessage.success(`期间 ${targetPeriod.value} 已结账`); await load(); } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "结账失败"); } finally { acting.value = undefined; } };
const reopenPeriod = async () => { if (!canOperate.value || !bookId.value || !selectedPeriod.value) return; await confirmAction(`确认重新开启 ${targetPeriod.value} 吗？此操作仅管理员可执行。`); acting.value = "reopen"; try { await periodsApi.reopen(selectedPeriod.value.id, bookId.value); ElMessage.success(`期间 ${targetPeriod.value} 已重新开启`); await load(); } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "重新开启失败"); } finally { acting.value = undefined; } };

onMounted(async () => { try { books.value = (await mumarenFinanceCenterApi.listBooks()).data.data; bookId.value = books.value[0]?.id; await load(); } catch (e: any) { error.value = e?.response?.data?.detail || "无法加载独立账簿。"; } });
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading, .card-title { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.heading { align-items: flex-start; }.heading-actions, .operation-row, .check-summary { display: flex; gap: 8px; flex-wrap: wrap; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; } h2 { margin: 8px 0; } p { color: #5d6b7e; }
.context-grid { display: grid; grid-template-columns: minmax(220px, 1.4fr) minmax(160px, 1fr) repeat(2, minmax(120px, .7fr)); gap: 18px; align-items: end; }.context-grid > div { display: grid; gap: 7px; }.context-label, .context-fact span { color: #718096; font-size: 12px; }.context-fact strong { color: #172b4d; min-height: 32px; display: flex; align-items: center; }.operation-card, .check-card, .period-card, .context-card { border-color: #e4eaf2; }.operation-hint, .muted { margin: 12px 0 0; color: #8492a6; font-size: 13px; }.card-title .muted { margin: 0; }.checks { display: grid; gap: 10px; }.check-item { display: flex; gap: 12px; align-items: center; padding: 12px 14px; border-radius: 8px; background: #f7f9fc; border-left: 3px solid #67c23a; }.check-warning { border-left-color: #e6a23c; }.check-error { border-left-color: #f56c6c; }.check-icon { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; color: #fff; background: #67c23a; font-weight: 700; }.check-warning .check-icon { background: #e6a23c; }.check-error .check-icon { background: #f56c6c; }.check-body { display: grid; gap: 3px; flex: 1; }.check-body span { color: #718096; font-size: 13px; }.check-count { color: #64748b; font-weight: 700; }.operation-row { margin-bottom: 4px; }
@media (max-width: 900px) { .context-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 640px) { .panel { padding: 18px; }.context-grid { grid-template-columns: 1fr; }.heading, .card-title { align-items: flex-start; flex-direction: column; } }
</style>
