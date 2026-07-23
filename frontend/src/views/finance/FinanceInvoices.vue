<template>
  <div class="fc-invoices">
    <div class="page-header">
      <h2>发票管理</h2>
    </div>

    <div class="filter-bar">
      <el-select v-model="selectedBookId" placeholder="选择账套" filterable @change="loadInvoices">
        <el-option v-for="b in books" :key="b.id" :label="b.company_name" :value="b.id" />
      </el-select>
      <el-select v-model="filterDirection" placeholder="发票方向" clearable style="width: 120px;" @change="loadInvoices">
        <el-option label="进项" value="in" />
        <el-option label="销项" value="out" />
      </el-select>
      <el-button type="primary" @click="openCreate">新建发票</el-button>
    </div>

    <el-table :data="invoices" stripe size="small" v-loading="loading">
      <el-table-column prop="invoice_code" label="发票代码" width="150" />
      <el-table-column prop="invoice_no" label="发票号码" width="150" />
      <el-table-column prop="invoice_type" label="发票类型" width="120" />
      <el-table-column label="方向" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.direction === 'in' ? 'success' : 'warning'" size="small">{{ row.direction === 'in' ? '进项' : '销项' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="invoice_date" label="开票日期" width="110" />
      <el-table-column label="不含税金额" width="130" align="right">
        <template #default="{ row }">{{ money(row.amount_excluding_tax) }}</template>
      </el-table-column>
      <el-table-column label="税额" width="120" align="right">
        <template #default="{ row }">{{ money(row.tax_amount) }}</template>
      </el-table-column>
      <el-table-column label="价税合计" width="130" align="right">
        <template #default="{ row }">{{ money(row.total_amount) }}</template>
      </el-table-column>
      <el-table-column prop="counterparty_name" label="往来单位" min-width="150" />
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
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
      @change="loadInvoices"
      style="margin-top: 16px; justify-content: flex-end;"
    />

    <!-- 新建弹窗 -->
    <el-dialog v-model="showCreateDialog" title="新建发票" width="520px" :close-on-click-modal="false">
      <el-form ref="createFormRef" :model="createForm" label-width="100px">
        <el-form-item label="发票代码">
          <el-input v-model="createForm.invoice_code" />
        </el-form-item>
        <el-form-item label="发票号码" required>
          <el-input v-model="createForm.invoice_no" />
        </el-form-item>
        <el-form-item label="发票类型" required>
          <el-select v-model="createForm.invoice_type" style="width: 100%;">
            <el-option label="增值税专用发票" value="vat_special" />
            <el-option label="增值税普通发票" value="vat_normal" />
            <el-option label="电子发票" value="electronic" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="方向" required>
          <el-select v-model="createForm.direction" style="width: 100%;">
            <el-option label="进项" value="in" />
            <el-option label="销项" value="out" />
          </el-select>
        </el-form-item>
        <el-form-item label="开票日期" required>
          <el-date-picker v-model="createForm.invoice_date" type="date" value-format="YYYY-MM-DD" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="不含税金额" required>
          <el-input-number v-model="createForm.amount_excluding_tax" :min="0" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="税额" required>
          <el-input-number v-model="createForm.tax_amount" :min="0" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="往来单位">
          <el-select v-model="createForm.counterparty_aux_id" placeholder="选择辅助核算" filterable clearable style="width: 100%;">
            <el-option v-for="aux in auxItems" :key="aux.id" :label="aux.item_name" :value="aux.id" />
          </el-select>
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
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { financeCenterApi, type FinBook, type FinInvoice, type FinAuxItem } from "@/api/financeCenter";

const money = (v: number | null | undefined) => v == null ? "--" : v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });

const selectedBookId = ref<number | null>(null);
const books = ref<FinBook[]>([]);
const auxItems = ref<FinAuxItem[]>([]);
const filterDirection = ref("");

const invoices = ref<FinInvoice[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const showCreateDialog = ref(false);
const createFormRef = ref();
const creating = ref(false);
const createForm = ref({
  book_id: 0,
  invoice_code: "",
  invoice_no: "",
  invoice_type: "vat_special",
  direction: "in",
  invoice_date: "",
  amount_excluding_tax: 0,
  tax_amount: 0,
  counterparty_aux_id: undefined as number | undefined,
});

const loadBooks = async () => {
  try {
    const res = await financeCenterApi.listBooks();
    books.value = res.data.data || [];
    if (books.value.length > 0 && !selectedBookId.value) {
      selectedBookId.value = books.value[0].id;
      loadInvoices();
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

const loadInvoices = async () => {
  if (!selectedBookId.value) return;
  loading.value = true;
  try {
    const params: any = { page: page.value, page_size: pageSize.value };
    if (filterDirection.value) params.direction = filterDirection.value;
    const res = await financeCenterApi.listInvoices({ book_id: selectedBookId.value, ...params });
    const data = res.data.data;
    invoices.value = data?.items || [];
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
    invoice_code: "",
    invoice_no: "",
    invoice_type: "vat_special",
    direction: "in",
    invoice_date: "",
    amount_excluding_tax: 0,
    tax_amount: 0,
    counterparty_aux_id: undefined,
  };
  showCreateDialog.value = true;
};

const handleCreate = async () => {
  if (!selectedBookId.value) return;
  creating.value = true;
  try {
    await financeCenterApi.createInvoice({
      book_id: selectedBookId.value,
      invoice_code: createForm.value.invoice_code,
      invoice_no: createForm.value.invoice_no,
      invoice_type: createForm.value.invoice_type,
      direction: createForm.value.direction,
      invoice_date: createForm.value.invoice_date,
      amount_excluding_tax: createForm.value.amount_excluding_tax,
      tax_amount: createForm.value.tax_amount,
      counterparty_aux_id: createForm.value.counterparty_aux_id,
    });
    ElMessage.success("发票创建成功");
    showCreateDialog.value = false;
    loadInvoices();
  } catch { ElMessage.error("创建失败"); }
  creating.value = false;
};

onMounted(() => {
  loadBooks();
  loadAuxItems();
});
</script>

<script lang="ts">
export default { name: "FinanceInvoices" };
</script>

<style scoped>
.fc-invoices { padding: 0; }
.page-header { margin-bottom: 16px; }
.page-header h2 { font-size: 20px; color: #1f2937; margin: 0; }
.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
</style>