<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">出纳管理</p>
        <h2>账户与流水</h2>
        <p>资金账户与日记账流水;按独立账簿隔离,数据持久化。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button :disabled="!bookId || isReadonly" @click="openAccountDialog">新增账户</el-button>
        <el-button type="primary" :disabled="!bookId || isReadonly || accounts.length === 0" @click="openTxnDialog">录入流水</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-alert v-if="isReadonly" type="warning" title="金蝶迁移账簿只读，不能维护资金账户或录入流水。" :closable="false" show-icon />

    <h3 class="block-title">资金账户</h3>
    <el-table v-loading="loading" :data="accounts" empty-text="暂无账户" stripe show-summary :summary-method="accountSummary">
      <el-table-column prop="account_name" label="账户名称" min-width="180" />
      <el-table-column prop="account_type" label="类型" width="120" />
      <el-table-column label="期初余额" width="150" align="right">
        <template #default="{ row }">{{ money(row.opening_balance) }}</template>
      </el-table-column>
      <el-table-column label="当前余额" width="150" align="right">
        <template #default="{ row }">{{ money(row.current_balance) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-popconfirm title="确定删除该账户?关联流水将一并删除" @confirm="removeAccount(row)">
            <template #reference>
              <el-button link type="danger" size="small" :disabled="isReadonly" :loading="actingId === row.id">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <h3 class="block-title">日记账流水</h3>
    <el-table v-loading="loading" :data="transactions" empty-text="暂无流水" stripe show-summary :summary-method="txnSummary">
      <el-table-column prop="transaction_date" label="日期" width="130" />
      <el-table-column label="账户" min-width="160">
        <template #default="{ row }">{{ accountName(row.account_id) }}</template>
      </el-table-column>
      <el-table-column label="方向" width="100">
        <template #default="{ row }">
          <el-tag :type="row.direction === 'income' ? 'success' : 'warning'" size="small">{{ row.direction === 'income' ? '收入' : '支出' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="140" align="right">
        <template #default="{ row }">{{ money(row.amount) }}</template>
      </el-table-column>
      <el-table-column prop="counterparty" label="对方" min-width="160" />
      <el-table-column prop="remark" label="备注" min-width="160" />
    </el-table>

    <el-dialog v-model="accountDialogVisible" title="新增账户" width="460px" :close-on-click-modal="false">
      <el-form :model="accountForm" label-width="100px">
        <el-form-item label="账户名称">
          <el-input v-model="accountForm.account_name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="accountForm.account_type" style="width:100%">
            <el-option label="银行" value="银行" />
            <el-option label="支付宝" value="支付宝" />
            <el-option label="微信" value="微信" />
            <el-option label="现金" value="现金" />
          </el-select>
        </el-form-item>
        <el-form-item label="期初余额">
          <el-input-number v-model="accountForm.opening_balance" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accountDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingAccount" @click="saveAccount">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="txnDialogVisible" title="录入流水" width="520px" :close-on-click-modal="false">
      <el-form :model="txnForm" label-width="100px">
        <el-form-item label="账户">
          <el-select v-model="txnForm.account_id" style="width:100%" placeholder="选择账户">
            <el-option v-for="a in accounts" :key="a.id" :label="`${a.account_name} (${a.account_type})`" :value="a.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="日期">
          <el-date-picker v-model="txnForm.transaction_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="方向">
          <el-radio-group v-model="txnForm.direction">
            <el-radio label="income">收入</el-radio>
            <el-radio label="expense">支出</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="金额">
          <el-input-number v-model="txnForm.amount" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="对方">
          <el-input v-model="txnForm.counterparty" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="txnForm.remark" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="txnDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingTxn" @click="saveTxn">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  cashAccountsApi,
  cashFlowsApi,
  type MumarenCashAccount,
  type MumarenCashFlow,
} from "@/api/mumarenFinanceCenter";

const { books, bookId, isReadonly, loadBooks } = useMumarenFinanceBook();
const accounts = ref<MumarenCashAccount[]>([]);
const transactions = ref<MumarenCashFlow[]>([]);
const loading = ref(false);
const error = ref("");
const actingId = ref<number>();
const accountDialogVisible = ref(false);
const txnDialogVisible = ref(false);
const savingAccount = ref(false);
const savingTxn = ref(false);

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const accountForm = reactive({
  account_name: "",
  account_type: "银行",
  opening_balance: 0,
});

const txnForm = reactive({
  account_id: undefined as number | undefined,
  transaction_date: new Date().toISOString().slice(0, 10),
  direction: "income" as "income" | "expense",
  amount: 0,
  counterparty: "",
  remark: "",
});

const accountName = (id: number) => {
  const a = accounts.value.find((x) => x.id === id);
  return a ? `${a.account_name} (${a.account_type})` : "—";
};

const load = async () => {
  if (!bookId.value) return;
  loading.value = true;
  error.value = "";
  try {
    const [accRes, flowRes] = await Promise.all([
      cashAccountsApi.list({ book_id: bookId.value }),
      cashFlowsApi.list({ book_id: bookId.value }),
    ]);
    accounts.value = accRes.data.data;
    transactions.value = flowRes.data.data;
  } catch {
    error.value = "无法加载出纳账户与流水。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = () => {
  accounts.value = [];
  transactions.value = [];
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

const openAccountDialog = () => {
  if (isReadonly.value) return;
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  accountForm.account_name = "";
  accountForm.account_type = "银行";
  accountForm.opening_balance = 0;
  accountDialogVisible.value = true;
};

const saveAccount = async () => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  if (!accountForm.account_name) {
    ElMessage.warning("请填写账户名称");
    return;
  }
  savingAccount.value = true;
  try {
    await cashAccountsApi.create({
      book_id: bookId.value,
      account_name: accountForm.account_name,
      account_type: accountForm.account_type,
      opening_balance: Number(accountForm.opening_balance || 0),
    });
    ElMessage.success("账户已新增");
    accountDialogVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败");
  } finally {
    savingAccount.value = false;
  }
};

const openTxnDialog = () => {
  if (isReadonly.value) return;
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  if (accounts.value.length === 0) {
    ElMessage.warning("请先新增账户");
    return;
  }
  txnForm.account_id = accounts.value[0].id;
  txnForm.transaction_date = new Date().toISOString().slice(0, 10);
  txnForm.direction = "income";
  txnForm.amount = 0;
  txnForm.counterparty = "";
  txnForm.remark = "";
  txnDialogVisible.value = true;
};

const saveTxn = async () => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  if (!txnForm.account_id) {
    ElMessage.warning("请选择账户");
    return;
  }
  const amount = Number(txnForm.amount || 0);
  if (amount <= 0) {
    ElMessage.warning("金额需大于 0");
    return;
  }
  savingTxn.value = true;
  try {
    await cashFlowsApi.create({
      book_id: bookId.value,
      cash_account_id: txnForm.account_id,
      transaction_date: txnForm.transaction_date,
      direction: txnForm.direction,
      amount,
      counterparty: txnForm.counterparty,
      remark: txnForm.remark,
    });
    ElMessage.success("流水已录入");
    txnDialogVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败");
  } finally {
    savingTxn.value = false;
  }
};

const removeAccount = async (row: MumarenCashAccount) => {
  if (isReadonly.value) return;
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await cashAccountsApi.delete(row.id, bookId.value);
    ElMessage.success("账户已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "删除失败");
  } finally {
    actingId.value = undefined;
  }
};

const accountSummary = ({ columns, data }: { columns: any[]; data: MumarenCashAccount[] }) => {
  const sums: (string | number)[] = [];
  columns.forEach((_, i) => {
    sums[i] = i === 0 ? "合计" : "";
  });
  const idxOpening = columns.findIndex((c) => c.label === "期初余额");
  const idxCurrent = columns.findIndex((c) => c.label === "当前余额");
  if (idxOpening >= 0) sums[idxOpening] = money(data.reduce((s, a) => s + Number(a.opening_balance || 0), 0));
  if (idxCurrent >= 0) sums[idxCurrent] = money(data.reduce((s, a) => s + Number(a.current_balance || 0), 0));
  return sums;
};

const txnSummary = ({ columns, data }: { columns: any[]; data: MumarenCashFlow[] }) => {
  const sums: (string | number)[] = [];
  columns.forEach((_, i) => {
    sums[i] = i === 0 ? "合计" : "";
  });
  const idxAmount = columns.findIndex((c) => c.label === "金额");
  if (idxAmount >= 0) sums[idxAmount] = money(data.reduce((s, t) => s + Number(t.amount || 0), 0));
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
h3.block-title { margin: 8px 0 4px; font-size: 15px; color: #1f2937; }
p { color: #5d6b7e; }
@media (max-width: 640px) { .filters { flex-direction: column; } .heading { flex-direction: column; } }
</style>
