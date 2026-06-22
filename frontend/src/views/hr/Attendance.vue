<template>
  <div class="page">
    <div class="page-header"><h2 class="page-title">考勤管理</h2><span class="page-sub">按员工 x 日 的考勤日汇总</span></div>
    <div class="sec" v-loading="loading">
      <el-empty v-if="!items.length && !loading" description="暂无考勤数据，运行钉钉考勤同步后展示" :image-size="90" />
      <el-table v-else :data="items" size="small" stripe>
        <el-table-column prop="work_date" label="日期" min-width="110" />
        <el-table-column prop="employee_name" label="员工" min-width="120" />
        <el-table-column prop="normal_count" label="正常" width="70" align="center" />
        <el-table-column prop="late_count" label="迟到" width="70" align="center" />
        <el-table-column prop="early_leave_count" label="早退" width="70" align="center" />
        <el-table-column prop="missing_check_count" label="缺卡" width="70" align="center" />
        <el-table-column label="状态" width="90"><template #default="{row}"><el-tag size="small" :type="row.attendance_status==='abnormal'?'danger':'success'">{{ row.attendance_status==='abnormal'?'异常':'正常' }}</el-tag></template></el-table-column>
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
  try { const res = await hrApi.getAttendance({ page: page.value, page_size: pageSize }); const d = res.data.data || {}; items.value = d.items || []; total.value = d.total || 0; }
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
