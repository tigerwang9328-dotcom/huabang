<template>
  <el-drawer :model-value="modelValue" title="数据资产详情" size="560px" @open="open" @close="emit('update:modelValue',false)">
    <template v-if="file">
      <div class="detail-heading"><div class="extension">{{ file.file_extension.replace('.','') }}</div><div><h3>{{ file.data_name }}</h3><p>{{ file.original_filename }}</p></div></div>
      <div v-if="!editing" class="detail-grid">
        <span>分类<b>{{ file.category_path_text }}</b></span><span>数据类型<b>{{ typeLabel(file.data_type) }}</b></span>
        <span>所属项目<b>{{ file.project_name||'-' }}</b></span><span>公司主体<b>{{ file.company_name||'-' }}</b></span>
        <span>所属店铺<b>{{ file.store_name||'-' }}</b></span><span>数据期间<b>{{ file.data_year }}年{{ file.data_month }}月</b></span>
        <span>日期范围<b>{{ file.data_start_date||'-' }} 至 {{ file.data_end_date||'-' }}</b></span><span>上传人<b>{{ file.uploader_name||'-' }}</b></span>
        <span>文件大小<b>{{ formatSize(file.file_size) }}</b></span><span>存储方式<b>{{ file.storage_provider }}</b></span>
        <span class="wide">数据说明<b>{{ file.description||'-' }}</b></span><span class="wide hash">MD5<b>{{ file.md5||'历史文件未计算' }}</b></span><span class="wide hash">SHA256<b>{{ file.sha256 }}</b></span>
      </div>
      <el-form v-else label-position="top" class="edit-form">
        <el-form-item label="数据名称"><el-input v-model="form.data_name" /></el-form-item>
        <el-form-item label="数据分类"><el-cascader v-model="form.categoryPath" :options="categories" :props="categoryProps" clearable filterable /></el-form-item>
        <div class="two"><el-form-item label="所属项目"><el-input v-model="form.project_name" /></el-form-item><el-form-item label="公司主体"><el-input v-model="form.company_name" /></el-form-item></div>
        <div class="two"><el-form-item label="所属店铺"><el-select v-model="form.store_id" clearable filterable><el-option v-for="item in options.stores" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="数据类型"><el-select v-model="form.data_type"><el-option v-for="item in DATA_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item></div>
        <div class="two"><el-form-item label="年份"><el-input-number v-model="form.data_year" :min="1900" :max="2100" /></el-form-item><el-form-item label="月份"><el-input-number v-model="form.data_month" :min="1" :max="12" /></el-form-item></div>
        <el-form-item label="数据说明"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存修改</el-button><el-button @click="editing=false">取消</el-button>
      </el-form>
      <div class="section-title"><b>操作记录</b><el-button v-if="canUpdate&&file.status==='NORMAL'&&!editing" link type="primary" @click="startEdit">编辑元数据</el-button></div>
      <el-timeline v-loading="logsLoading">
        <el-timeline-item v-for="item in logs" :key="item.id" :timestamp="formatDate(item.operation_time)" placement="top">
          <div class="log-card"><b>{{ operationLabel(item.operation_type) }}</b><span>{{ item.operation_user_name||'系统' }}<template v-if="item.ip_address"> · {{ item.ip_address }}</template></span><p>{{ detailText(item) }}</p></div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-if="!logsLoading&&!logs.length" description="暂无操作记录" />
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import { DATA_TYPE_OPTIONS, getArchiveLogs, updateArchiveFile } from "@/api/historyArchive"
import type { ArchiveCategory, ArchiveFile, ArchiveLog, ArchiveOptions } from "@/api/historyArchive"

const props=defineProps<{modelValue:boolean;file:ArchiveFile|null;categories:ArchiveCategory[];options:ArchiveOptions;canUpdate:boolean}>()
const emit=defineEmits<{(e:"update:modelValue",value:boolean):void;(e:"complete"):void}>()
const categoryProps={value:"id",label:"name",children:"children",checkStrictly:true,emitPath:true}
const logs=ref<ArchiveLog[]>([]),logsLoading=ref(false),editing=ref(false),saving=ref(false)
const form=reactive<any>({data_name:"",categoryPath:[],project_name:"",company_name:"",store_id:null,data_year:2026,data_month:1,data_type:"RAW_DATA",description:""})
function startEdit(){if(!props.file)return;Object.assign(form,{data_name:props.file.data_name,categoryPath:props.file.category_path.map(i=>i.id),project_name:props.file.project_name,company_name:props.file.company_name,store_id:props.file.store_id,data_year:props.file.data_year,data_month:props.file.data_month,data_type:props.file.data_type,description:props.file.description});editing.value=true}
async function open(){editing.value=false;if(!props.file)return;logsLoading.value=true;try{logs.value=(await getArchiveLogs(props.file.id)).rows}catch{ElMessage.error("操作记录加载失败")}finally{logsLoading.value=false}}
async function save(){if(!props.file)return;saving.value=true;try{await updateArchiveFile(props.file.id,{data_name:form.data_name,category_id:form.categoryPath[form.categoryPath.length-1],project_name:form.project_name,company_name:form.company_name,store_id:form.store_id,data_year:form.data_year,data_month:form.data_month,data_type:form.data_type,description:form.description} as any);ElMessage.success("元数据已更新");editing.value=false;emit("complete")}catch(error:any){ElMessage.error(error?.response?.data?.detail||"保存失败")}finally{saving.value=false}}
function typeLabel(value:string){return DATA_TYPE_OPTIONS.find(i=>i.value===value)?.label||value}
function operationLabel(value:string){return({UPLOAD:"上传",DOWNLOAD:"下载",UPDATE:"修改",DELETE:"删除到回收站",RESTORE:"从回收站恢复"} as Record<string,string>)[value]||value}
function formatDate(value?:string|null){return value?value.replace("T"," ").slice(0,16):"-"}
function formatSize(bytes:number){if(!bytes)return"0 B";const u=["B","KB","MB","GB"];const i=Math.min(Math.floor(Math.log(bytes)/Math.log(1024)),u.length-1);return`${(bytes/1024**i).toFixed(i?1:0)} ${u[i]}`}
function detailText(item:ArchiveLog){const d=item.change_detail||{};if(d.reason)return`原因：${d.reason}`;if(d.file_name)return String(d.file_name);if(d.changes)return"已修改存档元数据";if(d.previous_delete_reason)return`原删除原因：${d.previous_delete_reason}`;return""}
</script>

<style scoped>
.detail-heading{display:flex;align-items:center;gap:13px;padding:15px;border-radius:11px;background:#f5f8fc}.detail-heading h3,.detail-heading p{margin:0}.detail-heading p{margin-top:4px;color:#667085;font-size:12px}.extension{display:grid;width:48px;height:54px;place-items:center;border:1px solid #cfe0fb;border-radius:7px;color:#316bd8;font-size:10px;font-weight:800}.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin:18px 0}.detail-grid span{padding:10px;border:1px solid #edf0f4;border-radius:7px;color:#667085;font-size:11px}.detail-grid b{display:block;margin-top:5px;color:#17243b;font-size:12px}.detail-grid .wide{grid-column:1/-1}.hash b{overflow-wrap:anywhere;font-family:monospace}.section-title{display:flex;justify-content:space-between;margin:24px 0 15px}.log-card{padding:10px 12px;border:1px solid #e5e9f0;border-radius:8px}.log-card span,.log-card p{display:block;margin:5px 0 0;color:#667085;font-size:11px}.edit-form{margin:18px 0}.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}.two :deep(.el-select),.two :deep(.el-input-number),.edit-form :deep(.el-cascader){width:100%}
</style>
