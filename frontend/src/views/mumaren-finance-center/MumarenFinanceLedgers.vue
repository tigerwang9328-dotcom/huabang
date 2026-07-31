<template>
  <section class="panel"><div class="heading"><div><p class="panel-kicker">当前账</p><h2>账簿</h2><p>只展示新财务中心独立账簿，不读取旧财务表。</p></div><el-button :loading="loading" @click="load">刷新</el-button></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-table v-else :data="books" empty-text="暂无独立账簿" stripe><el-table-column prop="book_code" label="账簿编码" min-width="150" /><el-table-column prop="book_name" label="账簿名称" min-width="180" /><el-table-column prop="company_name" label="公司" min-width="180" /><el-table-column prop="status" label="状态" width="110" /></el-table>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from "vue"; import { mumarenFinanceCenterApi, type MumarenFinanceBook } from "@/api/mumarenFinanceCenter";
const books = ref<MumarenFinanceBook[]>([]); const error = ref(""); const loading = ref(false); const load = async () => { loading.value = true; error.value = ""; try { books.value = (await mumarenFinanceCenterApi.listBooks()).data.data; } catch { error.value = "无法加载独立账簿。"; } finally { loading.value = false; } }; onMounted(load);
</script>
<style scoped>.panel { padding:30px; border:1px solid #e1e7ef; border-radius:14px; background:#fff; }.heading { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:16px; }.panel-kicker { margin:0; color:#176b97; font-size:12px; font-weight:700; letter-spacing:.08em; }h2 { margin:8px 0; }p { color:#5d6b7e; }</style>
