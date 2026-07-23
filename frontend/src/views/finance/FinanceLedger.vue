<template>
  <div class="finance-ledger">
    <el-tabs v-model="activeTab" class="ledger-tabs" @tab-change="handleTabChange">
      <el-tab-pane label="总账" name="general" />
      <el-tab-pane label="明细账" name="subsidiary" />
      <el-tab-pane label="试算平衡" name="trial" />
      <el-tab-pane label="科目余额" name="balance" />
      <el-tab-pane label="辅助核算" name="auxiliary" />
    </el-tabs>

    <!-- 总账 -->
    <template v-if="activeTab === 'general'">
      <div class="filter-bar">
        <el-select
          v-model="generalFilters.account_id"
          placeholder="选择科目"
          filterable
          clearable
          style="width: 260px"
          @change="loadGeneralLedger"
        >
          <el-option
            v-for="acc in accountList"
            :key="acc.id"
            :label="`${acc.account_code} ${acc.account_name}`"
            :value="acc.id"
          />
        </el-select>
        <el-select
          v-model="generalFilters.period_start"
          placeholder="起始期间"
          filterable
          clearable
          style="width: 160px"
          @change="loadGeneralLedger"
        >
          <el-option
            v-for="p in periodList"
            :key="p"
            :label="p"
            :value="p"
          />
        </el-select>
        <el-select
          v-model="generalFilters.period_end"
          placeholder="截止期间"
          filterable
          clearable
          style="width: 160px"
          @change="loadGeneralLedger"
        >
          <el-option
            v-for="p in periodList"
            :key="p"
            :label="p"
            :value="p"
          />
        </el-select>
        <el-button :icon="Refresh" circle @click="loadGeneralLedger" />
      </div>

      <el-table
        v-loading="generalLoading"
        :data="generalData"
        stripe
        show-summary
        :summary-method="generalSummary"
      >
        <el-table-column prop="voucher_no" label="凭证号" width="140" />
        <el-table-column prop="voucher_date" label="日期" width="120" />
        <el-table-column prop="summary" label="摘要" min-width="220" show-overflow-tooltip />
        <el-table-column label="借方金额" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.debit_amount) }}
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.credit_amount) }}
          </template>
        </el-table-column>
        <el-table-column label="余额方向" width="100" align="center">
          <template #default="scope">
            <el-tag
              :type="scope.row.balance_direction === 'debit' ? '' : 'warning'"
              effect="plain"
              size="small"
            >
              {{ scope.row.balance_direction === 'debit' ? '借' : '贷' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="余额" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.balance) }}
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 明细账 -->
    <template v-if="activeTab === 'subsidiary'">
      <div class="filter-bar">
        <el-select
          v-model="subFilters.account_id"
          placeholder="选择科目"
          filterable
          clearable
          style="width: 260px"
          @change="loadSubsidiaryLedger"
        >
          <el-option
            v-for="acc in accountList"
            :key="acc.id"
            :label="`${acc.account_code} ${acc.account_name}`"
            :value="acc.id"
          />
        </el-select>
        <el-select
          v-model="subFilters.period_start"
          placeholder="起始期间"
          filterable
          clearable
          style="width: 160px"
          @change="loadSubsidiaryLedger"
        >
          <el-option
            v-for="p in periodList"
            :key="p"
            :label="p"
            :value="p"
          />
        </el-select>
        <el-select
          v-model="subFilters.period_end"
          placeholder="截止期间"
          filterable
          clearable
          style="width: 160px"
          @change="loadSubsidiaryLedger"
        >
          <el-option
            v-for="p in periodList"
            :key="p"
            :label="p"
            :value="p"
          />
        </el-select>
        <el-button :icon="Refresh" circle @click="loadSubsidiaryLedger" />
      </div>

      <el-table
        v-loading="subLoading"
        :data="subData"
        stripe
      >
        <el-table-column prop="voucher_date" label="日期" width="120" />
        <el-table-column prop="voucher_no" label="凭证号" width="140" />
        <el-table-column prop="summary" label="摘要" min-width="220" show-overflow-tooltip />
        <el-table-column label="借方金额" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.debit_amount) }}
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.credit_amount) }}
          </template>
        </el-table-column>
        <el-table-column label="余额方向" width="100" align="center">
          <template #default="scope">
            <el-tag
              :type="scope.row.balance_direction === 'debit' ? '' : 'warning'"
              effect="plain"
              size="small"
            >
              {{ scope.row.balance_direction === 'debit' ? '借' : '贷' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="余额" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.balance) }}
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="subTotal > 0"
        v-model:current-page="subPagination.page"
        :page-size="subPagination.page_size"
        :total="subTotal"
        layout="total, prev, pager, next"
        class="ledger-pagination"
        @current-change="loadSubsidiaryLedger"
      />
    </template>

    <!-- 试算平衡 -->
    <template v-if="activeTab === 'trial'">
      <div class="filter-bar">
        <el-select
          v-model="trialFilters.book_id"
          placeholder="选择账套"
          filterable
          clearable
          style="width: 200px"
          @change="loadTrialBalance"
        >
          <el-option
            v-for="book in bookList"
            :key="book.id"
            :label="book.company_name"
            :value="book.id"
          />
        </el-select>
        <el-select
          v-model="trialFilters.period"
          placeholder="选择期间"
          filterable
          clearable
          style="width: 160px"
          @change="loadTrialBalance"
        >
          <el-option
            v-for="p in periodList"
            :key="p"
            :label="p"
            :value="p"
          />
        </el-select>
        <el-button :icon="Refresh" circle @click="loadTrialBalance" />
      </div>

      <el-table
        v-loading="trialLoading"
        :data="trialData"
        stripe
        show-summary
        :summary-method="trialSummary"
        max-height="calc(100vh - 280px)"
      >
        <el-table-column prop="account_code" label="科目编码" width="140" fixed />
        <el-table-column prop="account_name" label="科目名称" min-width="200" fixed />
        <el-table-column label="期初借方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.opening_debit) }}
          </template>
        </el-table-column>
        <el-table-column label="期初贷方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.opening_credit) }}
          </template>
        </el-table-column>
        <el-table-column label="本期借方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.period_debit) }}
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.period_credit) }}
          </template>
        </el-table-column>
        <el-table-column label="期末借方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.closing_debit) }}
          </template>
        </el-table-column>
        <el-table-column label="期末贷方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.closing_credit) }}
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 科目余额 -->
    <template v-if="activeTab === 'balance'">
      <div class="filter-bar">
        <el-select
          v-model="balanceFilters.book_id"
          placeholder="选择账套"
          filterable
          clearable
          style="width: 200px"
          @change="loadBalance"
        >
          <el-option
            v-for="book in bookList"
            :key="book.id"
            :label="book.company_name"
            :value="book.id"
          />
        </el-select>
        <el-select
          v-model="balanceFilters.period"
          placeholder="选择期间"
          filterable
          clearable
          style="width: 160px"
          @change="loadBalance"
        >
          <el-option
            v-for="p in periodList"
            :key="p"
            :label="p"
            :value="p"
          />
        </el-select>
        <el-select
          v-model="balanceFilters.account_id"
          placeholder="科目筛选"
          filterable
          clearable
          style="width: 260px"
          @change="loadBalance"
        >
          <el-option
            v-for="acc in accountList"
            :key="acc.id"
            :label="`${acc.account_code} ${acc.account_name}`"
            :value="acc.id"
          />
        </el-select>
        <el-button :icon="Refresh" circle @click="loadBalance" />
      </div>

      <el-table
        v-loading="balanceLoading"
        :data="balanceData"
        stripe
        show-summary
        :summary-method="balanceSummary"
        max-height="calc(100vh - 280px)"
      >
        <el-table-column prop="account_code" label="科目编码" width="140" fixed />
        <el-table-column prop="account_name" label="科目名称" min-width="200" fixed />
        <el-table-column label="期初借方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.opening_debit) }}
          </template>
        </el-table-column>
        <el-table-column label="期初贷方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.opening_credit) }}
          </template>
        </el-table-column>
        <el-table-column label="本期借方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.period_debit) }}
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.period_credit) }}
          </template>
        </el-table-column>
        <el-table-column label="期末借方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.closing_debit) }}
          </template>
        </el-table-column>
        <el-table-column label="期末贷方" width="150" align="right">
          <template #default="scope">
            {{ money(scope.row.closing_credit) }}
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 辅助核算 -->
    <template v-if="activeTab === 'auxiliary'">
      <div class="filter-bar">
        <el-select
          v-model="auxFilters.category_id"
          placeholder="选择核算类别"
          filterable
          clearable
          style="width: 220px"
          @change="loadAuxItems"
        >
          <el-option
            v-for="cat in auxCategoryList"
            :key="cat.id"
            :label="cat.category_name"
            :value="cat.id"
          />
        </el-select>
        <el-input
          v-model="auxFilters.keyword"
          placeholder="搜索项目名称"
          clearable
          style="width: 220px"
          @clear="loadAuxItems"
          @keyup.enter="loadAuxItems"
        >
          <template #append>
            <el-button :icon="Search" @click="loadAuxItems" />
          </template>
        </el-input>
        <el-button :icon="Refresh" circle @click="loadAuxItems" />
      </div>

      <el-table
        v-loading="auxLoading"
        :data="auxData"
        stripe
      >
        <el-table-column prop="item_code" label="项目编码" width="140" />
        <el-table-column prop="item_name" label="项目名称" min-width="200" />
        <el-table-column prop="category_name" label="核算类别" width="150" />
        <el-table-column label="启用状态" width="100" align="center">
          <template #default="scope">
            <el-tag
              :type="scope.row.is_active ? 'success' : 'info'"
              effect="plain"
              size="small"
            >
              {{ scope.row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
      </el-table>

      <el-pagination
        v-if="auxTotal > 0"
        v-model:current-page="auxPagination.page"
        :page-size="auxPagination.page_size"
        :total="auxTotal"
        layout="total, prev, pager, next"
        class="ledger-pagination"
        @current-change="loadAuxItems"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Refresh, Search } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { financeCenterApi } from "@/api/financeCenter";

defineComponent({ name: "FinanceLedger" });

// ==================== 类型 ====================
interface BookOption {
  id: number;
  company_name: string;
}

interface AccountOption {
  id: number;
  account_code: string;
  account_name: string;
}

interface GeneralLedgerItem {
  voucher_no: string;
  voucher_date: string;
  summary: string;
  debit_amount: number;
  credit_amount: number;
  balance_direction: string;
  balance: number;
}

interface SubsidiaryLedgerItem {
  voucher_date: string;
  voucher_no: string;
  summary: string;
  debit_amount: number;
  credit_amount: number;
  balance_direction: string;
  balance: number;
}

interface BalanceRow {
  account_code: string;
  account_name: string;
  opening_debit: number;
  opening_credit: number;
  period_debit: number;
  period_credit: number;
  closing_debit: number;
  closing_credit: number;
}

interface AuxCategory {
  id: number;
  category_name: string;
}

interface AuxItem {
  id: number;
  item_code: string;
  item_name: string;
  category_name: string;
  is_active: boolean;
  remark: string;
}

// ==================== 数据字典 ====================
const bookList = ref<BookOption[]>([]);
const periodList = ref<string[]>([]);
const accountList = ref<AccountOption[]>([]);
const auxCategoryList = ref<AuxCategory[]>([]);

// ==================== Tab ====================
const activeTab = ref("general");

// ==================== 工具函数 ====================
const money = (value: number | null | undefined) =>
  value == null ? "-" : new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);

// ==================== 总账 ====================
const generalLoading = ref(false);
const generalData = ref<GeneralLedgerItem[]>([]);

const generalFilters = reactive({
  account_id: null as number | null,
  period_start: "",
  period_end: "",
});

const loadGeneralLedger = async () => {
  generalLoading.value = true;
  try {
    const res = await financeCenterApi.generalLedger({
      book_id: trialFilters.book_id,
      account_id: generalFilters.account_id,
      period_start: generalFilters.period_start || undefined,
      period_end: generalFilters.period_end || undefined,
    });
    generalData.value = (res as any).data?.data || (res as any).data || [];
  } catch {
    ElMessage.error("总账数据加载失败");
  } finally {
    generalLoading.value = false;
  }
};

const generalSummary = (param: { columns: any[]; data: GeneralLedgerItem[] }) => {
  const { columns, data } = param;
  const sums: string[] = [];
  columns.forEach((col, index) => {
    if (index === 0) { sums[index] = "合计"; return; }
    if (col.property === "debit_amount") {
      sums[index] = money(data.reduce((s, r) => s + (r.debit_amount || 0), 0));
    } else if (col.property === "credit_amount") {
      sums[index] = money(data.reduce((s, r) => s + (r.credit_amount || 0), 0));
    } else {
      sums[index] = "";
    }
  });
  return sums;
};

// ==================== 明细账 ====================
const subLoading = ref(false);
const subData = ref<SubsidiaryLedgerItem[]>([]);
const subTotal = ref(0);
const subPagination = reactive({ page: 1, page_size: 20 });

const subFilters = reactive({
  account_id: null as number | null,
  period_start: "",
  period_end: "",
});

const loadSubsidiaryLedger = async () => {
  subLoading.value = true;
  try {
    const res = await financeCenterApi.subsidiaryLedger({
      book_id: trialFilters.book_id,
      account_id: subFilters.account_id,
      period_start: subFilters.period_start || undefined,
      period_end: subFilters.period_end || undefined,
      page: subPagination.page,
      page_size: subPagination.page_size,
    });
    const data = (res as any).data?.data || (res as any).data;
    subData.value = data.items || [];
    subTotal.value = data.total || 0;
  } catch {
    ElMessage.error("明细账数据加载失败");
  } finally {
    subLoading.value = false;
  }
};

// ==================== 试算平衡 ====================
const trialLoading = ref(false);
const trialData = ref<BalanceRow[]>([]);

const trialFilters = reactive({
  book_id: null as number | null,
  period: "",
});

const loadTrialBalance = async () => {
  trialLoading.value = true;
  try {
    const res = await financeCenterApi.trialBalance({
      book_id: trialFilters.book_id,
      period: trialFilters.period || undefined,
    });
    trialData.value = (res as any).data?.data || (res as any).data || [];
  } catch {
    ElMessage.error("试算平衡数据加载失败");
  } finally {
    trialLoading.value = false;
  }
};

const trialSummary = (param: { columns: any[]; data: BalanceRow[] }) => {
  const { columns, data } = param;
  const sums: string[] = [];
  columns.forEach((col, index) => {
    if (index === 0) { sums[index] = "合计"; return; }
    const prop = col.property as keyof BalanceRow;
    if (typeof data[0]?.[prop] === "number") {
      sums[index] = money(data.reduce((s, r) => s + ((r[prop] as number) || 0), 0));
    } else {
      sums[index] = "";
    }
  });
  return sums;
};

// ==================== 科目余额 ====================
const balanceLoading = ref(false);
const balanceData = ref<BalanceRow[]>([]);

const balanceFilters = reactive({
  book_id: null as number | null,
  period: "",
  account_id: null as number | null,
});

const loadBalance = async () => {
  balanceLoading.value = true;
  try {
    const res = await financeCenterApi.listLedgerBalances({
      book_id: balanceFilters.book_id,
      period: balanceFilters.period || undefined,
      account_id: balanceFilters.account_id || undefined,
    });
    balanceData.value = (res as any).data?.data || (res as any).data || [];
  } catch {
    ElMessage.error("科目余额数据加载失败");
  } finally {
    balanceLoading.value = false;
  }
};

const balanceSummary = (param: { columns: any[]; data: BalanceRow[] }) => {
  const { columns, data } = param;
  const sums: string[] = [];
  columns.forEach((col, index) => {
    if (index === 0) { sums[index] = "合计"; return; }
    const prop = col.property as keyof BalanceRow;
    if (typeof data[0]?.[prop] === "number") {
      sums[index] = money(data.reduce((s, r) => s + ((r[prop] as number) || 0), 0));
    } else {
      sums[index] = "";
    }
  });
  return sums;
};

// ==================== 辅助核算 ====================
const auxLoading = ref(false);
const auxData = ref<AuxItem[]>([]);
const auxTotal = ref(0);
const auxPagination = reactive({ page: 1, page_size: 20 });

const auxFilters = reactive({
  category_id: null as number | null,
  keyword: "",
});

const loadAuxCategories = async () => {
  try {
    const res = await financeCenterApi.listAuxCategories({ book_id: trialFilters.book_id });
    auxCategoryList.value = (res as any).data?.data || (res as any).data || [];
  } catch { /* 静默 */ }
};

const loadAuxItems = async () => {
  auxLoading.value = true;
  try {
    const res = await financeCenterApi.listAuxItems({
      book_id: trialFilters.book_id,
      category_id: auxFilters.category_id || undefined,
      keyword: auxFilters.keyword || undefined,
      page: auxPagination.page,
      page_size: auxPagination.page_size,
    });
    const data = (res as any).data?.data || (res as any).data;
    auxData.value = data.items || [];
    auxTotal.value = data.total || 0;
  } catch {
    ElMessage.error("辅助核算数据加载失败");
  } finally {
    auxLoading.value = false;
  }
};

// ==================== Tab 切换 ====================
const handleTabChange = (tab: string) => {
  if (tab === "general" && generalData.value.length === 0) loadGeneralLedger();
  if (tab === "subsidiary" && subData.value.length === 0) loadSubsidiaryLedger();
  if (tab === "trial" && trialData.value.length === 0) loadTrialBalance();
  if (tab === "balance" && balanceData.value.length === 0) loadBalance();
  if (tab === "auxiliary" && auxData.value.length === 0) loadAuxItems();
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
    const res = await financeCenterApi.listPeriods({ book_id: bookList.value[0]?.id });
    periodList.value = (res as any).data?.data || (res as any).data || [];
  } catch { /* 静默 */ }
};

const loadAccountList = async () => {
  try {
    const res = await financeCenterApi.listAccounts({ book_id: bookList.value[0]?.id });
    accountList.value = (res as any).data?.data || (res as any).data || [];
  } catch { /* 静默 */ }
};

onMounted(async () => {
  await loadBookList();
  // 设置默认账套后加载期间和科目
  if (bookList.value.length > 0) {
    // 设置默认账套
    trialFilters.book_id = bookList.value[0].id;
    balanceFilters.book_id = bookList.value[0].id;
  }
  await Promise.all([loadPeriodList(), loadAccountList(), loadAuxCategories()]);
  await loadGeneralLedger();
});
</script>

<style scoped>
.finance-ledger {
  min-width: 0;
}

.ledger-tabs {
  margin-bottom: 16px;
}

.ledger-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.ledger-pagination {
  justify-content: flex-end;
  margin-top: 16px;
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
}
</style>