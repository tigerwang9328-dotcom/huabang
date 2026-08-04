<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">财务报表</p>
        <h2>资产负债表</h2>
        <p>按科目类别(资产/负债/权益)分组汇总期末余额,资产=负债+权益平衡校验展示。</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" :disabled="!bookId" @click="load">查询</el-button>
        <el-button :disabled="!bookId || isHistoricalBook" @click="printReport">打印</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="load">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-alert v-if="isHistoricalBook" type="info" :closable="false" show-icon title="金蝶迁移账簿只读；以下数据按该账簿已过账凭证汇总。" />
    <el-alert v-if="hasPendingHistoricalMapping" type="warning" :closable="false" show-icon :title="mappingWarning" />

    <template v-if="bookId">
      <div class="bs-section">
        <h3 class="bs-title">资产</h3>
        <el-table :data="assetRows" empty-text="暂无资产类科目" stripe size="small">
          <el-table-column prop="account_code" label="科目编码" width="140" />
          <el-table-column prop="account_name" label="科目名称" min-width="200" />
          <el-table-column label="期末借方" align="right">
            <template #default="scope">{{ money(scope.row.closing_debit) }}</template>
          </el-table-column>
          <el-table-column label="期末贷方" align="right">
            <template #default="scope">{{ money(scope.row.closing_credit) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <div class="bs-section">
        <h3 class="bs-title">负债</h3>
        <el-table :data="liabilityRows" empty-text="暂无负债类科目" stripe size="small">
          <el-table-column prop="account_code" label="科目编码" width="140" />
          <el-table-column prop="account_name" label="科目名称" min-width="200" />
          <el-table-column label="期末借方" align="right">
            <template #default="scope">{{ money(scope.row.closing_debit) }}</template>
          </el-table-column>
          <el-table-column label="期末贷方" align="right">
            <template #default="scope">{{ money(scope.row.closing_credit) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <div class="bs-section">
        <h3 class="bs-title">权益</h3>
        <el-table :data="equityRows" empty-text="暂无权益类科目" stripe size="small">
          <el-table-column prop="account_code" label="科目编码" width="140" />
          <el-table-column prop="account_name" label="科目名称" min-width="200" />
          <el-table-column label="期末借方" align="right">
            <template #default="scope">{{ money(scope.row.closing_debit) }}</template>
          </el-table-column>
          <el-table-column label="期末贷方" align="right">
            <template #default="scope">{{ money(scope.row.closing_credit) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="资产合计">{{ money(assetTotal) }}</el-descriptions-item>
        <el-descriptions-item label="负债合计">{{ money(liabilityTotal) }}</el-descriptions-item>
        <el-descriptions-item label="权益合计">{{ money(equityTotal) }}</el-descriptions-item>
        <el-descriptions-item label="平衡校验">
          <el-tag :type="balanced ? 'success' : 'danger'">{{ balanced ? '平衡' : '不平衡' }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </template>

    <el-empty v-else description="请选择独立账簿后查看资产负债表" />
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { computed, onMounted, ref } from "vue";
import { mumarenFinanceCenterApi, type MumarenFinanceBook, type MumarenTrialBalanceRow } from "@/api/mumarenFinanceCenter";

// 余额表行可能携带 account_type(后端若返回),接口类型未声明,这里扩展为可选以兼容分组。
interface TrialRowWithType extends MumarenTrialBalanceRow {
  account_type?: string;
}

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook, isReadonly } = useMumarenFinanceBook();
const rows = ref<TrialRowWithType[]>([]);
const error = ref("");
const loading = ref(false);
const unclassifiedAccountCount = ref(0);
let loadRequestVersion = 0;
const isHistoricalBook = computed(() =>
  isReadonly.value || Boolean(books.value.find((book) => book.id === bookId.value)?.is_readonly),
);
const hasPendingHistoricalMapping = computed(() =>
  isHistoricalBook.value && unclassifiedAccountCount.value > 0,
);
const mappingWarning = computed(() =>
  `该金蝶历史账簿有 ${unclassifiedAccountCount.value} 个科目待会计分类映射；资产负债表不会按科目编码推断分类，0.00 不代表历史业务为零。请以科目余额表与余额快照核对。`,
);

const money = (value?: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
const printReport = () => window.print();

// 当前账按明确分类展示；金蝶历史账簿若来源未提供分类，则不能用科目编码猜测三表映射。
const classify = (row: TrialRowWithType): "asset" | "liability" | "equity" | "other" => {
  if (hasPendingHistoricalMapping.value) return "other";
  const t = row.account_type || "";
  if (t.includes("资产")) return "asset";
  if (t.includes("负债")) return "liability";
  if (t.includes("权益")) return "equity";
  const code = (row.account_code || "").trim();
  const first = code.charAt(0);
  if (first === "1") return "asset";
  if (first === "2") return "liability";
  if (first === "4") return "equity";
  return "other";
};

const assetRows = computed(() => rows.value.filter((r) => classify(r) === "asset"));
const liabilityRows = computed(() => rows.value.filter((r) => classify(r) === "liability"));
const equityRows = computed(() => rows.value.filter((r) => classify(r) === "equity"));

// 资产合计 = Σ(期末借方 - 期末贷方);负债/权益合计 = Σ(期末贷方 - 期末借方)。
const assetTotal = computed(() =>
  assetRows.value.reduce((sum, r) => sum + (Number(r.closing_debit) - Number(r.closing_credit)), 0),
);
const liabilityTotal = computed(() =>
  liabilityRows.value.reduce((sum, r) => sum + (Number(r.closing_credit) - Number(r.closing_debit)), 0),
);
const equityTotal = computed(() =>
  equityRows.value.reduce((sum, r) => sum + (Number(r.closing_credit) - Number(r.closing_debit)), 0),
);
const balanced = computed(() => Math.abs(assetTotal.value - (liabilityTotal.value + equityTotal.value)) < 0.01);

const load = async () => {
  const requestedBookId = bookId.value;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId) {
    rows.value = [];
    unclassifiedAccountCount.value = 0;
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const result = await mumarenFinanceCenterApi.getTrialBalance({ book_id: requestedBookId });
    if (requestVersion !== loadRequestVersion || requestedBookId !== bookId.value) return;
    rows.value = (result.data.data.rows || []) as TrialRowWithType[];
    unclassifiedAccountCount.value = Number(result.data.data.unclassified_account_count || 0);
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value) {
      error.value = "无法加载资产负债表数据。";
      rows.value = [];
      unclassifiedAccountCount.value = 0;
    }
  } finally {
    if (requestVersion === loadRequestVersion) loading.value = false;
  }
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    initializeBook(books.value);
    await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});
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
.bs-section { display: grid; gap: 8px; }
.bs-title { margin: 0; font-size: 15px; color: #172033; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
