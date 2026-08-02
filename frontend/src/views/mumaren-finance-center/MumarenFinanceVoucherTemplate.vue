<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">凭证管理</p>
        <h2>凭证模板</h2>
        <p>{{ isReadonly ? "金蝶迁移账簿未导入可维护凭证模板；请查询原始凭证、明细账和余额快照。" : "模板保存科目和借贷分录；套用只预填录凭证草稿，仍须人工审核、人工过账。" }}</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!bookId || isReadonly" @click="openCreate">新增模板</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable>
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-alert v-if="isReadonly" type="warning" title="金蝶迁移账簿未导入可维护凭证模板，当前页面不以空表表示历史模板为零。" :closable="false" show-icon />

    <el-table v-if="!isReadonly" v-loading="loading" :data="templates" empty-text="暂无凭证模板" stripe>
      <el-table-column prop="template_name" label="模板名称" min-width="150" show-overflow-tooltip />
      <el-table-column prop="voucher_type" label="凭证字" width="88" />
      <el-table-column label="分录" width="90" align="right"><template #default="{ row }">{{ row.lines_json?.lines.length || 0 }} 行</template></el-table-column>
      <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" link type="primary" :disabled="isReadonly" @click="applyTemplate(row)">套用</el-button>
          <el-button size="small" link :disabled="isReadonly" @click="openEdit(row)">编辑</el-button>
          <el-popconfirm title="确定删除该模板吗?" confirm-button-text="删除" cancel-button-text="取消" @confirm="removeRow(row)">
            <template #reference><el-button size="small" link type="danger" :disabled="isReadonly" :loading="actingId === row.id">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑模板' : '新增模板'" width="880px" :close-on-click-modal="false">
      <el-form :model="form" label-width="88px">
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="模板名称" required><el-input v-model="form.template_name" maxlength="50" show-word-limit /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="凭证字"><el-select v-model="form.voucher_type" style="width:100%"><el-option label="记" value="记" /><el-option label="转" value="转" /><el-option label="收" value="收" /><el-option label="付" value="付" /></el-select></el-form-item></el-col>
        </el-row>
        <el-form-item label="摘要"><el-input v-model="form.summary" type="textarea" :rows="2" maxlength="200" show-word-limit /></el-form-item>
      </el-form>
      <div class="line-heading"><strong>模板分录</strong><div><el-button size="small" :disabled="!form.lines.length" @click="copyLastLine">复制上一行</el-button><el-button size="small" type="primary" plain @click="addLine">添加分录</el-button></div></div>
      <el-table :data="form.lines" border size="small">
        <el-table-column type="index" label="#" width="42" />
        <el-table-column label="会计科目" min-width="250"><template #default="{ row }"><el-select v-model="row.account_id" filterable placeholder="选择科目" style="width:100%"><el-option v-for="account in accounts" :key="account.id" :label="`${account.account_code} ${account.account_name}`" :value="account.id" /></el-select></template></el-table-column>
        <el-table-column label="摘要" min-width="150"><template #default="{ row }"><el-input v-model="row.summary" size="small" /></template></el-table-column>
        <el-table-column label="借方" width="126"><template #default="{ row }"><el-input-number v-model="row.debit_amount" :min="0" :precision="2" :controls="false" size="small" style="width:105px" @focus="row.credit_amount = 0" /></template></el-table-column>
        <el-table-column label="贷方" width="126"><template #default="{ row }"><el-input-number v-model="row.credit_amount" :min="0" :precision="2" :controls="false" size="small" style="width:105px" @focus="row.debit_amount = 0" /></template></el-table-column>
        <el-table-column label="操作" width="64"><template #default="{ $index }"><el-button link type="danger" size="small" :disabled="form.lines.length <= 2" @click="removeLine($index)">删除</el-button></template></el-table-column>
      </el-table>
      <div class="totals"><span>借方 <b>{{ money(totalDebit) }}</b></span><span>贷方 <b>{{ money(totalCredit) }}</b></span><el-tag size="small" :type="balanced ? 'success' : 'danger'">{{ balanced ? '已平衡' : '未平衡' }}</el-tag></div>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" :disabled="!canSave" @click="submit">保存</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { mumarenFinanceCenterApi, voucherTemplatesApi, type MumarenFinanceAccount, type MumarenVoucherTemplate, type VoucherTemplateLine } from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";

const router = useRouter();
const { books, bookId, isReadonly, loadBooks } = useMumarenFinanceBook();
const templates = ref<MumarenVoucherTemplate[]>([]);
const accounts = ref<MumarenFinanceAccount[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const actingId = ref<number>();
const dialogVisible = ref(false);
const editingId = ref<number>();
let accountRequestVersion = 0;
let templateRequestVersion = 0;

const newLine = (): VoucherTemplateLine => ({ account_id: 0, summary: "", debit_amount: 0, credit_amount: 0 });
const defaultForm = () => ({ template_name: "", voucher_type: "记", summary: "", lines: [newLine(), newLine()] });
const form = reactive(defaultForm());
const totalDebit = computed(() => form.lines.reduce((sum, line) => sum + Number(line.debit_amount || 0), 0));
const totalCredit = computed(() => form.lines.reduce((sum, line) => sum + Number(line.credit_amount || 0), 0));
const balanced = computed(() => totalDebit.value > 0 && Math.abs(totalDebit.value - totalCredit.value) < 0.005);
const canSave = computed(() => Boolean(form.template_name.trim()) && form.lines.length >= 2 && balanced.value && form.lines.every((line) => line.account_id > 0 && (Number(line.debit_amount) > 0) !== (Number(line.credit_amount) > 0)));
const money = (value: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const load = async () => {
  const requestedBookId = bookId.value;
  const version = ++templateRequestVersion;
  if (!requestedBookId) { templates.value = []; error.value = ""; loading.value = false; return; }
  if (isReadonly.value) { templates.value = []; error.value = ""; loading.value = false; return; }
  loading.value = true; error.value = "";
  try {
    const rows = (await voucherTemplatesApi.list({ book_id: requestedBookId })).data.data;
    if (version === templateRequestVersion && requestedBookId === bookId.value && !isReadonly.value) templates.value = rows;
  } catch {
    if (version === templateRequestVersion && requestedBookId === bookId.value && !isReadonly.value) error.value = "无法加载凭证模板。";
  } finally {
    if (version === templateRequestVersion) loading.value = false;
  }
};
const loadAccounts = async () => {
  const requestedBookId = bookId.value;
  const version = ++accountRequestVersion;
  if (!requestedBookId) { accounts.value = []; return; }
  if (isReadonly.value) { accounts.value = []; return; }
  try {
    const result = await mumarenFinanceCenterApi.listAccounts(requestedBookId);
    if (version === accountRequestVersion && requestedBookId === bookId.value && !isReadonly.value) accounts.value = result.data.data;
  } catch { if (version === accountRequestVersion) accounts.value = []; }
};
const reloadForBook = async () => { await Promise.all([load(), loadAccounts()]); };
onMounted(async () => { try { await loadBooks(); await reloadForBook(); } catch { error.value = "无法加载独立账簿。"; } });
watch(bookId, () => void reloadForBook());

const resetForm = () => Object.assign(form, defaultForm());
const openCreate = () => { if (isReadonly.value || !bookId.value) return; editingId.value = undefined; resetForm(); dialogVisible.value = true; };
const openEdit = (row: MumarenVoucherTemplate) => {
  if (isReadonly.value || !bookId.value) return;
  editingId.value = row.id;
  Object.assign(form, { template_name: row.template_name, voucher_type: row.voucher_type, summary: row.summary || "", lines: (row.lines_json?.lines || [newLine(), newLine()]).map((line) => ({ ...line })) });
  dialogVisible.value = true;
};
const addLine = () => form.lines.push(newLine());
const copyLastLine = () => {
  const line = form.lines[form.lines.length - 1];
  if (!line) return;
  form.lines.push({ ...line });
};
const removeLine = (index: number) => { if (form.lines.length > 2) form.lines.splice(index, 1); };
const submit = async () => {
  if (isReadonly.value || !bookId.value || !canSave.value) return;
  saving.value = true;
  const payload = { book_id: bookId.value, template_name: form.template_name.trim(), voucher_type: form.voucher_type, summary: form.summary.trim(), lines_json: { lines: form.lines.map((line) => ({ ...line, summary: line.summary?.trim() || null })) } };
  try {
    if (editingId.value) await voucherTemplatesApi.update(editingId.value, payload);
    else await voucherTemplatesApi.create(payload);
    ElMessage.success(editingId.value ? "模板已更新" : "模板已新增"); dialogVisible.value = false; await load();
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "保存失败"); }
  finally { saving.value = false; }
};
const applyTemplate = (row: MumarenVoucherTemplate) => {
  if (isReadonly.value || !bookId.value) return;
  if (!row.lines_json?.lines.length) { ElMessage.warning("该旧模板没有分录，无法套用；请先编辑补齐分录。"); return; }
  router.push({ path: "/app/finance-center/mumaren/vouchers/create", query: { template_id: String(row.id) } });
};
const removeRow = async (row: MumarenVoucherTemplate) => {
  if (isReadonly.value || !bookId.value) return;
  actingId.value = row.id;
  try { await voucherTemplatesApi.delete(row.id, bookId.value); ElMessage.success("模板已删除"); await load(); }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "删除失败"); }
  finally { actingId.value = undefined; }
};
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }.heading-actions,.line-heading,.totals { display:flex; gap:12px; align-items:center; }.filters > * { max-width: 280px; }.line-heading { justify-content: space-between; }.totals { justify-content: flex-end; margin-top: 12px; }.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; } h2 { margin: 8px 0; } p { color:#5d6b7e; }
@media (max-width: 640px) { .heading { flex-direction: column; } .panel { padding: 16px; } }
</style>
