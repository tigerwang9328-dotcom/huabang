<template>
  <div class="register-audit-page">
    <div class="page-header">
      <div>
        <h2>注册审核</h2>
        <p>审核登录页提交的账号注册申请，通过后自动创建用户并绑定申请岗位。</p>
      </div>
      <el-button @click="load" :loading="loading">刷新</el-button>
    </div>

    <div class="stat-grid">
      <el-card class="stat-card pending"><span>待审核</span><strong>{{ counts.pending }}</strong></el-card>
      <el-card class="stat-card approved"><span>已通过</span><strong>{{ counts.approved }}</strong></el-card>
      <el-card class="stat-card rejected"><span>已驳回</span><strong>{{ counts.rejected }}</strong></el-card>
    </div>

    <el-card>
      <template #header>
        <div class="card-head">
          <span>申请列表</span>
          <el-radio-group v-model="status" size="small" @change="load">
            <el-radio-button label="pending">待审核</el-radio-button>
            <el-radio-button label="approved">已通过</el-radio-button>
            <el-radio-button label="rejected">已驳回</el-radio-button>
            <el-radio-button label="">全部</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <el-table :data="items" stripe v-loading="loading" empty-text="暂无注册申请">
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column prop="real_name" label="姓名" width="110" />
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column label="申请岗位" width="130">
          <template #default="{ row }"><el-tag>{{ roleName(row.apply_role) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="department" label="部门/门店" min-width="150" show-overflow-tooltip />
        <el-table-column prop="store_code" label="门店编码" width="110" />
        <el-table-column prop="remark" label="申请说明" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusName(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="申请时间" width="190" />
        <el-table-column prop="reviewed_by" label="审核人" width="110" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button size="small" type="success" @click="approve(row)">通过</el-button>
              <el-button size="small" type="danger" @click="reject(row)">驳回</el-button>
            </template>
            <span v-else class="muted">已处理</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { systemApi } from '@/api/system'

const loading = ref(false)
const status = ref('pending')
const items = ref<any[]>([])
const allItems = ref<any[]>([])
const roleMap: Record<string, string> = {
  boss: 'BOSS', ceo: '总经理', product_manager: '商品经理', product_specialist: '商品专员',
  finance_manager: '财务经理', accountant: '会计', cashier: '出纳', warehouse_manager: '仓库主管',
  operation_manager: '运营经理', store_manager: '店长', guide: '导购', super_admin: '超级管理员'
}
const roleName = (code: string) => roleMap[code] || code || '-'
const statusName = (s: string) => ({ pending: '待审核', approved: '已通过', rejected: '已驳回' } as any)[s] || s
const statusType = (s: string) => ({ pending: 'warning', approved: 'success', rejected: 'danger' } as any)[s] || 'info'
const counts = computed(() => ({
  pending: allItems.value.filter(i => i.status === 'pending').length,
  approved: allItems.value.filter(i => i.status === 'approved').length,
  rejected: allItems.value.filter(i => i.status === 'rejected').length,
}))

const load = async () => {
  loading.value = true
  try {
    const [filtered, all] = await Promise.all([
      systemApi.getRegisterApplications({ status: status.value || undefined }),
      systemApi.getRegisterApplications(),
    ])
    items.value = filtered.data.data?.items || []
    allItems.value = all.data.data?.items || []
  } finally { loading.value = false }
}

const approve = async (row: any) => {
  await ElMessageBox.confirm(`确认通过 ${row.real_name || row.username} 的注册申请，并创建账号 ${row.username}？`, '通过注册申请', { type: 'warning' })
  await systemApi.approveRegisterApplication(row.id)
  ElMessage.success('已通过申请并创建账号')
  load()
}

const reject = async (row: any) => {
  const { value } = await ElMessageBox.prompt('请输入驳回原因', '驳回注册申请', {
    inputPlaceholder: '例如：岗位信息不完整 / 非授权人员',
    confirmButtonText: '确认驳回',
    cancelButtonText: '取消',
  })
  await systemApi.rejectRegisterApplication(row.id, { reason: value })
  ElMessage.success('已驳回申请')
  load()
}

onMounted(load)
</script>

<style scoped>
.register-audit-page{padding:0}.page-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.page-header h2{font-size:20px;margin:0 0 6px;color:#0f172a}.page-header p{margin:0;color:#64748b}.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:16px}.stat-card span{display:block;color:#64748b;font-size:13px}.stat-card strong{font-size:28px;color:#0f172a}.stat-card.pending strong{color:#d97706}.stat-card.approved strong{color:#16a34a}.stat-card.rejected strong{color:#dc2626}.card-head{display:flex;justify-content:space-between;align-items:center}.muted{color:#94a3b8;font-size:12px}@media(max-width:900px){.stat-grid{grid-template-columns:1fr}.card-head{align-items:flex-start;gap:12px;flex-direction:column}}
</style>
