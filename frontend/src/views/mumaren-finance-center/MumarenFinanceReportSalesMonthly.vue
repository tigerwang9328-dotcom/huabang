<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">财务报表</p>
        <h2>销售月报表</h2>
        <p>按期间、门店展示销售汇总月报;按独立账簿隔离,数据持久化。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!bookId" @click="openCreate">录入月报</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-table v-loading="loading" :data="records" empty-text="暂无销售月报" stripe show-summary :summary-method="getSummaries">
      <el-table-column prop="period" label="月份" width="120" />
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
      <el-table-column label="操作" width="120">
        <template #default="scope">
          <el-popconfirm
            title="确定删除该记录吗?"
            confirm-button-text="删除"
            cancel-button-text="取消"
            @confirm="removeRow(scope.row)"
          >
            <template #reference>
              <el-button size="small" link type="danger" :loading="actingId === scope.row.id">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="录入月报" width="520px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="90px">
        <el-form-item label="月份" prop="period">
          <el-date-picker v-model="form.period" type="month" value-format="YYYY-MM" placeholder="请选择月份" style="width: 100%" />
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
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { onMounted, reactive, ref } from "vue";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import {
  salesMonthlyReportsApi,
  mumarenFinanceCenterApi,
  type MumarenSalesMonthlyReport,
  type MumarenFinanceBook,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook } = useMumarenFinanceBook();
const records = ref<MumarenSalesMonthlyReport[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const actingId = ref<number>();

const dialogVisible = ref(false);
const formRef = ref<FormInstance>();

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const defaultForm = () => ({
  period: "",
  store_name: "",
  sales_amount: 0,
  return_amount: 0,
  remark: "",
});

const form = reactive(defaultForm());

const formRules: FormRules = {
  period: [{ required: true, message: "请选择月份", trigger: "change" }],
  store_name: [{ required: true, message: "请输入门店名称", trigger: "blur" }],
  sales_amount: [{ required: true, message: "请输入销售额", trigger: "blur" }],
  return_amount: [{ required: true, message: "请输入退货额", trigger: "blur" }],
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
    records.value = (await salesMonthlyReportsApi.list({ book_id: bookId.value })).data.data;
  } catch {
    error.value = "无法加载销售月报。";
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
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    initializeBook(books.value);
    if (bookId.value) await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

const openCreate = () => {
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  resetForm();
  dialogVisible.value = true;
};

const submit = async () => {
  if (!formRef.value || !bookId.value) return;
  const bid = bookId.value;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    saving.value = true;
    try {
      await salesMonthlyReportsApi.create({
        book_id: bid,
        period: form.period,
        store_name: form.store_name.trim(),
        sales_amount: form.sales_amount,
        return_amount: form.return_amount,
        remark: form.remark.trim(),
      });
      ElMessage.success("月报已录入");
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
