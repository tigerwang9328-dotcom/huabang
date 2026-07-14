<template>
  <div class="page-container">
    <el-page-header @back="$router.back()" title="返回任务列表">
      <template #content>任务详情</template>
    </el-page-header>
    <el-card style="margin-top:16px" v-loading="loading">
      <div v-if="task">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务编号">{{ task.task_no }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusType[task.status] || 'info'">{{ statusLabel[task.status] || task.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="任务标题" :span="2">{{ task.title }}</el-descriptions-item>
          <el-descriptions-item label="责任人">{{ task.assignee_name || '--' }}</el-descriptions-item>
          <el-descriptions-item label="截止日期">{{ task.due_date || '--' }}</el-descriptions-item>
          <el-descriptions-item label="优先级">{{ task.priority }}</el-descriptions-item>
          <el-descriptions-item label="风险等级">
            <el-tag :type="task.risk_level === 'high' ? 'danger' : task.risk_level === 'medium' ? 'warning' : 'info'" size="small">
              {{ task.risk_level }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="需人工确认">
            <el-tag :type="task.requires_human_confirm ? 'danger' : 'info'" size="small">
              {{ task.requires_human_confirm ? '是' : '否' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="任务来源">{{ task.source_type }}</el-descriptions-item>
          <el-descriptions-item label="问题描述" :span="2">{{ task.description || '--' }}</el-descriptions-item>
          <el-descriptions-item label="数据依据" :span="2">{{ task.data_evidence_text || '--' }}</el-descriptions-item>
          <el-descriptions-item label="反馈要求" :span="2">{{ task.feedback_requirement || '--' }}</el-descriptions-item>
        </el-descriptions>

        <div class="action-bar">
          <el-button v-if="canConfirmOrRetry" type="success" @click="confirmTask">{{ task.status === 'draft' ? '确认派发' : '重试通知' }}</el-button>
          <el-button v-if="task.can_feedback && authStore.hasPermission('task:feedback')" type="primary" @click="openFeedback">提交反馈</el-button>
          <el-button v-if="task.status === 'feedback_submitted' && authStore.hasPermission('task:review')" type="success" @click="openReview('passed')">复查通过</el-button>
          <el-button v-if="task.status === 'feedback_submitted' && authStore.hasPermission('task:review')" type="warning" @click="openReview('failed')">退回整改</el-button>
          <el-button v-if="task.status === 'review_passed' && authStore.hasPermission('task:close')" type="primary" @click="closeTask">关闭任务</el-button>
        </div>

        <el-divider>反馈记录</el-divider>
        <div v-if="task.feedbacks?.length">
          <el-card v-for="fb in task.feedbacks" :key="fb.id" style="margin-bottom:12px">
            <p><strong>反馈内容：</strong>{{ fb.content }}</p>
            <p v-if="fb.action_taken"><strong>行动：</strong>{{ fb.action_taken }}</p>
            <p v-if="fb.result_description"><strong>结果：</strong>{{ fb.result_description }}</p>
            <p v-if="safeAttachmentUrls(fb.attachment_urls).length"><strong>结果附件：</strong>
              <a v-for="url in safeAttachmentUrls(fb.attachment_urls)" :key="url" :href="url" target="_blank" rel="noopener noreferrer">{{ url }} </a>
            </p>
            <p style="color:#999;font-size:12px">{{ fb.created_at }}</p>
          </el-card>
        </div>
        <el-empty v-else description="暂无反馈" />

        <el-divider>复查记录</el-divider>
        <div v-if="task.reviews?.length">
          <el-card v-for="rv in task.reviews" :key="rv.id" style="margin-bottom:12px">
            <el-tag :type="rv.result === 'passed' ? 'success' : 'danger'">{{ rv.result }}</el-tag>
            <p style="margin-top:8px">{{ rv.note }}</p>
            <p style="color:#999;font-size:12px">{{ rv.created_at }}</p>
          </el-card>
        </div>
        <el-empty v-else description="暂无复查记录" />
      </div>
    </el-card>

    <el-dialog v-model="showFeedback" title="提交任务反馈" width="620px">
      <el-form label-width="90px">
        <el-form-item label="反馈内容" required><el-input v-model="feedback.feedback_content" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="采取行动"><el-input v-model="feedback.action_taken" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="执行结果"><el-input v-model="feedback.result_description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="结果附件"><el-input v-model="feedback.attachment_urls" type="textarea" :rows="2" placeholder="每行一个链接" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showFeedback=false">取消</el-button><el-button type="primary" @click="submitFeedback">提交</el-button></template>
    </el-dialog>

    <el-dialog v-model="showReview" :title="review.review_result === 'passed' ? '复查通过' : '退回整改'" width="560px">
      <el-input v-model="review.review_note" type="textarea" :rows="4" placeholder="填写复查意见和后续要求" />
      <template #footer><el-button @click="showReview=false">取消</el-button><el-button type="primary" @click="submitReview">确认</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { taskApi } from '@/api/task'
import { useAuthStore } from '@/stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const authStore = useAuthStore()
const task = ref<any>(null)
const loading = ref(true)
const showFeedback = ref(false)
const showReview = ref(false)
const feedback = reactive({ request_id: '', feedback_content: '', action_taken: '', result_description: '', attachment_urls: '' })
const review = reactive({ request_id: '', review_result: 'passed', review_note: '' })
const canConfirmOrRetry = computed(() => authStore.hasPermission('task:approve') && task.value && (
  task.value.status === 'draft' || (
    task.value.status !== 'closed' && task.value.notification_status && task.value.notification_status !== 'success'
  )
))

const statusType: Record<string, string> = {
  pending: 'warning', processing: 'primary', overdue: 'danger',
  review_passed: 'success', draft: 'info', closed: 'info',
  feedback_submitted: 'warning', cancelled: 'info',
}
const statusLabel: Record<string, string> = {
  pending: '待处理', processing: '处理中', overdue: '已逾期',
  review_passed: '复查通过', draft: '草稿', closed: '已关闭',
  feedback_submitted: '待复查', cancelled: '已取消',
  review_failed: '已退回',
}

function safeAttachmentUrls(values: unknown): string[] {
  if (!Array.isArray(values)) return []
  return values.filter((value): value is string => {
    if (typeof value !== 'string') return false
    try {
      const parsed = new URL(value)
      return parsed.protocol === 'http:' || parsed.protocol === 'https:'
    } catch {
      return false
    }
  })
}

async function loadTask() {
  loading.value = true
  try {
    const res = await taskApi.getDetail(Number(route.params.id))
    task.value = res.data.data
  } finally {
    loading.value = false
  }
}

async function confirmTask() {
  const retrying = task.value.status !== 'draft'
  await ElMessageBox.confirm(retrying ? '重新发送责任人通知？' : '确认派发给当前责任人？', '确认派发', { type: 'warning' })
  const res = retrying
    ? await taskApi.retryNotification(task.value.id)
    : await taskApi.confirm(task.value.id)
  const notification = res.data.data?.notification
  if (notification && !notification.success) ElMessage.warning('任务状态已保存，但责任人通知未送达，可稍后重试')
  else ElMessage.success(retrying ? '通知已重试' : '任务已派发')
  await loadTask()
}

async function submitFeedback() {
  if (!feedback.feedback_content.trim()) return ElMessage.warning('请填写反馈内容')
  await taskApi.feedback(task.value.id, {
    ...feedback,
    attachment_urls: feedback.attachment_urls.split(/\r?\n/).map(v => v.trim()).filter(Boolean),
  })
  showFeedback.value = false
  ElMessage.success('反馈已提交')
  await loadTask()
}

function openFeedback() {
  Object.assign(feedback, {
    request_id: crypto.randomUUID(),
    feedback_content: '', action_taken: '', result_description: '', attachment_urls: '',
  })
  showFeedback.value = true
}

function openReview(result: 'passed' | 'failed') {
  review.request_id = crypto.randomUUID()
  review.review_result = result
  review.review_note = ''
  showReview.value = true
}

async function submitReview() {
  await taskApi.review(task.value.id, review)
  showReview.value = false
  ElMessage.success(review.review_result === 'passed' ? '复查已通过' : '已退回整改')
  await loadTask()
}

async function closeTask() {
  await ElMessageBox.confirm('关闭后任务进入完整归档，确认关闭？', '关闭任务', { type: 'warning' })
  await taskApi.close(task.value.id)
  ElMessage.success('任务已关闭')
  await loadTask()
}

onMounted(loadTask)
</script>

<style scoped>
.page-container { padding: 0; }
.action-bar { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
</style>
