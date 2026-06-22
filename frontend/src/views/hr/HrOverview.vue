<template>
  <div class="page">
    <div class="page-header">
      <div><h2 class="page-title">人事首页</h2><span class="page-sub">员工 / 考勤 / 请假 汇总（来自钉钉同步）</span></div>
      <el-button size="small" :loading="loading" @click="load">刷新</el-button>
    </div>

    <div class="cards" v-loading="loading">
      <div class="card" v-for="c in cards" :key="c.label">
        <div class="c-label">{{ c.label }}</div>
        <div class="c-val" :class="c.cls">{{ c.value }}</div>
      </div>
    </div>

    <div class="sec">
      <div class="sec-title">今日部门出勤统计</div>
      <el-empty v-if="!deptAtt.length" description="今日暂无考勤数据" :image-size="80" />
      <el-table v-else :data="deptAtt" size="small" stripe>
        <el-table-column prop="department" label="部门" min-width="160" />
        <el-table-column prop="users" label="出勤人数" width="100" align="center" />
        <el-table-column prop="late" label="迟到" width="80" align="center" />
        <el-table-column prop="missing" label="缺卡" width="80" align="center" />
      </el-table>
    </div>

    <div class="sec">
      <div class="sec-title">最近考勤异常</div>
      <el-empty v-if="!abnormal.length" description="暂无考勤异常" :image-size="80" />
      <el-table v-else :data="abnormal" size="small" stripe>
        <el-table-column prop="work_date" label="日期" min-width="110" />
        <el-table-column prop="employee_name" label="员工" min-width="120" />
        <el-table-column prop="late_count" label="迟到" width="70" align="center" />
        <el-table-column prop="early_leave_count" label="早退" width="70" align="center" />
        <el-table-column prop="missing_check_count" label="缺卡" width="70" align="center" />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { hrApi } from "@/api/hr";
const loading = ref(true); const data = ref<any>({}); const deptAtt = ref<any[]>([]); const abnormal = ref<any[]>([]);
const cards = computed(() => {
  const t = data.value.today || {};
  return [
    { label: "在职人数", value: data.value.headcount || 0 },
    { label: "今日出勤人数", value: t.attendance_count || 0 },
    { label: "今日迟到", value: t.late_count || 0, cls: (t.late_count||0)>0?'warn':'' },
    { label: "今日早退", value: t.early_leave_count || 0, cls: (t.early_leave_count||0)>0?'warn':'' },
    { label: "今日缺卡", value: t.missing_check_count || 0, cls: (t.missing_check_count||0)>0?'danger':'' },
    { label: "今日请假", value: t.leave_count || 0 },
  ];
});
const load = async () => {
  loading.value = true;
  try { const res = await hrApi.getOverview(); data.value = res.data.data || {}; deptAtt.value = data.value.department_attendance || []; abnormal.value = data.value.recent_abnormal || []; }
  catch (e) { console.error("人事概览加载失败", e); } finally { loading.value = false; }
};
onMounted(load);
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 18px; }
.page-header { display: flex; align-items: center; justify-content: space-between; }
.page-title { font-size: 20px; font-weight: 700; color: #111827; margin: 0; }
.page-sub { font-size: 13px; color: #9CA3AF; margin-left: 10px; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
.card { background: #fff; border-radius: 12px; padding: 16px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.c-label { font-size: 12px; color: #9CA3AF; margin-bottom: 8px; }
.c-val { font-size: 22px; font-weight: 700; color: #111827; }
.c-val.warn { color: #D97706; } .c-val.danger { color: #DC2626; }
.sec { background: #fff; border-radius: 12px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.sec-title { font-size: 14px; font-weight: 700; color: #111827; margin-bottom: 14px; }
</style>
