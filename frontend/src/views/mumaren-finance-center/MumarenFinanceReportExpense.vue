<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">财务报表</p>
        <h2>费用明细表</h2>
        <p>按期间、科目展示费用发生明细;按独立账簿隔离,数据持久化。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!bookId" @click="openCreate">登记费用</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-table v-loading="loading" :data="records" empty-text="暂无费用明细" stripe show-summary :summary-method="getSummaries">
      <el-table-column prop="period" label="期间" width="120" />
      <el-table-column prop="account_code" label="科目编码" width="140" />
      <el-table-column prop="account_name" label="科目名称" min-width="180" show-overflow-tooltip />
      <el-table-column label="金额" width="160" align="right">
        <template #default="scope">¥{{ money(scope.row.amount) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="scope">
          <el-tag :type="statusTagType(scope.row.status)" size="small">{{ statusLabel(scope.row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="220">
        <template #default="scope">
          <el-button :disabled="isReadonly" v-if="scope.row.status === 'draft'" size="small" link type="primary" :loading="actingId === scope.row.id" @click="reviewRow(scope.row)">审核</el-button>
          <el-button :disabled="isReadonly" v-if="scope.row.status === 'reviewed'" size="small" link type="success" :loading="actingId === scope.row.id" @click="postRow(scope.row)">过账</el-button>
          <el-popconfirm
            title="确定删除该记录吗?"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="removeRow(scope.row)"
          >
            <template #reference>
              <el-button :disabled="isReadonly" size="small" link type="danger" :loading="actingId === scope.row.id">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="登记费用" width="520px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="期间" prop="period">
          <el-date-picker v-model="form.period" type="month" value-format="YYYY-MM" placeholder="请选择期间" style="width: 100%" />
        </el-form-item>
        <el-form-item label="科目编码" prop="account_code">
          <el-input v-model="form.account_code" placeholder="请输入科目编码" maxlength="30" />
        </el-form-item>
        <el-form-item label="科目名称" prop="account_name">
          <el-input v-model="form.account_name" placeholder="请输入科目名称" maxlength="50" />
        </el-form-item>
        <el-form-item label="金额" prop="amount">
          <el-input-number v-model="form.amount" :min="0" :precision="2" :step="100" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="请输入备注" maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button :disabled="isReadonly" type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { storeToRefs } from "pinia";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import {
  expenseEntriesApi,
  mumarenFinanceCenterApi,
  type MumarenExpenseEntry,
  type MumarenFinanceBook,
} from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBookStore } from "@/stores/mumarenFinanceBook";

const bookStore = useMumarenFinanceBookStore();
const { books, bookId, isReadonly } = storeToRefs(bookStore);
const records = ref<MumarenExpenseEntry[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const actingId = ref<number>();

const dialogVisible = ref(false);
const formRef = ref<FormInstance>();

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const statusLabel = (status: string) => {
  if (status === "draft") return "草稿";
  if (status === "reviewed") return "已审核";
  if (status === "posted") return "已过账";
  return status;
};
const statusTagType = (status: string): "" | "warning" | "success" => {
  if (status === "draft") return "";
  if (status === "reviewed") return "warning";
  return "success";
};

const defaultForm = () => ({
  period: "",
  account_code: "",
  account_name: "",
  amount: 0,
  remark: "",
});

const form = reactive(defaultForm());

const formRules: FormRules = {
  period: [{ required: true, message: "请选择期间", trigger: "change" }],
  account_code: [{ required: true, message: "请输入科目编码", trigger: "blur" }],
  account_name: [{ required: true, message: "请输入科目名称", trigger: "blur" }],
  amount: [{ required: true, message: "请输入金额", trigger: "blur" }],
};

const resetForm = () => {
  Object.assign(form, defaultForm());
  formRef.value?.clearValidate();
};

const load = async () => {
  if (!bookId.value) return;
  loading.value = true;
  error.value = "";
  try {
    records.value = (await expenseEntriesApi.list({ book_id: bookId.value })).data.data;
  } catch {
    error.value = "无法加载费用明细。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = () => {
  records.value = [];
  load();
};

onMounted(async () => {
  try {
    await bookStore.loadBooks();
    if (bookId.value) await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

const openCreate = () => {
  if (isReadonly.value) return;
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  resetForm();
  dialogVisible.value = true;
};

const submit = async () => {
  if (isReadonly.value) return;
  if (!formRef.value || !bookId.value) return;
  const bid = bookId.value;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    saving.value = true;
    try {
      await expenseEntriesApi.create({
        book_id: bid,
        period: form.period,
        account_code: form.account_code.trim(),
        account_name: form.account_name.trim(),
        amount: form.amount,
        remark: form.remark.trim(),
      });
      ElMessage.success("费用已登记");
      dialogVisible.value = false;
      await load();
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || "保存失败");
    } finally {
      saving.value = false;
    }
  });
};

const reviewRow = async (row: MumarenExpenseEntry) => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await expenseEntriesApi.review(row.id, bookId.value);
    ElMessage.success("已审核");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "审核失败");
  } finally {
    actingId.value = undefined;
  }
};

const postRow = async (row: MumarenExpenseEntry) => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await expenseEntriesApi.post(row.id, bookId.value);
    ElMessage.success("已过账");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "过账失败");
  } finally {
    actingId.value = undefined;
  }
};

const removeRow = async (row: MumarenExpenseEntry) => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await expenseEntriesApi.delete(row.id, bookId.value);
    ElMessage.success("记录已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "删除失败");
  } finally {
    actingId.value = undefined;
  }
};

const getSummaries = (param: { columns: any[]; data: MumarenExpenseEntry[] }) => {
  const { columns, data } = param;
  const sums: string[] = [];
  columns.forEach((column, index) => {
    if (index === 0) {
      sums[index] = "合计";
      return;
    }
    if (column.property === "amount") {
      const total = data.reduce((sum, item) => sum + (item.amount || 0), 0);
      sums[index] = "¥" + money(total);
    } else {
      sums[index] = "";
    }
  });
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
@media (max-width: 640px) { .filters { flex-direction: column; } .heading { flex-direction: column; } }
</style>
