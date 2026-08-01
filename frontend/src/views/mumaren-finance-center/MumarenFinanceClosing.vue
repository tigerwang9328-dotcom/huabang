<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">期末结账</p>
        <h2>结账</h2>
        <p>期末结账预检与会话内结账标记;不调用后端结账接口。</p>
      </div>
      <div class="heading-actions">
        <el-button @click="openCreate">新增期间</el-button>
        <el-button type="primary" plain @click="precheckAll">预检</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon title="完整数据接口待后端补,本会话数据刷新后清空" />

    <el-table :data="periods" empty-text="暂无结账期间" stripe>
      <el-table-column prop="period" label="期间" width="140" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="预检状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.precheck_passed ? 'success' : 'info'" size="small">{{ row.precheck_passed ? '通过' : '未通过' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="precheck_notes" label="预检备注" min-width="220" />
      <el-table-column label="结账时间" width="180">
        <template #default="{ row }">{{ row.closed_at || '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row, $index }">
          <el-button link type="primary" size="small" @click="precheck(row)">预检</el-button>
          <el-button link type="success" size="small" :disabled="!canClose(row)" @click="close(row)">结账</el-button>
          <el-popconfirm title="确定删除该期间?" @confirm="remove($index)">
            <template #reference>
              <el-button link type="danger" size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增期间" width="420px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="期间">
          <el-date-picker v-model="form.period" type="month" value-format="YYYY-MM" placeholder="选择月份" style="width:100%" />
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
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";

interface ClosingPeriod {
  id: number;
  period: string; // 期间 YYYY-MM
  status: "open" | "closing" | "closed";
  precheck_passed: boolean;
  precheck_notes: string;
  closed_at: string | null;
  created_at: string;
}

const periods = ref<ClosingPeriod[]>([]);
const dialogVisible = ref(false);
let seed = 1;

const form = reactive({ period: "" });

const statusLabel = (s: string) => (s === "open" ? "未结账" : s === "closing" ? "结账中" : "已结账");
const statusTagType = (s: string): "info" | "warning" | "success" =>
  s === "open" ? "info" : s === "closing" ? "warning" : "success";

const openCreate = () => {
  form.period = "";
  dialogVisible.value = true;
};

const save = () => {
  if (!form.period) {
    ElMessage.warning("请选择期间");
    return;
  }
  if (periods.value.find((p) => p.period === form.period)) {
    ElMessage.warning("该期间已存在");
    return;
  }
  periods.value.push({
    id: seed++,
    period: form.period,
    status: "open",
    precheck_passed: false,
    precheck_notes: "",
    closed_at: null,
    created_at: new Date().toISOString(),
  });
  dialogVisible.value = false;
  ElMessage.success("期间已新增");
};

const precheck = (row: ClosingPeriod) => {
  row.precheck_passed = true;
  row.precheck_notes = "借贷平衡,无未审核凭证(模拟)";
  ElMessage.success(`期间 ${row.period} 预检通过(模拟)`);
};

const precheckAll = () => {
  if (periods.value.length === 0) {
    ElMessage.warning("暂无可预检的期间");
    return;
  }
  let count = 0;
  periods.value.forEach((p) => {
    if (p.status === "open") {
      p.precheck_passed = true;
      p.precheck_notes = "借贷平衡,无未审核凭证(模拟)";
      count++;
    }
  });
  if (count === 0) {
    ElMessage.warning("没有可预检的未结账期间");
  } else {
    ElMessage.success(`已对 ${count} 个未结账期间执行预检(模拟)`);
  }
};

const canClose = (row: ClosingPeriod) => row.precheck_passed && row.status === "open";

const close = (row: ClosingPeriod) => {
  if (!canClose(row)) return;
  row.status = "closed";
  row.closed_at = new Date().toISOString().replace("T", " ").slice(0, 19);
  ElMessage.success(`期间 ${row.period} 已结账`);
};

const remove = (index: number) => {
  periods.value.splice(index, 1);
  ElMessage.success("已删除");
};
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }
.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.heading-actions { display: flex; gap: 8px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
@media (max-width: 640px) { .heading { flex-direction: column; } }
</style>
