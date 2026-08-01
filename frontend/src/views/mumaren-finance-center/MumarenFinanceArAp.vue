<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">独立往来账</p>
        <h2>应收应付</h2>
        <p>独立 AR/AP 台账与账龄：草稿录入 → 财务审核 → 人工结算；不自动生成凭证。</p>
      </div>
      <div class="heading-actions">
        <el-button type="primary" :disabled="!bookId" :loading="loading" @click="load">查询账龄</el-button>
        <el-button :disabled="!bookId" @click="openCreate">录入草稿</el-button>
      </div>
    </div>
    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
      <el-radio-group v-model="orderType" @change="load">
        <el-radio-button label="receivable">应收</el-radio-button>
        <el-radio-button label="payable">应付</el-radio-button>
      </el-radio-group>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <!-- 本会话单据列表(可在此审核/结算,闭环演示;刷新后清空) -->
    <el-card v-if="sessionOrders.length" class="created-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>本会话单据（可审核 / 结算）</span>
          <el-button link type="info" @click="sessionOrders = []">清空</el-button>
        </div>
      </template>
      <p class="session-note">完整订单列表接口待后端补,刷新后列表清空;账龄查询不依赖此列表。</p>
      <el-table :data="sessionOrders" stripe size="small">
        <el-table-column prop="order_no" label="单号" min-width="140" />
        <el-table-column prop="counterparty_name" label="往来单位" min-width="160" show-overflow-tooltip />
        <el-table-column label="类型" width="80">
          <template #default="scope">{{ scope.row.order_type === "receivable" ? "应收" : "应付" }}</template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="scope">{{ money(scope.row.total_amount) }}</template>
        </el-table-column>
        <el-table-column label="已结算" width="120" align="right">
          <template #default="scope">{{ money(scope.row.settled_amount) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="scope">
            <el-tag :type="statusTagType(scope.row)" size="small">{{ statusLabel(scope.row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170">
          <template #default="scope">
            <el-button v-if="scope.row.workflow_status === 'draft'" size="small" link type="primary" :loading="actingId === scope.row.id" @click="reviewSession(scope.row)">审核</el-button>
            <el-button v-if="scope.row.workflow_status === 'reviewed' && scope.row.settlement_status !== 'settled'" size="small" link type="success" :loading="actingId === scope.row.id" @click="openSettleSession(scope.row)">人工结算</el-button>
            <span v-if="scope.row.settlement_status === 'settled'" class="done-text">已结算</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <template v-if="aging">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="截止日">{{ aging.as_of }}</el-descriptions-item>
        <el-descriptions-item label="未结余额">{{ money(aging.total_balance) }}</el-descriptions-item>
      </el-descriptions>
      <div class="bucket-grid">
        <div v-for="(amount, bucket) in aging.buckets" :key="bucket" class="bucket">
          <span>{{ bucket }}</span><strong>{{ money(amount) }}</strong>
        </div>
      </div>
      <el-table :data="aging.counterparties" empty-text="暂无未结往来余额" stripe>
        <el-table-column prop="counterparty_name" label="往来单位" min-width="200" />
        <el-table-column label="未结余额" width="160" align="right">
          <template #default="scope">{{ money(scope.row.total_balance) }}</template>
        </el-table-column>
      </el-table>
      <p class="gap-note">注:账龄按往来单位聚合展示。历史单据的逐单审核/结算需要 AR/AP 订单列表接口(待后端补),仅上方"本会话单据"可在此闭环操作。</p>
    </template>
    <el-empty v-else-if="!error" description="请选择独立账簿后查询账龄" />

    <!-- 录入 AR/AP 草稿对话框 -->
    <el-dialog v-model="showCreate" :title="`录入${orderType === 'receivable' ? '应收' : '应付'}草稿`" width="500px" destroy-on-close :close-on-click-modal="false">
      <el-form :model="form" label-width="90px">
        <el-form-item label="单号" required>
          <el-input v-model="form.order_no" placeholder="如 AR-2026-07-001" />
        </el-form-item>
        <el-form-item label="单据日期" required>
          <el-date-picker v-model="form.order_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="往来单位" required>
          <el-input v-model="form.counterparty_name" maxlength="128" placeholder="客户/供应商名称" />
        </el-form-item>
        <el-form-item label="金额" required>
          <el-input-number v-model="form.total_amount" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!canCreate" @click="save">保存草稿</el-button>
      </template>
    </el-dialog>

    <!-- 人工结算对话框 -->
    <el-dialog v-model="showSettle" title="人工结算确认" width="420px" destroy-on-close :close-on-click-modal="false">
      <el-form :model="settleForm" label-width="90px">
        <el-form-item label="单号">
          <el-input :value="settleTarget?.order_no" disabled />
        </el-form-item>
        <el-form-item label="应收/应付">
          <el-input :value="settleTarget?.total_amount != null ? money(settleTarget.total_amount) : ''" disabled />
        </el-form-item>
        <el-form-item label="结算金额" required>
          <el-input-number v-model="settleForm.amount" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="结算日期" required>
          <el-date-picker v-model="settleForm.settlement_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="settleForm.remark" type="textarea" :rows="2" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSettle = false">取消</el-button>
        <el-button type="primary" :loading="settling" :disabled="!canSettle" @click="confirmSettle">确认结算</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  mumarenFinanceCenterApi,
  type MumarenArApAging,
  type MumarenArApOrder,
  type MumarenFinanceBook,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const bookId = ref<number>();
const orderType = ref<"receivable" | "payable">("receivable");
const aging = ref<MumarenArApAging>();
const sessionOrders = ref<MumarenArApOrder[]>([]); // 本会话创建/审核/结算过的单据(刷新清空)
const error = ref("");
const loading = ref(false);
const actingId = ref<number>(); // 当前正在审核/结算的单据 id

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

// 状态展示契约:结算状态读取 settlement_status(open/partial/settled),
// 不得把 workflow_status 误判为 settled(后端结算后 workflow_status 仍为 reviewed)。
const statusLabel = (row: MumarenArApOrder) => {
  if (row.workflow_status === "draft") return "草稿";
  if (row.settlement_status === "settled") return "已结算";
  if (row.settlement_status === "partial") return "部分结算";
  return "已审核";
};
const statusTagType = (row: MumarenArApOrder): "" | "warning" | "success" => {
  if (row.workflow_status === "draft") return "";
  if (row.settlement_status === "settled") return "success";
  return "warning";
};

const load = async () => {
  if (!bookId.value) return;
  loading.value = true;
  error.value = "";
  try {
    aging.value = (await mumarenFinanceCenterApi.getArApAging({ book_id: bookId.value, order_type: orderType.value })).data.data;
  } catch {
    error.value = "无法加载独立应收应付账龄。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = () => {
  aging.value = undefined;
  sessionOrders.value = [];
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    bookId.value = books.value[0]?.id;
    if (bookId.value) await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

// ── 录入草稿对话框 ──
const showCreate = ref(false);
const saving = ref(false);
const form = reactive({
  order_no: "",
  order_date: new Date().toISOString().slice(0, 10),
  counterparty_name: "",
  total_amount: 0,
  remark: "",
});
const canCreate = computed(
  () => !!bookId.value && !!form.order_no && !!form.order_date && !!form.counterparty_name && form.total_amount >= 0,
);

const openCreate = () => {
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  form.order_no = "";
  form.order_date = new Date().toISOString().slice(0, 10);
  form.counterparty_name = "";
  form.total_amount = 0;
  form.remark = "";
  showCreate.value = true;
};

const save = async () => {
  if (!bookId.value || !canCreate.value) return;
  saving.value = true;
  try {
    const res = await mumarenFinanceCenterApi.createArApOrder({
      book_id: bookId.value,
      order_type: orderType.value,
      order_no: form.order_no,
      order_date: form.order_date,
      counterparty_name: form.counterparty_name,
      total_amount: form.total_amount,
      remark: form.remark || null,
    });
    sessionOrders.value.unshift(res.data.data);
    ElMessage.success("AR/AP 草稿已创建,已加入本会话单据列表");
    showCreate.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
};

// 本会话单据的本地更新工具
const updateSessionOrder = (updated: MumarenArApOrder) => {
  const idx = sessionOrders.value.findIndex((o) => o.id === updated.id);
  if (idx >= 0) sessionOrders.value.splice(idx, 1, updated);
};

// ── 本会话单据审核(状态机:draft → reviewed,禁止反向) ──
const reviewSession = async (row: MumarenArApOrder) => {
  actingId.value = row.id;
  try {
    const res = await mumarenFinanceCenterApi.reviewArApOrder(row.id);
    updateSessionOrder(res.data.data);
    ElMessage.success("AR/AP 单据已审核");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "审核失败");
  } finally {
    actingId.value = undefined;
  }
};

// ── 人工结算对话框 ──
const showSettle = ref(false);
const settling = ref(false);
const settleTarget = ref<MumarenArApOrder>();
const settleForm = reactive({
  amount: 0,
  settlement_date: new Date().toISOString().slice(0, 10),
  remark: "",
});
const canSettle = computed(
  () => !!settleTarget.value && settleForm.amount > 0 && !!settleForm.settlement_date &&
    settleForm.amount <= Number(settleTarget.value.total_amount) - Number(settleTarget.value.settled_amount) + 0.001,
);

const openSettleSession = (row: MumarenArApOrder) => {
  settleTarget.value = row;
  settleForm.amount = Number(row.total_amount) - Number(row.settled_amount);
  settleForm.settlement_date = new Date().toISOString().slice(0, 10);
  settleForm.remark = "";
  showSettle.value = true;
};

const confirmSettle = async () => {
  if (!settleTarget.value || !canSettle.value) return;
  settling.value = true;
  try {
    const res = await mumarenFinanceCenterApi.settleArApOrder(settleTarget.value.id, {
      settlement_date: settleForm.settlement_date,
      amount: settleForm.amount,
      remark: settleForm.remark || null,
    });
    updateSessionOrder(res.data.data);
    ElMessage.success("AR/AP 单据已结算");
    showSettle.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "结算失败");
  } finally {
    settling.value = false;
  }
};
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.heading-actions { display: flex; gap: 8px; }
.filters { display: flex; gap: 12px; align-items: center; }
.bucket-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; }
.bucket { display: grid; gap: 6px; padding: 14px; border: 1px solid #e1e7ef; border-radius: 10px; background: #fbfdff; color: #5d6b7e; }
.bucket strong { color: #172033; font-size: 17px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
.created-card { border: 1px solid #d7b879; }
.card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; color: #9b5b00; }
.card-actions { margin-top: 12px; display: flex; gap: 8px; }
.done-text { color: #909399; font-size: 13px; }
.gap-note { color: #9b5b00; font-size: 12px; line-height: 1.6; margin: 4px 0 0; }
@media (max-width: 640px) { .filters { align-items: stretch; flex-direction: column; } .heading { flex-direction: column; } }
</style>
