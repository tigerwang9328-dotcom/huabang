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

        <el-divider>反馈记录</el-divider>
        <div v-if="task.feedbacks?.length">
          <el-card v-for="fb in task.feedbacks" :key="fb.id" style="margin-bottom:12px">
            <p><strong>反馈内容：</strong>{{ fb.content }}</p>
            <p v-if="fb.action_taken"><strong>行动：</strong>{{ fb.action_taken }}</p>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { taskApi } from '@/api/task'

const route = useRoute()
const task = ref<any>(null)
const loading = ref(true)

const statusType: Record<string, string> = {
  pending: 'warning', processing: 'primary', overdue: 'danger',
  review_passed: 'success', draft: 'info', closed: 'info',
  feedback_submitted: 'warning', cancelled: 'info',
}
const statusLabel: Record<string, string> = {
  pending: '待处理', processing: '处理中', overdue: '已逾期',
  review_passed: '复查通过', draft: '草稿', closed: '已关闭',
  feedback_submitted: '待复查', cancelled: '已取消',
}

onMounted(async () => {
  try {
    const res = await taskApi.getDetail(Number(route.params.id))
    task.value = res.data.data
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page-container { padding: 0; }
</style>
