<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">财务报表</p>
        <h2>销售月报表</h2>
        <p>{{ isReadonly ? "金蝶迁移账簿未导入门店销售月报；请通过原始凭证、明细账和余额快照核对。" : "按期间、门店展示销售汇总月报;按独立账簿隔离,数据持久化。" }}</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button :disabled="!bookId || !records.length" @click="exportReports">导出当前月报</el-button>
        <el-button type="primary" :disabled="!bookId || isReadonly" @click="openCreate">录入月报</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-alert v-if="isReadonly" type="warning" title="金蝶迁移账簿未导入门店销售月报，当前页面不以空表表示历史销售为零。" :closable="false" show-icon />

    <el-table v-if="!isReadonly" v-loading="loading" :data="records" empty-text="暂无销售月报" stripe show-summary :summary-method="getSummaries">
      <el-table-column prop="period" label="月份" width="120" />
      <el-table-column prop="store_code" label="门店编码" width="120" />
      <el-table-column prop="store_name" label="门店名称" min-width="180" show-overflow-tooltip />
      <el-table-column label="销售额" width="160" align="right">
        <template #default="scope">¥{{ money(scope.row.sales_amount) }}</template>
      </el-table-column>
      <el-table-column label="退货额" width="160" align="right">
        <template #default="scope">¥{{ money(scope.row.return_amount) }}</template>
      </el-table-column>
      <el-table-column label="净销售额" width="160" align="right">
        <template #default="scope">¥{{ money(scope.row.net_sales) }}</template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="170">
        <template #default="scope">
          <el-button size="small" link type="primary" :disabled="isReadonly" @click="openEdit(scope.row)">编辑</el-button>
          <el-popconfirm
            title="确定删除该记录吗?"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="removeRow(scope.row)"
          >
            <template #reference>
              <el-button size="small" link type="danger" :disabled="isReadonly" :loading="actingId === scope.row.id">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑月报' : '录入月报'" width="520px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="月份" prop="period">
          <el-date-picker v-model="form.period" type="month" value-format="YYYY-MM" :disabled="!!editingId" placeholder="请选择月份" style="width: 100%" />
        </el-form-item>
        <el-form-item label="门店编码" prop="store_code">
          <el-input v-model="form.store_code" :disabled="!!editingId" placeholder="如 285101" maxlength="32" />
        </el-form-item>
        <el-form-item label="门店名称" prop="store_name">
          <el-input v-model="form.store_name" placeholder="请输入门店名称" maxlength="50" />
        </el-form-item>
        <el-form-item label="销售额" prop="sales_amount">
          <el-input-number v-model="form.sales_amount" :min="0" :precision="2" :step="1000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="退货额" prop="return_amount">
          <el-input-number v-model="form.return_amount" :min="0" :precision="2" :step="100" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="请输入备注" maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import {
  salesMonthlyReportsApi,
  type MumarenSalesMonthlyReport,
} from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";

const { books, bookId, isReadonly, loadBooks } = useMumarenFinanceBook();
const records = ref<MumarenSalesMonthlyReport[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const actingId = ref<number>();
const editingId = ref<number>();
let loadRequestVersion = 0;

const dialogVisible = ref(false);
const formRef = ref<FormInstance>();

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const defaultForm = () => ({
  period: "",
  store_code: "",
  store_name: "",
  sales_amount: 0,
  return_amount: 0,
  remark: "",
});

const form = reactive(defaultForm());

const formRules: FormRules = {
  period: [{ required: true, message: "请选择月份", trigger: "change" }],
  store_code: [{ required: true, message: "请输入门店编码", trigger: "blur" }],
  store_name: [{ required: true, message: "请输入门店名称", trigger: "blur" }],
  sales_amount: [{ required: true, message: "请输入销售额", trigger: "blur" }],
  return_amount: [{ required: true, message: "请输入退货额", trigger: "blur" }],
};

const resetForm = () => {
  Object.assign(form, defaultForm());
  formRef.value?.clearValidate();
};

const load = async () => {
  const requestedBookId = bookId.value;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId || isReadonly.value) { records.value = []; loading.value = false; error.value = ""; return; }
  loading.value = true;
  error.value = "";
  try {
    const response = await salesMonthlyReportsApi.list({ book_id: requestedBookId });
    if (requestVersion !== loadRequestVersion || requestedBookId !== bookId.value || isReadonly.value) return;
    records.value = response.data.data;
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value && !isReadonly.value) error.value = "无法加载销售月报。";
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

const openCreate = () => {
  if (isReadonly.value) return;
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  resetForm();
  editingId.value = undefined;
  dialogVisible.value = true;
};

const openEdit = (row: MumarenSalesMonthlyReport) => {
  if (isReadonly.value) return;
  editingId.value = row.id;
  Object.assign(form, {
    period: row.period,
    store_code: row.store_code,
    store_name: row.store_name || "",
    sales_amount: Number(row.sales_amount || 0),
    return_amount: Number(row.return_amount || 0),
    remark: row.remark || "",
  });
  formRef.value?.clearValidate();
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
      if (editingId.value) {
        await salesMonthlyReportsApi.update(editingId.value, {
          book_id: bid,
          store_name: form.store_name.trim(),
          sales_amount: form.sales_amount,
          return_amount: form.return_amount,
          remark: form.remark.trim() || null,
        });
        ElMessage.success("月报已更新");
      } else {
        await salesMonthlyReportsApi.create({
          book_id: bid,
          period: form.period,
          store_code: form.store_code.trim(),
          store_name: form.store_name.trim(),
          sales_amount: form.sales_amount,
          return_amount: form.return_amount,
          remark: form.remark.trim(),
        });
        ElMessage.success("月报已录入");
      }
      dialogVisible.value = false;
      await load();
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || "保存失败");
    } finally {
      saving.value = false;
    }
  });
};

const removeRow = async (row: MumarenSalesMonthlyReport) => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await salesMonthlyReportsApi.delete(row.id, bookId.value);
    ElMessage.success("记录已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "删除失败");
  } finally {
    actingId.value = undefined;
  }
};

const exportReports = () => {
  const escape = (value: unknown) => {
    const text = String(value ?? "");
    const safe = /^[=+@-]/.test(text) ? `'${text}` : text;
    return `"${safe.replace(/"/g, '""')}"`;
  };
  const rows = [
    ["月份", "门店编码", "门店名称", "销售额", "退货额", "净销售额", "备注"],
    ...records.value.map((row) => [row.period, row.store_code, row.store_name, row.sales_amount, row.return_amount, row.net_sales, row.remark]),
  ];
  const csv = `\uFEFF${rows.map((row) => row.map(escape).join(",")).join("\r\n")}`;
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `销售月报-${bookId.value}.csv`;
  link.click();
  URL.revokeObjectURL(url);
};

const getSummaries = (param: { columns: any[]; data: MumarenSalesMonthlyReport[] }) => {
  const { columns, data } = param;
  const sums: string[] = [];
  columns.forEach((column, index) => {
    if (index === 0) {
      sums[index] = "合计";
      return;
    }
    const property = column.property as keyof MumarenSalesMonthlyReport;
    if (property === "sales_amount" || property === "return_amount" || property === "net_sales") {
      const total = data.reduce((sum, item) => sum + (item[property] as number || 0), 0);
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
