<template>
  <el-dialog v-model="visible" title="管理店铺组" width="720px" :append-to-body="true" draggable @open="onOpen">
    <div class="sgm">
      <div class="sgm-list">
        <div class="sgm-list-hd">
          <span>店铺组（{{ groups.length }}）</span>
          <el-button size="small" type="primary" @click="startCreate">新建</el-button>
        </div>
        <el-scrollbar height="360px">
          <div
            v-for="g in groups" :key="g.id"
            :class="['sgm-item', editing && editing.id === g.id ? 'active' : '']"
            @click="startEdit(g)"
          >
            <div class="sgm-item-name">{{ g.name }}</div>
            <div class="sgm-item-sub">{{ g.members.length }} 家店 · {{ g.is_active ? '启用' : '停用' }}<template v-if="g.parent_group_id"> · 上级：{{ groupName(g.parent_group_id) }}</template></div>
          </div>
          <el-empty v-if="!groups.length" description="暂无店铺组" :image-size="60" />
        </el-scrollbar>
      </div>

      <div class="sgm-edit" v-if="editing">
        <el-form label-width="72px" size="small">
          <el-form-item label="组名">
            <el-input v-model="editing.name" maxlength="128" placeholder="如：女装A组" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="editing.remark" placeholder="可选" />
          </el-form-item>
          <el-form-item label="上级组">
            <el-select v-model="editing.parent_group_id" clearable filterable placeholder="无（顶层组）" style="width:100%">
              <el-option v-for="g in parentOptions" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="editing.is_active" />
          </el-form-item>
          <el-form-item label="店铺">
            <el-select
              v-model="editing.store_ids" multiple filterable collapse-tags collapse-tags-tooltip
              placeholder="选择店铺" style="width:100%"
            >
              <el-option
                v-for="s in storeOptions" :key="s.store_id"
                :label="s.store_name" :value="s.store_id"
                :disabled="occupiedElsewhere.has(s.store_id)"
              >
                <span>{{ s.store_name }}</span>
                <span v-if="occupiedElsewhere.has(s.store_id)" style="color:#c0c4cc;font-size:11px;margin-left:6px">已属其它组</span>
              </el-option>
            </el-select>
          </el-form-item>
        </el-form>
        <div class="sgm-actions">
          <el-button v-if="editing.id" type="danger" plain size="small" @click="onDelete">删除该组</el-button>
          <div style="flex:1" />
          <el-button size="small" @click="editing = null">取消</el-button>
          <el-button size="small" type="primary" :loading="saving" @click="onSave">保存</el-button>
        </div>
      </div>
      <div class="sgm-edit sgm-empty" v-else>
        <el-text type="info">选择左侧店铺组编辑，或点「新建」创建</el-text>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import request from "@/api/request"
import { listGroups, createGroup, updateGroup, deleteGroup } from "@/api/storeReportGroup"
import type { StoreReportGroup } from "@/api/storeReportGroup"

const visible = defineModel<boolean>("visible", { default: false })
const emit = defineEmits<{ (e: "changed"): void }>()

const groups = ref<StoreReportGroup[]>([])
const storeOptions = ref<{ store_id: number; store_name: string; platform: string }[]>([])
const saving = ref(false)
const editing = ref<{ id: number | null; name: string; remark: string; is_active: boolean; parent_group_id: number | null; store_ids: number[] } | null>(null)

function groupName(id: number | null) {
  const g = groups.value.find(x => x.id === id)
  return g ? g.name : ""
}
// 可选父组：排除自身及其所有后代(防环)
const parentOptions = computed(() => {
  const cur = editing.value
  if (!cur || cur.id == null) return groups.value
  const banned = new Set<number>([cur.id])
  let changed = true
  while (changed) {
    changed = false
    for (const g of groups.value) {
      if (g.parent_group_id != null && banned.has(g.parent_group_id) && !banned.has(g.id)) {
        banned.add(g.id); changed = true
      }
    }
  }
  return groups.value.filter(g => !banned.has(g.id))
})

const occupiedElsewhere = computed(() => {
  const set = new Set<number>()
  for (const g of groups.value) {
    if (editing.value && editing.value.id === g.id) continue
    for (const m of g.members) set.add(m.store_id)
  }
  return set
})

async function onOpen() {
  editing.value = null
  await Promise.all([loadGroups(), loadStores()])
}
async function loadGroups() { groups.value = (await listGroups()) || [] }
async function loadStores() { storeOptions.value = (await request.get("/finance/daily-report/params/stores")) as any[] || [] }

function startCreate() { editing.value = { id: null, name: "", remark: "", is_active: true, parent_group_id: null, store_ids: [] } }
function startEdit(g: StoreReportGroup) {
  editing.value = { id: g.id, name: g.name, remark: g.remark || "", is_active: g.is_active, parent_group_id: g.parent_group_id ?? null, store_ids: g.members.map(m => m.store_id) }
}

async function onSave() {
  if (!editing.value) return
  if (!editing.value.name.trim()) { ElMessage.warning("请填写组名"); return }
  saving.value = true
  try {
    const body = { name: editing.value.name.trim(), remark: editing.value.remark, is_active: editing.value.is_active, parent_group_id: editing.value.parent_group_id, store_ids: editing.value.store_ids }
    if (editing.value.id) await updateGroup(editing.value.id, body)
    else await createGroup(body)
    ElMessage.success("已保存")
    await loadGroups(); emit("changed"); editing.value = null
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败")
  } finally { saving.value = false }
}

async function onDelete() {
  if (!editing.value?.id) return
  try {
    await ElMessageBox.confirm(`确认删除店铺组「${editing.value.name}」？`, "删除确认", { type: "warning" })
    await deleteGroup(editing.value.id)
    ElMessage.success("已删除")
    await loadGroups(); emit("changed"); editing.value = null
  } catch {}
}
</script>

<style scoped>
.sgm { display: flex; gap: 16px; }
.sgm-list { width: 240px; border-right: 1px solid var(--el-border-color-light); padding-right: 12px; }
.sgm-list-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 13px; font-weight: 600; }
.sgm-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; }
.sgm-item:hover { background: var(--el-fill-color-light); }
.sgm-item.active { background: var(--el-color-primary-light-9); }
.sgm-item-name { font-size: 13px; font-weight: 500; }
.sgm-item-sub { font-size: 11px; color: #909399; margin-top: 2px; }
.sgm-edit { flex: 1; }
.sgm-empty { display: flex; align-items: center; justify-content: center; min-height: 200px; }
.sgm-actions { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
</style>
