<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">科目体系</p>
        <h2>科目</h2>
        <p>只读展示独立账簿下的会计科目体系，不读取旧财务表。</p>
      </div>
      <el-button :loading="loading" :disabled="!bookId" @click="load">刷新</el-button>
    </div>
    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="load">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-table v-else :data="accounts" empty-text="请选择独立账簿后查看科目" stripe>
      <el-table-column prop="account_code" label="科目编码" width="140" />
      <el-table-column prop="account_name" label="科目名称" min-width="200" />
      <el-table-column prop="account_type" label="科目类别" width="140" />
      <el-table-column prop="direction" label="余额方向" width="110" />
      <el-table-column prop="level" label="级次" width="90" align="center" />
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { storeToRefs } from "pinia";
import { mumarenFinanceCenterApi, type MumarenFinanceAccount, type MumarenFinanceBook } from "@/api/mumarenFinanceCenter";
import { useMumarenFinanceBookStore } from "@/stores/mumarenFinanceBook";

const bookStore = useMumarenFinanceBookStore();
const { books, bookId, isReadonly } = storeToRefs(bookStore);
const accounts = ref<MumarenFinanceAccount[]>([]);
const error = ref("");
const loading = ref(false);

const load = async () => {
  if (!bookId.value) {
    accounts.value = [];
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    accounts.value = (await mumarenFinanceCenterApi.listAccounts(bookId.value)).data.data;
  } catch {
    error.value = "无法加载独立科目体系。";
  } finally {
    loading.value = false;
  }
};

onMounted(async () => {
  try {
    await bookStore.loadBooks();
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
@media (max-width: 640px) { .filters { flex-direction: column; } .filters > * { max-width: none; } }
</style>
