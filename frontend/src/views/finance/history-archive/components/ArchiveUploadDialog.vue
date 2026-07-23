<template>
  <el-dialog :model-value="modelValue" title="上传历史数据" width="820px" :close-on-click-modal="false" @close="close">
    <el-alert title="文件只做安全存档，不解析或写入其他财务模块；删除后仅进入回收站。" type="info" :closable="false" show-icon />
    <el-form label-position="top" class="upload-form">
      <div class="form-grid">
        <el-form-item label="数据名称" required><el-input v-model="form.dataName" maxlength="200" /></el-form-item>
        <el-form-item label="数据分类" required>
          <el-cascader v-model="form.categoryPath" :options="categories" :props="categoryProps" clearable filterable placeholder="选择一级/二级/三级分类" />
        </el-form-item>
        <el-form-item label="所属项目"><el-select v-model="form.projectName" filterable allow-create clearable><el-option v-for="item in options.projects" :key="item" :label="item" :value="item" /></el-select></el-form-item>
        <el-form-item label="公司主体"><el-select v-model="form.companyName" filterable allow-create clearable><el-option v-for="item in options.companies" :key="item" :label="item" :value="item" /></el-select></el-form-item>
        <el-form-item label="所属店铺"><el-select v-model="form.storeId" filterable clearable><el-option v-for="item in options.stores" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
        <el-form-item label="数据类型" required><el-select v-model="form.dataType"><el-option v-for="item in DATA_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
        <el-form-item label="数据年份" required><el-date-picker v-model="form.year" type="year" value-format="YYYY" format="YYYY年" /></el-form-item>
        <el-form-item label="数据月份" required><el-select v-model="form.month"><el-option v-for="month in 12" :key="month" :label="`${month}月`" :value="month" /></el-select></el-form-item>
        <el-form-item label="数据日期范围" class="range-item"><el-date-picker v-model="form.dateRange" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期" /></el-form-item>
        <el-form-item label="数据说明" class="description-item"><el-input v-model="form.description" type="textarea" :rows="2" maxlength="4000" show-word-limit /></el-form-item>
      </div>
      <el-form-item label="文件（Excel / CSV / PDF）" required>
        <el-upload drag action="#" accept=".xlsx,.xls,.xlsm,.csv,.pdf" :limit="1" :auto-upload="false" :on-change="onFile" :on-remove="removeFile">
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入文件，或<em>点击选择</em></div>
          <template #tip><div class="el-upload__tip">单个文件默认不超过 50MB</div></template>
        </el-upload>
      </el-form-item>
      <el-progress v-if="uploading" :percentage="progress" />
    </el-form>
    <template #footer><el-button :disabled="uploading" @click="close">取消</el-button><el-button type="primary" :loading="uploading" @click="submit">确认上传</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import type { UploadFile, UploadRawFile } from "element-plus"
import { UploadFilled } from "@element-plus/icons-vue"
import { DATA_TYPE_OPTIONS, uploadArchiveFile } from "@/api/historyArchive"
import type { ArchiveCategory, ArchiveDataType, ArchiveOptions } from "@/api/historyArchive"

defineProps<{ modelValue: boolean; categories: ArchiveCategory[]; options: ArchiveOptions }>()
const emit = defineEmits<{ (e:"update:modelValue", value:boolean):void; (e:"complete"):void }>()
const categoryProps = { value: "id", label: "name", children: "children", checkStrictly: true, emitPath: true }
const form = reactive({ dataName:"", categoryPath:[] as number[], projectName:"", companyName:"", storeId:undefined as number|undefined, year:String(new Date().getFullYear()), month:new Date().getMonth()+1, dateRange:[] as string[], dataType:"RAW_DATA" as ArchiveDataType, description:"" })
const rawFile = ref<UploadRawFile | null>(null)
const uploading = ref(false)
const progress = ref(0)
function onFile(file: UploadFile) { rawFile.value = file.raw || null; if (!form.dataName) form.dataName = file.name.replace(/\.(xlsx|xlsm|xls|csv|pdf)$/i, "") }
function removeFile() { rawFile.value = null }
function reset() { Object.assign(form,{dataName:"",categoryPath:[],projectName:"",companyName:"",storeId:undefined,year:String(new Date().getFullYear()),month:new Date().getMonth()+1,dateRange:[],dataType:"RAW_DATA",description:""}); rawFile.value=null; progress.value=0 }
function close() { if (uploading.value) return; emit("update:modelValue",false); reset() }
async function submit() {
  if (!form.dataName.trim()) return ElMessage.warning("请填写数据名称")
  if (!form.categoryPath.length) return ElMessage.warning("请选择数据分类")
  if (!form.year || !form.month) return ElMessage.warning("请选择数据年份和月份")
  if (!rawFile.value) return ElMessage.warning("请选择文件")
  const body = new FormData()
  body.append("file",rawFile.value); body.append("data_name",form.dataName.trim()); body.append("category_id",String(form.categoryPath[form.categoryPath.length-1]))
  body.append("data_year",form.year); body.append("data_month",String(form.month)); body.append("data_type",form.dataType)
  if(form.projectName) body.append("project_name",form.projectName); if(form.companyName) body.append("company_name",form.companyName)
  if(form.storeId) body.append("store_id",String(form.storeId)); if(form.dateRange[0]) body.append("data_start_date",form.dateRange[0]); if(form.dateRange[1]) body.append("data_end_date",form.dateRange[1])
  if(form.description) body.append("description",form.description)
  uploading.value=true
  try { await uploadArchiveFile(body,value=>progress.value=value); ElMessage.success("历史数据上传成功"); emit("complete"); close() }
  catch(error:any){ ElMessage.error(error?.response?.data?.detail || "上传失败") }
  finally { uploading.value=false }
}
</script>

<style scoped>
.upload-form{margin-top:18px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 16px}.form-grid :deep(.el-select),.form-grid :deep(.el-cascader),.form-grid :deep(.el-date-editor){width:100%}.range-item,.description-item{grid-column:1/-1}.upload-form :deep(.el-upload),.upload-form :deep(.el-upload-dragger){width:100%}@media(max-width:700px){.form-grid{grid-template-columns:1fr}.range-item,.description-item{grid-column:auto}}
</style>
