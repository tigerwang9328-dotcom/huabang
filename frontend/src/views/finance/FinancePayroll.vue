<template>
  <div class="fc-payroll">
    <div class="page-header">
      <h2>工资管理</h2>
    </div>

    <div class="filter-bar">
      <el-select v-model="selectedBookId" placeholder="选择账套" filterable @change="loadPayrolls">
        <el-option v-for="b in books" :key="b.id" :label="b.company_name" :value="b.id" />
      </el-select>
      <el-input v-model="filterPeriod" placeholder="期间（如 202601）" clearable style="width: 150px;" @change="loadPayrolls" />
      <el-button type="primary" @click="openCreate">新建工资</el-button>
    </div>

    <el-table :data="payrolls" stripe size="small" v-loading="loading">
      <el-table-column prop="period" label="期间" width="110" />
      <el-table-column prop="employee_name" label="员工" min-width="120" />
      <el-table-column prop="department_name" label="部门" min-width="120" />
      <el-table-column label="应发" width="120" align="right">
        <template #default="{ row }">{{ money(row.gross_amount) }}</template>
      </el-table-column>
      <el-table-column label="社保" width="100" align="right">
        <template #default="{ row }">{{ money(row.social_security_amount) }}</template>
      </el-table-column>
      <el-table-column label="公积金" width="100" align="right">
        <template #default="{ row }">{{ money(row.housing_fund_amount) }}</template>
      </el-table-column>
      <el-table-column label="个税" width="100" align="right">
        <template #default="{ row }">{{ money(row.tax_amount) }}</template>
      </el-table-column>
      <el-table-column label="其他扣款" width="100" align="right">
        <template #default="{ row }">{{ money(row.other_deduction) }}</template>
      </el-table-column>
      <el-table-column label="实发" width="120" align="right">
        <template #default="{ row }">
          <b style="color: #2563eb;">{{ money(row.net_amount) }}</b>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'confirmed' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-if="total > 0"
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[10, 20, 50]"
      layout="total, prev, pager, next, sizes"
      @change="loadPayrolls"
      style="margin-top: 16px; justify-content: flex-end;"
    />

    <!-- 新建弹窗 -->
    <el-dialog v-model="showCreateDialog" title="新建工资" width="520px" :close-on-click-modal="false">
      <el-form ref="createFormRef" :model="createForm" label-width="100px">
        <el-form-item label="期间" required>
          <el-input v-model="createForm.period" placeholder="如 202601" />
        </el-form-item>
        <el-form-item label="员工" required>
          <el-select v-model="createForm.employee_aux_id" placeholder="选择辅助核算" filterable style="width: 100%;">
            <el-option v-for="aux in auxItems" :key="aux.id" :label="aux.item_name" :value="aux.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门">
          <el-select v-model="createForm.department_aux_id" placeholder="选择辅助核算" filterable clearable style="width: 100%;">
            <el-option v-for="aux in auxItems" :key="aux.id" :label="aux.item_name" :value="aux.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="应发" required>
          <el-input-number v-model="createForm.gross_amount" :min="0" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="社保">
          <el-input-number v-model="createForm.social_security_amount" :min="0" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="公积金">
          <el-input-number v-model="createForm.housing_fund_amount" :min="0" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="个税">
          <el-input-number v-model="createForm.tax_amount" :min="0" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="其他扣款">
          <el-input-number v-model="createForm.other_deduction" :min="0" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="实发">
          <span class="computed-value">{{ money(computedNet) }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { financeCenterApi, type FinBook, type FinPayroll, type FinAuxItem } from "@/api/financeCenter";

const money = (v: number | null | undefined) => v == null ? "--" : v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });

const selectedBookId = ref<number | null>(null);
const books = ref<FinBook[]>([]);
const auxItems = ref<FinAuxItem[]>([]);
const filterPeriod = ref("");

const payrolls = ref<FinPayroll[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const showCreateDialog = ref(false);
const createFormRef = ref();
const creating = ref(false);
const createForm = ref({
  book_id: 0,
  period: "",
  employee_aux_id: undefined as number | undefined,
  department_aux_id: undefined as number | undefined,
  gross_amount: 0,
  social_security_amount: 0,
  housing_fund_amount: 0,
  tax_amount: 0,
  other_deduction: 0,
});

const computedNet = computed(() => {
  const f = createForm.value;
  return f.gross_amount - f.social_security_amount - f.housing_fund_amount - f.tax_amount - f.other_deduction;
});

const loadBooks = async () => {
  try {
    const res = await financeCenterApi.listBooks();
    books.value = res.data.data || [];
    if (books.value.length > 0 && !selectedBookId.value) {
      selectedBookId.value = books.value[0].id;
      loadPayrolls();
    }
  } catch { /* ignore */ }
};

const loadAuxItems = async () => {
  if (!selectedBookId.value) return;
  try {
    const res = await financeCenterApi.listAuxItems({ book_id: selectedBookId.value });
    auxItems.value = res.data.data || [];
  } catch { /* ignore */ }
};

const loadPayrolls = async () => {
  if (!selectedBookId.value) return;
  loading.value = true;
  try {
    const res = await financeCenterApi.listPayrolls({ book_id: selectedBookId.value, period: filterPeriod.value || undefined, ...{
      page: page.value,
      page_size: pageSize.value,
    } });
    const data = res.data.data;
    payrolls.value = data?.items || [];
    total.value = data?.total || 0;
  } catch { /* ignore */ }
  loading.value = false;
};

const openCreate = () => {
  if (!selectedBookId.value) {
    ElMessage.warning("请先选择账套");
    return;
  }
  createForm.value = {
    book_id: selectedBookId.value,
    period: "",
    employee_aux_id: undefined,
    department_aux_id: undefined,
    gross_amount: 0,
    social_security_amount: 0,
    housing_fund_amount: 0,
    tax_amount: 0,
    other_deduction: 0,
  };
  showCreateDialog.value = true;
};

const handleCreate = async () => {
  if (!selectedBookId.value) return;
  creating.value = true;
  try {
    await financeCenterApi.createPayroll({
      book_id: selectedBookId.value,
      period: createForm.value.period,
      employee_aux_id: createForm.value.employee_aux_id!,
      department_aux_id: createForm.value.department_aux_id,
      gross_amount: createForm.value.gross_amount,
      social_security_amount: createForm.value.social_security_amount,
      housing_fund_amount: createForm.value.housing_fund_amount,
      tax_amount: createForm.value.tax_amount,
      other_deduction: createForm.value.other_deduction,
    });
    ElMessage.success("工资记录创建成功");
    showCreateDialog.value = false;
    loadPayrolls();
  } catch { ElMessage.error("创建失败"); }
  creating.value = false;
};

onMounted(() => {
  loadBooks();
  loadAuxItems();
});
</script>

<script lang="ts">
export default { name: "FinancePayroll" };
</script>

<style scoped>
.fc-payroll { padding: 0; }
.page-header { margin-bottom: 16px; }
.page-header h2 { font-size: 20px; color: #1f2937; margin: 0; }
.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
.computed-value { font-size: 18px; font-weight: 700; color: #2563eb; }
</style>