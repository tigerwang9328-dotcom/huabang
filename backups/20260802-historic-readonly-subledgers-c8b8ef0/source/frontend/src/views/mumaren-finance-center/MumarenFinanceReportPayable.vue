<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">财务报表</p>
        <h2>应付明细</h2>
        <p>按供应商展开应付明细与账龄分桶。</p>
      </div>
      <div class="heading-actions">
        <el-button :loading="loading" :disabled="!bookId" @click="load">查询</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="load">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <template v-else-if="aging">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="截止日">{{ aging.as_of }}</el-descriptions-item>
        <el-descriptions-item label="未结余额总计">{{ money(aging.total_balance) }}</el-descriptions-item>
      </el-descriptions>

      <div class="bucket-grid">
        <div v-for="(amount, bucket) in aging.buckets" :key="bucket" class="bucket">
          <span>{{ bucket }}</span><strong>{{ money(amount) }}</strong>
        </div>
      </div>

      <el-table :data="aging.counterparties" empty-text="暂无未结供应商余额" stripe>
        <el-table-column prop="counterparty_name" label="供应商名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="未结余额" width="160" align="right">
          <template #default="scope">{{ money(scope.row.total_balance) }}</template>
        </el-table-column>
        <el-table-column
          v-for="bucket in bucketKeys"
          :key="bucket"
          :label="bucket"
          width="140"
          align="right"
        >
          <template #default="scope">{{ money(Number(scope.row[bucket] || 0)) }}</template>
        </el-table-column>
      </el-table>
    </template>

    <el-empty v-else-if="!error" description="请选择独立账簿后查询应付明细" />
  </section>
</template>

<script setup lang="ts">
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { computed, onMounted, ref } from "vue";
import { mumarenFinanceCenterApi, type MumarenArApAging, type MumarenFinanceBook } from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook } = useMumarenFinanceBook();
const aging = ref<MumarenArApAging>();
const error = ref("");
const loading = ref(false);

const money = (value?: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const bucketKeys = computed<string[]>(() => (aging.value ? Object.keys(aging.value.buckets) : []));

const load = async () => {
  if (!bookId.value) {
    aging.value = undefined;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    aging.value = (await mumarenFinanceCenterApi.getArApAging({ book_id: bookId.value, order_type: "payable" })).data.data;
  } catch {
    error.value = "无法加载应付账龄数据。";
    aging.value = undefined;
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    initializeBook(books.value);
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
.bucket-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; }
.bucket { display: grid; gap: 6px; padding: 14px; border: 1px solid #e1e7ef; border-radius: 10px; background: #fbfdff; color: #5d6b7e; }
.bucket strong { color: #172033; font-size: 17px; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } .heading { flex-direction: column; } }
</style>
