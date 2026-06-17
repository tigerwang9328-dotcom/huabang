<template>
  <div class="page-container">
    <div class="page-header"><h2>数据同步</h2></div>
    <el-row :gutter="16">
      <el-col :span="10">
        <el-card>
          <template #header>Excel数据导入</template>
          <el-form label-width="100px">
            <el-form-item label="数据类型">
              <el-select v-model="dataType" placeholder="选择数据类型" style="width:100%">
                <el-option v-for="t in dataTypes" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="Excel文件">
              <el-upload
                ref="uploadRef"
                :auto-upload="false"
                accept=".xlsx,.xls,.csv"
                :on-change="(file: any) => { selectedFile = file.raw }"
                :limit="1"
              >
                <el-button>选择文件</el-button>
                <template #tip><div style="color:#999;font-size:12px">支持 .xlsx .xls .csv，最大50MB</div></template>
              </el-upload>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handlePreview" :loading="previewing" :disabled="!dataType || !selectedFile">
                预览字段
              </el-button>
              <el-button type="success" @click="handleImport" :loading="importing" :disabled="!dataType || !selectedFile" style="margin-left:8px">
                直接导入
              </el-button>
            </el-form-item>
          </el-form>

          <div v-if="previewData" style="margin-top:16px">
            <el-divider>字段预览（前3行）</el-divider>
            <el-table :data="previewData.rows" size="small" max-height="200">
              <el-table-column v-for="col in previewData.columns" :key="col" :prop="col" :label="col" show-overflow-tooltip />
            </el-table>
            <el-alert type="info" :title="'识别到 ' + previewData.columns.length + ' 列，' + previewData.total_rows + ' 行数据'" show-icon style="margin-top:8px" />
          </div>

          <el-alert v-if="importResult" :title="importResult.message"
            :type="importResult.status === 'success' ? 'success' : 'warning'"
            :description="importResult.detail" show-icon style="margin-top:12px" />
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card style="margin-bottom:16px">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>同步状态</span>
              <div>
                <el-button size="small" type="primary" @click="triggerEtl" :loading="etlRunning">手动触发ETL</el-button>
                <el-button size="small" @click="loadStatus" style="margin-left:4px">刷新</el-button>
              </div>
            </div>
          </template>
          <div v-if="etlStatus" style="margin-bottom:8px">
            <el-tag :type="etlStatus.status === 'success' ? 'success' : etlStatus.status === 'running' ? 'primary' : 'info'">
              ETL: {{ etlStatus.status }}
            </el-tag>
            <span style="font-size:12px;color:#999;margin-left:8px">{{ etlStatus.last_run_at }}</span>
          </div>
          <el-table :data="syncStatus" stripe size="small">
            <el-table-column prop="data_type" label="数据类型" />
            <el-table-column prop="status" label="状态">
              <template #default="{ row }">
                <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'info'">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="success_rows" label="成功行" width="70" />
            <el-table-column prop="error_rows" label="失败行" width="70" />
            <el-table-column prop="batch_no" label="批次号" show-overflow-tooltip />
            <el-table-column prop="last_sync_at" label="最后同步" show-overflow-tooltip />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button v-if="row.batch_no" size="small" type="danger" plain @click="rollback(row.batch_no)">回滚</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card>
          <template #header>ETL日志（最近5次）</template>
          <el-table :data="etlLogs" stripe size="small">
            <el-table-column prop="task_name" label="任务" width="120" />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'success' ? 'success' : row.status === 'running' ? 'primary' : 'danger'">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="input_rows" label="输入" width="60" />
            <el-table-column prop="output_rows" label="输出" width="60" />
            <el-table-column prop="started_at" label="开始时间" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { syncApi } from '@/api/sync'
import { ElMessage, ElMessageBox } from 'element-plus'

const dataType = ref('')
const selectedFile = ref<File | null>(null)
const importing = ref(false)
const previewing = ref(false)
const etlRunning = ref(false)
const importResult = ref<any>(null)
const previewData = ref<any>(null)
const syncStatus = ref<any[]>([])
const etlLogs = ref<any[]>([])
const etlStatus = ref<any>(null)

const dataTypes = [
  { label: '门店资料', value: 'store' },
  { label: '商品资料', value: 'product' },
  { label: 'SKU/条码', value: 'sku' },
  { label: '销售明细', value: 'sales_detail' },
  { label: '退货明细', value: 'return_detail' },
  { label: '库存余额', value: 'inventory' },
  { label: '会员资料', value: 'member' },
  { label: '导购资料', value: 'employee' },
  { label: '调拨明细', value: 'transfer' },
  { label: '商品成本', value: 'product_cost' },
  { label: '销售单', value: 'sales_order' },
]

const handlePreview = async () => {
  if (!dataType.value || !selectedFile.value) return
  previewing.value = true
  previewData.value = null
  try {
    const res = await syncApi.previewExcel(dataType.value, selectedFile.value)
    previewData.value = res.data.data
  } catch (e: any) {
    ElMessage.error('预览失败：' + e.message)
  } finally {
    previewing.value = false
  }
}

const handleImport = async () => {
  if (!dataType.value || !selectedFile.value) return
  importing.value = true
  importResult.value = null
  try {
    const res = await syncApi.importExcel(dataType.value, selectedFile.value)
    const d = res.data.data
    importResult.value = {
      status: d.status,
      message: res.data.message,
      detail: `总行数:${d.total_rows} 成功:${d.success_rows} 重复:${d.duplicate_rows} 失败:${d.error_rows}  批次:${d.batch_no}`,
    }
    ElMessage.success('导入完成')
    loadStatus()
  } catch (e: any) {
    importResult.value = { status: 'failed', message: '导入失败', detail: e.message }
  } finally {
    importing.value = false
  }
}

const rollback = async (batchNo: string) => {
  await ElMessageBox.confirm(`确认回滚批次 ${batchNo}？此操作将删除该批次导入的所有数据`, '危险操作', { type: 'warning' })
  try {
    await syncApi.rollbackBatch(batchNo)
    ElMessage.success('回滚成功')
    loadStatus()
  } catch (e: any) {
    ElMessage.error('回滚失败：' + e.message)
  }
}

const triggerEtl = async () => {
  etlRunning.value = true
  try {
    const res = await syncApi.runEtl()
    ElMessage.success(res.data.message || 'ETL已触发')
    setTimeout(loadStatus, 2000)
  } catch (e: any) {
    ElMessage.error('ETL触发失败：' + e.message)
  } finally {
    etlRunning.value = false
  }
}

const loadStatus = async () => {
  try {
    const [r1, r2, r3] = await Promise.all([
      syncApi.getStatus().catch(() => ({ data: { data: [] } })),
      syncApi.getEtlLogs().catch(() => ({ data: { data: [] } })),
      syncApi.getEtlStatus().catch(() => ({ data: { data: null } })),
    ])
    syncStatus.value = r1.data.data || []
    etlLogs.value = r2.data.data || []
    etlStatus.value = r3.data.data
  } catch {}
}

onMounted(loadStatus)
</script>

<style scoped>
.page-container { padding: 0; }
.page-header { margin-bottom: 16px; }
.page-header h2 { font-size: 18px; color: #333; }
</style>
