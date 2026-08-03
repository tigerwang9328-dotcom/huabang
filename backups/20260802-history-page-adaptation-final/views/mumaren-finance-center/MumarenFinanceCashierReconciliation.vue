<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">出纳管理</p>
        <h2>银行余额调节表</h2>
        <p>{{ isReadonly ? "金蝶迁移账簿未导入银行流水与余额调节记录；请通过原始凭证、明细账和余额快照核对。" : "银行流水与账面余额的对账差异核销;按独立账簿隔离,数据持久化。" }}</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button v-if="!isReadonly" type="primary" :disabled="!bookId" @click="openDialog">新增对账记录</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <MumarenFinanceHistoricalSourceNotice :readonly="isReadonly" module-key="cashier-reconciliation" />

    <el-table v-if="!isReadonly" v-loading="loading" :data="records" empty-text="暂无对账记录" stripe show-summary :summary-method="summary">
      <el-table-column prop="account_name" label="账户" min-width="180" />
      <el-table-column prop="reconcile_date" label="对账日期" width="130" />
      <el-table-column label="账面余额" width="150" align="right">
        <template #default="{ row }">{{ money(row.book_balance) }}</template>
      </el-table-column>
      <el-table-column label="银行余额" width="150" align="right">
        <template #default="{ row }">{{ money(row.bank_balance) }}</template>
      </el-table-column>
      <el-table-column label="差异" width="150" align="right">
        <template #default="{ row }">
          <span :class="{ 'diff-warn': Math.abs(row.difference) > 0.001 }">{{ money(row.difference) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.status === 'pending' ? 'warning' : 'success'" size="small">
            {{ row.status === "pending" ? "待调节" : "已调节" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ row.remark || "—" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'pending'"
            link
            type="primary"
            size="small"
            :disabled="isReadonly"
            :loading="actingId === row.id"
            @click="reconcile(row)"
          >调节</el-button>
          <el-popconfirm title="确定删除该对账记录?" @confirm="remove(row)">
            <template #reference>
              <el-button link type="danger" size="small" :disabled="isReadonly" :loading="actingId === row.id">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增对账记录" width="480px" :close-on-click-modal="false">
      <el-form :model="form" label-width="100px">
        <el-form-item label="账户名称">
          <el-input v-model="form.account_name" placeholder="如 招行基本户" />
        </el-form-item>
        <el-form-item label="对账日期">
          <el-date-picker v-model="form.reconcile_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="账面余额">
          <el-input-number v-model="form.book_balance" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="银行余额">
          <el-input-number v-model="form.bank_balance" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import MumarenFinanceHistoricalSourceNotice from "./MumarenFinanceHistoricalSourceNotice.vue";
import {
  bankReconciliationsApi,
  type MumarenBankReconciliation,
} from "@/api/mumarenFinanceCenter";

const { books, bookId, isReadonly, loadBooks } = useMumarenFinanceBook();
const records = ref<MumarenBankReconciliation[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const actingId = ref<number>();
let loadRequestVersion = 0;
const dialogVisible = ref(false);

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const form = reactive({
  account_name: "",
  reconcile_date: new Date().toISOString().slice(0, 10),
  book_balance: 0,
  bank_balance: 0,
  remark: "",
});

const load = async () => {
  const requestedBookId = bookId.value;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId || isReadonly.value) { records.value = []; loading.value = false; error.value = ""; return; }
  loading.value = true;
  error.value = "";
  try {
    const response = await bankReconciliationsApi.list({ book_id: requestedBookId });
    if (requestVersion !== loadRequestVersion || requestedBookId !== bookId.value || isReadonly.value) return;
    records.value = response.data.data;
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value && !isReadonly.value) error.value = "无法加载银行余额调节记录。";
  } finally {
    if (requestVersion === loadRequestVersion) loading.value = false;
  }
};

const onBookChange = () => {
  loadRequestVersion += 1;
  records.value = [];
  loading.value = false;
  error.value = "";
  void load();
};

onMounted(async () => {
  try {
    await loadBooks();
    if (bookId.value) await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

const openDialog = () => {
  if (isReadonly.value) return;
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  form.account_name = "";
  form.reconcile_date = new Date().toISOString().slice(0, 10);
  form.book_balance = 0;
  form.bank_balance = 0;
  form.remark = "";
  dialogVisible.value = true;
};

const save = async () => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  if (!form.account_name) {
    ElMessage.warning("请填写账户名称");
    return;
  }
  saving.value = true;
  try {
    await bankReconciliationsApi.create({
      book_id: bookId.value,
      account_name: form.account_name,
      reconcile_date: form.reconcile_date,
      book_balance: Number(form.book_balance || 0),
      bank_balance: Number(form.bank_balance || 0),
      remark: form.remark,
    });
    ElMessage.success("对账记录已新增");
    dialogVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
};

const reconcile = async (row: MumarenBankReconciliation) => {
  if (isReadonly.value || !bookId.value || row.status !== "pending") return;
  actingId.value = row.id;
  try {
    await bankReconciliationsApi.update(row.id, { status: "reconciled" }, bookId.value);
    ElMessage.success("已调节");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "调节失败");
  } finally {
    actingId.value = undefined;
  }
};

const remove = async (row: MumarenBankReconciliation) => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await bankReconciliationsApi.delete(row.id, bookId.value);
    ElMessage.success("对账记录已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "删除失败");
  } finally {
    actingId.value = undefined;
  }
};

const summary = ({ columns, data }: { columns: any[]; data: MumarenBankReconciliation[] }) => {
  const sums: (string | number)[] = [];
  columns.forEach((_, i) => {
    sums[i] = i === 0 ? "合计" : "";
  });
  const idxBook = columns.findIndex((c) => c.label === "账面余额");
  const idxBank = columns.findIndex((c) => c.label === "银行余额");
  const idxDiff = columns.findIndex((c) => c.label === "差异");
  if (idxBook >= 0) sums[idxBook] = money(data.reduce((s, r) => s + Number(r.book_balance || 0), 0));
  if (idxBank >= 0) sums[idxBank] = money(data.reduce((s, r) => s + Number(r.bank_balance || 0), 0));
  if (idxDiff >= 0) sums[idxDiff] = money(data.reduce((s, r) => s + Number(r.difference || 0), 0));
  return sums;
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
.diff-warn { color: #d9504a; font-weight: 600; }
@media (max-width: 640px) { .filters { flex-direction: column; } .heading { flex-direction: column; } }
</style>
