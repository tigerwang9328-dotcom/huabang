<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">发票管理</p>
        <h2>发票</h2>
        <p>发票登记、认证与台账;按独立账簿隔离,数据持久化。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!bookId" @click="openCreate">登记发票</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-table v-loading="loading" :data="invoices" empty-text="暂无发票记录" stripe show-summary :summary-method="summary">
      <el-table-column prop="invoice_code" label="发票代码" width="140" />
      <el-table-column prop="invoice_no" label="号码" width="130" />
      <el-table-column label="方向" width="90">
        <template #default="{ row }">
          <el-tag :type="row.direction === 'input' ? 'warning' : 'success'" size="small">{{ row.direction === 'input' ? '进项' : '销项' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="counterparty" label="对方" min-width="180" />
      <el-table-column label="金额" width="130" align="right">
        <template #default="{ row }">{{ money(row.amount) }}</template>
      </el-table-column>
      <el-table-column label="税额" width="130" align="right">
        <template #default="{ row }">{{ money(row.tax_amount) }}</template>
      </el-table-column>
      <el-table-column label="价税合计" width="140" align="right">
        <template #default="{ row }">{{ money(row.total_amount) }}</template>
      </el-table-column>
      <el-table-column prop="invoice_date" label="日期" width="130" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.status === 'verified' ? 'success' : 'info'" size="small">{{ row.status === 'verified' ? '已认证' : '草稿' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button link type="primary" size="small" :disabled="!canVerify(row)" :loading="actingId === row.id" @click="verify(row)">认证</el-button>
          <el-popconfirm title="确定删除该发票?" @confirm="remove(row)">
            <template #reference>
              <el-button link type="danger" size="small" :loading="actingId === row.id">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="登记发票" width="520px" :close-on-click-modal="false">
      <el-form :model="form" label-width="110px">
        <el-form-item label="发票代码">
          <el-input v-model="form.invoice_code" />
        </el-form-item>
        <el-form-item label="发票号码">
          <el-input v-model="form.invoice_no" />
        </el-form-item>
        <el-form-item label="方向">
          <el-radio-group v-model="form.direction">
            <el-radio label="input">进项</el-radio>
            <el-radio label="output">销项</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="对方单位">
          <el-input v-model="form.counterparty" />
        </el-form-item>
        <el-form-item label="金额(不含税)">
          <el-input-number v-model="form.amount" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="税额">
          <el-input-number v-model="form.tax_amount" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="价税合计">
          <span>{{ money(totalAmount) }}</span>
        </el-form-item>
        <el-form-item label="开票日期">
          <el-date-picker v-model="form.invoice_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
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
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  invoicesApi,
  mumarenFinanceCenterApi,
  type MumarenFinanceBook,
  type MumarenInvoice,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook } = useMumarenFinanceBook();
const invoices = ref<MumarenInvoice[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const actingId = ref<number>();
const dialogVisible = ref(false);

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const form = reactive({
  invoice_code: "",
  invoice_no: "",
  direction: "input" as "input" | "output",
  counterparty: "",
  amount: 0,
  tax_amount: 0,
  invoice_date: new Date().toISOString().slice(0, 10),
});

const totalAmount = computed(() => Number(form.amount || 0) + Number(form.tax_amount || 0));

const load = async () => {
  if (!bookId.value) return;
  loading.value = true;
  error.value = "";
  try {
    invoices.value = (await invoicesApi.list({ book_id: bookId.value })).data.data;
  } catch {
    error.value = "无法加载发票记录。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = () => {
  invoices.value = [];
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
  form.invoice_code = "";
  form.invoice_no = "";
  form.direction = "input";
  form.counterparty = "";
  form.amount = 0;
  form.tax_amount = 0;
  form.invoice_date = new Date().toISOString().slice(0, 10);
  dialogVisible.value = true;
};

const save = async () => {
  if (!bookId.value) return;
  if (!form.invoice_code || !form.invoice_no) {
    ElMessage.warning("请填写发票代码与号码");
    return;
  }
  saving.value = true;
  try {
    await invoicesApi.create({
      book_id: bookId.value,
      invoice_code: form.invoice_code,
      invoice_no: form.invoice_no,
      direction: form.direction,
      counterparty: form.counterparty,
      amount: Number(form.amount || 0),
      tax_amount: Number(form.tax_amount || 0),
      invoice_date: form.invoice_date,
    });
    ElMessage.success("发票已登记");
    dialogVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
};

const canVerify = (row: MumarenInvoice) => row.direction === "input" && row.status !== "verified";

const verify = async (row: MumarenInvoice) => {
  if (!bookId.value || !canVerify(row)) return;
  actingId.value = row.id;
  try {
    await invoicesApi.verify(row.id, bookId.value);
    ElMessage.success("发票已认证");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "认证失败");
  } finally {
    actingId.value = undefined;
  }
};

const remove = async (row: MumarenInvoice) => {
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await invoicesApi.delete(row.id, bookId.value);
    ElMessage.success("已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "删除失败");
  } finally {
    actingId.value = undefined;
  }
};

const summary = ({ columns, data }: { columns: any[]; data: MumarenInvoice[] }) => {
  const sums: (string | number)[] = [];
  columns.forEach((_, i) => {
    sums[i] = i === 0 ? "合计" : "";
  });
  const idxAmount = columns.findIndex((c) => c.label === "金额");
  const idxTax = columns.findIndex((c) => c.label === "税额");
  const idxTotal = columns.findIndex((c) => c.label === "价税合计");
  if (idxAmount >= 0) sums[idxAmount] = money(data.reduce((s, r) => s + Number(r.amount || 0), 0));
  if (idxTax >= 0) sums[idxTax] = money(data.reduce((s, r) => s + Number(r.tax_amount || 0), 0));
  if (idxTotal >= 0) sums[idxTotal] = money(data.reduce((s, r) => s + Number(r.total_amount || 0), 0));
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
