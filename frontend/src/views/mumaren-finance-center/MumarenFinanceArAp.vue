<template>
  <section class="panel">
    <div class="heading"><div><p class="panel-kicker">独立往来账</p><h2>应收应付</h2><p>仅查询牧马人独立 AR/AP 台账和账龄；结算、录入等写入功能尚未开放。</p></div><el-button type="primary" :disabled="!bookId" :loading="loading" @click="load">查询账龄</el-button></div>
    <div class="filters"><el-select v-model="bookId" placeholder="选择独立账簿" clearable><el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" /></el-select><el-radio-group v-model="orderType"><el-radio-button label="receivable">应收</el-radio-button><el-radio-button label="payable">应付</el-radio-button></el-radio-group></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <template v-else-if="aging"><el-descriptions :column="2" border><el-descriptions-item label="截止日">{{ aging.as_of }}</el-descriptions-item><el-descriptions-item label="未结余额">{{ money(aging.total_balance) }}</el-descriptions-item></el-descriptions><div class="bucket-grid"><div v-for="(amount, bucket) in aging.buckets" :key="bucket" class="bucket"><span>{{ bucket }}</span><strong>{{ money(amount) }}</strong></div></div><el-table :data="aging.counterparties" empty-text="暂无未结往来余额" stripe><el-table-column prop="counterparty_name" label="往来单位" min-width="200" /><el-table-column label="未结余额" width="160" align="right"><template #default="scope">{{ money(scope.row.total_balance) }}</template></el-table-column></el-table></template>
    <el-empty v-else description="请选择独立账簿后查询账龄" />
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { mumarenFinanceCenterApi, type MumarenArApAging, type MumarenFinanceBook } from "@/api/mumarenFinanceCenter";
const books = ref<MumarenFinanceBook[]>([]); const bookId = ref<number>(); const orderType = ref<"receivable" | "payable">("receivable"); const aging = ref<MumarenArApAging>(); const error = ref(""); const loading = ref(false);
const money = (value: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
const load = async () => { if (!bookId.value) return; loading.value=true; error.value=""; try { aging.value=(await mumarenFinanceCenterApi.getArApAging({ book_id:bookId.value, order_type:orderType.value })).data.data; } catch { error.value="无法加载独立应收应付账龄。"; } finally { loading.value=false; } };
onMounted(async () => { try { books.value=(await mumarenFinanceCenterApi.listBooks()).data.data; bookId.value=books.value[0]?.id; if (bookId.value) await load(); } catch { error.value="无法加载独立账簿。"; } });
</script>
<style scoped>.panel { padding:30px; border:1px solid #e1e7ef; border-radius:14px; background:#fff; display:grid; gap:16px; }.heading { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }.filters { display:flex; gap:12px; align-items:center; }.bucket-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px; }.bucket { display:grid; gap:6px; padding:14px; border:1px solid #e1e7ef; border-radius:10px; background:#fbfdff; color:#5d6b7e; }.bucket strong { color:#172033; font-size:17px; }.panel-kicker { margin:0; color:#176b97; font-size:12px; font-weight:700; letter-spacing:.08em; } h2 { margin:8px 0; } p { color:#5d6b7e; } @media(max-width:640px){.filters{align-items:stretch;flex-direction:column}}</style>
