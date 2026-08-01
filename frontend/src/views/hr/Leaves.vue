<template>
  <div class="page">
    <div class="page-header"><h2 class="page-title">请假外出</h2><span class="page-sub">请假 / 出差 / 外出 审批</span></div>
    <div class="sec" v-loading="loading">
      <el-empty v-if="!items.length && !loading" description="暂无请假/外出数据，待钉钉审批数据接入后展示" :image-size="90" />
      <el-table v-else :data="items" size="small" stripe>
        <el-table-column prop="originator_name" label="申请人" min-width="110" />
        <el-table-column prop="department_name" label="部门" min-width="120" />
        <el-table-column prop="process_name" label="类型" min-width="130" />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="分类" width="90"><template #default="{row}"><el-tag size="small" :type="row.category==='leave'?'info':'warning'">{{ row.category==='leave'?'请假':'出差/外出' }}</el-tag></template></el-table-column>
        <el-table-column prop="status" label="状态" width="110" />
      </el-table>
      <div class="pager" v-if="total > pageSize">
        <el-pagination layout="prev, pager, next" :total="total" :page-size="pageSize" :current-page="page" @current-change="onPage" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { hrApi } from "@/api/hr";
const loading = ref(true); const items = ref<any[]>([]); const total = ref(0); const page = ref(1); const pageSize = 20;
const load = async () => {
  loading.value = true;
  try { const res = await hrApi.getLeaves({ page: page.value, page_size: pageSize }); const d = res.data.data || {}; items.value = d.items || []; total.value = d.total || 0; }
  catch (e) { console.error(e); } finally { loading.value = false; }
};
const onPage = (p: number) => { page.value = p; load(); };
onMounted(load);
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 18px; }
.page-header { display: flex; align-items: baseline; }
.page-title { font-size: 20px; font-weight: 700; color: #111827; margin: 0; }
.page-sub { font-size: 13px; color: #9CA3AF; margin-left: 10px; }
.sec { background: #fff; border-radius: 12px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.pager { margin-top: 14px; display: flex; justify-content: flex-end; }
</style>
