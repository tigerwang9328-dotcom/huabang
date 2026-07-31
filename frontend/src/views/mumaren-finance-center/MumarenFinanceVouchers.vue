<template>
  <section class="panel"><div class="heading"><div><p class="panel-kicker">凭证流程</p><h2>凭证</h2><p>仅查询独立当前账凭证；状态依次为草稿、审核、人工过账。</p></div><el-button :loading="loading" @click="load">刷新</el-button></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-table v-else :data="vouchers" empty-text="暂无独立当前账凭证" stripe><el-table-column prop="voucher_no" label="凭证号" min-width="130" /><el-table-column prop="voucher_date" label="日期" width="120" /><el-table-column prop="summary" label="摘要" min-width="180" /><el-table-column prop="status" label="状态" width="110" /><el-table-column label="借方" width="140" align="right"><template #default="scope">{{ money(scope.row.total_debit) }}</template></el-table-column><el-table-column label="贷方" width="140" align="right"><template #default="scope">{{ money(scope.row.total_credit) }}</template></el-table-column></el-table>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from "vue"; import { mumarenFinanceCenterApi, type MumarenFinanceVoucher } from "@/api/mumarenFinanceCenter";
const vouchers = ref<MumarenFinanceVoucher[]>([]); const error = ref(""); const loading = ref(false); const money = (value: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
const load = async () => { loading.value = true; error.value = ""; try { vouchers.value = (await mumarenFinanceCenterApi.listVouchers()).data.data; } catch { error.value = "无法加载独立当前账凭证。"; } finally { loading.value = false; } }; onMounted(load);
</script>
<style scoped>.panel { padding:30px; border:1px solid #e1e7ef; border-radius:14px; background:#fff; }.heading { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:16px; }.panel-kicker { margin:0; color:#176b97; font-size:12px; font-weight:700; letter-spacing:.08em; }h2 { margin:8px 0; }p { color:#5d6b7e; }</style>
