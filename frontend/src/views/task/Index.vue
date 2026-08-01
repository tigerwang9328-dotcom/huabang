<template>
  <div class="page-container">
    <div class="page-header">
      <h2>任务管理</h2>
      <el-button v-if="authStore.hasPermission('task:create')" type="primary" @click="showCreate = true">创建任务</el-button>
    </div>

    <el-card>
      <div class="filter-bar">
        <el-select v-model="filters.status" placeholder="任务状态" clearable style="width:140px" @change="loadTasks">
          <el-option v-for="(label, key) in statusLabels" :key="key" :label="label" :value="key" />
        </el-select>
        <el-input v-model="filters.store_code" placeholder="门店编码" clearable style="width:160px; margin-left:8px" @change="loadTasks" />
      </div>

      <el-table :data="tasks" stripe size="small" style="margin-top:12px">
        <el-table-column prop="task_no" label="任务编号" width="160" />
        <el-table-column prop="title" label="任务标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{row}">
            <el-tag :type="statusType[row.status] || 'info'" size="small">{{ statusLabels[row.status] || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="80" />
        <el-table-column prop="risk_level" label="风险" width="80">
          <template #default="{row}">
            <el-tag :type="riskType[row.risk_level] || 'info'" size="small">{{ row.risk_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="assignee_name" label="责任人" width="100" />
        <el-table-column prop="due_date" label="截止日期" width="110" />
        <el-table-column prop="related_store_code" label="关联门店" width="100" />
        <el-table-column label="操作" width="200">
          <template #default="{row}">
            <el-button size="small" @click="viewDetail(row.id)">详情</el-button>
            <el-button size="small" type="success" v-if="canConfirmOrRetry(row)" @click="confirmTask(row)">{{ row.status === 'draft' ? '确认派发' : '重试通知' }}</el-button>
            <el-button size="small" type="primary" v-if="row.can_feedback && authStore.hasPermission('task:feedback')" @click="openFeedback(row)">反馈</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page" v-model:page-size="pageSize"
        :total="total" layout="total, prev, pager, next"
        @change="loadTasks" style="margin-top:12px; justify-content:flex-end; display:flex"
      />
    </el-card>

    <el-dialog v-model="showCreate" title="创建任务草稿" width="680px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="任务标题" required>
          <el-input v-model="createForm.title" maxlength="256" />
        </el-form-item>
        <el-form-item label="问题描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="数据证据" required>
          <el-input v-model="createForm.data_evidence_text" type="textarea" :rows="3" placeholder="填写触发指标、来源和业务日期" />
        </el-form-item>
        <el-form-item label="责任角色" required>
          <el-select v-model="createForm.assignee_role" style="width:100%">
            <el-option label="门店督导" value="area_supervisor" />
            <el-option label="店长" value="store_manager" />
            <el-option label="导购" value="guide" />
            <el-option label="运营经理" value="operation_manager" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联门店">
          <el-input v-model="createForm.related_store_code" placeholder="门店编码" />
        </el-form-item>
        <el-form-item label="截止日期" required>
          <el-date-picker v-model="createForm.due_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="处理要求" required>
          <el-input v-model="createForm.feedback_requirement" type="textarea" :rows="2" placeholder="说明处理动作、结果证据和复查口径" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate=false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">保存草稿</el-button>
      </template>
    </el-dialog>

    <!-- 反馈弹窗 -->
    <el-dialog v-model="showFeedback" title="提交任务反馈" width="600px">
      <el-form :model="feedbackForm" label-width="100px">
        <el-form-item label="反馈内容" required>
          <el-input v-model="feedbackForm.feedback_content" type="textarea" :rows="4" placeholder="详细描述已执行的动作和结果..." />
        </el-form-item>
        <el-form-item label="采取的行动">
          <el-input v-model="feedbackForm.action_taken" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="执行结果">
          <el-input v-model="feedbackForm.result_description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="结果附件">
          <el-input v-model="feedbackForm.attachment_urls" type="textarea" :rows="2" placeholder="每行一个图片或文件链接" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showFeedback=false">取消</el-button>
        <el-button type="primary" @click="submitFeedback" :loading="submitting">提交反馈</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { taskApi } from "@/api/task";
import { useAuthStore } from "@/stores/auth";
import { ElMessage, ElMessageBox } from "element-plus";

const router = useRouter();
const authStore = useAuthStore();
const tasks = ref<any[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const showCreate = ref(false);
const showFeedback = ref(false);
const submitting = ref(false);
const currentTaskId = ref<number | null>(null);
const feedbackForm = reactive({ request_id: "", feedback_content: "", action_taken: "", result_description: "", attachment_urls: "" });
const createForm = reactive({
  title: "", description: "", data_evidence_text: "", assignee_role: "store_manager",
  related_store_code: "", due_date: "", feedback_requirement: "",
});
const filters = reactive({ status: "", store_code: "" });

const statusLabels: Record<string, string> = {
  draft: "草稿", pending: "待处理", processing: "处理中",
  feedback_submitted: "已反馈", review_passed: "复查通过",
  review_failed: "复查不通过", overdue: "已逾期", closed: "已关闭", cancelled: "已取消",
};
const statusType: Record<string, string> = {
  draft: "info", pending: "warning", processing: "primary",
  feedback_submitted: "", review_passed: "success",
  review_failed: "danger", overdue: "danger", closed: "info",
};
const riskType: Record<string, string> = {
  low: "success", medium: "warning", high: "danger", critical: "danger",
};

const loadTasks = async () => {
  const res = await taskApi.getList({ page: page.value, page_size: pageSize.value, ...filters });
  tasks.value = res.data.data?.items || [];
  total.value = res.data.data?.total || 0;
};

const viewDetail = (id: number) => router.push(`/app/task/${id}`);
const canConfirmOrRetry = (task: any) => authStore.hasPermission('task:approve') && (
  task.status === 'draft' || (task.status !== 'closed' && task.notification_status && task.notification_status !== 'success')
);
const confirmTask = async (task: any) => {
  await ElMessageBox.confirm(task.status === 'draft' ? "确认将此任务草稿派发给责任人？" : "重新发送责任人通知？", "派发确认", { type: "warning" });
  const res = task.status === 'draft'
    ? await taskApi.confirm(task.id)
    : await taskApi.retryNotification(task.id);
  const notification = res.data.data?.notification;
  if (notification && !notification.success) ElMessage.warning("任务状态已保存，但责任人通知未送达，可稍后重试");
  else ElMessage.success(task.status === 'draft' ? "任务已派发" : "通知已重试");
  loadTasks();
};
const openFeedback = (task: any) => {
  currentTaskId.value = task.id;
  Object.assign(feedbackForm, { request_id: crypto.randomUUID(), feedback_content: "", action_taken: "", result_description: "", attachment_urls: "" });
  showFeedback.value = true;
};
const submitCreate = async () => {
  if (!createForm.title.trim() || !createForm.data_evidence_text.trim() || !createForm.due_date || !createForm.feedback_requirement.trim()) {
    return ElMessage.warning("请完整填写标题、数据证据、截止日期和处理要求");
  }
  submitting.value = true;
  try {
    await taskApi.create({ ...createForm, related_store_code: createForm.related_store_code || null });
    ElMessage.success("任务草稿已创建");
    showCreate.value = false;
    Object.assign(createForm, { title: "", description: "", data_evidence_text: "", assignee_role: "store_manager", related_store_code: "", due_date: "", feedback_requirement: "" });
    loadTasks();
  } finally {
    submitting.value = false;
  }
};
const submitFeedback = async () => {
  if (!feedbackForm.feedback_content.trim()) return ElMessage.warning("请填写反馈内容");
  submitting.value = true;
  try {
    await taskApi.feedback(currentTaskId.value!, {
      ...feedbackForm,
      attachment_urls: feedbackForm.attachment_urls.split(/\r?\n/).map(v => v.trim()).filter(Boolean),
    });
    ElMessage.success("反馈提交成功，等待管理层复查");
    showFeedback.value = false;
    loadTasks();
  } finally {
    submitting.value = false;
  }
};

onMounted(loadTasks);
</script>

<style scoped>
.page-container { padding: 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { font-size: 18px; color: #333; }
.filter-bar { display: flex; align-items: center; }
</style>
