<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">金蝶迁移数据</p>
        <h2>金蝶迁移凭证</h2>
        <p>按账簿查看三套金蝶迁移凭证；迁移账簿永久只读，不混入当前账。</p>
      </div>
      <div>
        <router-link to="/app/finance-center/mumaren/history/balance-snapshots"><el-button>余额快照核对</el-button></router-link>
        <el-button :loading="loading" :disabled="!bookId" @click="load">刷新</el-button>
      </div>
    </div>
    <el-select v-model="bookId" placeholder="选择金蝶迁移账簿" clearable @change="load">
      <el-option v-for="book in readonlyBooks" :key="book.id" :label="book.book_name" :value="book.id" />
    </el-select>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-empty v-else-if="!bookId" description="请选择金蝶迁移账簿" />
    <el-table v-else :data="rows" empty-text="该金蝶迁移账簿暂无凭证" stripe>
      <el-table-column label="标记" width="150"><template #default="scope"><el-tag type="info">金蝶迁移</el-tag><el-tag v-if="scope.row.is_normalized" type="warning" class="readonly">已规范化</el-tag></template></el-table-column>
      <el-table-column prop="source_system" label="来源" width="130" />
      <el-table-column prop="voucher_no" label="凭证号" width="150" />
      <el-table-column prop="voucher_date" label="日期" width="120" />
      <el-table-column prop="summary" label="摘要" min-width="200" />
      <el-table-column label="状态" width="100"><template #default><el-tag type="success">已过账</el-tag></template></el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import { mumarenFinanceCenterApi, type MumarenFinanceBook, type MumarenFinanceVoucher } from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const { bookId, initializeBook } = useMumarenFinanceBook();
const rows = ref<MumarenFinanceVoucher[]>([]);
const error = ref("");
const loading = ref(false);
let loadRequestVersion = 0;

const readonlyBooks = computed(() => books.value.filter((book) => book.is_readonly));

const load = async () => {
  const requestedBookId = bookId.value;
  const requestVersion = ++loadRequestVersion;
  if (!requestedBookId) {
    rows.value = [];
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const response = await mumarenFinanceCenterApi.listVouchers({ book_id: requestedBookId, limit: 500 });
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value) rows.value = response.data.data;
  } catch {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value) error.value = "无法加载金蝶迁移凭证。";
  } finally {
    if (requestVersion === loadRequestVersion && requestedBookId === bookId.value) loading.value = false;
  }
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    initializeBook(readonlyBooks.value);
    if (!readonlyBooks.value.some((book) => book.id === bookId.value)) bookId.value = readonlyBooks.value[0]?.id;
    await load();
  } catch {
    error.value = "无法加载金蝶迁移账簿。";
  }
});
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 16px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
.readonly { margin-left: 4px; }
</style>
