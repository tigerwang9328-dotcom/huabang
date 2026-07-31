<template>
  <section class="panel"><div class="heading"><div><p class="panel-kicker">历史数据</p><h2>历史归档</h2><p>金蝶历史数据始终只读，不混入当前账。</p></div><el-button :loading="loading" @click="load">刷新</el-button></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-table v-else :data="rows" empty-text="暂无历史归档记录" stripe><el-table-column label="标记" width="120"><template #default="scope"><el-tag type="info">历史数据</el-tag><el-tag v-if="scope.row.is_readonly" type="warning" class="readonly">只读</el-tag></template></el-table-column><el-table-column prop="source_system" label="来源" width="110" /><el-table-column prop="voucher_no" label="凭证号" width="130" /><el-table-column prop="voucher_date" label="日期" width="120" /><el-table-column prop="summary" label="摘要" min-width="200" /></el-table>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from "vue"; import { mumarenFinanceCenterApi, type MumarenFinanceHistoryVoucher } from "@/api/mumarenFinanceCenter";
const rows = ref<MumarenFinanceHistoryVoucher[]>([]); const error = ref(""); const loading = ref(false); const load = async () => { loading.value=true; error.value=""; try { rows.value=(await mumarenFinanceCenterApi.listHistory({ source_system:"kingdee" })).data.data; } catch { error.value="无法加载独立历史归档。"; } finally { loading.value=false; } }; onMounted(load);
</script>
<style scoped>.panel { padding:30px; border:1px solid #e1e7ef; border-radius:14px; background:#fff; }.heading { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:16px; }.panel-kicker { margin:0; color:#176b97; font-size:12px; font-weight:700; letter-spacing:.08em; }h2 { margin:8px 0; }p { color:#5d6b7e; }.readonly { margin-left:4px; }</style>
