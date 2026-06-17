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
              <el-upload ref="uploadRef" :auto-upload="false" accept=".xlsx,.xls,.csv"
                :on-change="(file:any) => selectedFile = file.raw" :limit="1">
                <el-button>选择文件</el-button>
                <template #tip><div style="color:#999;font-size:12px">支持 .xlsx .xls .csv，最大50MB</div></template>
              </el-upload>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleImport" :loading="importing" :disabled="!dataType||!selectedFile">
                开始导入
              </el-button>
            </el-form-item>
          </el-form>
          <el-alert v-if="importResult" :title="importResult.message" :type="importResult.status===success?\"success\":\"warning\""
            :description="importResult.detail" show-icon style="margin-top:12px" />
        </el-card>
      </el-col>
      <el-col :span="14">
        <el-card>
          <template #header>同步状态</template>
          <el-table :data="syncStatus" stripe size="small">
            <el-table-column prop="data_type" label="数据类型" />
            <el-table-column prop="status" label="状态">
              <template #default="{row}">
                <el-tag :type="row.status==\"success\"?\"success\":row.status==\"failed\"?\"danger\":\"info\"">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="success_rows" label="成功行" width="80" />
            <el-table-column prop="error_rows" label="失败行" width="80" />
            <el-table-column prop="last_sync_at" label="最后同步" show-overflow-tooltip />
          </el-table>
          <el-button @click="loadStatus" style="margin-top:8px" size="small">刷新</el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from "vue";
import { syncApi } from "@/api/sync";
import { ElMessage } from "element-plus";
const dataType = ref("");
const selectedFile = ref<File | null>(null);
const importing = ref(false);
const importResult = ref<any>(null);
const syncStatus = ref<any[]>([]);
const dataTypes = [
  { label: "销售单", value: "sales_order" },
  { label: "销售明细", value: "sales_detail" },
  { label: "退货单", value: "return_order" },
  { label: "退货明细", value: "return_detail" },
  { label: "库存快照", value: "inventory" },
  { label: "会员资料", value: "member" },
  { label: "员工资料", value: "employee" },
  { label: "门店资料", value: "store" },
  { label: "商品资料", value: "product" },
  { label: "SKU资料", value: "sku" },
];
const handleImport = async () => {
  if (!dataType.value || !selectedFile.value) return;
  importing.value = true;
  importResult.value = null;
  try {
    const res = await syncApi.importExcel(dataType.value, selectedFile.value);
    const d = res.data.data;
    importResult.value = {
      status: d.status,
      message: res.data.message,
      detail: `总行数:${d.total_rows} 成功:${d.success_rows} 重复:${d.duplicate_rows} 失败:${d.error_rows}`,
    };
    ElMessage.success("导入完成");
    loadStatus();
  } catch (e: any) {
    importResult.value = { status: "failed", message: "导入失败", detail: e.message };
  } finally { importing.value = false; }
};
const loadStatus = async () => {
  try {
    const res = await syncApi.getStatus();
    syncStatus.value = res.data.data || [];
  } catch {}
};
onMounted(loadStatus);
</script>
<style scoped>
.page-container { padding: 0; }
.page-header { margin-bottom: 16px; }
.page-header h2 { font-size: 18px; color: #333; }
</style>
