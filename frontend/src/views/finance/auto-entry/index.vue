<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div>
        <h3 style="margin:0">自动凭证生成</h3>
        <p style="margin:4px 0 0;color:#909399;font-size:12px">从业务数据自动生成会计凭证，同一期间幂等（重复触发自动跳过）</p>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <el-date-picker v-model="period" type="month" format="YYYY-MM" value-format="YYYY-MM"
          placeholder="选择期间" style="width:140px" @change="loadPreview" />
        <el-button @click="loadPreview" :loading="previewLoading">预览</el-button>
      </div>
    </div>

    <!-- 预览卡片 -->
    <el-row :gutter="12" v-if="preview" style="margin-bottom:20px">
      <!-- 销售凭证 -->
      <el-col :span="8">
        <el-card shadow="never" :class="['entry-card', preview.sales.already_generated ? 'done' : '']">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span style="font-weight:600"><el-icon><ShoppingCart /></el-icon> 销售自动入账</span>
              <el-tag v-if="preview.sales.already_generated" type="success" size="small">已生成 {{ preview.sales.already_generated }}</el-tag>
              <el-tag v-else type="info" size="small">待生成</el-tag>
            </div>
          </template>
          <div class="preview-row"><span>净销售额</span><span>{{ fmt(preview.sales.net_sales) }}</span></div>
          <div class="preview-row"><span>净销售成本</span><span>{{ fmt(preview.sales.net_cogs) }}</span></div>
          <div class="preview-row"><span>广告费</span><span>{{ fmt(preview.sales.ad_cost) }}</span></div>
          <div style="margin-top:12px">
            <el-button type="primary" size="small" :disabled="!!preview.sales.already_generated || running.sales"
              :loading="running.sales" @click="trigger('sales')" style="width:100%">
              {{ preview.sales.already_generated ? '已生成' : '生成销售凭证' }}
            </el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 工资凭证 -->
      <el-col :span="8">
        <el-card shadow="never" :class="['entry-card', preview.payroll.already_generated ? 'done' : '']">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span style="font-weight:600"><el-icon><User /></el-icon> 工资自动入账</span>
              <el-tag v-if="preview.payroll.already_generated" type="success" size="small">已生成 {{ preview.payroll.already_generated }}</el-tag>
              <el-tag v-else type="info" size="small">待生成</el-tag>
            </div>
          </template>
          <div class="preview-row"><span>待处理记录</span><span>{{ preview.payroll.pending_records }} 条</span></div>
          <div class="preview-row"><span>应发工资合计</span><span>{{ fmt(preview.payroll.total_gross) }}</span></div>
          <div class="preview-row" style="color:#909399;font-size:12px">
            <span>生成后自动回写 voucher_id</span>
          </div>
          <div style="margin-top:12px">
            <el-button type="primary" size="small"
              :disabled="!!preview.payroll.already_generated || preview.payroll.pending_records === 0 || running.payroll"
              :loading="running.payroll" @click="trigger('payroll')" style="width:100%">
              {{ preview.payroll.already_generated ? '已生成' : preview.payroll.pending_records === 0 ? '无待处理记录' : '生成工资凭证' }}
            </el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 折旧凭证 -->
      <el-col :span="8">
        <el-card shadow="never" :class="['entry-card', preview.depreciation.already_generated ? 'done' : '']">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span style="font-weight:600"><el-icon><OfficeBuilding /></el-icon> 折旧自动入账</span>
              <el-tag v-if="preview.depreciation.already_generated" type="success" size="small">已生成 {{ preview.depreciation.already_generated }}</el-tag>
              <el-tag v-else type="info" size="small">待生成</el-tag>
            </div>
          </template>
          <div class="preview-row"><span>在用资产数</span><span>{{ preview.depreciation.asset_count }} 项</span></div>
          <div class="preview-row"><span>月折旧总额</span><span>{{ fmt(preview.depreciation.total_monthly_depre) }}</span></div>
          <div class="preview-row" style="color:#909399;font-size:12px">
            <span>生成后自动更新累计折旧/净值</span>
          </div>
          <div style="margin-top:12px">
            <el-button type="primary" size="small"
              :disabled="!!preview.depreciation.already_generated || preview.depreciation.asset_count === 0 || running.depreciation"
              :loading="running.depreciation" @click="trigger('depreciation')" style="width:100%">
              {{ preview.depreciation.already_generated ? '已生成' : preview.depreciation.asset_count === 0 ? '无在用资产' : '生成折旧凭证' }}
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 一键月结 -->
    <el-card shadow="never" v-if="preview" style="margin-bottom:20px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <div style="font-weight:600;font-size:15px">一键月结</div>
          <div style="color:#909399;font-size:12px;margin-top:4px">同时触发销售+工资+折旧三类凭证，各类独立执行互不影响</div>
        </div>
        <el-button type="warning" :loading="running.all" @click="triggerAll">
          一键生成 {{ period }} 所有凭证
        </el-button>
      </div>
    </el-card>

    <!-- 执行结果 -->
    <el-card shadow="never" v-if="lastResult" style="margin-top:12px">
      <template #header><span style="font-weight:600">最近执行结果</span></template>
      <el-alert v-for="(res, type) in lastResult.details" :key="type"
        :type="res.ok ? 'success' : 'warning'"
        :title="`${typeLabel(type as string)}：${res.message}`"
        :closable="false" style="margin-bottom:8px" show-icon />
      <div style="color:#606266;font-size:13px;margin-top:8px">
        成功 {{ lastResult.success_count }} / 共 {{ lastResult.total }} 类
      </div>
    </el-card>

    <el-empty v-if="!preview && !previewLoading" description="请先选择期间，点击预览查看可生成的凭证" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ShoppingCart, User, OfficeBuilding } from '@element-plus/icons-vue'
import request from '@/api/request'
import { useFinanceStore } from '@/stores/finance'

const finStore = useFinanceStore()
const period = ref(finStore.currentPeriod || new Date().toISOString().slice(0, 7))
const preview = ref<any>(null)
const previewLoading = ref(false)
const running = ref({ sales: false, payroll: false, depreciation: false, all: false })
const lastResult = ref<any>(null)

const fmt = (v: number) => '¥' + (v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const typeLabel = (t: string) => ({ sales: '销售入账', payroll: '工资入账', depreciation: '折旧计提' }[t] || t)

async function loadPreview() {
  if (!period.value) return
  previewLoading.value = true
  try {
    preview.value = await request.get(`/finance/auto-entry/preview?book_id=${finStore.bookId}&period=${period.value}`)
  } catch (e: any) {
    ElMessage.error('加载预览失败')
  } finally {
    previewLoading.value = false
  }
}

async function trigger(type: 'sales' | 'payroll' | 'depreciation') {
  running.value[type] = true
  try {
    const res: any = await request.post(`/finance/auto-entry/${type}`, {
      book_id: finStore.bookId,
      period: period.value,
      auto_post: true,
    })
    if (res.ok) {
      ElMessage.success(res.message)
    } else {
      ElMessage.warning(res.message)
    }
    await loadPreview()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    running.value[type] = false
  }
}

async function triggerAll() {
  running.value.all = true
  try {
    const res: any = await request.post('/finance/auto-entry/all', {
      book_id: finStore.bookId,
      period: period.value,
      auto_post: true,
    })
    lastResult.value = res
    ElMessage.success(`月结完成，成功 ${res.success_count}/${res.total} 类`)
    await loadPreview()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '月结失败')
  } finally {
    running.value.all = false
  }
}

onMounted(loadPreview)
</script>

<style scoped>
.entry-card { height: 100%; }
.entry-card.done { opacity: 0.8; }
.preview-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 13px;
  border-bottom: 1px solid #f0f0f0;
}
.preview-row:last-child { border-bottom: none; }
</style>
