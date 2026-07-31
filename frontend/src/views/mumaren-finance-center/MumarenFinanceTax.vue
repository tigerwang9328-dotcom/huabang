<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">独立税务台账</p>
        <h2>税务</h2>
        <p>仅展示独立税务记录与到期预警；申报、缴纳和凭证动作均未开放。</p>
      </div>
      <el-button type="primary" :disabled="!bookId" :loading="loading" @click="load">查询税务</el-button>
    </div>
    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable>
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
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
        <el-table-column prop="due_date" label="截止日" width="130" />
        <el-table-column prop="status" label="状态" width="110" />
      </el-table>
    </template>
    <el-empty v-else description="请选择独立账簿后查询税务台账" />
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { mumarenFinanceCenterApi, type MumarenFinanceBook, type MumarenTaxAlert, type MumarenTaxRecord } from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const bookId = ref<number>();
const alerts = ref<MumarenTaxAlert[]>([]);
const records = ref<MumarenTaxRecord[]>([]);
const error = ref("");
const loading = ref(false);
const loaded = ref(false);
const money = (value: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const load = async () => {
  if (!bookId.value) {
    loaded.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const [alertResult, recordResult] = await Promise.all([
      mumarenFinanceCenterApi.getTaxAlerts({ book_id: bookId.value }),
      mumarenFinanceCenterApi.listTaxRecords({ book_id: bookId.value }),
    ]);
    alerts.value = alertResult.data.data.alerts || [];
    records.value = recordResult.data.data;
    loaded.value = true;
  } catch {
    error.value = "无法加载独立税务台账。";
    loaded.value = false;
  } finally {
    loading.value = false;
  }
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
</script>
<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.filters { display: flex; gap: 12px; }
.filters > * { max-width: 280px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
.alert-row { display: block; margin: 4px 0; }
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } }
</style>
