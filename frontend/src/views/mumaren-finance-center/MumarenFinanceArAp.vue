<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">独立往来账</p>
        <h2>{{ pageTitle }}</h2>
        <p>独立{{ typeText }}单台账：草稿录入 → 财务审核 → {{ settlementAction }}；不自动生成凭证。按独立账簿隔离，数据持久化。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!bookId || isReadonly" @click="openCreate">录入{{ typeText }}草稿</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable>
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
      <el-radio-group v-if="!fixedOrderType" v-model="orderType">
        <el-radio-button label="receivable">应收</el-radio-button>
        <el-radio-button label="payable">应付</el-radio-button>
      </el-radio-group>
      <el-date-picker v-model="periodFilter" type="month" value-format="YYYY-MM" placeholder="筛选期间" clearable />
      <el-select v-model="settlementFilter" placeholder="结算状态" clearable>
        <el-option label="草稿" value="draft" />
        <el-option label="待结算" value="open" />
        <el-option label="部分结算" value="partial" />
        <el-option label="已结清" value="settled" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-alert v-if="summary && summary.total_count > orders.length" type="warning" :closable="false" show-icon title="明细最多显示最近 500 条；上方汇总已按当前筛选条件统计全部单据。" />

    <el-row :gutter="12" class="metric-grid">
      <el-col v-for="metric in metrics" :key="metric.label" :xs="12" :sm="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-label">{{ metric.label }}</div>
          <strong :class="metric.className">{{ metric.isMoney ? money(metric.value) : metric.value }}</strong>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="created-card" shadow="never">
      <template #header>
        <div class="card-header"><span>{{ pageTitle }}列表</span><span class="muted">{{ summary?.total_count || 0 }} 条</span></div>
      </template>
      <el-table v-loading="loading" :data="filteredOrders" stripe size="small" empty-text="暂无订单" @row-click="openDetail">
        <el-table-column prop="order_no" label="单号" min-width="140" />
        <el-table-column prop="order_date" label="日期" width="120" />
        <el-table-column prop="counterparty_name" :label="counterpartyLabel" min-width="160" show-overflow-tooltip />
        <el-table-column :label="amountLabel" width="120" align="right">
          <template #default="scope">{{ money(scope.row.total_amount) }}</template>
        </el-table-column>
        <el-table-column :label="settledLabel" width="120" align="right">
          <template #default="scope">{{ money(scope.row.settled_amount) }}</template>
        </el-table-column>
        <el-table-column label="未结余额" width="120" align="right">
          <template #default="scope"><span class="balance">{{ money(balanceOf(scope.row)) }}</span></template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope"><el-tag :type="statusTagType(scope.row)" size="small">{{ statusLabel(scope.row) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="250" @click.stop>
          <template #default="scope">
            <el-button size="small" link @click.stop="openDetail(scope.row)">详情</el-button>
            <el-button v-if="scope.row.workflow_status === 'draft'" size="small" link type="primary" :disabled="isReadonly" @click.stop="openEdit(scope.row)">编辑</el-button>
            <el-button v-if="scope.row.workflow_status === 'draft'" size="small" link type="primary" :disabled="isReadonly" :loading="actingId === scope.row.id" @click.stop="reviewOrder(scope.row)">审核</el-button>
            <el-button v-if="scope.row.workflow_status === 'reviewed' && scope.row.settlement_status !== 'settled'" size="small" link type="success" :disabled="isReadonly" :loading="actingId === scope.row.id" @click.stop="openSettle(scope.row)">{{ settlementAction }}</el-button>
            <el-popconfirm v-if="scope.row.workflow_status === 'draft' && !isReadonly" title="确定删除该订单？" @confirm="removeOrder(scope.row)">
              <template #reference><el-button size="small" link type="danger" :loading="actingId === scope.row.id">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-alert v-if="isReadonly" type="warning" :closable="false" show-icon title="金蝶迁移账簿只读：可查询台账，不能录入、审核、回款、付款或删除。" />

    <el-dialog v-model="showCreate" :title="editingId ? `编辑${typeText}草稿` : `录入${typeText}草稿`" width="500px" destroy-on-close :close-on-click-modal="false">
      <el-form :model="form" label-width="90px">
        <el-form-item label="单号" required><el-input v-model="form.order_no" :disabled="!!editingId" :placeholder="orderType === 'receivable' ? '如 AR-2026-08-001' : '如 AP-2026-08-001'" /></el-form-item>
        <el-form-item label="单据日期" required><el-date-picker v-model="form.order_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item :label="counterpartyLabel" required><el-input v-model="form.counterparty_name" maxlength="128" :placeholder="counterpartyLabel" /></el-form-item>
        <el-form-item :label="amountLabel" required><el-input-number v-model="form.total_amount" :min="0.01" :precision="2" :controls="false" style="width:100%" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showCreate = false">取消</el-button><el-button type="primary" :loading="saving" :disabled="!canCreate" @click="save">{{ editingId ? '保存修改' : '保存草稿' }}</el-button></template>
    </el-dialog>

    <el-dialog v-model="showSettle" :title="settlementAction" width="420px" destroy-on-close :close-on-click-modal="false">
      <el-form :model="settleForm" label-width="90px">
        <el-form-item label="单号"><el-input :model-value="settleTarget?.order_no" disabled /></el-form-item>
        <el-form-item :label="amountLabel"><el-input :model-value="settleTarget?.total_amount != null ? money(settleTarget.total_amount) : ''" disabled /></el-form-item>
        <el-form-item label="未结余额"><el-input :model-value="settleTarget ? money(balanceOf(settleTarget)) : ''" disabled /></el-form-item>
        <el-form-item :label="settlementAmountLabel" required><el-input-number v-model="settleForm.amount" :min="0.01" :precision="2" :controls="false" style="width:100%" /></el-form-item>
        <el-form-item :label="settlementDateLabel" required><el-date-picker v-model="settleForm.settlement_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="settleForm.remark" type="textarea" :rows="2" maxlength="500" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showSettle = false">取消</el-button><el-button type="primary" :loading="settling" :disabled="!canSettle" @click="confirmSettle">确认{{ settlementAction }}</el-button></template>
    </el-dialog>

    <el-drawer v-model="showDetail" :title="`${typeText}单据详情`" size="480px">
      <el-descriptions v-if="detailOrder" :column="1" border>
        <el-descriptions-item label="单号">{{ detailOrder.order_no }}</el-descriptions-item>
        <el-descriptions-item label="日期">{{ detailOrder.order_date }}</el-descriptions-item>
        <el-descriptions-item :label="counterpartyLabel">{{ detailOrder.counterparty_name }}</el-descriptions-item>
        <el-descriptions-item :label="amountLabel">{{ money(detailOrder.total_amount) }}</el-descriptions-item>
        <el-descriptions-item :label="settledLabel">{{ money(detailOrder.settled_amount) }}</el-descriptions-item>
        <el-descriptions-item label="未结余额">{{ money(balanceOf(detailOrder)) }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ statusLabel(detailOrder) }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { arApOrdersApi, mumarenFinanceCenterApi, type MumarenArApOrder, type MumarenArApSummary } from "@/api/mumarenFinanceCenter";

const props = defineProps<{ fixedOrderType?: "receivable" | "payable" }>();
const { books, bookId, isReadonly, loadBooks } = useMumarenFinanceBook();
const orderType = ref<"receivable" | "payable">(props.fixedOrderType || "receivable");
const orders = ref<MumarenArApOrder[]>([]);
const summary = ref<MumarenArApSummary>();
const error = ref("");
const loading = ref(false);
const actingId = ref<number>();
const periodFilter = ref("");
const settlementFilter = ref<"draft" | "open" | "partial" | "settled" | "">("");
const showDetail = ref(false);
const detailOrder = ref<MumarenArApOrder>();
let loadRequestVersion = 0;

const isReceivable = computed(() => orderType.value === "receivable");
const typeText = computed(() => isReceivable.value ? "应收" : "应付");
const pageTitle = computed(() => `${typeText.value}单台账`);
const counterpartyLabel = computed(() => isReceivable.value ? "客户" : "供应商");
const amountLabel = computed(() => isReceivable.value ? "应收金额" : "应付金额");
const settledLabel = computed(() => isReceivable.value ? "已回款" : "已付款");
const settlementAction = computed(() => isReceivable.value ? "登记回款" : "登记付款");
const settlementAmountLabel = computed(() => isReceivable.value ? "回款金额" : "付款金额");
const settlementDateLabel = computed(() => isReceivable.value ? "回款日期" : "付款日期");
const money = (value: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
const balanceOf = (row: MumarenArApOrder) => Math.max(0, Number(row.total_amount) - Number(row.settled_amount));

const filteredOrders = computed(() => orders.value);
const metrics = computed(() => {
  const data = summary.value || { total_amount: 0, settled_amount: 0, outstanding_amount: 0, open_count: 0 };
  return [
    { label: isReceivable.value ? "应收总额" : "应付总额", value: data.total_amount, isMoney: true, className: "metric-primary" },
    { label: isReceivable.value ? "已回款" : "已付款", value: data.settled_amount, isMoney: true, className: "metric-success" },
    { label: "未结余额", value: data.outstanding_amount, isMoney: true, className: "metric-danger" },
    { label: "未结清单数", value: data.open_count, isMoney: false, className: "metric-warning" },
  ];
});

const statusLabel = (row: MumarenArApOrder) => {
  if (row.workflow_status === "draft") return "草稿";
  if (row.settlement_status === "settled") return "已结清";
  if (row.settlement_status === "partial") return "部分结算";
  return "已审核";
};
const statusTagType = (row: MumarenArApOrder): "" | "warning" | "success" => row.workflow_status === "draft" ? "" : row.settlement_status === "settled" ? "success" : "warning";

const load = async () => {
  const requestedBookId = bookId.value;
  const requestedOrderType = orderType.value;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId) { orders.value = []; summary.value = undefined; loading.value = false; error.value = ""; return; }
  loading.value = true;
  error.value = "";
  try {
    const params = { book_id: requestedBookId, order_type: requestedOrderType, period: periodFilter.value || undefined, status: settlementFilter.value || undefined };
    const [listResponse, summaryResponse] = await Promise.all([arApOrdersApi.list({ ...params, limit: 500 }), arApOrdersApi.summary(params)]);
    if (requestVersion !== loadRequestVersion || requestedBookId !== bookId.value || requestedOrderType !== orderType.value) return;
    orders.value = listResponse.data.data;
    summary.value = summaryResponse.data.data;
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value && requestedOrderType === orderType.value) error.value = "无法加载独立应收应付数据。";
  } finally {
    if (requestVersion === loadRequestVersion) loading.value = false;
  }
};

watch(bookId, async () => { orders.value = []; summary.value = undefined; showCreate.value = false; showSettle.value = false; await load(); });
watch(orderType, load);
watch([periodFilter, settlementFilter], load);
watch(() => props.fixedOrderType, (value) => { if (value) orderType.value = value; });
onMounted(async () => { try { await loadBooks(); await load(); } catch { error.value = "无法加载独立账簿。"; } });

const showCreate = ref(false);
const saving = ref(false);
const editingId = ref<number>();
const form = reactive({ order_no: "", order_date: new Date().toISOString().slice(0, 10), counterparty_name: "", total_amount: 0, remark: "" });
const canCreate = computed(() => !!bookId.value && !!form.order_no && !!form.order_date && !!form.counterparty_name && form.total_amount > 0);
const openCreate = () => {
  if (isReadonly.value) { ElMessage.warning("金蝶迁移账簿只读，不能录入应收应付单据"); return; }
  if (!bookId.value) { ElMessage.warning("请先选择独立账簿"); return; }
  Object.assign(form, { order_no: "", order_date: new Date().toISOString().slice(0, 10), counterparty_name: "", total_amount: 0, remark: "" });
  editingId.value = undefined;
  showCreate.value = true;
};
const openEdit = (row: MumarenArApOrder) => {
  if (isReadonly.value || row.workflow_status !== "draft") return;
  editingId.value = row.id;
  Object.assign(form, { order_no: row.order_no, order_date: row.order_date, counterparty_name: row.counterparty_name, total_amount: Number(row.total_amount), remark: "" });
  showCreate.value = true;
};
const save = async () => {
  if (!bookId.value || isReadonly.value || !canCreate.value) return;
  saving.value = true;
  try {
    if (editingId.value) {
      await arApOrdersApi.update(editingId.value, { order_date: form.order_date, counterparty_name: form.counterparty_name, total_amount: form.total_amount, remark: form.remark || null }, bookId.value, orderType.value);
      ElMessage.success(`${typeText.value}草稿已更新`);
    } else {
      await mumarenFinanceCenterApi.createArApOrder({ book_id: bookId.value, order_type: orderType.value, order_no: form.order_no, order_date: form.order_date, counterparty_name: form.counterparty_name, total_amount: form.total_amount, remark: form.remark || null });
      ElMessage.success(`${typeText.value}草稿已创建`);
    }
    showCreate.value = false; await load();
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "保存失败"); }
  finally { saving.value = false; }
};
const reviewOrder = async (row: MumarenArApOrder) => {
  if (isReadonly.value) return;
  actingId.value = row.id;
  try { await mumarenFinanceCenterApi.reviewArApOrder(row.id, orderType.value); ElMessage.success(`${typeText.value}单据已审核`); await load(); }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "审核失败"); }
  finally { actingId.value = undefined; }
};
const removeOrder = async (row: MumarenArApOrder) => {
  if (!bookId.value || isReadonly.value) return;
  actingId.value = row.id;
  try { await arApOrdersApi.delete(row.id, bookId.value, orderType.value); ElMessage.success("订单已删除"); await load(); }
  catch (e: any) { ElMessage.error(e?.response?.data?.detail || "删除失败"); }
  finally { actingId.value = undefined; }
};
const openDetail = (row: MumarenArApOrder) => { detailOrder.value = row; showDetail.value = true; };

const showSettle = ref(false);
const settling = ref(false);
const settleTarget = ref<MumarenArApOrder>();
const settleForm = reactive({ amount: 0, settlement_date: new Date().toISOString().slice(0, 10), remark: "" });
const canSettle = computed(() => !!settleTarget.value && settleForm.amount > 0 && !!settleForm.settlement_date && settleForm.amount <= balanceOf(settleTarget.value) + 0.001);
const openSettle = (row: MumarenArApOrder) => {
  if (isReadonly.value) return;
  settleTarget.value = row; settleForm.amount = balanceOf(row); settleForm.settlement_date = new Date().toISOString().slice(0, 10); settleForm.remark = ""; showSettle.value = true;
};
const confirmSettle = async () => {
  if (isReadonly.value || !settleTarget.value || !canSettle.value) return;
  settling.value = true;
  try {
    await mumarenFinanceCenterApi.settleArApOrder(settleTarget.value.id, orderType.value, { settlement_date: settleForm.settlement_date, amount: settleForm.amount, remark: settleForm.remark || null });
    ElMessage.success(`${settlementAction.value}已登记`); showSettle.value = false; await load();
  } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "登记失败"); }
  finally { settling.value = false; }
};
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading, .heading-actions, .filters, .card-header { display: flex; gap: 12px; align-items: center; }
.heading { justify-content: space-between; align-items: flex-start; }
.filters { flex-wrap: wrap; }
.metric-grid { margin: 0 -6px; }.metric-card { text-align: center; }.metric-label, .muted { color: #718096; font-size: 13px; }.metric-card strong { display: block; margin-top: 6px; font-size: 20px; }.metric-primary { color: #176b97; }.metric-success { color: #2f855a; }.metric-danger, .balance { color: #c53030; }.metric-warning { color: #b7791f; }
.card-header { justify-content: space-between; color: #176b97; font-weight: 600; }.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }h2 { margin: 8px 0; }p { color: #5d6b7e; }
@media (max-width: 640px) { .heading, .filters { align-items: stretch; flex-direction: column; } .heading-actions { width: 100%; } }
</style>
