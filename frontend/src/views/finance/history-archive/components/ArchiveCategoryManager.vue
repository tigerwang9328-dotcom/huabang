<template>
  <el-dialog :model-value="modelValue" title="数据分类管理" width="680px" @open="load" @close="emit('update:modelValue',false)">
    <el-alert title="一级分类为系统固定分类；二级、三级分类可独立维护。" type="info" :closable="false" />
    <div class="manager-body" v-loading="loading">
      <el-tree :data="tree" node-key="id" default-expand-all :expand-on-click-node="false" @node-click="selectNode">
        <template #default="{ data }">
          <div class="tree-node"><span>{{ data.name }}</span><el-tag v-if="data.status==='INACTIVE'" size="small" type="info">已停用</el-tag><small>{{ data.level }}级</small></div>
        </template>
      </el-tree>
      <div class="editor">
        <template v-if="selected">
          <h3>{{ selected.name }}</h3>
          <p>层级：{{ selected.level }}级 · {{ selected.is_fixed ? "固定分类" : "自定义分类" }}</p>
          <el-form label-position="top">
            <el-form-item label="分类名称"><el-input v-model="editName" :disabled="selected.is_fixed || selected.status==='INACTIVE'" maxlength="128" /></el-form-item>
            <el-form-item label="排序"><el-input-number v-model="editSort" :min="0" :max="9999" /></el-form-item>
          </el-form>
          <div class="buttons">
            <el-button type="primary" :disabled="selected.status==='INACTIVE'" @click="saveEdit">保存</el-button>
            <el-button v-if="selected.level<3 && selected.status==='ACTIVE'" @click="addChild">新增下级</el-button>
            <el-button v-if="!selected.is_fixed && selected.status==='ACTIVE'" type="danger" plain @click="deactivate">停用</el-button>
          </div>
        </template>
        <el-empty v-else description="请选择左侧分类" :image-size="70" />
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { createArchiveCategory, deactivateArchiveCategory, getManageCategoryTree, updateArchiveCategory } from "@/api/historyArchive"
import type { ArchiveCategory } from "@/api/historyArchive"

defineProps<{modelValue:boolean}>()
const emit=defineEmits<{(e:"update:modelValue",value:boolean):void;(e:"complete"):void}>()
const tree=ref<ArchiveCategory[]>([]),selected=ref<ArchiveCategory|null>(null),loading=ref(false),editName=ref(""),editSort=ref(0)
async function load(){loading.value=true;try{tree.value=(await getManageCategoryTree()).rows}catch{ElMessage.error("分类加载失败")}finally{loading.value=false}}
function selectNode(data:ArchiveCategory){selected.value=data;editName.value=data.name;editSort.value=data.sort_order}
async function saveEdit(){if(!selected.value)return;try{await updateArchiveCategory(selected.value.id,{name:editName.value.trim(),sort_order:editSort.value});ElMessage.success("分类已更新");await load();emit("complete")}catch(error:any){ElMessage.error(error?.response?.data?.detail||"更新失败")}}
async function addChild(){if(!selected.value)return;try{const result=await ElMessageBox.prompt(`在“${selected.value.name}”下新增分类`,`新增${selected.value.level+1}级分类`,{inputPlaceholder:"分类名称",inputValidator:value=>Boolean(value?.trim())||"请输入分类名称"});await createArchiveCategory({name:result.value.trim(),parent_id:selected.value.id});ElMessage.success("分类已新增");await load();emit("complete")}catch(error:any){if(error==="cancel"||error==="close")return;ElMessage.error(error?.response?.data?.detail||"新增失败")}}
async function deactivate(){if(!selected.value)return;try{await ElMessageBox.confirm("停用后不能再用于新存档，确认继续？","停用分类",{type:"warning"});await deactivateArchiveCategory(selected.value.id);ElMessage.success("分类已停用");selected.value=null;await load();emit("complete")}catch(error:any){if(error==="cancel"||error==="close")return;ElMessage.error(error?.response?.data?.detail||"停用失败")}}
</script>

<style scoped>
.manager-body{display:grid;grid-template-columns:1fr 280px;gap:20px;min-height:360px;margin-top:18px}.manager-body>.el-tree{padding:12px;border:1px solid #e5e9f0;border-radius:10px}.tree-node{display:flex;align-items:center;gap:7px;width:100%}.tree-node small{margin-left:auto;color:#98a2b3}.editor{padding:16px;border-radius:10px;background:#f7f9fc}.editor h3{margin:0 0 7px}.editor p{margin:0 0 18px;color:#667085;font-size:12px}.buttons{display:flex;flex-wrap:wrap;gap:8px}@media(max-width:700px){.manager-body{grid-template-columns:1fr}}
</style>
