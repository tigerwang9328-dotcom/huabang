<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <h3 style="margin:0;font-size:18px;font-weight:700;color:var(--text-1)">银行余额调节表</h3>
      <el-button @click="load" :loading="loading">
        <el-icon style="margin-right:4px"><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <!-- 账户选择 -->
    <el-card shadow="never" style="margin-bottom:20px">
      <div style="display:flex;align-items:center;gap:12px">
        <span style="font-size:14px;color:var(--text-3);white-space:nowrap">选择账户：</span>
        <el-select v-model="selectedAccountId" style="width:220px" placeholder="请选择出纳账户"
          @change="load" :loading="acctLoading">
          <el-option v-for="a in accounts" :key="a.id" :label="a.account_name" :value="a.id" />
        </el-select>
        <span style="font-size:12px;color:#909399">与账簿 1002「银行存款」科目余额进行对比</span>
      </div>
    </el-card>

    <!-- 调节表主体 -->
    <template v-if="data">
      <!-- 平衡状态提示 -->
      <el-alert
        :type="data.is_balanced ? 'success' : 'warning'"
        :title="data.is_balanced ? '账实相符：出纳账户余额与账簿余额一致' : `存在差异：差异金额 ¥${data.difference}`"
        :closable="false"
        show-icon
        style="margin-bottom:16px"
      />

      <!-- 余额对比卡片 -->
      <el-row :gutter="16" style="margin-bottom:20px">
        <el-col :span="6">
          <el-card shadow="never" class="bal-card">
            <div class="bal-label">账户名称</div>
            <div class="bal-value" style="font-size:15px">{{ data.account_name }}</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="bal-card">
            <div class="bal-label">出纳账面余额</div>
            <div class="bal-value primary">{{ fmt(data.cashier_balance) }}</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="bal-card">
            <div class="bal-label">账簿余额（1002）</div>
            <div class="bal-value">{{ fmt(data.ledger_balance) }}</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="bal-card">
            <div class="bal-label">差异金额</div>
            <div class="bal-value" :class="Math.abs(data.difference) < 0.01 ? 'success' : 'danger'">
              {{ fmt(data.difference) }}
            </div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 未达账项 -->
      <el-card shadow="never">
        <template #header>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-weight:600">未达账项（出纳有记录但账簿无凭证）</span>
            <el-tag type="warning" size="small">{{ data.unmatched_items.length }} 笔</el-tag>
          </div>
        </template>

        <el-table :data="data.unmatched_items" stripe border>
          <el-table-column prop="flow_date" label="日期" width="110" />
          <el-table-column prop="flow_type" label="方向" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.flow_type === 'in' ? 'success' : 'danger'" size="small">
                {{ row.flow_type === 'in' ? '收入' : '支出' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="金额" width="130" align="right">
            <template #default="{ row }">{{ fmt(row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="category" label="类别" width="110" show-overflow-tooltip />
          <el-table-column prop="counterpart" label="对方" min-width="130" show-overflow-tooltip />
          <el-table-column prop="remark" label="备注" min-width="150" show-overflow-tooltip />
        </el-table>
        <el-empty v-if="data.unmatched_items.length === 0"
          description="暂无未达账项，账实核对完毕" />
      </el-card>
    </template>

    <!-- 未选账户时的空状态 -->
    <el-card v-else-if="!loading" shadow="never">
      <el-empty description="请先选择要核对的出纳账户" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import request from '@/api/request'
import { useFinanceStore } from '@/stores/finance'

const finStore = useFinanceStore()
const loading     = ref(false)
const acctLoading = ref(false)
const accounts    = ref<any[]>([])
const selectedAccountId = ref<number | null>(null)
const data = ref<any>(null)

const fmt = (v: number) =>
  '¥' + (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

async function loadAccounts() {
  acctLoading.value = true
  try {
    const res: any = await request.get(`/finance/cashier/accounts?book_id=${finStore.bookId}`)
    accounts.value = res.rows || []
  } catch {
    ElMessage.error('加载账户列表失败')
  } finally {
    acctLoading.value = false
  }
}

async function load() {
  if (!selectedAccountId.value) {
    data.value = null
    return
  }
  loading.value = true
  try {
    const res: any = await request.get(
      `/finance/bank-reconciliation?book_id=${finStore.bookId}&account_id=${selectedAccountId.value}`
    )
    if (res.error) {
      ElMessage.warning(res.error)
      data.value = null
    } else {
      data.value = res
    }
  } catch {
    ElMessage.error('加载调节表失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadAccounts()
  // 自动选中第一个账户
  if (accounts.value.length > 0) {
    selectedAccountId.value = accounts.value[0].id
    await load()
  }
})
</script>

<style scoped>
.bal-card { text-align: center; }
.bal-label {
  font-size: 12px; color: var(--text-4, #9ca3af); margin-bottom: 6px;
}
.bal-value {
  font-size: 20px; font-weight: 700; color: var(--text-1, #1e293b);
}
.bal-value.primary { color: #409eff; }
.bal-value.success { color: #67c23a; }
.bal-value.danger  { color: #f56c6c; }
</style>
