<template>
  <div class="fc-tax">
    <div class="page-header">
      <h2>税务管理</h2>
    </div>

    <div class="filter-bar">
      <el-select v-model="selectedBookId" placeholder="选择账套" filterable @change="loadTaxRecords">
        <el-option v-for="b in books" :key="b.id" :label="b.company_name" :value="b.id" />
      </el-select>
      <el-input v-model="filterPeriod" placeholder="期间（如 202601）" clearable style="width: 150px;" @change="loadTaxRecords" />
      <el-button type="primary" @click="openCreate">新建税务记录</el-button>
    </div>

    <el-table :data="records" stripe size="small" v-loading="loading">
      <el-table-column prop="tax_type" label="税种" width="120" />
      <el-table-column prop="period" label="期间" width="110" />
      <el-table-column label="计税金额" width="130" align="right">
        <template #default="{ row }">{{ money(row.taxable_amount) }}</template>
      </el-table-column>
      <el-table-column label="税额" width="120" align="right">
        <template #default="{ row }">{{ money(row.tax_amount) }}</template>
      </el-table-column>
      <el-table-column label="已缴金额" width="120" align="right">
        <template #default="{ row }">{{ money(row.paid_amount) }}</template>
      </el-table-column>
      <el-table-column prop="due_date" label="应缴日期" width="110" />
      <el-table-column prop="paid_date" label="缴纳日期" width="110" />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'paid' ? 'success' : 'warning'" size="small">
            {{ row.status === 'paid' ? '已缴' : '未缴' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'unpaid'"
            link
            type="primary"
            size="small"
            @click="openMarkPaid(row)"
          >标记已缴</el-button>
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
      @change="loadTaxRecords"
      style="margin-top: 16px; justify-content: flex-end;"
    />

    <!-- 新建弹窗 -->
    <el-dialog v-model="showCreateDialog" title="新建税务记录" width="480px" :close-on-click-modal="false">
      <el-form ref="createFormRef" :model="createForm" label-width="100px">
        <el-form-item label="税种" required>
          <el-select v-model="createForm.tax_type" style="width: 100%;">
            <el-option label="增值税" value="vat" />
            <el-option label="企业所得税" value="corporate_income" />
            <el-option label="个人所得税" value="personal_income" />
            <el-option label="印花税" value="stamp" />
            <el-option label="城建税" value="urban_construction" />
            <el-option label="教育费附加" value="education_surcharge" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="期间" required>
          <el-input v-model="createForm.period" placeholder="如 202601" />
        </el-form-item>
        <el-form-item label="计税金额">
          <el-input-number v-model="createForm.taxable_amount" :min="0" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="税额" required>
          <el-input-number v-model="createForm.tax_amount" :min="0" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="应缴日期">
          <el-date-picker v-model="createForm.due_date" type="date" value-format="YYYY-MM-DD" style="width: 100%;" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 标记已缴弹窗 -->
    <el-dialog v-model="showPaidDialog" title="标记已缴" width="420px" :close-on-click-modal="false">
      <el-form :model="paidForm" label-width="100px">
        <el-form-item label="税种">
          <span>{{ paidTarget?.tax_type }}</span>
        </el-form-item>
        <el-form-item label="期间">
          <span>{{ paidTarget?.period }}</span>
        </el-form-item>
        <el-form-item label="税额">
          <span>{{ money(paidTarget?.tax_amount) }}</span>
        </el-form-item>
        <el-form-item label="缴纳日期" required>
          <el-date-picker v-model="paidForm.paid_date" type="date" value-format="YYYY-MM-DD" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="原因" required>
          <el-input v-model="paidForm.reason" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPaidDialog = false">取消</el-button>
        <el-button type="primary" :loading="marking" @click="handleMarkPaid">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { financeCenterApi, type FinBook, type FinTaxRecord } from "@/api/financeCenter";

const money = (v: number | null | undefined) => v == null ? "--" : v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });

const selectedBookId = ref<number | null>(null);
const books = ref<FinBook[]>([]);
const filterPeriod = ref("");

const records = ref<FinTaxRecord[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const showCreateDialog = ref(false);
const createFormRef = ref();
const creating = ref(false);
const createForm = ref({
  book_id: 0,
  tax_type: "vat",
  period: "",
  tax_amount: 0,
  taxable_amount: 0,
  due_date: "",
});

const showPaidDialog = ref(false);
const paidTarget = ref<FinTaxRecord | null>(null);
const marking = ref(false);
const paidForm = ref({ paid_date: "", reason: "" });

const loadBooks = async () => {
  try {
    const res = await financeCenterApi.listBooks();
    books.value = res.data.data || [];
    if (books.value.length > 0 && !selectedBookId.value) {
      selectedBookId.value = books.value[0].id;
      loadTaxRecords();
    }
  } catch { /* ignore */ }
};

const loadTaxRecords = async () => {
  if (!selectedBookId.value) return;
  loading.value = true;
  try {
    const res = await financeCenterApi.listTaxRecords({ book_id: selectedBookId.value, period: filterPeriod.value || undefined, ...{
      page: page.value,
      page_size: pageSize.value,
    } });
    const data = res.data.data;
    records.value = data?.items || [];
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
    tax_type: "vat",
    period: "",
    tax_amount: 0,
    taxable_amount: 0,
    due_date: "",
  };
  showCreateDialog.value = true;
};

const handleCreate = async () => {
  if (!selectedBookId.value) return;
  creating.value = true;
  try {
    await financeCenterApi.createTaxRecord({
      book_id: selectedBookId.value,
      tax_type: createForm.value.tax_type,
      period: createForm.value.period,
      tax_amount: createForm.value.tax_amount,
      taxable_amount: createForm.value.taxable_amount,
      due_date: createForm.value.due_date || undefined,
    });
    ElMessage.success("税务记录创建成功");
    showCreateDialog.value = false;
    loadTaxRecords();
  } catch { ElMessage.error("创建失败"); }
  creating.value = false;
};

const openMarkPaid = (row: FinTaxRecord) => {
  paidTarget.value = row;
  paidForm.value = { paid_date: "", reason: "" };
  showPaidDialog.value = true;
};

const handleMarkPaid = async () => {
  if (!paidTarget.value || !paidForm.value.paid_date || !paidForm.value.reason) {
    ElMessage.warning("请填写缴纳日期和原因");
    return;
  }
  marking.value = true;
  try {
    await financeCenterApi.markTaxPaid(paidTarget.value.id, {
      paid_date: paidForm.value.paid_date,
      reason: paidForm.value.reason,
    });
    ElMessage.success("已标记为已缴");
    showPaidDialog.value = false;
    loadTaxRecords();
  } catch { ElMessage.error("操作失败"); }
  marking.value = false;
};

onMounted(() => {
  loadBooks();
});
</script>

<script lang="ts">
export default { name: "FinanceTax" };
</script>

<style scoped>
.fc-tax { padding: 0; }
.page-header { margin-bottom: 16px; }
.page-header h2 { font-size: 20px; color: #1f2937; margin: 0; }
.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
</style>