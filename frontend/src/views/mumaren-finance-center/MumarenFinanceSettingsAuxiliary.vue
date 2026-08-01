<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">系统设置</p>
        <h2>辅助核算</h2>
        <p>客户、供应商、部门、项目等辅助核算维度管理;会话内维护,刷新清空。</p>
      </div>
      <div class="heading-actions">
        <el-button type="primary" @click="openDialog">新增核算项</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon title="完整数据接口待后端补,本会话数据刷新后清空" />

    <div class="filters">
      <el-select v-model="filterDimension" placeholder="按维度过滤" clearable style="width: 200px">
        <el-option label="客户" value="客户" />
        <el-option label="供应商" value="供应商" />
        <el-option label="部门" value="部门" />
        <el-option label="项目" value="项目" />
      </el-select>
    </div>

    <el-table :data="filteredItems" empty-text="暂无核算项" stripe>
      <el-table-column prop="dimension" label="维度" width="120" />
      <el-table-column prop="code" label="编码" width="140" />
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column label="父级编码" width="140">
        <template #default="{ row }">{{ row.parent_code || "—" }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
            {{ row.status === "active" ? "启用" : "停用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ row.remark || "—" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button link :type="row.status === 'active' ? 'warning' : 'success'" size="small" @click="toggle(row)">
            {{ row.status === "active" ? "停用" : "启用" }}
          </el-button>
          <el-popconfirm title="确定删除该核算项?" @confirm="remove(row)">
            <template #reference>
              <el-button link type="danger" size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增核算项" width="480px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="维度">
          <el-select v-model="form.dimension" style="width:100%" placeholder="选择维度">
            <el-option label="客户" value="客户" />
            <el-option label="供应商" value="供应商" />
            <el-option label="部门" value="部门" />
            <el-option label="项目" value="项目" />
          </el-select>
        </el-form-item>
        <el-form-item label="编码">
          <el-input v-model="form.code" placeholder="如 C001 / S001 / D001 / P001" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="父级编码">
          <el-input v-model="form.parent_code" placeholder="可选,留空表示顶级" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

interface AuxiliaryItem {
  id: number;
  dimension: string;
  code: string;
  name: string;
  parent_code: string | null;
  status: "active" | "inactive";
  remark: string;
  created_at: string;
}

const items = ref<AuxiliaryItem[]>([]);
const dialogVisible = ref(false);
const filterDimension = ref("");
let seed = 1;

const form = reactive({
  dimension: "客户",
  code: "",
  name: "",
  parent_code: "",
  remark: "",
});

const filteredItems = computed(() => {
  if (!filterDimension.value) return items.value;
  return items.value.filter((x) => x.dimension === filterDimension.value);
});

const openDialog = () => {
  form.dimension = "客户";
  form.code = "";
  form.name = "";
  form.parent_code = "";
  form.remark = "";
  dialogVisible.value = true;
};

const save = () => {
  if (!form.code) {
    ElMessage.warning("请填写编码");
    return;
  }
  if (!form.name) {
    ElMessage.warning("请填写名称");
    return;
  }
  items.value.push({
    id: seed++,
    dimension: form.dimension,
    code: form.code,
    name: form.name,
    parent_code: form.parent_code || null,
    status: "active",
    remark: form.remark,
    created_at: new Date().toISOString(),
  });
  dialogVisible.value = false;
  ElMessage.success("核算项已新增");
};

const toggle = (row: AuxiliaryItem) => {
  row.status = row.status === "active" ? "inactive" : "active";
  ElMessage.success(row.status === "active" ? "已启用" : "已停用");
};

const remove = (row: AuxiliaryItem) => {
  const idx = items.value.findIndex((x) => x.id === row.id);
  if (idx >= 0) items.value.splice(idx, 1);
  ElMessage.success("核算项已删除");
};
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.heading-actions { display: flex; gap: 8px; }
.filters { display: flex; gap: 12px; align-items: center; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
@media (max-width: 640px) { .filters { flex-direction: column; align-items: stretch; } .heading { flex-direction: column; } }
</style>
