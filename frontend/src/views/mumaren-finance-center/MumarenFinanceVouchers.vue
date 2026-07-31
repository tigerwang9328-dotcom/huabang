<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">凭证流程</p>
        <h2>凭证</h2>
        <p>独立当前账凭证：草稿录入 → 财务审核 → 人工过账；不自动过账，不反过账。</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!bookId" @click="openCreate">录入草稿</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-table v-else :data="vouchers" empty-text="暂无独立当前账凭证" stripe>
      <el-table-column prop="voucher_no" label="凭证号" min-width="130" />
      <el-table-column prop="voucher_date" label="日期" width="120" />
      <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
      <el-table-column label="状态" width="110">
        <template #default="scope">
          <el-tag :type="statusTagType(scope.row.status)" size="small">{{ statusLabel(scope.row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="借方" width="140" align="right">
        <template #default="scope">{{ money(scope.row.total_debit) }}</template>
      </el-table-column>
      <el-table-column label="贷方" width="140" align="right">
        <template #default="scope">{{ money(scope.row.total_credit) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="scope">
          <el-button v-if="scope.row.status === 'draft'" size="small" link type="primary" :loading="actingId === scope.row.id" @click="review(scope.row)">审核</el-button>
          <el-button v-if="scope.row.status === 'reviewed'" size="small" link type="success" :loading="actingId === scope.row.id" @click="post(scope.row)">人工过账</el-button>
          <span v-if="scope.row.status === 'posted'" class="done-text">已过账</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 录入草稿对话框 -->
    <el-dialog v-model="showCreate" title="录入凭证草稿" width="780px" destroy-on-close :close-on-click-modal="false">
      <el-form :model="form" label-width="84px">
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12" :md="6">
            <el-form-item label="凭证字">
              <el-select v-model="form.voucher_type" style="width:100%">
                <el-option label="记" value="记" />
                <el-option label="收" value="收" />
                <el-option label="付" value="付" />
                <el-option label="转" value="转" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="9">
            <el-form-item label="凭证号">
              <el-input v-model="form.voucher_no" placeholder="如 2026-07-001" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="9">
            <el-form-item label="凭证日期">
              <el-date-picker v-model="form.voucher_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="总摘要">
          <el-input v-model="form.summary" maxlength="200" show-word-limit placeholder="例如：确认店铺销售收入" />
        </el-form-item>
      </el-form>

      <div class="dialog-toolbar">
        <el-button type="primary" plain @click="addLine">添加分录</el-button>
        <div class="totals">
          <span>借方 <b>{{ money(totalDebit) }}</b></span>
          <span>贷方 <b>{{ money(totalCredit) }}</b></span>
          <span>差额 <b :class="{ danger: !balanced }">{{ money(balanceDiff) }}</b></span>
          <el-tag size="small" :type="balanced ? 'success' : 'danger'">{{ balanced ? '已平衡' : '未平衡' }}</el-tag>
        </div>
      </div>

      <el-table :data="form.lines" border size="small" row-key="key" :max-height="360">
        <el-table-column type="index" label="#" width="42" />
        <el-table-column label="会计科目" min-width="240">
          <template #default="{ row }">
            <el-select v-model="row.account_id" filterable clearable size="small" placeholder="选择科目" style="width:100%">
              <el-option v-for="a in accounts" :key="a.id" :label="`${a.account_code} ${a.account_name}`" :value="a.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="160">
          <template #default="{ row }"><el-input v-model="row.summary" size="small" placeholder="行摘要" /></template>
        </el-table-column>
        <el-table-column label="借方金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.debit_amount" :min="0" :precision="2" :controls="false" size="small" style="width:108px" @focus="row.credit_amount = 0" />
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.credit_amount" :min="0" :precision="2" :controls="false" size="small" style="width:108px" @focus="row.debit_amount = 0" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" :disabled="form.lines.length <= 1" @click="removeLine($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!canSave" @click="save">保存草稿</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  mumarenFinanceCenterApi,
  type MumarenFinanceAccount,
  type MumarenFinanceBook,
  type MumarenFinanceVoucher,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const bookId = ref<number>();
const accounts = ref<MumarenFinanceAccount[]>([]);
const vouchers = ref<MumarenFinanceVoucher[]>([]);
const error = ref("");
const loading = ref(false);
const actingId = ref<number>(); // 当前正在审核/过账的凭证 id

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const statusLabel = (s: string) => ({ draft: "草稿", reviewed: "已审核", posted: "已过账" }[s] || s);
const statusTagType = (s: string): "" | "warning" | "success" => (s === "draft" ? "" : s === "reviewed" ? "warning" : "success");

const load = async () => {
  loading.value = true;
  error.value = "";
  try {
    vouchers.value = (await mumarenFinanceCenterApi.listVouchers(bookId.value ? { book_id: bookId.value } : undefined)).data.data;
  } catch {
    error.value = "无法加载独立当前账凭证。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = async () => {
  await load();
  // 预载科目供录入草稿使用
  if (bookId.value) {
    try {
      accounts.value = (await mumarenFinanceCenterApi.listAccounts(bookId.value)).data.data;
    } catch {
      accounts.value = [];
    }
  } else {
    accounts.value = [];
  }
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
  } catch {
    error.value = "无法加载独立账簿。";
  }
  await load();
});

// ── 审核与人工过账(状态机:draft → reviewed → posted,禁止反向) ──
const review = async (row: MumarenFinanceVoucher) => {
  actingId.value = row.id;
  try {
    await mumarenFinanceCenterApi.reviewVoucher(row.id);
    ElMessage.success("凭证已审核");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "审核失败");
  } finally {
    actingId.value = undefined;
  }
};

const post = async (row: MumarenFinanceVoucher) => {
  actingId.value = row.id;
  try {
    await mumarenFinanceCenterApi.postVoucher(row.id);
    ElMessage.success("凭证已人工过账");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "过账失败");
  } finally {
    actingId.value = undefined;
  }
};

// ── 录入草稿对话框 ──
const showCreate = ref(false);
const saving = ref(false);
let lineSeed = 1;
const newLine = () => ({ key: `line-${lineSeed++}`, account_id: undefined as number | undefined, summary: "", debit_amount: 0, credit_amount: 0 });
const form = reactive({
  voucher_type: "记",
  voucher_no: "",
  voucher_date: new Date().toISOString().slice(0, 10),
  summary: "",
  lines: [newLine(), newLine()],
});

const validLines = computed(() =>
  form.lines.filter((l) => l.account_id && (Number(l.debit_amount) > 0 || Number(l.credit_amount) > 0)),
);
const totalDebit = computed(() => validLines.value.reduce((s, l) => s + Number(l.debit_amount || 0), 0));
const totalCredit = computed(() => validLines.value.reduce((s, l) => s + Number(l.credit_amount || 0), 0));
const balanceDiff = computed(() => totalDebit.value - totalCredit.value);
const balanced = computed(() => Math.abs(balanceDiff.value) < 0.005 && totalDebit.value > 0);
const canSave = computed(() => balanced.value && validLines.value.length >= 2 && !!form.voucher_no && !!form.voucher_date);

const openCreate = () => {
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  form.voucher_type = "记";
  form.voucher_no = "";
  form.voucher_date = new Date().toISOString().slice(0, 10);
  form.summary = "";
  form.lines = [newLine(), newLine()];
  showCreate.value = true;
};

const addLine = () => form.lines.push(newLine());
const removeLine = (index: number) => {
  if (form.lines.length > 1) form.lines.splice(index, 1);
};

const save = async () => {
  if (!bookId.value || !canSave.value) return;
  // 同一行不能同时填借贷
  if (validLines.value.find((l) => Number(l.debit_amount) > 0 && Number(l.credit_amount) > 0)) {
    ElMessage.error("同一分录行不能同时填写借方和贷方金额");
    return;
  }
  saving.value = true;
  try {
    await mumarenFinanceCenterApi.createVoucher({
      book_id: bookId.value,
      voucher_no: form.voucher_no,
      voucher_date: form.voucher_date,
      summary: form.summary || null,
      voucher_type: form.voucher_type,
      lines: validLines.value.map((l) => ({
        account_id: l.account_id as number,
        summary: l.summary || form.summary || null,
        debit_amount: Number(l.debit_amount || 0),
        credit_amount: Number(l.credit_amount || 0),
      })),
    });
    ElMessage.success("凭证草稿已创建");
    showCreate.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
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
.done-text { color: #909399; font-size: 13px; }
.dialog-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 12px 0; flex-wrap: wrap; }
.totals { display: flex; align-items: center; gap: 14px; font-size: 13px; color: #4b5563; }
.totals b { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: #111827; }
.totals .danger { color: #dc2626; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
