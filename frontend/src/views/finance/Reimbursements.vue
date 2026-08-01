<template>
  <div class="page">
    <div class="page-header"><h2 class="page-title">报销管理</h2></div>
    <div class="sec" v-loading="loading">
      <el-empty v-if="!items.length && !loading" description="暂无报销记录，待钉钉报销审批数据接入后展示" :image-size="90" />
      <el-table v-else :data="items" size="small" stripe>
        <el-table-column prop="applicant_name" label="申请人" min-width="100" />
        <el-table-column prop="department_name" label="部门" min-width="120" />
        <el-table-column prop="expense_type" label="报销类型" min-width="150" />
        <el-table-column label="金额" min-width="110"><template #default="{row}">{{ fmtMoney(row.amount) }}</template></el-table-column>
        <el-table-column prop="approval_status" label="审批状态" width="110" />
        <el-table-column prop="expense_date" label="日期" min-width="110" />
      </el-table>
      <div class="pager" v-if="total > pageSize">
        <el-pagination layout="prev, pager, next" :total="total" :page-size="pageSize" :current-page="page" @current-change="onPage" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { financeApi } from "@/api/finance";
const loading = ref(true); const items = ref<any[]>([]); const total = ref(0); const page = ref(1); const pageSize = 20;
const fmtMoney = (v: any) => { const n = Number(v || 0); return n >= 10000 ? "¥" + (n / 10000).toFixed(2) + "万" : "¥" + n.toFixed(0); };
const load = async () => {
  loading.value = true;
  try { const res = await financeApi.getReimbursements({ page: page.value, page_size: pageSize }); const d = res.data.data || {}; items.value = d.items || []; total.value = d.total || 0; }
  catch (e) { console.error(e); } finally { loading.value = false; }
};
const onPage = (p: number) => { page.value = p; load(); };
onMounted(load);
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 18px; }
.page-title { font-size: 20px; font-weight: 700; color: #111827; margin: 0; }
.sec { background: #fff; border-radius: 12px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.pager { margin-top: 14px; display: flex; justify-content: flex-end; }
</style>
