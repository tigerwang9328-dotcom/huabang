<template>
  <div class="attendance-page">
    <section class="hero-panel">
      <div class="hero-copy">
        <div class="title-row">
          <el-icon class="title-icon"><Calendar /></el-icon>
          <div>
            <h2>人事考勤看板</h2>
            <p>
              钉钉考勤同步 · 今日编制 {{ summary.headcount || 0 }} 人 ·
              <span>{{ nowText }}</span>
            </p>
          </div>
        </div>
      </div>
      <div class="hero-actions">
        <el-date-picker
          v-model="workDate"
          type="date"
          size="large"
          value-format="YYYY-MM-DD"
          format="YYYY-MM-DD"
          :clearable="false"
          @change="onWorkDateChange"
        />
        <el-button :icon="TrendCharts" size="large" @click="deptDialogVisible = true">部门统计</el-button>
        <el-button :icon="Download" size="large" @click="exportCsv">导出 CSV</el-button>
        <el-button :icon="Refresh" size="large" type="primary" :loading="syncing" @click="syncDialogVisible = true">
          同步钉钉
        </el-button>
      </div>
    </section>

    <section class="kpi-grid" v-loading="summaryLoading">
      <article v-for="card in kpiCards" :key="card.label" class="kpi-card">
        <div class="kpi-icon" :class="card.tone">
          <el-icon><component :is="card.icon" /></el-icon>
        </div>
        <div>
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
          <small>{{ card.hint }}</small>
        </div>
      </article>
    </section>

    <section class="content-grid">
      <div class="main-stack">
        <section class="filter-panel">
          <el-input
            v-model="filters.keyword"
            class="search-input"
            :prefix-icon="Search"
            clearable
            placeholder="搜索员工、部门或钉钉 userId"
            @keyup.enter="resetAndLoad"
            @clear="resetAndLoad"
          />
          <el-select v-model="filters.department" placeholder="部门" clearable @change="resetAndLoad">
            <el-option label="全部部门" value="全部" />
            <el-option v-for="dept in departments" :key="dept" :label="dept" :value="dept" />
          </el-select>
          <el-select v-model="filters.status" placeholder="状态" clearable @change="resetAndLoad">
            <el-option v-for="st in statusOptions" :key="st" :label="st" :value="st" />
          </el-select>
          <el-button :icon="Refresh" @click="reloadAll">刷新</el-button>
        </section>

        <section class="table-panel" v-loading="loading">
          <div class="section-head">
            <div>
              <h3>打卡明细</h3>
              <p>{{ workDate }} · 共 {{ total }} 条员工日汇总</p>
            </div>
            <el-radio-group v-model="rosterView" size="small" @change="applyRosterView">
              <el-radio-button label="all">全部</el-radio-button>
              <el-radio-button label="abnormal">只看异常</el-radio-button>
            </el-radio-group>
          </div>

          <el-empty
            v-if="!items.length && !loading"
            description="暂无考勤数据，可先点击同步钉钉拉取最近 7 天考勤"
            :image-size="96"
          />
          <el-table v-else :data="items" stripe height="520" row-key="id" class="attendance-table">
            <el-table-column label="员工" min-width="180" fixed>
              <template #default="{ row }">
                <div class="employee-cell">
                  <span class="avatar" :style="{ background: avatarColor(row.employee_name) }">
                    {{ initials(row.employee_name) }}
                  </span>
                  <div>
                    <strong>{{ row.employee_name || "未知员工" }}</strong>
                    <small>{{ row.dingtalk_user_id }}</small>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="department_name" label="部门" min-width="130" />
            <el-table-column prop="work_date" label="日期" width="116" />
            <el-table-column label="状态" width="96" align="center">
              <template #default="{ row }">
                <el-tag round :type="statusTag(row.status_label)">{{ row.status_label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="normal_count" label="正常卡" width="86" align="center" />
            <el-table-column prop="late_count" label="迟到" width="76" align="center" />
            <el-table-column prop="early_leave_count" label="早退" width="76" align="center" />
            <el-table-column prop="missing_check_count" label="缺卡" width="76" align="center" />
            <el-table-column prop="leave_count" label="请假" width="76" align="center" />
          </el-table>

          <div class="pager" v-if="total > pageSize">
            <el-pagination
              background
              layout="prev, pager, next, total"
              :total="total"
              :page-size="pageSize"
              :current-page="page"
              @current-change="onPage"
            />
          </div>
        </section>
      </div>

      <aside class="side-stack">
        <section class="side-panel">
          <div class="section-head compact">
            <div>
              <h3>审批中心</h3>
              <p>请假 / 报销 / 付款</p>
            </div>
            <el-tag type="warning" round>{{ summary.pending_approval_count || 0 }} 待处理</el-tag>
          </div>
          <el-tabs v-model="approvalCategory" @tab-change="loadApprovals">
            <el-tab-pane label="请假" name="leave" />
            <el-tab-pane label="报销" name="reimbursement" />
            <el-tab-pane label="付款" name="payment" />
          </el-tabs>
          <div class="approval-list" v-loading="approvalsLoading">
            <el-empty v-if="!approvals.length && !approvalsLoading" description="暂无审批数据" :image-size="72" />
            <template v-else>
              <article v-for="item in approvals" :key="item.id" class="approval-item">
                <div>
                  <strong>{{ item.originator_name || "未知申请人" }}</strong>
                  <span>{{ item.process_name || categoryName(item.category) }}</span>
                </div>
                <p>{{ item.title || "钉钉审批实例" }}</p>
                <footer>
                  <small>{{ formatDateTime(item.create_time) }}</small>
                  <el-tag size="small" :type="approvalTag(item.status, item.result)">
                    {{ approvalStatus(item.status, item.result) }}
                  </el-tag>
                </footer>
              </article>
            </template>
          </div>
        </section>

        <section class="side-panel">
          <div class="section-head compact">
            <div>
              <h3>免考核白名单</h3>
              <p>前端临时名单，后续可落库</p>
            </div>
            <el-button :icon="Setting" circle @click="whitelistDialogVisible = true" />
          </div>
          <div class="whitelist-tags">
            <el-tag v-for="person in activeWhitelist" :key="person.id" effect="plain" round>
              {{ person.name }} · {{ person.role }}
            </el-tag>
            <span v-if="!activeWhitelist.length" class="empty-note">暂无启用人员</span>
          </div>
        </section>

        <section class="side-panel dept-mini">
          <div class="section-head compact">
            <div>
              <h3>部门出勤率</h3>
              <p>{{ workDate }}</p>
            </div>
          </div>
          <div v-for="dept in deptStats.slice(0, 6)" :key="dept.department" class="dept-row">
            <span>{{ dept.department }}</span>
            <el-progress :percentage="dept.attendance_rate" :stroke-width="8" :show-text="false" />
            <strong>{{ dept.attendance_rate }}%</strong>
          </div>
          <el-empty v-if="!deptStats.length" description="暂无部门数据" :image-size="70" />
        </section>
      </aside>
    </section>

    <el-dialog v-model="deptDialogVisible" title="部门考勤统计" width="720px">
      <el-table :data="deptStats" size="small" stripe>
        <el-table-column prop="department" label="部门" min-width="160" />
        <el-table-column prop="users" label="出勤人数" width="90" align="center" />
        <el-table-column prop="attendance_rate" label="出勤率" width="150">
          <template #default="{ row }">
            <el-progress :percentage="row.attendance_rate" :stroke-width="8" />
          </template>
        </el-table-column>
        <el-table-column prop="late" label="迟到" width="70" align="center" />
        <el-table-column prop="early" label="早退" width="70" align="center" />
        <el-table-column prop="missing" label="缺卡" width="70" align="center" />
        <el-table-column prop="leave" label="请假" width="70" align="center" />
      </el-table>
    </el-dialog>

    <el-dialog v-model="syncDialogVisible" title="同步钉钉人事数据" width="460px">
      <el-form label-position="top">
        <el-form-item label="同步范围">
          <el-radio-group v-model="syncForm.scope">
            <el-radio-button label="attendance">考勤</el-radio-button>
            <el-radio-button label="employees">员工</el-radio-button>
            <el-radio-button label="approvals">审批</el-radio-button>
            <el-radio-button label="all">全部</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="同步天数">
          <el-input-number v-model="syncForm.days" :min="1" :max="30" />
          <span class="form-tip">考勤接口按钉钉限制最多拉 7 天，审批最多 30 天。</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="syncDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="syncing" @click="runSync">开始同步</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="whitelistDialogVisible" title="考勤白名单管理" width="560px">
      <el-form class="whitelist-form" inline @submit.prevent>
        <el-form-item label="姓名">
          <el-input v-model="newWhitelist.name" placeholder="输入姓名" />
        </el-form-item>
        <el-form-item label="角色">
          <el-input v-model="newWhitelist.role" placeholder="如 外部顾问" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Plus" @click="addWhitelist">添加</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="whitelist" size="small" row-key="id">
        <el-table-column prop="name" label="姓名" />
        <el-table-column prop="role" label="角色" />
        <el-table-column label="启用" width="90" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.active" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="right">
          <template #default="{ row }">
            <el-button text type="danger" :icon="Delete" @click="removeWhitelist(row.id)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  Calendar,
  CircleCheck,
  Clock,
  Delete,
  Download,
  Plus,
  Refresh,
  Search,
  Setting,
  TrendCharts,
  User,
  Warning,
} from "@element-plus/icons-vue";
import { hrApi } from "@/api/hr";

const localDateText = (date = new Date()) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};

const today = localDateText();
const workDate = ref(today);
const nowText = ref("");
const loading = ref(false);
const summaryLoading = ref(false);
const approvalsLoading = ref(false);
const syncing = ref(false);
const autoSyncing = ref(false);
const page = ref(1);
const pageSize = 20;
const total = ref(0);
const items = ref<any[]>([]);
const summary = ref<any>({});
const departments = ref<string[]>([]);
const deptStats = ref<any[]>([]);
const approvals = ref<any[]>([]);
const approvalCategory = ref("leave");
const rosterView = ref("all");
const deptDialogVisible = ref(false);
const syncDialogVisible = ref(false);
const whitelistDialogVisible = ref(false);
const timer = ref<number | undefined>();
const autoSyncTimer = ref<number | undefined>();

const filters = reactive({
  keyword: "",
  department: "全部",
  status: "全部",
});

const syncForm = reactive({
  scope: "attendance" as "employees" | "attendance" | "approvals" | "all",
  days: 7,
});

const whitelist = ref([
  { id: "wl-1", name: "陈硕", role: "技术总监", active: true },
  { id: "wl-2", name: "张三", role: "外部顾问", active: true },
  { id: "wl-3", name: "李思", role: "实习生", active: false },
]);
const newWhitelist = reactive({ name: "", role: "外部顾问" });

const statusOptions = ["全部", "正常", "迟到", "早退", "缺卡", "请假", "异常"];
const kpiCards = computed(() => [
  { label: "在职人数", value: summary.value.headcount || 0, hint: "钉钉通讯录 active", icon: User, tone: "blue" },
  { label: "已出勤", value: summary.value.checked_users || 0, hint: `未出勤 ${summary.value.unchecked_users || 0} 人`, icon: CircleCheck, tone: "green" },
  { label: "迟到", value: summary.value.late_count || 0, hint: "含严重迟到", icon: Clock, tone: "amber" },
  { label: "缺卡/异常", value: (summary.value.missing_check_count || 0) + (summary.value.early_leave_count || 0), hint: `请假 ${summary.value.leave_count || 0} 条`, icon: Warning, tone: "red" },
]);

const activeWhitelist = computed(() => whitelist.value.filter((item) => item.active));

const updateTime = () => {
  const d = new Date();
  nowText.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
};

const loadSummary = async () => {
  summaryLoading.value = true;
  try {
    const res = await hrApi.getAttendanceSummary({ work_date: workDate.value });
    summary.value = res.data.data || {};
  } finally {
    summaryLoading.value = false;
  }
};

const loadAttendance = async () => {
  loading.value = true;
  try {
    const status = rosterView.value === "abnormal" && filters.status === "全部" ? "异常" : filters.status;
    const res = await hrApi.getAttendance({
      page: page.value,
      page_size: pageSize,
      work_date: workDate.value,
      department: filters.department || "全部",
      status,
      keyword: filters.keyword || undefined,
    });
    const data = res.data.data || {};
    items.value = data.items || [];
    total.value = data.total || 0;
  } finally {
    loading.value = false;
  }
};

const loadDepartments = async () => {
  const res = await hrApi.getDepartments();
  departments.value = res.data.data?.items || [];
};

const loadDeptStats = async () => {
  const res = await hrApi.getAttendanceDepartments({ work_date: workDate.value });
  deptStats.value = res.data.data?.items || [];
};

const loadApprovals = async () => {
  approvalsLoading.value = true;
  try {
    const res = await hrApi.getApprovals({ category: approvalCategory.value, page: 1, page_size: 8 });
    approvals.value = res.data.data?.items || [];
  } finally {
    approvalsLoading.value = false;
  }
};

const reloadAll = async () => {
  page.value = 1;
  await Promise.all([loadSummary(), loadAttendance(), loadDeptStats(), loadApprovals()]);
};

const onWorkDateChange = async () => {
  await reloadAll();
  await autoSyncAttendance("date-change");
};

const resetAndLoad = () => {
  page.value = 1;
  loadAttendance();
};

const applyRosterView = () => {
  page.value = 1;
  loadAttendance();
};

const onPage = (p: number) => {
  page.value = p;
  loadAttendance();
};

const runSync = async () => {
  syncing.value = true;
  try {
    await hrApi.syncDingtalk({ scope: syncForm.scope, days: syncForm.days });
    ElMessage.success("钉钉同步完成");
    syncDialogVisible.value = false;
    await reloadAll();
  } finally {
    syncing.value = false;
  }
};

const autoSyncAttendance = async (reason: "enter" | "timer" | "date-change") => {
  if (workDate.value !== localDateText()) return;
  if (syncing.value || autoSyncing.value) return;

  const key = `hr_attendance_auto_sync_${workDate.value}`;
  const now = Date.now();
  const last = Number(localStorage.getItem(key) || 0);
  const minInterval = reason === "enter" ? 10 * 60 * 1000 : 30 * 60 * 1000;
  if (last && now - last < minInterval) return;

  autoSyncing.value = true;
  try {
    await hrApi.syncDingtalk({ scope: "attendance", days: 1 });
    localStorage.setItem(key, String(Date.now()));
    await reloadAll();
  } catch (err) {
    console.warn("自动同步钉钉考勤失败", err);
  } finally {
    autoSyncing.value = false;
  }
};

const exportCsv = () => {
  if (!items.value.length) {
    ElMessage.warning("当前筛选没有可导出的考勤数据");
    return;
  }
  const headers = ["日期", "员工", "部门", "状态", "正常卡", "迟到", "早退", "缺卡", "请假"];
  const rows = items.value.map((row) => [
    row.work_date,
    row.employee_name,
    row.department_name,
    row.status_label,
    row.normal_count,
    row.late_count,
    row.early_leave_count,
    row.missing_check_count,
    row.leave_count,
  ]);
  const csv = ["\uFEFF" + headers.join(","), ...rows.map((row) => row.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `考勤导出_${workDate.value}.csv`;
  link.click();
  URL.revokeObjectURL(url);
};

const addWhitelist = () => {
  if (!newWhitelist.name.trim()) {
    ElMessage.warning("请输入姓名");
    return;
  }
  whitelist.value.unshift({
    id: `wl-${Date.now()}`,
    name: newWhitelist.name.trim(),
    role: newWhitelist.role.trim() || "免考核人员",
    active: true,
  });
  newWhitelist.name = "";
};

const removeWhitelist = (id: string) => {
  whitelist.value = whitelist.value.filter((item) => item.id !== id);
};

const initials = (name?: string) => (name || "?").slice(0, 1);
const palette = ["#2563EB", "#059669", "#D97706", "#7C3AED", "#E11D48", "#0891B2", "#4F46E5"];
const avatarColor = (name?: string) => {
  const code = (name || "x").split("").reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
  return palette[code % palette.length];
};
const statusTag = (status: string) => {
  if (status === "正常") return "success";
  if (status === "迟到" || status === "早退") return "warning";
  if (status === "请假") return "info";
  return "danger";
};
const categoryName = (category?: string) => {
  if (category === "reimbursement") return "报销";
  if (category === "payment") return "付款";
  if (category === "leave") return "请假";
  return "审批";
};
const approvalStatus = (status?: string, result?: string) => {
  if (result === "agree") return "已同意";
  if (result === "refuse") return "已拒绝";
  if (status === "COMPLETED") return "已完成";
  if (status === "RUNNING" || status === "NEW") return "审批中";
  return status || "未知";
};
const approvalTag = (status?: string, result?: string) => {
  if (result === "agree" || status === "COMPLETED") return "success";
  if (result === "refuse") return "danger";
  return "warning";
};
const formatDateTime = (v?: string) => (v ? v.replace("T", " ").slice(0, 16) : "-");

onMounted(async () => {
  updateTime();
  timer.value = window.setInterval(updateTime, 1000);
  await Promise.all([loadDepartments(), reloadAll()]);
  await autoSyncAttendance("enter");
  autoSyncTimer.value = window.setInterval(() => {
    void autoSyncAttendance("timer");
  }, 30 * 60 * 1000);
});

onBeforeUnmount(() => {
  if (timer.value) window.clearInterval(timer.value);
  if (autoSyncTimer.value) window.clearInterval(autoSyncTimer.value);
});
</script>

<style scoped>
.attendance-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: #111827;
}

.hero-panel,
.filter-panel,
.table-panel,
.side-panel,
.kpi-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.hero-panel {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 22px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.title-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #eff6ff;
  color: #2563eb;
  font-size: 22px;
}

.hero-panel h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
}

.hero-panel p {
  margin: 6px 0 0;
  color: #6b7280;
  font-size: 13px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.kpi-card {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 18px;
}

.kpi-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.kpi-icon.blue { background: #eff6ff; color: #2563eb; }
.kpi-icon.green { background: #ecfdf5; color: #059669; }
.kpi-icon.amber { background: #fffbeb; color: #d97706; }
.kpi-icon.red { background: #fef2f2; color: #dc2626; }

.kpi-card span,
.kpi-card small {
  display: block;
  color: #6b7280;
  font-size: 12px;
}

.kpi-card strong {
  display: block;
  margin: 3px 0;
  font-size: 26px;
  line-height: 1.1;
  font-weight: 800;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 18px;
}

.main-stack,
.side-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.filter-panel {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 160px 140px auto;
  gap: 10px;
  padding: 14px;
}

.table-panel,
.side-panel {
  padding: 18px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.section-head.compact {
  margin-bottom: 10px;
}

.section-head h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 800;
}

.section-head p {
  margin: 4px 0 0;
  color: #9ca3af;
  font-size: 12px;
}

.employee-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.employee-cell strong,
.employee-cell small {
  display: block;
}

.employee-cell small {
  margin-top: 2px;
  color: #9ca3af;
  font-size: 11px;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  flex: 0 0 auto;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.approval-list {
  min-height: 280px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.approval-item {
  border: 1px solid #eef2f7;
  border-radius: 10px;
  padding: 12px;
}

.approval-item div,
.approval-item footer {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.approval-item strong {
  font-size: 13px;
}

.approval-item span,
.approval-item small,
.approval-item p {
  color: #6b7280;
  font-size: 12px;
}

.approval-item p {
  margin: 8px 0;
  line-height: 1.45;
}

.whitelist-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.empty-note,
.form-tip {
  color: #9ca3af;
  font-size: 12px;
}

.dept-mini {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dept-row {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr) 48px;
  gap: 10px;
  align-items: center;
  font-size: 12px;
}

.dept-row span {
  color: #4b5563;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.dept-row strong {
  text-align: right;
  color: #111827;
}

.whitelist-form {
  margin-bottom: 12px;
}

@media (max-width: 1180px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
  .side-stack {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .dept-mini {
    grid-column: 1 / -1;
  }
}

@media (max-width: 860px) {
  .hero-panel {
    flex-direction: column;
  }
  .hero-actions,
  .hero-actions :deep(.el-date-editor),
  .hero-actions :deep(.el-button) {
    width: 100%;
  }
  .kpi-grid,
  .side-stack {
    grid-template-columns: 1fr;
  }
  .filter-panel {
    grid-template-columns: 1fr;
  }
}
</style>
