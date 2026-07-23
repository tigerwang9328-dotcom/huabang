<template>
  <div class="fc-assets">
    <div class="page-header">
      <h2>固定资产管理</h2>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="资产卡片" name="cards">
        <div class="filter-bar">
          <el-select v-model="selectedBookId" placeholder="选择账套" filterable @change="loadAssets">
            <el-option v-for="b in books" :key="b.id" :label="b.company_name" :value="b.id" />
          </el-select>
          <el-button type="primary" @click="showCreateDialog = true">新建资产</el-button>
        </div>

        <el-table :data="assets" stripe size="small" v-loading="loading">
          <el-table-column prop="asset_code" label="资产编码" width="130" />
          <el-table-column prop="asset_name" label="资产名称" min-width="160" />
          <el-table-column prop="category" label="类别" width="100" />
          <el-table-column prop="acquisition_date" label="购置日期" width="110" />
          <el-table-column prop="in_service_date" label="启用日期" width="110" />
          <el-table-column label="原值" width="130" align="right">
            <template #default="{ row }">{{ money(row.original_cost) }}</template>
          </el-table-column>
          <el-table-column label="残值率" width="80" align="center">
            <template #default="{ row }">{{ pct(row.residual_rate) }}</template>
          </el-table-column>
          <el-table-column prop="useful_life_months" label="使用月限" width="80" align="center" />
          <el-table-column label="月折旧额" width="120" align="right">
            <template #default="{ row }">{{ money(row.monthly_depreciation) }}</template>
          </el-table-column>
          <el-table-column label="累计折旧" width="130" align="right">
            <template #default="{ row }">{{ money(row.accumulated_depreciation) }}</template>
          </el-table-column>
          <el-table-column label="净值" width="130" align="right">
            <template #default="{ row }">{{ money(row.net_book_value) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openDepreciate(row)">计提折旧</el-button>
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
          @change="loadAssets"
          style="margin-top: 16px; justify-content: flex-end;"
        />
      </el-tab-pane>

      <el-tab-pane label="折旧明细" name="depreciations">
        <div class="filter-bar">
          <el-select v-model="selectedBookId" placeholder="选择账套" filterable @change="loadDepreciations">
            <el-option v-for="b in books" :key="b.id" :label="b.company_name" :value="b.id" />
          </el-select>
          <el-input v-model="deprPeriod" placeholder="期间（如 202601）" clearable style="width: 150px;" @change="loadDepreciations" />
        </div>

        <el-table :data="depreciations" stripe size="small" v-loading="deprLoading">
          <el-table-column prop="asset_code" label="资产编码" width="130" />
          <el-table-column prop="asset_name" label="资产名称" min-width="160" />
          <el-table-column prop="period" label="期间" width="110" />
          <el-table-column label="折旧金额" width="130" align="right">
            <template #default="{ row }">{{ money(row.depreciation_amount) }}</template>
          </el-table-column>
          <el-table-column label="累计折旧" width="130" align="right">
            <template #default="{ row }">{{ money(row.accumulated_depreciation) }}</template>
          </el-table-column>
          <el-table-column label="净值" width="130" align="right">
            <template #default="{ row }">{{ money(row.net_book_value) }}</template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-if="deprTotal > 0"
          v-model:current-page="deprPage"
          v-model:page-size="deprPageSize"
          :total="deprTotal"
          :page-sizes="[10, 20, 50]"
          layout="total, prev, pager, next, sizes"
          @change="loadDepreciations"
          style="margin-top: 16px; justify-content: flex-end;"
        />
      </el-tab-pane>
    </el-tabs>

    <!-- 新建资产弹窗 -->
    <el-dialog v-model="showCreateDialog" title="新建资产" width="560px" :close-on-click-modal="false">
      <el-form ref="createFormRef" :model="createForm" label-width="100px">
        <el-form-item label="资产编码" required>
          <el-input v-model="createForm.asset_code" />
        </el-form-item>
        <el-form-item label="资产名称" required>
          <el-input v-model="createForm.asset_name" />
        </el-form-item>
        <el-form-item label="类别" required>
          <el-input v-model="createForm.category" />
        </el-form-item>
        <el-form-item label="购置日期" required>
          <el-date-picker v-model="createForm.acquisition_date" type="date" value-format="YYYY-MM-DD" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="启用日期" required>
          <el-date-picker v-model="createForm.in_service_date" type="date" value-format="YYYY-MM-DD" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="原值" required>
          <el-input-number v-model="createForm.original_cost" :min="0" :precision="2" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="残值率">
          <el-input-number v-model="createForm.residual_rate" :min="0" :max="1" :precision="2" :step="0.01" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="使用月限" required>
          <el-input-number v-model="createForm.useful_life_months" :min="1" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="部门">
          <el-select v-model="createForm.department_aux_id" placeholder="选择辅助核算" filterable clearable style="width: 100%;">
            <el-option v-for="aux in auxItems" :key="aux.id" :label="aux.item_name" :value="aux.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="费用科目">
          <el-select v-model="createForm.expense_account_id" placeholder="选择科目" filterable clearable style="width: 100%;">
            <el-option v-for="acct in accounts" :key="acct.id" :label="`${acct.account_code} ${acct.account_name}`" :value="acct.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>

    <!-- 计提折旧弹窗 -->
    <el-dialog v-model="showDepreciateDialog" title="计提折旧" width="400px" :close-on-click-modal="false">
      <el-form :model="depreciateForm" label-width="80px">
        <el-form-item label="资产">
          <span>{{ depreciateTarget?.asset_name }} ({{ depreciateTarget?.asset_code }})</span>
        </el-form-item>
        <el-form-item label="期间" required>
          <el-input v-model="depreciateForm.period" placeholder="如 202601" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDepreciateDialog = false">取消</el-button>
        <el-button type="primary" :loading="depreciating" @click="handleDepreciate">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { financeCenterApi, type FinBook, type FinFixedAsset, type FinAccount, type FinAuxItem, type DepreciationItem } from "@/api/financeCenter";

const money = (v: number | null | undefined) => v == null ? "--" : v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
const pct = (v: number | null | undefined) => v == null ? "--" : (v * 100).toFixed(0) + "%";

const activeTab = ref("cards");
const selectedBookId = ref<number | null>(null);
const books = ref<FinBook[]>([]);
const accounts = ref<FinAccount[]>([]);
const auxItems = ref<FinAuxItem[]>([]);

// 资产卡片
const assets = ref<FinFixedAsset[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

// 折旧明细
const depreciations = ref<DepreciationItem[]>([]);
const deprLoading = ref(false);
const deprPage = ref(1);
const deprPageSize = ref(20);
const deprTotal = ref(0);
const deprPeriod = ref("");

// 新建
const showCreateDialog = ref(false);
const createFormRef = ref();
const creating = ref(false);
const createForm = ref({
  book_id: 0,
  asset_code: "",
  asset_name: "",
  category: "",
  acquisition_date: "",
  in_service_date: "",
  original_cost: 0,
  residual_rate: 0.05,
  useful_life_months: 60,
  department_aux_id: undefined as number | undefined,
  expense_account_id: undefined as number | undefined,
});

// 计提折旧
const showDepreciateDialog = ref(false);
const depreciateTarget = ref<FinFixedAsset | null>(null);
const depreciating = ref(false);
const depreciateForm = ref({ period: "" });

const loadBooks = async () => {
  try {
    const res = await financeCenterApi.listBooks();
    books.value = res.data.data || [];
    if (books.value.length > 0 && !selectedBookId.value) {
      selectedBookId.value = books.value[0].id;
      loadAssets();
    }
  } catch { /* ignore */ }
};

const loadAuxAndAccounts = async () => {
  if (!selectedBookId.value) return;
  try {
    const [auxRes, acctRes] = await Promise.all([
      financeCenterApi.listAuxItems({ book_id: selectedBookId.value }),
      financeCenterApi.listAccounts({ book_id: selectedBookId.value }),
    ]);
    auxItems.value = auxRes.data.data || [];
    accounts.value = acctRes.data.data || [];
  } catch { /* ignore */ }
};

const loadAssets = async () => {
  if (!selectedBookId.value) return;
  loading.value = true;
  try {
    const res = await financeCenterApi.listFixedAssets({ book_id: selectedBookId.value, page: page.value, page_size: pageSize.value });
    const data = res.data.data;
    assets.value = data?.items || [];
    total.value = data?.total || 0;
  } catch { /* ignore */ }
  loading.value = false;
};

const loadDepreciations = async () => {
  if (!selectedBookId.value) return;
  deprLoading.value = true;
  try {
    const res = await financeCenterApi.listDepreciations({
      book_id: selectedBookId.value,
      period: deprPeriod.value || undefined,
      page: deprPage.value,
      page_size: deprPageSize.value,
    });
    const data = res.data.data;
    depreciations.value = data?.items || [];
    deprTotal.value = data?.total || 0;
  } catch { /* ignore */ }
  deprLoading.value = false;
};

const openDepreciate = (row: FinFixedAsset) => {
  depreciateTarget.value = row;
  depreciateForm.value.period = "";
  showDepreciateDialog.value = true;
};

const handleDepreciate = async () => {
  if (!depreciateTarget.value || !depreciateForm.value.period) {
    ElMessage.warning("请输入期间");
    return;
  }
  depreciating.value = true;
  try {
    await financeCenterApi.calculateDepreciation(depreciateTarget.value.id, depreciateForm.value.period);
    ElMessage.success("计提折旧成功");
    showDepreciateDialog.value = false;
    loadAssets();
  } catch { ElMessage.error("计提折旧失败"); }
  depreciating.value = false;
};

const handleCreate = async () => {
  if (!selectedBookId.value) return;
  creating.value = true;
  try {
    await financeCenterApi.createFixedAsset({
      book_id: selectedBookId.value,
      asset_code: createForm.value.asset_code,
      asset_name: createForm.value.asset_name,
      category: createForm.value.category,
      acquisition_date: createForm.value.acquisition_date,
      in_service_date: createForm.value.in_service_date,
      original_cost: createForm.value.original_cost,
      residual_rate: createForm.value.residual_rate,
      useful_life_months: createForm.value.useful_life_months,
      department_aux_id: createForm.value.department_aux_id,
      expense_account_id: createForm.value.expense_account_id,
    });
    ElMessage.success("资产创建成功");
    showCreateDialog.value = false;
    loadAssets();
  } catch { ElMessage.error("创建失败"); }
  creating.value = false;
};

onMounted(() => {
  loadBooks();
  loadAuxAndAccounts();
});
</script>

<script lang="ts">
export default { name: "FinanceAssets" };
</script>

<style scoped>
.fc-assets { padding: 0; }
.page-header { margin-bottom: 16px; }
.page-header h2 { font-size: 20px; color: #1f2937; margin: 0; }
.filter-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
</style>