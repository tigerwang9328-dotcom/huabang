<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">凭证流程</p>
        <h2>录凭证</h2>
        <p>独立当前账凭证草稿录入;借贷平衡后保存为草稿。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" @click="reloadAll">刷新</el-button>
        <router-link to="/app/finance-center/mumaren/vouchers/list">
          <el-button>查看凭证列表</el-button>
        </router-link>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable>
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <template v-else>
      <el-alert v-if="isReadonly" type="warning" :closable="false" show-icon title="金蝶迁移账簿只读，不能录入或修改凭证。" />
      <el-form :model="form" label-width="84px" :disabled="isReadonly">
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12" :md="6">
            <el-form-item label="凭证字">
              <el-select v-model="form.voucher_type" style="width:100%">
                <el-option label="记" value="记" />
                <el-option label="收" value="收" />
                <el-option label="付" value="付" />
                <el-option label="转" value="转" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="9">
            <el-form-item label="凭证号">
              <el-input v-model="form.voucher_no" readonly placeholder="选择账簿后自动生成" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="9">
            <el-form-item label="凭证日期">
              <el-date-picker v-model="form.voucher_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="总摘要">
          <el-input v-model="form.summary" maxlength="200" show-word-limit placeholder="例如:确认店铺销售收入" />
        </el-form-item>
      </el-form>

      <div class="dialog-toolbar">
        <div class="voucher-actions">
          <el-button type="primary" plain :disabled="isReadonly" @click="addLine">添加分录</el-button>
          <el-button :disabled="isReadonly || !form.lines.length" @click="copyLastLine">复制上一行</el-button>
          <el-button :disabled="isReadonly" @click="addReceiptPair">收款分录</el-button>
          <el-button :disabled="isReadonly" @click="addPaymentPair">付款分录</el-button>
          <el-button :disabled="isReadonly || !form.lines.length" @click="balanceLastLine">自动找平</el-button>
        </div>
        <div class="totals">
          <span>借方 <b>{{ money(totalDebit) }}</b></span>
          <span>贷方 <b>{{ money(totalCredit) }}</b></span>
          <span>差额 <b :class="{ danger: !balanced }">{{ money(balanceDiff) }}</b></span>
          <el-tag size="small" :type="balanced ? 'success' : 'danger'">{{ balanced ? '已平衡' : '未平衡' }}</el-tag>
        </div>
      </div>

      <el-table :data="form.lines" border size="small" row-key="key" :max-height="360" :class="{ 'is-readonly': isReadonly }">
        <el-table-column type="index" label="#" width="42" />
        <el-table-column label="摘要" min-width="160">
          <template #default="{ row }">
            <div class="summary-cell">
              <el-input
                :model-value="row.summary"
                :disabled="isReadonly"
                size="small"
                :placeholder="summaryPreview(row) || '行摘要'"
                @update:model-value="updateLineSummary(row, $event)"
              />
              <el-button class="summary-clear" link :disabled="isReadonly" aria-label="清空本行摘要" @click="clearLineSummary(row)">×</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="会计科目" min-width="240">
          <template #default="{ row }">
            <el-select v-model="row.account_id" :disabled="isReadonly" filterable clearable size="small" placeholder="选择科目" style="width:100%">
              <el-option v-for="a in accounts" :key="a.id" :label="`${a.account_code} ${a.account_name}`" :value="a.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="供应商" min-width="180">
          <template #default="{ row }">
            <el-select v-if="requiresSupplier(row.account_id)" v-model="row.supplier_id" :disabled="isReadonly" filterable clearable size="small" placeholder="必须选择供应商" style="width:100%">
              <el-option v-for="supplier in suppliers" :key="supplier.id" :label="`${supplier.code} ${supplier.name}`" :value="supplier.id" />
            </el-select>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="借方金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.debit_amount" :disabled="isReadonly" :min="0" :precision="2" :controls="false" size="small" style="width:108px" @focus="row.credit_amount = 0" />
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.credit_amount" :disabled="isReadonly" :min="0" :precision="2" :controls="false" size="small" style="width:108px" @focus="row.debit_amount = 0" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" :disabled="isReadonly || form.lines.length <= 1" @click="removeLine($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="form-actions">
        <el-button type="primary" :loading="saving" :disabled="isReadonly || !canSave" @click="save">保存草稿</el-button>
      </div>

      <el-alert v-if="created" type="success" :closable="false" show-icon title="凭证草稿已创建">
        <template #default>
          <div class="success-row">
            <span>凭证草稿已创建,可前往凭证列表进行审核与人工过账。</span>
            <router-link to="/app/finance-center/mumaren/vouchers/list">
              <el-button type="primary" size="small">查看凭证列表</el-button>
            </router-link>
          </div>
        </template>
      </el-alert>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { storeToRefs } from "pinia";
import { ElMessage } from "element-plus";
import { resolveVoucherLineSummaries } from "@/utils/mumarenVoucherLineSummary.mjs";
import {
  mumarenFinanceCenterApi,
  auxiliaryAccountingsApi,
  voucherTemplatesApi,
  type MumarenFinanceAccount,
  type MumarenFinanceBook,
  type MumarenAuxiliaryAccounting,
} from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBookStore } from "@/stores/mumarenFinanceBook";

const bookStore = useMumarenFinanceBookStore();
const route = useRoute();
const { books, bookId, isReadonly } = storeToRefs(bookStore);
const accounts = ref<MumarenFinanceAccount[]>([]);
const suppliers = ref<MumarenAuxiliaryAccounting[]>([]);
const accountRequestVersion = ref(0);
const error = ref("");
const saving = ref(false);
const created = ref(false);
const clearedSummaryKeys = ref(new Set<string>());
let templateApplyVersion = 0;
let voucherNumberRequestVersion = 0;

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const onBookChange = async () => {
  // 选择账簿后加载科目列表供录入使用
  created.value = false;
  const requestedBookId = bookId.value;
  const requestVersion = ++accountRequestVersion.value;
  if (requestedBookId) {
    try {
      const [result, supplierResult] = await Promise.all([
        mumarenFinanceCenterApi.listAccounts(requestedBookId),
        auxiliaryAccountingsApi.list({ book_id: requestedBookId, aux_type: "supplier", limit: 500 }),
      ]);
      if (requestVersion === accountRequestVersion.value && requestedBookId === bookId.value) {
        accounts.value = result.data.data;
        suppliers.value = supplierResult.data.data.filter((item) => item.is_active);
      }
    } catch {
      if (requestVersion === accountRequestVersion.value) accounts.value = [];
    }
  } else {
    accounts.value = [];
    suppliers.value = [];
  }
};

const reloadAll = async () => {
  error.value = "";
  await bookStore.loadBooks();
  await onBookChange();
  await applyTemplateFromRoute();
};

onMounted(async () => {
  try {
    await reloadAll();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

watch(bookId, () => void onBookChange());

// ── 录入表单 ──
let lineSeed = 1;
const newLine = () => ({ key: `line-${lineSeed++}`, account_id: undefined as number | undefined, supplier_id: undefined as number | undefined, summary: "", debit_amount: 0, credit_amount: 0 });
const form = reactive({
  voucher_type: "记",
  voucher_no: "",
  voucher_date: new Date().toISOString().slice(0, 10),
  summary: "",
  lines: [newLine(), newLine()],
});

const resolvedLineSummaries = computed(() =>
  resolveVoucherLineSummaries(form.lines, clearedSummaryKeys.value),
);
const summaryPreview = (line: { key: string }) => resolvedLineSummaries.value.previewByKey[line.key] || "";
const updateLineSummary = (line: { key: string; summary: string }, value: string) => {
  line.summary = value;
  const next = new Set(clearedSummaryKeys.value);
  next.delete(line.key);
  clearedSummaryKeys.value = next;
};
const clearLineSummary = (line: { key: string; summary: string }) => {
  line.summary = "";
  const next = new Set(clearedSummaryKeys.value);
  next.add(line.key);
  clearedSummaryKeys.value = next;
};

const refreshVoucherNo = async () => {
  const requestedBookId = bookId.value;
  const requestedDate = form.voucher_date;
  const requestedType = form.voucher_type;
  const version = ++voucherNumberRequestVersion;
  if (!requestedBookId || !requestedDate || !requestedType || isReadonly.value) {
    form.voucher_no = "";
    return;
  }
  try {
    const result = await mumarenFinanceCenterApi.getNextVoucherNumber({
      book_id: requestedBookId,
      voucher_date: requestedDate,
      voucher_type: requestedType,
    });
    if (version === voucherNumberRequestVersion && requestedBookId === bookId.value && requestedDate === form.voucher_date && requestedType === form.voucher_type) {
      form.voucher_no = result.data.data.voucher_no;
    }
  } catch {
    if (version === voucherNumberRequestVersion) form.voucher_no = "";
  }
};

const applyTemplateFromRoute = async () => {
  const templateId = Number(route.query.template_id);
  const requestedBookId = bookId.value;
  const requestedTemplateId = String(route.query.template_id || "");
  const version = ++templateApplyVersion;
  if (!templateId || !requestedBookId || isReadonly.value) return;
  try {
    const template = (await voucherTemplatesApi.list({ book_id: requestedBookId, limit: 500 })).data.data
      .find((item) => item.id === templateId);
    if (version !== templateApplyVersion || requestedBookId !== bookId.value || requestedTemplateId !== String(route.query.template_id || "")) return;
    if (!template?.lines_json?.lines.length) {
      resetTemplateDraft();
      error.value = "所选模板不存在、与当前账簿不一致，或尚未配置分录。";
      return;
    }
    form.voucher_type = template.voucher_type;
    form.summary = template.summary || "";
    clearedSummaryKeys.value = new Set();
    form.lines = template.lines_json.lines.map((line) => ({
      key: `line-${lineSeed++}`,
      account_id: line.account_id,
      supplier_id: undefined as number | undefined,
      summary: line.summary || "",
      debit_amount: Number(line.debit_amount),
      credit_amount: Number(line.credit_amount),
    }));
    ElMessage.success(`已套用模板“${template.template_name}”，凭证号已自动生成。`);
  } catch {
    if (version === templateApplyVersion && requestedBookId === bookId.value && requestedTemplateId === String(route.query.template_id || "")) {
      resetTemplateDraft();
      error.value = "无法读取所选凭证模板。";
    }
  }
};

const resetTemplateDraft = () => {
  form.voucher_type = "记";
  form.summary = "";
  form.lines = [newLine(), newLine()];
  clearedSummaryKeys.value = new Set();
};

watch(() => route.query.template_id, () => { resetTemplateDraft(); void applyTemplateFromRoute(); });
watch(bookId, () => { if (route.query.template_id) resetTemplateDraft(); void applyTemplateFromRoute(); });
watch([bookId, () => form.voucher_date, () => form.voucher_type], () => void refreshVoucherNo(), { immediate: true });

const validLines = computed(() =>
  form.lines.filter((l) => l.account_id && (Number(l.debit_amount) > 0 || Number(l.credit_amount) > 0)),
);
const requiresSupplier = (accountId: number | undefined) =>
  !!accounts.value.find((account) => account.id === accountId)?.required_auxiliary_types?.includes("supplier");
const totalDebit = computed(() => validLines.value.reduce((s, l) => s + Number(l.debit_amount || 0), 0));
const totalCredit = computed(() => validLines.value.reduce((s, l) => s + Number(l.credit_amount || 0), 0));
const balanceDiff = computed(() => totalDebit.value - totalCredit.value);
const balanced = computed(() => Math.abs(balanceDiff.value) < 0.005 && totalDebit.value > 0);
const canSave = computed(() => balanced.value && validLines.value.length >= 2 && !!form.voucher_no && !!form.voucher_date
  && validLines.value.every((line) => !requiresSupplier(line.account_id) || !!line.supplier_id));

const addLine = () => {
  if (isReadonly.value) return;
  form.lines.push(newLine());
};
const removeLine = (index: number) => {
  if (isReadonly.value) return;
  if (form.lines.length > 1) {
    const [removed] = form.lines.splice(index, 1);
    const next = new Set(clearedSummaryKeys.value);
    next.delete(removed.key);
    clearedSummaryKeys.value = next;
  }
};

const copyLastLine = () => {
  if (isReadonly.value || !form.lines.length) return;
  const line = form.lines[form.lines.length - 1];
  form.lines.push({
    key: `line-${lineSeed++}`,
    account_id: line.account_id,
    supplier_id: line.supplier_id,
    summary: line.summary,
    debit_amount: Number(line.debit_amount || 0),
    credit_amount: Number(line.credit_amount || 0),
  });
};

const addVoucherPair = (voucherType: "收" | "付", summary: string) => {
  if (isReadonly.value) return;
  form.voucher_type = voucherType;
  if (!form.summary) form.summary = summary;
  form.lines.push(
    { ...newLine(), summary },
    { ...newLine(), summary },
  );
};

const addReceiptPair = () => addVoucherPair("收", "收款分录");
const addPaymentPair = () => addVoucherPair("付", "付款分录");

const balanceLastLine = () => {
  if (isReadonly.value || !form.lines.length) return;
  const line = form.lines[form.lines.length - 1];
  const debitBeforeLast = form.lines.slice(0, -1).reduce((sum, item) => sum + Number(item.debit_amount || 0), 0);
  const creditBeforeLast = form.lines.slice(0, -1).reduce((sum, item) => sum + Number(item.credit_amount || 0), 0);
  const difference = debitBeforeLast - creditBeforeLast;
  if (Math.abs(difference) < 0.005) {
    ElMessage.info("前面的分录已经平衡，无需找平。");
    return;
  }
  line.debit_amount = difference < 0 ? Math.abs(difference) : 0;
  line.credit_amount = difference > 0 ? difference : 0;
  if (!line.summary) line.summary = "自动找平";
};

const save = async () => {
  if (isReadonly.value || !bookId.value || !canSave.value) return;
  // 同一行不能同时填借贷
  if (validLines.value.find((l) => Number(l.debit_amount) > 0 && Number(l.credit_amount) > 0)) {
    ElMessage.error("同一分录行不能同时填写借方和贷方金额");
    return;
  }
  saving.value = true;
  try {
    await mumarenFinanceCenterApi.createVoucher({
      book_id: bookId.value,
      voucher_no: form.voucher_no,
      voucher_date: form.voucher_date,
      summary: form.summary || null,
      voucher_type: form.voucher_type,
      lines: validLines.value.map((l) => ({
        account_id: l.account_id as number,
        summary: resolvedLineSummaries.value.savedByKey[l.key] || null,
        summary_explicitly_cleared: clearedSummaryKeys.value.has(l.key),
        debit_amount: Number(l.debit_amount || 0),
        credit_amount: Number(l.credit_amount || 0),
        auxiliaries: l.supplier_id ? [{ aux_type: "supplier" as const, auxiliary_id: l.supplier_id }] : [],
      })),
    });
    ElMessage.success("凭证草稿已创建");
    created.value = true;
    // 重置表单
    form.voucher_date = new Date().toISOString().slice(0, 10);
    form.summary = "";
    form.lines = [newLine(), newLine()];
    clearedSummaryKeys.value = new Set();
    await refreshVoucherNo();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
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
.dialog-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 12px 0; flex-wrap: wrap; }
.voucher-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.totals { margin-left: auto; display: flex; align-items: center; gap: 14px; font-size: 13px; color: #4b5563; }
.totals b { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #111827; }
.totals .danger { color: #dc2626; }
.summary-cell { position: relative; }
.summary-cell :deep(.el-input__wrapper) { padding-right: 28px; }
.summary-clear { position: absolute; top: 50%; right: 6px; z-index: 1; min-width: 18px; height: 18px; padding: 0; color: #9ca3af; font-size: 17px; line-height: 1; transform: translateY(-50%); }
.summary-clear:hover { color: #6b7280; }
.muted { color: #9ca3af; }
.form-actions { display: flex; justify-content: flex-end; }
.success-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } .dialog-toolbar { align-items: flex-start; } .totals { margin-left: 0; flex-wrap: wrap; } }
</style>
