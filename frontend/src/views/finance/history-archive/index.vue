<template>
  <div class="archive-page">
    <section class="page-heading">
      <div><div class="eyebrow">ENTERPRISE DATA ASSET CENTER</div><h1>历史数据存档</h1><p>集中沉淀公司的财务原始数据、加工数据、月度报表与历史分析资料。</p></div>
      <div class="heading-actions">
        <el-button v-if="canManageCategory" :icon="CollectionTag" @click="categoryVisible=true">分类管理</el-button>
        <el-button v-if="canUpload" type="primary" size="large" :icon="UploadFilled" @click="uploadVisible=true">上传数据</el-button>
      </div>
    </section>

    <ArchiveDashboard :summary="summary" :loading="summaryLoading" />

    <section class="list-panel">
      <header class="list-heading">
        <div><h2>数据资产清单</h2><span>共 {{ total }} 条</span></div>
        <div><el-radio-group v-model="filters.status" @change="search"><el-radio-button value="NORMAL">正常数据</el-radio-button><el-radio-button value="DELETED">回收站</el-radio-button></el-radio-group><el-button :icon="Refresh" circle title="刷新" @click="refreshAll" /></div>
      </header>

      <div class="filters">
        <el-input v-model="filters.keyword" clearable placeholder="搜索数据名称、文件名或说明" :prefix-icon="Search" @keyup.enter="search" />
        <el-cascader v-model="filters.categoryPath" :options="categories" :props="categoryProps" clearable filterable placeholder="数据分类" />
        <el-select v-model="filters.project_name" clearable filterable placeholder="所属项目"><el-option v-for="item in options.projects" :key="item" :label="item" :value="item" /></el-select>
        <el-select v-model="filters.company_name" clearable filterable placeholder="公司主体"><el-option v-for="item in options.companies" :key="item" :label="item" :value="item" /></el-select>
        <el-select v-model="filters.store_id" clearable filterable placeholder="所属店铺"><el-option v-for="item in options.stores" :key="item.id" :label="item.name" :value="item.id" /></el-select>
        <el-date-picker v-model="filters.year" type="year" value-format="YYYY" format="YYYY年" placeholder="年份" clearable />
        <el-select v-model="filters.month" clearable placeholder="月份"><el-option v-for="month in 12" :key="month" :label="`${month}月`" :value="month" /></el-select>
        <el-select v-model="filters.data_type" clearable placeholder="数据类型"><el-option v-for="item in DATA_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select>
        <el-select v-model="filters.uploader" clearable filterable placeholder="上传人"><el-option v-for="item in options.uploaders" :key="item.id" :label="item.name" :value="item.name" /></el-select>
        <div class="filter-actions"><el-button type="primary" :icon="Search" @click="search">查询</el-button><el-button @click="resetFilters">重置</el-button></div>
      </div>

      <el-table :data="rows" v-loading="listLoading" stripe>
        <el-table-column label="数据资产" min-width="250">
          <template #default="{row}"><button class="file-cell" type="button" @click="showDetail(row)"><span>{{ row.file_extension.replace('.','') }}</span><div><b>{{ row.data_name }}</b><small>{{ row.original_filename }}</small></div></button></template>
        </el-table-column>
        <el-table-column label="分类" min-width="190" show-overflow-tooltip><template #default="{row}">{{ row.category_path_text }}</template></el-table-column>
        <el-table-column label="归属" min-width="170"><template #default="{row}"><div class="meta-cell"><span>{{ row.company_name||'-' }}</span><small>{{ row.project_name||'未归属项目' }}<template v-if="row.store_name"> · {{ row.store_name }}</template></small></div></template></el-table-column>
        <el-table-column label="数据期间" width="105"><template #default="{row}">{{ row.data_year }}-{{ String(row.data_month).padStart(2,'0') }}</template></el-table-column>
        <el-table-column label="类型" width="100"><template #default="{row}"><el-tag size="small" effect="plain">{{ typeLabel(row.data_type) }}</el-tag></template></el-table-column>
        <el-table-column label="大小" width="88"><template #default="{row}">{{ formatSize(row.file_size) }}</template></el-table-column>
        <el-table-column label="上传信息" width="150"><template #default="{row}"><div class="meta-cell"><span>{{ row.uploader_name||'未知' }}</span><small>{{ formatDate(row.created_at) }}</small></div></template></el-table-column>
        <el-table-column v-if="filters.status==='DELETED'" label="删除信息" min-width="160"><template #default="{row}"><div class="meta-cell"><span>{{ formatDate(row.deleted_at) }}</span><small>{{ row.delete_reason||'-' }}</small></div></template></el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{row}">
            <el-button link type="primary" @click="showDetail(row)">详情</el-button>
            <el-button v-if="canDownload" link type="primary" :icon="Download" @click="download(row)">下载</el-button>
            <el-button v-if="row.status==='NORMAL'&&canDelete" link type="danger" @click="remove(row)">删除</el-button>
            <el-button v-if="row.status==='DELETED'&&canDelete" link type="success" @click="restore(row)">恢复</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty :description="filters.status==='DELETED'?'回收站为空':'没有符合条件的数据资产'" /></template>
      </el-table>
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" :page-sizes="[20,50,100]" layout="total, sizes, prev, pager, next, jumper" @current-change="loadList" @size-change="pageSizeChange" />
    </section>

    <ArchiveUploadDialog v-model="uploadVisible" :categories="categories" :options="options" @complete="refreshAfterMutation" />
    <ArchiveCategoryManager v-model="categoryVisible" @complete="loadCategories" />
    <ArchiveDetailDrawer v-model="detailVisible" :file="selectedFile" :categories="categories" :options="options" :can-update="canUpdate" @complete="detailUpdated" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { CollectionTag, Download, Refresh, Search, UploadFilled } from "@element-plus/icons-vue"
import { useAuthStore } from "@/stores/auth"
import { ARCHIVE_PERMISSIONS, DATA_TYPE_OPTIONS, deleteArchiveFile, downloadArchiveFile, getArchiveFile, getArchiveFiles, getArchiveOptions, getArchiveSummary, getCategoryTree, restoreArchiveFile } from "@/api/historyArchive"
import type { ArchiveCategory, ArchiveDataType, ArchiveFile, ArchiveOptions, ArchiveStatus, ArchiveSummary } from "@/api/historyArchive"
import ArchiveDashboard from "./components/ArchiveDashboard.vue"
import ArchiveUploadDialog from "./components/ArchiveUploadDialog.vue"
import ArchiveCategoryManager from "./components/ArchiveCategoryManager.vue"
import ArchiveDetailDrawer from "./components/ArchiveDetailDrawer.vue"

const auth=useAuthStore()
const canUpload=computed(()=>auth.hasPermission(ARCHIVE_PERMISSIONS.upload)),canDownload=computed(()=>auth.hasPermission(ARCHIVE_PERMISSIONS.download)),canUpdate=computed(()=>auth.hasPermission(ARCHIVE_PERMISSIONS.update)),canDelete=computed(()=>auth.hasPermission(ARCHIVE_PERMISSIONS.delete)),canManageCategory=computed(()=>auth.hasPermission(ARCHIVE_PERMISSIONS.category))
const emptySummary=():ArchiveSummary=>({total_files:0,total_size:0,covered_year_count:0,covered_years:[],category_count:0,category_distribution:[],recent_uploads:[],recent_downloads:[]})
const summary=ref(emptySummary()),summaryLoading=ref(false),listLoading=ref(false),rows=ref<ArchiveFile[]>([]),total=ref(0),page=ref(1),pageSize=ref(20)
const categories=ref<ArchiveCategory[]>([]),options=ref<ArchiveOptions>({projects:[],companies:[],stores:[],uploaders:[]})
const filters=reactive({keyword:"",categoryPath:[] as number[],project_name:"",company_name:"",store_id:undefined as number|undefined,year:"",month:undefined as number|undefined,uploader:"",data_type:"" as ArchiveDataType|"",status:"NORMAL" as ArchiveStatus})
const uploadVisible=ref(false),categoryVisible=ref(false),detailVisible=ref(false),selectedFile=ref<ArchiveFile|null>(null)
const categoryProps={value:"id",label:"name",children:"children",checkStrictly:true,emitPath:true}
async function loadSummary(){summaryLoading.value=true;try{summary.value=await getArchiveSummary()}catch{ElMessage.error("数据资产看板加载失败")}finally{summaryLoading.value=false}}
async function loadList(){listLoading.value=true;try{const result=await getArchiveFiles({keyword:filters.keyword||undefined,category_id:filters.categoryPath.length?filters.categoryPath[filters.categoryPath.length-1]:undefined,project_name:filters.project_name||undefined,company_name:filters.company_name||undefined,store_id:filters.store_id,year:filters.year?Number(filters.year):undefined,month:filters.month,uploader:filters.uploader||undefined,data_type:filters.data_type,status:filters.status,page:page.value,page_size:pageSize.value});rows.value=result.rows;total.value=result.total}catch{ElMessage.error("数据资产列表加载失败")}finally{listLoading.value=false}}
async function loadCategories(){try{categories.value=(await getCategoryTree()).rows}catch{ElMessage.error("分类树加载失败")}}
async function loadOptions(){try{options.value=await getArchiveOptions()}catch{ElMessage.error("筛选项加载失败")}}
async function refreshAll(){await Promise.all([loadSummary(),loadList(),loadCategories(),loadOptions()])}
async function refreshAfterMutation(){await refreshAll()}
function search(){page.value=1;loadList()}
function pageSizeChange(){page.value=1;loadList()}
function resetFilters(){Object.assign(filters,{keyword:"",categoryPath:[],project_name:"",company_name:"",store_id:undefined,year:"",month:undefined,uploader:"",data_type:"",status:filters.status});search()}
function typeLabel(value:string){return DATA_TYPE_OPTIONS.find(item=>item.value===value)?.label||value}
function formatDate(value?:string|null){return value?value.replace("T"," ").slice(0,16):"-"}
function formatSize(bytes:number){if(!bytes)return"0 B";const units=["B","KB","MB","GB","TB"];const index=Math.min(Math.floor(Math.log(bytes)/Math.log(1024)),units.length-1);return`${(bytes/1024**index).toFixed(index?1:0)} ${units[index]}`}
function showDetail(row:ArchiveFile){selectedFile.value=row;detailVisible.value=true}
async function detailUpdated(){if(selectedFile.value)selectedFile.value=await getArchiveFile(selectedFile.value.id);await Promise.all([loadList(),loadSummary(),loadOptions()])}
async function download(row:ArchiveFile){try{const blob=await downloadArchiveFile(row.id);const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=row.original_filename;link.click();URL.revokeObjectURL(url);await loadSummary()}catch(error:any){ElMessage.error(error?.response?.data?.detail||"下载失败")}}
async function remove(row:ArchiveFile){try{const result=await ElMessageBox.prompt("文件只会进入回收站，不会物理删除。","删除数据资产",{confirmButtonText:"移入回收站",cancelButtonText:"取消",inputPlaceholder:"请输入删除原因",inputValidator:value=>Boolean(value?.trim())||"必须填写删除原因",type:"warning"});await deleteArchiveFile(row.id,result.value.trim());ElMessage.success("已移入回收站，物理文件仍保留");await refreshAll()}catch(error:any){if(error==="cancel"||error==="close")return;ElMessage.error(error?.response?.data?.detail||"删除失败")}}
async function restore(row:ArchiveFile){try{await ElMessageBox.confirm("确认将该数据资产恢复为正常状态？","恢复数据",{type:"info"});await restoreArchiveFile(row.id);ElMessage.success("数据资产已恢复");await refreshAll()}catch(error:any){if(error==="cancel"||error==="close")return;ElMessage.error(error?.response?.data?.detail||"恢复失败")}}
onMounted(refreshAll)
</script>

<style scoped>
.archive-page{display:flex;flex-direction:column;gap:16px;color:#17243b}.page-heading{display:flex;min-height:112px;align-items:flex-end;justify-content:space-between;padding:23px 27px;border:1px solid #dce4f0;border-radius:14px;background:linear-gradient(105deg,rgba(49,107,216,.09),transparent 48%),#fff}.eyebrow{margin-bottom:8px;color:#316bd8;font-size:10px;font-weight:800;letter-spacing:.16em}.page-heading h1{margin:0;font-size:28px}.page-heading p{margin:8px 0 0;color:#667085}.heading-actions{display:flex;gap:9px}.list-panel{padding:20px;border:1px solid #e5e9f0;border-radius:12px;background:#fff}.list-heading{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}.list-heading>div{display:flex;align-items:center;gap:9px}.list-heading h2{margin:0;font-size:18px}.list-heading span{color:#667085;font-size:12px}.filters{display:grid;grid-template-columns:minmax(220px,1.4fr) repeat(4,minmax(125px,.8fr));gap:10px;margin-bottom:15px}.filters :deep(.el-date-editor),.filters :deep(.el-cascader){width:100%}.filter-actions{display:flex;gap:8px}.file-cell{display:flex;width:100%;align-items:center;gap:10px;border:0;background:transparent;color:inherit;cursor:pointer;text-align:left}.file-cell>span{display:grid;width:38px;height:42px;flex:0 0 38px;place-items:center;border:1px solid #cfe0fb;border-radius:6px;background:#f3f7fd;color:#316bd8;font-size:9px;font-weight:800}.file-cell b,.file-cell small,.meta-cell span,.meta-cell small{display:block}.file-cell small,.meta-cell small{margin-top:3px;color:#667085;font-size:11px}.file-cell small{max-width:210px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.el-pagination{justify-content:flex-end;margin-top:17px}@media(max-width:1250px){.filters{grid-template-columns:repeat(3,1fr)}}@media(max-width:760px){.page-heading{align-items:flex-start;flex-direction:column;gap:18px}.filters{grid-template-columns:1fr}.list-heading{align-items:flex-start;flex-direction:column;gap:12px}}
</style>
