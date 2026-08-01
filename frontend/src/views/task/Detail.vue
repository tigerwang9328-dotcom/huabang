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

        <section v-if="isMemberAction" class="member-action-panel">
          <div class="member-action-title">VIP会员行动</div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="会员编号">{{ memberAction.member_no || '--' }}</el-descriptions-item>
            <el-descriptions-item label="联系理由">{{ memberAction.contact_reason || '--' }}</el-descriptions-item>
            <el-descriptions-item label="建议商品" :span="2">{{ recommendedProductNames }}</el-descriptions-item>
            <el-descriptions-item label="建议话术" :span="2">{{ memberAction.suggested_script || '--' }}</el-descriptions-item>
            <el-descriptions-item v-if="memberAction.confirmed_script" label="已确认话术" :span="2">{{ memberAction.confirmed_script }}</el-descriptions-item>
          </el-descriptions>
          <el-alert type="warning" show-icon :closable="false" title="主管确认责任人和联系话术后才能联系会员；系统不会自动发送消息。" />
        </section>

        <div class="action-bar">
          <el-button v-if="canConfirmOrRetry" type="success" @click="confirmTask">{{ task.status === 'draft' ? (isMemberAction ? '确认会员行动' : '确认派发') : '重试通知' }}</el-button>
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
            <div v-if="fb.metrics_after?.member_followup" class="followup-result">
              <span>是否联系：{{ yesNo(fb.metrics_after.member_followup.contacted) }}</span>
              <span>是否到店：{{ yesNo(fb.metrics_after.member_followup.arrived) }}</span>
              <span>是否成交：{{ yesNo(fb.metrics_after.member_followup.converted) }}</span>
              <span v-if="fb.metrics_after.member_followup.linked_ticket_no">关联百胜小票：{{ fb.metrics_after.member_followup.linked_ticket_no }}</span>
              <span v-if="fb.metrics_after.member_followup.no_conversion_reason">未成交原因：{{ fb.metrics_after.member_followup.no_conversion_reason }}</span>
              <span v-if="fb.metrics_after.member_followup.next_followup_at">下次跟进时间：{{ formatTime(fb.metrics_after.member_followup.next_followup_at) }}</span>
            </div>
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

    <el-dialog v-model="showMemberConfirm" title="确认VIP会员行动" width="620px">
      <el-form label-width="110px">
        <el-form-item label="责任人" required>
          <el-select v-model="memberConfirm.assignee_id" filterable placeholder="选择本门店员工" style="width:100%" @change="syncAssigneeName">
            <el-option v-for="item in assigneeOptions" :key="item.id" :label="assigneeLabel(item)" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="确认联系话术" required>
          <el-input v-model="memberConfirm.member_contact_script" type="textarea" :rows="6" maxlength="2000" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="showMemberConfirm=false">取消</el-button><el-button type="primary" :loading="confirming" @click="submitMemberConfirm">确认并派发</el-button></template>
    </el-dialog>

    <el-dialog v-model="showFeedback" title="提交任务反馈" width="620px">
      <el-form label-width="90px">
        <el-form-item label="反馈内容" required><el-input v-model="feedback.feedback_content" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="采取行动"><el-input v-model="feedback.action_taken" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="执行结果"><el-input v-model="feedback.result_description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="结果附件"><el-input v-model="feedback.attachment_urls" type="textarea" :rows="2" placeholder="每行一个链接" /></el-form-item>
        <template v-if="isMemberAction">
          <el-divider>会员跟进结果</el-divider>
          <el-form-item label="是否联系"><el-switch v-model="feedback.contacted" /></el-form-item>
          <el-form-item label="是否到店"><el-switch v-model="feedback.arrived" :disabled="!feedback.contacted" /></el-form-item>
          <el-form-item label="是否成交"><el-switch v-model="feedback.converted" :disabled="!feedback.contacted" /></el-form-item>
          <el-form-item v-if="feedback.converted" label="成交金额" required><el-input-number v-model="feedback.conversion_amount" :min="0" :precision="2" /></el-form-item>
          <el-form-item v-if="feedback.converted" label="关联百胜小票" required><el-input v-model="feedback.linked_ticket_no" placeholder="系统将按会员、门店、日期和金额核验" /></el-form-item>
          <el-form-item v-if="feedback.contacted && !feedback.converted" label="未成交原因" required><el-input v-model="feedback.no_conversion_reason" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="下次跟进时间"><el-date-picker v-model="feedback.next_followup_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" placeholder="选择时间" /></el-form-item>
        </template>
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
const showMemberConfirm = ref(false)
const confirming = ref(false)
const assigneeOptions = ref<any[]>([])
const memberConfirm = reactive({ assignee_id: undefined as number | undefined, assignee_name: '', member_contact_script: '' })
const feedback = reactive({ request_id: '', feedback_content: '', action_taken: '', result_description: '', attachment_urls: '', contacted: false, arrived: false, converted: false, conversion_amount: 0, linked_ticket_no: '', no_conversion_reason: '', next_followup_at: '' })
const review = reactive({ request_id: '', review_result: 'passed', review_note: '' })
const canConfirmOrRetry = computed(() => authStore.hasPermission('task:approve') && task.value && (
  task.value.status === 'draft' || (
    task.value.status !== 'closed' && task.value.notification_status && task.value.notification_status !== 'success'
  )
))
const isMemberAction = computed(() => task.value?.source_type === 'member_action')
const memberAction = computed(() => task.value?.data_evidence?.member_action || {})
const recommendedProductNames = computed(() => (memberAction.value.recommended_products || []).map((item: any) => item.product_name || item.product_code).filter(Boolean).join('、') || '暂无有库存推荐')

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
function yesNo(value: boolean) { return value ? '是' : '否' }
function formatTime(value: unknown) { return value ? String(value).replace('T', ' ').slice(0, 19) : '--' }

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
  if (!retrying && isMemberAction.value) {
    const res = await taskApi.listAssignees({ store_code: task.value.related_store_code })
    if (!res.data?.success) return ElMessage.error(res.data?.message || '责任人列表加载失败')
    assigneeOptions.value = res.data.data?.items || []
    memberConfirm.assignee_id = task.value.assignee_id || memberAction.value.suggested_assignee?.user_id
    syncAssigneeName(memberConfirm.assignee_id)
    memberConfirm.member_contact_script = memberAction.value.confirmed_script || memberAction.value.suggested_script || ''
    showMemberConfirm.value = true
    return
  }
  await ElMessageBox.confirm(retrying ? '重新发送责任人通知？' : '确认派发给当前责任人？', '确认派发', { type: 'warning' })
  const res = retrying
    ? await taskApi.retryNotification(task.value.id)
    : await taskApi.confirm(task.value.id)
  const notification = res.data.data?.notification
  if (notification && !notification.success) ElMessage.warning('任务状态已保存，但责任人通知未送达，可稍后重试')
  else ElMessage.success(retrying ? '通知已重试' : '任务已派发')
  await loadTask()
}

function syncAssigneeName(value?: number) {
  memberConfirm.assignee_name = assigneeOptions.value.find(item => item.id === value)?.real_name || ''
}
function assigneeLabel(item: any) {
  const name = item.real_name || item.employee_no || item.username
  if (item.mapping_pending) return `${name}（门店映射待补）`
  return item.employee_no ? `${name}（${item.employee_no}）` : name
}

async function submitMemberConfirm() {
  if (!memberConfirm.assignee_id) return ElMessage.warning('请选择责任人')
  if (memberConfirm.member_contact_script.trim().length < 8) return ElMessage.warning('请确认完整联系话术')
  confirming.value = true
  try {
    const res = await taskApi.confirm(task.value.id, memberConfirm)
    if (!res.data?.success) throw new Error(res.data?.message || '会员行动派发失败')
    const notification = res.data.data?.notification
    showMemberConfirm.value = false
    if (notification && !notification.success) ElMessage.warning('任务已派发，但责任人通知未送达，可稍后重试')
    else ElMessage.success('会员行动已确认并派发')
    await loadTask()
  } catch (e: any) {
    ElMessage.error(e?.message || '会员行动派发失败')
  } finally {
    confirming.value = false
  }
}

async function submitFeedback() {
  if (!feedback.feedback_content.trim()) return ElMessage.warning('请填写反馈内容')
  if (isMemberAction.value && feedback.arrived && !feedback.contacted) return ElMessage.warning('未联系不能标记到店')
  if (isMemberAction.value && feedback.converted && (!feedback.linked_ticket_no.trim() || feedback.conversion_amount <= 0)) return ElMessage.warning('成交必须填写成交金额和关联百胜小票')
  if (isMemberAction.value && feedback.contacted && !feedback.converted && !feedback.no_conversion_reason.trim()) return ElMessage.warning('未成交时请填写原因')
  const payload: any = {
    request_id: feedback.request_id,
    feedback_content: feedback.feedback_content,
    action_taken: feedback.action_taken,
    result_description: feedback.result_description,
    attachment_urls: feedback.attachment_urls.split(/\r?\n/).map(v => v.trim()).filter(Boolean),
  }
  if (isMemberAction.value) payload.member_followup = {
    contacted: feedback.contacted,
    arrived: feedback.arrived,
    converted: feedback.converted,
    conversion_amount: feedback.conversion_amount,
    linked_ticket_no: feedback.linked_ticket_no.trim() || null,
    no_conversion_reason: feedback.no_conversion_reason.trim() || null,
    next_followup_at: feedback.next_followup_at || null,
  }
  await taskApi.feedback(task.value.id, payload)
  showFeedback.value = false
  ElMessage.success('反馈已提交')
  await loadTask()
}

function openFeedback() {
  Object.assign(feedback, {
    request_id: crypto.randomUUID(),
    feedback_content: '', action_taken: '', result_description: '', attachment_urls: '',
    contacted: false, arrived: false, converted: false, conversion_amount: 0,
    linked_ticket_no: '', no_conversion_reason: '', next_followup_at: '',
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
.member-action-panel { margin-top: 16px; padding: 14px; border: 1px solid #e5e7eb; border-radius: 8px; background: #f8fafc; }
.member-action-title { margin-bottom: 10px; color: #0f172a; font-size: 15px; font-weight: 700; }
.member-action-panel .el-alert { margin-top: 10px; }
.followup-result { display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 8px 0; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; background: #f8fafc; color: #475569; font-size: 13px; }
</style>
