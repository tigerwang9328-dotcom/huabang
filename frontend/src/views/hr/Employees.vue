<template>
  <div class="page">
    <div class="page-header"><h2 class="page-title">员工档案</h2></div>
    <div class="sec" v-loading="loading">
      <el-empty v-if="!items.length && !loading" description="暂无员工数据，运行钉钉员工同步后展示" :image-size="90" />
      <el-table v-else :data="items" size="small" stripe>
        <el-table-column prop="name" label="姓名" min-width="110" />
        <el-table-column prop="position" label="职位" min-width="130" />
        <el-table-column prop="job_number" label="工号" min-width="110" />
        <el-table-column prop="mobile" label="手机" min-width="130" />
        <el-table-column label="状态" width="90"><template #default="{row}"><el-tag size="small" :type="row.active?'success':'info'">{{ row.active?'在职':'离职' }}</el-tag></template></el-table-column>
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
  try { const res = await hrApi.getEmployees({ page: page.value, page_size: pageSize }); const d = res.data.data || {}; items.value = d.items || []; total.value = d.total || 0; }
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
