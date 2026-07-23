<template>
  <div class="finance-vouchers">
    <el-tabs v-model="activeTab" class="voucher-tabs">
      <el-tab-pane label="凭证列表" name="list" />
      <el-tab-pane label="新建凭证" name="create" />
      <el-tab-pane label="待审核" name="pending" />
      <el-tab-pane label="已过账" name="posted" />
    </el-tabs>

    <!-- 凭证列表 / 待审核 / 已过账 -->
    <template v-if="activeTab !== 'create'">
      <div class="filter-bar">
        <el-select
          v-model="filters.book_id"
          placeholder="选择账套"
          filterable
          clearable
          style="width: 200px"
          @change="handleFilterChange"
        >
          <el-option
            v-for="book in bookList"
            :key="book.id"
            :label="book.company_name"
            :value="book.id"
          />
        </el-select>
        <el-select
          v-model="filters.period"
          placeholder="选择期间"
          filterable
          clearable
          style="width: 160px"
          @change="handleFilterChange"
        >
          <el-option
            v-for="p in periodList"
            :key="p"
            :label="p"
            :value="p"
          />
        </el-select>
        <el-select
          v-model="filters.status"
          placeholder="状态筛选"
          clearable
          style="width: 140px"
          @change="handleFilterChange"
        >
          <el-option label="草稿" value="draft" />
          <el-option label="已审核" value="audited" />
          <el-option label="已过账" value="posted" />
          <el-option label="已冲销" value="reversed" />
        </el-select>
        <el-input
          v-model="filters.keyword"
          placeholder="搜索凭证号、摘要"
          clearable
          style="width: 240px"
          @clear="handleFilterChange"
          @keyup.enter="handleFilterChange"
        >
          <template #append>
            <el-button :icon="Search" @click="handleFilterChange" />
          </template>
        </el-input>
        <el-button :icon="Refresh" circle @click="loadVoucherList" />
      </div>

      <el-table
        v-loading="loading"
        :data="voucherList"
        stripe
        class="voucher-table"
      >
        <el-table-column prop="voucher_no" label="凭证号" width="140" />
        <el-table-column prop="voucher_date" label="日期" width="120" />
        <el-table-column prop="period" label="期间" width="100" />
        <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
        <el-table-column label="借方合计" width="140" align="right">
          <template #default="scope">
            {{ money(scope.row.total_debit) }}
          </template>
        </el-table-column>
        <el-table-column label="贷方合计" width="140" align="right">
          <template #default="scope">
            {{ money(scope.row.total_credit) }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="scope">
            <el-tag
              :type="statusTagType(scope.row.status)"
              effect="plain"
              size="small"
            >
              {{ statusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="制单人" width="120" />
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="scope">
            <div class="action-btns">
              <el-button link type="primary" size="small" @click="openVoucherDetail(scope.row)">
                查看
              </el-button>
              <el-popconfirm
                v-if="scope.row.status === 'draft' && hasWritePerm"
                title="确认审核该凭证？"
                @confirm="handleAudit(scope.row)"
              >
                <template #reference>
                  <el-button link type="warning" size="small">审核</el-button>
                </template>
              </el-popconfirm>
              <el-popconfirm
                v-if="(scope.row.status === 'draft' || scope.row.status === 'audited') && hasPostPerm"
                title="确认过账该凭证？"
                @confirm="handlePost(scope.row)"
              >
                <template #reference>
                  <el-button link type="success" size="small">过账</el-button>
                </template>
              </el-popconfirm>
              <el-popconfirm
                v-if="scope.row.status === 'posted' && hasPostPerm"
                title="确认反过账该凭证？"
                @confirm="handleUnpost(scope.row)"
              >
                <template #reference>
                  <el-button link type="warning" size="small">反过账</el-button>
                </template>
              </el-popconfirm>
              <el-popconfirm
                v-if="scope.row.status === 'posted' && hasWritePerm"
                title="确认冲销该凭证？"
                @confirm="handleReverse(scope.row)"
              >
                <template #reference>
                  <el-button link type="danger" size="small">冲销</el-button>
                </template>
              </el-popconfirm>
              <el-popconfirm
                v-if="scope.row.status === 'draft' && hasWritePerm"
                title="确认删除该凭证？"
                @confirm="handleDelete(scope.row)"
              >
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="total > 0"
        v-model:current-page="pagination.page"
        :page-size="pagination.page_size"
        :total="total"
        layout="total, prev, pager, next"
        class="voucher-pagination"
        @current-change="loadVoucherList"
      />
    </template>

    <!-- 新建凭证 -->
    <template v-else>
      <div class="create-form">
        <el-form
          ref="createFormRef"
          :model="createForm"
          :rules="createRules"
          label-width="100px"
          class="voucher-form"
        >
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="账套" prop="book_id">
                <el-select
                  v-model="createForm.book_id"
                  placeholder="选择账套"
                  filterable
                  style="width: 100%"
                >
                  <el-option
                    v-for="book in bookList"
                    :key="book.id"
                    :label="book.company_name"
                    :value="book.id"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="期间" prop="period">
                <el-select
                  v-model="createForm.period"
                  placeholder="选择期间"
                  filterable
                  style="width: 100%"
                >
                  <el-option
                    v-for="p in periodList"
                    :key="p"
                    :label="p"
                    :value="p"
                  />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="凭证号" prop="voucher_no">
                <el-input v-model="createForm.voucher_no" placeholder="自动或手动" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="日期" prop="voucher_date">
                <el-date-picker
                  v-model="createForm.voucher_date"
                  type="date"
                  placeholder="选择日期"
                  style="width: 100%"
                  value-format="YYYY-MM-DD"
                />
              </el-form-item>
            </el-col>
            <el-col :span="16">
              <el-form-item label="摘要" prop="summary">
                <el-input v-model="createForm.summary" placeholder="凭证摘要" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>

        <div class="entries-section">
          <div class="entries-header">
            <span class="entries-title">分录明细</span>
            <el-button type="primary" size="small" :icon="Plus" @click="addEntry">
              添加分录
            </el-button>
          </div>

          <el-table :data="createForm.entries" stripe class="entries-table">
            <el-table-column label="科目" min-width="200">
              <template #default="scope">
                <el-select
                  v-model="scope.row.account_id"
                  placeholder="选择会计科目"
                  filterable
                  style="width: 100%"
                >
                  <el-option
                    v-for="acc in accountList"
                    :key="acc.id"
                    :label="`${acc.account_code} ${acc.account_name}`"
                    :value="acc.id"
                  />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="摘要" min-width="200">
              <template #default="scope">
                <el-input v-model="scope.row.summary" placeholder="分录摘要" />
              </template>
            </el-table-column>
            <el-table-column label="借方金额" width="160" align="right">
              <template #default="scope">
                <el-input-number
                  v-model="scope.row.debit_amount"
                  :min="0"
                  :precision="2"
                  :controls="false"
                  style="width: 100%"
                  placeholder="0.00"
                />
              </template>
            </el-table-column>
            <el-table-column label="贷方金额" width="160" align="right">
              <template #default="scope">
                <el-input-number
                  v-model="scope.row.credit_amount"
                  :min="0"
                  :precision="2"
                  :controls="false"
                  style="width: 100%"
                  placeholder="0.00"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center">
              <template #default="scope">
                <el-button
                  link
                  type="danger"
                  size="small"
                  :icon="Delete"
                  :disabled="createForm.entries.length <= 1"
                  @click="removeEntry(scope.$index)"
                />
              </template>
            </el-table-column>
          </el-table>

          <div class="balance-check">
            <span>借方合计：<strong>{{ money(totalDebit) }}</strong></span>
            <span>贷方合计：<strong>{{ money(totalCredit) }}</strong></span>
            <el-tag
              :type="balanceCheck.type"
              effect="plain"
              size="small"
            >
              {{ balanceCheck.label }}
            </el-tag>
          </div>
        </div>

        <el-form ref="reasonFormRef" :model="reasonForm" :rules="reasonRules" label-width="100px" class="reason-form">
          <el-form-item label="提交原因" prop="reason">
            <el-input
              v-model="reasonForm.reason"
              type="textarea"
              :rows="2"
              placeholder="请输入提交原因"
            />
          </el-form-item>
        </el-form>

        <div class="create-actions">
          <el-button @click="activeTab = 'list'">取消</el-button>
          <el-button type="primary" :disabled="!balanceCheck.isBalanced" @click="submitVoucher">
            提交凭证
          </el-button>
        </div>
      </div>
    </template>

    <!-- 操作原因弹窗 -->
    <el-dialog
      v-model="reasonDialog.visible"
      title="操作原因"
      width="460px"
      :close-on-click-modal="false"
    >
      <el-form ref="reasonDialogFormRef" :model="reasonDialog" :rules="reasonRules">
        <el-form-item label="操作原因" prop="reason">
          <el-input
            v-model="reasonDialog.reason"
            type="textarea"
            :rows="3"
            placeholder="请输入操作原因"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reasonDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="reasonDialog.loading" @click="confirmReasonAction">
          确认
        </el-button>
      </template>
    </el-dialog>

    <!-- 凭证详情抽屉 -->
    <el-drawer
      v-model="detailDrawer.visible"
      title="凭证详情"
      size="760px"
    >
      <template v-if="detailDrawer.voucher">
        <div class="voucher-detail-meta">
          <div class="meta-row">
            <span class="meta-label">凭证号</span>
            <strong>{{ detailDrawer.voucher.voucher_no }}</strong>
          </div>
          <div class="meta-row">
            <span class="meta-label">日期</span>
            <span>{{ detailDrawer.voucher.voucher_date }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">期间</span>
            <span>{{ detailDrawer.voucher.period }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">状态</span>
            <el-tag
              :type="statusTagType(detailDrawer.voucher.status)"
              effect="plain"
              size="small"
            >
              {{ statusLabel(detailDrawer.voucher.status) }}
            </el-tag>
          </div>
          <div class="meta-row">
            <span class="meta-label">制单人</span>
            <span>{{ detailDrawer.voucher.created_by }}</span>
          </div>
        </div>

        <el-table :data="detailDrawer.voucher.entries" stripe class="detail-table">
          <el-table-column label="会计科目" min-width="220">
            <template #default="scope">
              {{ scope.row.account_code }} {{ scope.row.account_name }}
            </template>
          </el-table-column>
          <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
          <el-table-column label="借方金额" width="140" align="right">
            <template #default="scope">
              {{ money(scope.row.debit_amount) }}
            </template>
          </el-table-column>
          <el-table-column label="贷方金额" width="140" align="right">
            <template #default="scope">
              {{ money(scope.row.credit_amount) }}
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Delete, Plus, Refresh, Search } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { financeCenterApi } from "@/api/financeCenter";

defineComponent({ name: "FinanceVouchers" });

// ==================== 权限 ====================
const hasWritePerm = ref(true);
const hasPostPerm = ref(true);

// ==================== 数据字典 ====================
interface BookOption {
  id: number;
  book_name: string;
  account_set_code: string;
}

interface AccountOption {
  id: number;
  account_code: string;
  account_name: string;
}

interface VoucherEntry {
  id?: number;
  account_id: number | null;
  account_code?: string;
  account_name?: string;
  summary: string;
  debit_amount: number;
  credit_amount: number;
}

interface VoucherItem {
  id: number;
  voucher_no: string;
  voucher_date: string;
  period: string;
  summary: string;
  status: string;
  total_debit: number;
  total_credit: number;
  created_by: string;
  entries?: VoucherEntry[];
}

const bookList = ref<BookOption[]>([]);
const periodList = ref<string[]>([]);
const accountList = ref<AccountOption[]>([]);

// ==================== Tab ====================
const activeTab = ref("list");

// ==================== 筛选 ====================
const filters = reactive({
  book_id: null as number | null,
  period: "",
  status: "",
  keyword: "",
});

// ==================== 凭证列表 ====================
const loading = ref(false);
const voucherList = ref<VoucherItem[]>([]);
const total = ref(0);
const pagination = reactive({ page: 1, page_size: 20 });

const money = (value: number | null | undefined) =>
  value == null ? "-" : new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);

const statusLabel = (status: string) =>
  ({ draft: "草稿", audited: "已审核", posted: "已过账", reversed: "已冲销" }[status] || status);

const statusTagType = (status: string): "info" | "warning" | "success" | "danger" | "" =>
  ({ draft: "info", audited: "warning", posted: "success", reversed: "danger" }[status] as "info" | "warning" | "success" | "danger" | "") || "";

const buildListParams = () => {
  const params: Record<string, unknown> = {
    page: pagination.page,
    page_size: pagination.page_size,
  };
  if (filters.book_id) params.book_id = filters.book_id;
  if (filters.period) params.period = filters.period;
  if (filters.keyword) params.keyword = filters.keyword;

  if (activeTab.value === "pending") {
    params.status = "audited";
  } else if (activeTab.value === "posted") {
    params.status = "posted";
  } else if (filters.status) {
    params.status = filters.status;
  }
  return params;
};

const loadVoucherList = async () => {
  loading.value = true;
  try {
    const res = await financeCenterApi.listVouchers(buildListParams());
    const data = (res as any).data?.data || (res as any).data;
    voucherList.value = data.items || [];
    total.value = data.total || 0;
  } catch {
    ElMessage.error("凭证列表加载失败");
  } finally {
    loading.value = false;
  }
};

const handleFilterChange = () => {
  pagination.page = 1;
  loadVoucherList();
};

// ==================== 凭证详情 ====================
const detailDrawer = reactive({
  visible: false,
  voucher: null as VoucherItem | null,
});

const openVoucherDetail = async (row: VoucherItem) => {
  try {
    const res = await financeCenterApi.getVoucher(row.id);
    const data = (res as any).data?.data || (res as any).data;
    detailDrawer.voucher = data;
    detailDrawer.visible = true;
  } catch {
    ElMessage.error("凭证详情加载失败");
  }
};

// ==================== 操作原因弹窗 ====================
const reasonDialog = reactive({
  visible: false,
  reason: "",
  loading: false,
  action: null as (() => Promise<void>) | null,
});
const reasonDialogFormRef = ref<FormInstance>();
const reasonRules: FormRules = {
  reason: [{ required: true, message: "请输入操作原因", trigger: "blur" }],
};

const openReasonDialog = (action: () => Promise<void>) => {
  reasonDialog.reason = "";
  reasonDialog.action = action;
  reasonDialog.visible = true;
};

const confirmReasonAction = async () => {
  const valid = await reasonDialogFormRef.value?.validate().catch(() => false);
  if (!valid) return;
  reasonDialog.loading = true;
  try {
    await reasonDialog.action!();
    reasonDialog.visible = false;
    ElMessage.success("操作成功");
    loadVoucherList();
  } catch {
    ElMessage.error("操作失败");
  } finally {
    reasonDialog.loading = false;
  }
};

// ==================== 凭证操作 ====================
const handleAudit = (row: VoucherItem) => {
  openReasonDialog(async () => {
    await financeCenterApi.auditVoucher(row.id, reasonDialog.reason);
  });
};

const handlePost = (row: VoucherItem) => {
  openReasonDialog(async () => {
    await financeCenterApi.postVoucher(row.id, reasonDialog.reason);
  });
};

const handleUnpost = (row: VoucherItem) => {
  openReasonDialog(async () => {
    await financeCenterApi.unpostVoucher(row.id, reasonDialog.reason);
  });
};

const handleReverse = (row: VoucherItem) => {
  openReasonDialog(async () => {
    await financeCenterApi.reverseVoucher(row.id, { voucher_no: "", reason: reasonDialog.reason });
  });
};

const handleDelete = (row: VoucherItem) => {
  openReasonDialog(async () => {
    await financeCenterApi.deleteVoucher(row.id, reasonDialog.reason);
  });
};

// ==================== 新建凭证 ====================
const createFormRef = ref<FormInstance>();
const reasonFormRef = ref<FormInstance>();

const createForm = reactive({
  book_id: null as number | null,
  period: "",
  voucher_no: "",
  voucher_date: "",
  summary: "",
  entries: [
    { account_id: null, summary: "", debit_amount: 0, credit_amount: 0 },
  ] as VoucherEntry[],
});

const reasonForm = reactive({ reason: "" });

const createRules: FormRules = {
  book_id: [{ required: true, message: "请选择账套", trigger: "change" }],
  period: [{ required: true, message: "请选择期间", trigger: "change" }],
  voucher_date: [{ required: true, message: "请选择日期", trigger: "change" }],
};

const totalDebit = computed(() =>
  createForm.entries.reduce((sum, e) => sum + (e.debit_amount || 0), 0)
);

const totalCredit = computed(() =>
  createForm.entries.reduce((sum, e) => sum + (e.credit_amount || 0), 0)
);

const balanceCheck = computed(() => {
  const diff = Math.abs(totalDebit.value - totalCredit.value);
  if (totalDebit.value === 0 && totalCredit.value === 0) {
    return { isBalanced: false, type: "info" as const, label: "请输入金额" };
  }
  if (diff < 0.01) {
    return { isBalanced: true, type: "success" as const, label: "借贷平衡" };
  }
  return { isBalanced: false, type: "danger" as const, label: `借贷不平，差额 ${money(diff)}` };
});

const addEntry = () => {
  createForm.entries.push({ account_id: null, summary: "", debit_amount: 0, credit_amount: 0 });
};

const removeEntry = (index: number) => {
  if (createForm.entries.length > 1) {
    createForm.entries.splice(index, 1);
  }
};

const submitVoucher = async () => {
  const valid = await createFormRef.value?.validate().catch(() => false);
  if (!valid) return;
  const reasonValid = await reasonFormRef.value?.validate().catch(() => false);
  if (!reasonValid) return;

  if (!balanceCheck.value.isBalanced) {
    ElMessage.warning("借贷不平衡，请调整分录金额");
    return;
  }

  try {
    await financeCenterApi.createVoucher({
      book_id: createForm.book_id!,
      period: createForm.period,
      voucher_no: createForm.voucher_no,
      voucher_date: createForm.voucher_date,
      reason: reasonForm.reason,
      entries: createForm.entries.map((e) => ({
        account_id: e.account_id!,
        summary: e.summary,
        debit_amount: e.debit_amount,
        credit_amount: e.credit_amount,
      })),
    });
    ElMessage.success("凭证创建成功");
    activeTab.value = "list";
    loadVoucherList();
  } catch {
    ElMessage.error("凭证创建失败");
  }
};

// ==================== 初始化 ====================
const loadBookList = async () => {
  try {
    const res = await financeCenterApi.listBooks();
    bookList.value = (res as any).data?.data || (res as any).data || [];
  } catch { /* 静默 */ }
};

const loadPeriodList = async () => {
  try {
    const res = await financeCenterApi.listPeriods({ book_id: filters.book_id });
    periodList.value = (res as any).data?.data || (res as any).data || [];
  } catch { /* 静默 */ }
};

const loadAccountList = async () => {
  try {
    const res = await financeCenterApi.listAccounts({ book_id: filters.book_id });
    accountList.value = (res as any).data?.data || (res as any).data || [];
  } catch { /* 静默 */ }
};

onMounted(async () => {
  await loadBookList();
  // 设置默认账套后加载期间和科目
  if (bookList.value.length > 0 && !filters.book_id) {
    filters.book_id = bookList.value[0].id;
  }
  await Promise.all([loadPeriodList(), loadAccountList()]);
  await loadVoucherList();
});
</script>

<style scoped>
.finance-vouchers {
  min-width: 0;
}

.voucher-tabs {
  margin-bottom: 16px;
}

.voucher-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.voucher-table {
  margin-bottom: 16px;
}

.voucher-pagination {
  justify-content: flex-end;
}

.action-btns {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
}

/* 新建凭证 */
.create-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.voucher-form {
  background: #fff;
  padding: 20px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.entries-section {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}

.entries-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.entries-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}

.entries-table {
  margin-bottom: 12px;
}

.balance-check {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 10px 0;
  font-size: 14px;
  color: #374151;
}

.balance-check strong {
  font-size: 15px;
  color: #1f2937;
  margin-left: 4px;
}

.reason-form {
  background: #fff;
  padding: 16px 20px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.create-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 8px;
}

/* 凭证详情 */
.voucher-detail-meta {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 20px;
  padding: 16px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.meta-label {
  color: #64748b;
  font-size: 13px;
  min-width: 60px;
}

.detail-table {
  margin-top: 8px;
}

@media (max-width: 760px) {
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-bar .el-select,
  .filter-bar .el-input {
    width: 100% !important;
  }

  .voucher-detail-meta {
    grid-template-columns: 1fr;
  }
}
</style>