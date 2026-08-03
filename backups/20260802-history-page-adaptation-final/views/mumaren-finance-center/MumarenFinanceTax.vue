<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">独立税务台账</p>
        <h2>税务</h2>
        <p>{{ isReadonly ? "金蝶迁移账簿未导入税务业务台账；请通过原始凭证、明细账和余额快照核对。" : "独立税务记录：草稿录入 → 财务审核 → 人工缴税；不自动生成凭证，不反审核。" }}</p>
      </div>
      <div class="heading-actions">
        <el-button type="primary" :disabled="!bookId" :loading="loading" @click="load">查询税务</el-button>
        <el-button v-if="!isReadonly" :disabled="!bookId" @click="openCreate">录入草稿</el-button>
        <el-button v-if="!isReadonly" :disabled="!bookId" @click="openTaxTypes">管理税种</el-button>
      </div>
    </div>
    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <MumarenFinanceHistoricalSourceNotice v-else-if="isReadonly" :readonly="isReadonly" module-key="tax" />
    <template v-else-if="loaded">
      <el-alert v-if="alerts.length" type="warning" :closable="false" show-icon title="存在待处理税务预警">
        <template #default>
          <span v-for="alert in alerts" :key="`${alert.tax_name}-${alert.period}`" class="alert-row">
            {{ alert.tax_name }} {{ alert.period }}：待缴 {{ money(alert.outstanding) }}，截止 {{ alert.due_date }}
          </span>
        </template>
      </el-alert>
      <el-alert v-else type="success" :closable="false" show-icon title="当前没有临期或逾期的独立税务记录" />

      <el-table :data="records" empty-text="暂无独立税务记录" stripe>
        <el-table-column prop="tax_name" label="税种" min-width="160" />
        <el-table-column prop="period" label="所属期间" width="120" />
        <el-table-column label="应缴" width="140" align="right">
          <template #default="scope">{{ money(scope.row.tax_amount) }}</template>
        </el-table-column>
        <el-table-column label="已缴" width="140" align="right">
          <template #default="scope">{{ money(scope.row.paid_amount) }}</template>
        </el-table-column>
        <el-table-column label="未缴" width="140" align="right">
          <template #default="scope">
            <span :class="Number(scope.row.unpaid_amount) > 0 ? 'text-danger' : 'text-ok'">{{ money(scope.row.unpaid_amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="due_date" label="截止日" width="130" />
        <el-table-column label="状态" width="120">
          <template #default="scope">
            <el-tag :type="statusTagType(scope.row)" size="small">{{ statusLabel(scope.row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170">
          <template #default="scope">
            <el-button v-if="scope.row.workflow_status === 'draft'" size="small" link type="primary" :disabled="isReadonly" :loading="actingId === scope.row.id" @click="review(scope.row)">审核</el-button>
            <el-popconfirm v-if="scope.row.workflow_status === 'draft'" title="确定删除该税务草稿?" @confirm="remove(scope.row)">
              <template #reference><el-button link type="danger" size="small" :disabled="isReadonly" :loading="actingId === scope.row.id">删除</el-button></template>
            </el-popconfirm>
            <el-button v-if="scope.row.workflow_status === 'reviewed' && scope.row.status !== 'paid' && Number(scope.row.unpaid_amount) > 0" size="small" link type="success" :disabled="isReadonly" :loading="actingId === scope.row.id" @click="openPay(scope.row)">人工缴税</el-button>
            <span v-if="scope.row.status === 'paid'" class="done-text">已缴税</span>
          </template>
        </el-table-column>
      </el-table>
    </template>
    <el-empty v-else description="请选择独立账簿后查询税务台账" />

    <!-- 录入税务草稿对话框 -->
    <el-dialog v-model="showCreate" title="录入税务草稿" width="480px" destroy-on-close :close-on-click-modal="false">
      <el-form :model="form" label-width="90px">
        <el-form-item label="税种" required>
          <el-select v-model="form.tax_type_id" placeholder="选择税种" style="width:100%">
            <el-option v-for="taxType in taxTypes" :key="taxType.id" :value="taxType.id" :label="`${taxType.tax_name}（${taxType.tax_code}）`" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属期间" required>
          <el-date-picker v-model="form.period" type="month" value-format="YYYY-MM" style="width:100%" placeholder="如 2026-07" />
        </el-form-item>
        <el-form-item label="应纳税额" required>
          <el-input-number v-model="form.tax_amount" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="申报截止">
          <el-date-picker v-model="form.due_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="isReadonly || !canCreate" @click="save">保存草稿</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showTaxTypes" title="管理税种" width="620px" :close-on-click-modal="false">
      <div class="heading-actions"><el-button type="primary" @click="openTaxTypeCreate">新增税种</el-button></div>
      <el-table :data="taxTypes" size="small"><el-table-column prop="tax_code" label="编码" /><el-table-column prop="tax_name" label="名称" /><el-table-column label="默认税率"><template #default="scope">{{ Number(scope.row.default_rate || 0) * 100 }}%</template></el-table-column><el-table-column label="操作" width="110"><template #default="scope"><el-button link type="primary" @click="openTaxTypeEdit(scope.row)">编辑</el-button></template></el-table-column></el-table>
      <el-dialog v-model="showTaxTypeEditor" :title="editingTaxType ? '编辑税种' : '新增税种'" width="430px" append-to-body>
        <el-form :model="taxTypeForm" label-width="90px"><el-form-item label="税种编码" required><el-input v-model="taxTypeForm.tax_code" :disabled="!!editingTaxType" /></el-form-item><el-form-item label="税种名称" required><el-input v-model="taxTypeForm.tax_name" /></el-form-item><el-form-item label="默认税率"><el-input-number v-model="taxTypeForm.default_rate" :min="0" :max="1" :step="0.01" :precision="4" /></el-form-item><el-form-item label="类别"><el-input v-model="taxTypeForm.tax_category" /></el-form-item></el-form>
        <template #footer><el-button @click="showTaxTypeEditor=false">取消</el-button><el-button type="primary" :loading="savingTaxType" @click="saveTaxType">保存</el-button></template>
      </el-dialog>
    </el-dialog>

    <!-- 人工缴税对话框 -->
    <el-dialog v-model="showPay" title="人工缴税确认" width="420px" destroy-on-close :close-on-click-modal="false">
      <el-form :model="payForm" label-width="90px">
        <el-form-item label="税种">
          <el-input :value="payTarget?.tax_name" disabled />
        </el-form-item>
        <el-form-item label="应缴">
          <el-input :value="money(payTarget?.tax_amount)" disabled />
        </el-form-item>
        <el-form-item label="未缴">
          <el-input :value="money(payTarget?.unpaid_amount)" disabled />
        </el-form-item>
        <el-form-item label="缴纳金额" required>
          <el-input-number v-model="payForm.amount" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="缴税日期" required>
          <el-date-picker v-model="payForm.payment_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="payForm.remark" type="textarea" :rows="2" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPay = false">取消</el-button>
        <el-button type="primary" :loading="paying" :disabled="isReadonly || !canPay" @click="confirmPay">确认缴税</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import MumarenFinanceHistoricalSourceNotice from "./MumarenFinanceHistoricalSourceNotice.vue";
import {
  mumarenFinanceCenterApi,
  taxTypesApi,
  type MumarenFinanceBook,
  type MumarenTaxAlert,
  type MumarenTaxRecord,
  type MumarenTaxType,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, isReadonly, initializeBook } = useMumarenFinanceBook();
const alerts = ref<MumarenTaxAlert[]>([]);
const records = ref<MumarenTaxRecord[]>([]);
const taxTypes = ref<MumarenTaxType[]>([]);
const error = ref("");
const loading = ref(false);
const loaded = ref(false);
const actingId = ref<number>(); // 当前正在审核/缴税的记录 id
let loadRequestVersion = 0;

const money = (value: number | undefined) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

// 状态展示契约:缴税状态读取后端 status(pending/paid),
// 不得把 workflow_status 误判为 paid(后端缴税后 workflow_status 仍为 reviewed)。
const statusLabel = (row: MumarenTaxRecord) => {
  if (row.workflow_status === "draft") return "草稿";
  if (row.status === "paid") return "已缴税";
  return "已审核";
};
const statusTagType = (row: MumarenTaxRecord): "" | "warning" | "success" => {
  if (row.workflow_status === "draft") return "";
  if (row.status === "paid") return "success";
  return "warning";
};

const load = async () => {
  const requestedBookId = bookId.value;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId) {
    loaded.value = false;
    return;
  }
  if (isReadonly.value) {
    alerts.value = [];
    records.value = [];
    loaded.value = false;
    loading.value = false;
    error.value = "";
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const [alertResult, recordResult] = await Promise.all([
      mumarenFinanceCenterApi.getTaxAlerts({ book_id: requestedBookId }),
      mumarenFinanceCenterApi.listTaxRecords({ book_id: requestedBookId }),
    ]);
    if (requestVersion !== loadRequestVersion || requestedBookId !== bookId.value || isReadonly.value) return;
    alerts.value = alertResult.data.data.alerts || [];
    records.value = recordResult.data.data;
    loaded.value = true;
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value && !isReadonly.value) {
      error.value = "无法加载独立税务台账。";
      loaded.value = false;
    }
  } finally {
    if (requestVersion === loadRequestVersion) loading.value = false;
  }
};

const onBookChange = () => {
  // 切换账簿时清空已加载数据,必须由用户主动点击"查询税务"
  loadRequestVersion += 1;
  loading.value = false;
  error.value = "";
  loaded.value = false;
  alerts.value = [];
  records.value = [];
};

onMounted(async () => {
  // 仅加载账簿列表,不自动选择账簿,不自动请求税务接口。
  // 用户必须主动选择独立账簿后才能查询税务台账。
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    initializeBook(books.value);
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

// ── 审核(状态机:draft → reviewed,禁止反向) ──
const review = async (row: MumarenTaxRecord) => {
  if (isReadonly.value) return;
  actingId.value = row.id;
  try {
    await mumarenFinanceCenterApi.reviewTaxRecord(row.id);
    ElMessage.success("税务单据已审核");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "审核失败");
  } finally {
    actingId.value = undefined;
  }
};

const remove = async (row: MumarenTaxRecord) => {
  if (isReadonly.value || !bookId.value || row.workflow_status !== "draft") return;
  actingId.value = row.id;
  try {
    await mumarenFinanceCenterApi.deleteTaxRecord(row.id, bookId.value);
    ElMessage.success("税务草稿已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "删除失败");
  } finally {
    actingId.value = undefined;
  }
};

// ── 录入草稿对话框 ──
const showCreate = ref(false);
const showTaxTypes = ref(false);
const showTaxTypeEditor = ref(false);
const savingTaxType = ref(false);
const editingTaxType = ref<MumarenTaxType>();
const taxTypeForm = reactive({ tax_code: "", tax_name: "", default_rate: 0, tax_category: "" });
const saving = ref(false);
const form = reactive({
  tax_type_id: undefined as number | undefined,
  period: new Date().toISOString().slice(0, 7),
  tax_amount: 0,
  due_date: "",
  remark: "",
});
const canCreate = computed(() => !!bookId.value && !!form.tax_type_id && !!form.period && form.tax_amount >= 0);

const openCreate = async () => {
  if (isReadonly.value) return;
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  try {
    taxTypes.value = (await taxTypesApi.list({ book_id: bookId.value })).data.data;
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "无法加载当前账簿税种");
    return;
  }
  form.tax_type_id = undefined;
  form.period = new Date().toISOString().slice(0, 7);
  form.tax_amount = 0;
  form.due_date = "";
  form.remark = "";
  showCreate.value = true;
};

const loadTaxTypes = async () => {
  if (!bookId.value) return;
  taxTypes.value = (await taxTypesApi.list({ book_id: bookId.value })).data.data;
};
const openTaxTypes = async () => {
  if (isReadonly.value || !bookId.value) return;
  try { await loadTaxTypes(); showTaxTypes.value = true; }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "无法加载税种"); }
};
const openTaxTypeCreate = () => {
  editingTaxType.value = undefined;
  Object.assign(taxTypeForm, { tax_code: "", tax_name: "", default_rate: 0, tax_category: "" });
  showTaxTypeEditor.value = true;
};
const openTaxTypeEdit = (row: MumarenTaxType) => {
  editingTaxType.value = row;
  Object.assign(taxTypeForm, { tax_code: row.tax_code, tax_name: row.tax_name, default_rate: Number(row.default_rate), tax_category: row.tax_category || "" });
  showTaxTypeEditor.value = true;
};
const saveTaxType = async () => {
  if (!bookId.value || !taxTypeForm.tax_code.trim() || !taxTypeForm.tax_name.trim()) return;
  savingTaxType.value = true;
  try {
    if (editingTaxType.value) await taxTypesApi.updateTaxType(editingTaxType.value.id, { book_id: bookId.value, tax_name: taxTypeForm.tax_name, default_rate: taxTypeForm.default_rate, tax_category: taxTypeForm.tax_category || null });
    else await taxTypesApi.createTaxType({ book_id: bookId.value, ...taxTypeForm, tax_category: taxTypeForm.tax_category || null });
    ElMessage.success(editingTaxType.value ? "税种已更新" : "税种已创建"); showTaxTypeEditor.value = false; await loadTaxTypes();
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "保存失败"); } finally { savingTaxType.value = false; }
};

const save = async () => {
  if (isReadonly.value) return;
  if (!bookId.value || !canCreate.value) return;
  saving.value = true;
  try {
    await mumarenFinanceCenterApi.createTaxRecord({
      book_id: bookId.value,
      tax_type_id: form.tax_type_id as number,
      period: form.period,
      tax_amount: form.tax_amount,
      due_date: form.due_date || null,
      remark: form.remark || null,
    });
    ElMessage.success("税务草稿已创建");
    showCreate.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
};

// ── 人工缴税对话框 ──
const showPay = ref(false);
const paying = ref(false);
const payTarget = ref<MumarenTaxRecord>();
const payForm = reactive({
  amount: 0,
  payment_date: new Date().toISOString().slice(0, 10),
  remark: "",
});
const canPay = computed(
  () => !!payTarget.value && payForm.amount > 0 && !!payForm.payment_date && payForm.amount <= Number(payTarget.value.unpaid_amount || 0) + 0.001,
);

const openPay = (row: MumarenTaxRecord) => {
  payTarget.value = row;
  payForm.amount = Number(row.unpaid_amount || 0);
  payForm.payment_date = new Date().toISOString().slice(0, 10);
  payForm.remark = "";
  showPay.value = true;
};

const confirmPay = async () => {
  if (isReadonly.value) return;
  if (!payTarget.value || !canPay.value) return;
  paying.value = true;
  try {
    await mumarenFinanceCenterApi.payTaxRecord(payTarget.value.id, {
      payment_date: payForm.payment_date,
      amount: payForm.amount,
      remark: payForm.remark || null,
    });
    ElMessage.success("税务单据已缴税");
    showPay.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "缴税失败");
  } finally {
    paying.value = false;
  }
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
.alert-row { display: block; margin: 4px 0; }
.done-text { color: #909399; font-size: 13px; }
.text-danger { color: #f56c6c; font-weight: 600; }
.text-ok { color: #67c23a; }
.field-hint { margin: 4px 0 0; color: #9b5b00; font-size: 12px; line-height: 1.5; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
