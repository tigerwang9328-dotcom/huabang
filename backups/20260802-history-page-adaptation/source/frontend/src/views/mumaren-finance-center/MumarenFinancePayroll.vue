<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">薪资管理</p>
        <h2>工资</h2>
        <p>{{ isReadonly ? "金蝶迁移账簿未导入工资业务明细；请通过原始凭证、明细账和余额快照核对。" : "工资草稿、扣除额与实发额核对;按独立账簿隔离,数据持久化。" }}</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!bookId || isReadonly" @click="openDialog">录入工资</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-alert v-if="isReadonly" type="warning" title="金蝶迁移账簿未导入工资业务明细，当前页面不以空表表示历史工资为零。" :closable="false" show-icon />

    <el-table v-if="!isReadonly" v-loading="loading" :data="records" empty-text="暂无工资记录" stripe show-summary :summary-method="summary">
      <el-table-column prop="employee_no" label="员工编号" width="120" />
      <el-table-column prop="employee_name" label="员工" min-width="120" />
      <el-table-column prop="period" label="期间" width="110" />
      <el-table-column label="应发" width="130" align="right">
        <template #default="{ row }">{{ money(row.gross_amount) }}</template>
      </el-table-column>
      <el-table-column label="扣除" width="130" align="right">
        <template #default="{ row }">{{ money(row.deduction_amount) }}</template>
      </el-table-column>
      <el-table-column label="实发" width="130" align="right">
        <template #default="{ row }">{{ money(row.net_amount) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.workflow_status === 'draft' ? 'warning' : 'success'" size="small">
            {{ row.workflow_status === "draft" ? "草稿" : "已发放" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button v-if="row.workflow_status === 'draft'" link type="primary" size="small" :disabled="isReadonly" @click="openEdit(row)">编辑</el-button>
          <el-button
            v-if="row.workflow_status === 'draft'"
            link
            type="primary"
            size="small"
            :disabled="isReadonly"
            :loading="actingId === row.id"
            @click="pay(row)"
          >发放</el-button>
          <el-popconfirm title="确定删除该工资记录?" @confirm="remove(row)">
            <template #reference>
              <el-button link type="danger" size="small" :disabled="isReadonly" :loading="actingId === row.id">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑工资' : '录入工资'" width="520px" :close-on-click-modal="false">
      <el-form :model="form" label-width="100px">
        <el-form-item label="员工编号">
          <el-input v-model="form.employee_no" :disabled="!!editingId" />
        </el-form-item>
        <el-form-item label="员工姓名">
          <el-input v-model="form.employee_name" />
        </el-form-item>
        <el-form-item label="期间">
          <el-date-picker v-model="form.period" type="month" value-format="YYYY-MM" :disabled="!!editingId" style="width:100%" />
        </el-form-item>
        <el-form-item label="应发金额">
          <el-input-number v-model="form.gross_amount" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="扣除金额">
          <el-input-number v-model="form.deduction_amount" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="实发金额">
          <el-input-number :model-value="netAmount" disabled :precision="2" :controls="false" style="width:100%" />
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
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  payrollsApi,
  type MumarenPayroll,
} from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";

const { books, bookId, isReadonly, loadBooks } = useMumarenFinanceBook();
const records = ref<MumarenPayroll[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const actingId = ref<number>();
let loadRequestVersion = 0;
const dialogVisible = ref(false);
const editingId = ref<number>();

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const form = reactive({
  employee_no: "",
  employee_name: "",
  period: new Date().toISOString().slice(0, 7),
  gross_amount: 0,
  deduction_amount: 0,
});
const netAmount = computed(() => Math.max(0, Number(form.gross_amount || 0) - Number(form.deduction_amount || 0)));

const load = async () => {
  const requestedBookId = bookId.value;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId || isReadonly.value) { records.value = []; loading.value = false; error.value = ""; return; }
  loading.value = true;
  error.value = "";
  try {
    const response = await payrollsApi.list({ book_id: requestedBookId });
    if (requestVersion !== loadRequestVersion || requestedBookId !== bookId.value || isReadonly.value) return;
    records.value = response.data.data;
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value && !isReadonly.value) error.value = "无法加载工资记录。";
  } finally {
    if (requestVersion === loadRequestVersion) loading.value = false;
  }
};

const onBookChange = () => {
  records.value = [];
  load();
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
  form.employee_no = "";
  form.employee_name = "";
  form.period = new Date().toISOString().slice(0, 7);
  form.gross_amount = 0;
  form.deduction_amount = 0;
  editingId.value = undefined;
  dialogVisible.value = true;
};

const openEdit = (row: MumarenPayroll) => {
  if (isReadonly.value || row.workflow_status !== "draft") return;
  editingId.value = row.id;
  form.employee_no = row.employee_no;
  form.employee_name = row.employee_name;
  form.period = row.period;
  form.gross_amount = Number(row.gross_amount || 0);
  form.deduction_amount = Number(row.deduction_amount || 0);
  dialogVisible.value = true;
};

const save = async () => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  if (!form.employee_no || !form.employee_name) {
    ElMessage.warning("请填写员工编号和姓名");
    return;
  }
  saving.value = true;
  try {
    const payload = {
      employee_name: form.employee_name,
      gross_amount: Number(form.gross_amount || 0),
      deduction_amount: Number(form.deduction_amount || 0),
      net_amount: netAmount.value,
    };
    if (editingId.value) {
      await payrollsApi.update(editingId.value, { book_id: bookId.value, ...payload });
      ElMessage.success("工资记录已更新");
    } else {
      await payrollsApi.create({ book_id: bookId.value, period: form.period, employee_no: form.employee_no, ...payload });
      ElMessage.success("工资记录已录入");
    }
    dialogVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
};

const pay = async (row: MumarenPayroll) => {
  if (isReadonly.value) return;
  if (!bookId.value || row.workflow_status !== "draft") return;
  actingId.value = row.id;
  try {
    await payrollsApi.pay(row.id, bookId.value);
    ElMessage.success("工资已发放");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "发放失败");
  } finally {
    actingId.value = undefined;
  }
};

const remove = async (row: MumarenPayroll) => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await payrollsApi.delete(row.id, bookId.value);
    ElMessage.success("工资记录已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "删除失败");
  } finally {
    actingId.value = undefined;
  }
};

const summary = ({ columns, data }: { columns: any[]; data: MumarenPayroll[] }) => {
  const sums: (string | number)[] = [];
  columns.forEach((_, i) => {
    sums[i] = i === 0 ? "合计" : "";
  });
  const fields: Record<string, keyof MumarenPayroll> = {
    应发: "gross_amount",
    扣除: "deduction_amount",
    实发: "net_amount",
  };
  Object.keys(fields).forEach((label) => {
    const idx = columns.findIndex((c) => c.label === label);
    if (idx >= 0) {
      sums[idx] = money(data.reduce((s, r) => s + Number(r[fields[label]] || 0), 0));
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
