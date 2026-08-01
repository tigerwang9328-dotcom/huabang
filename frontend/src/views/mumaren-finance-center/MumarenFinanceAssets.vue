<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">固定资产</p>
        <h2>资产</h2>
        <p>资产卡片、折旧与净值管理;会话内维护,刷新清空。</p>
      </div>
      <div class="heading-actions">
        <el-button type="primary" @click="openCreate">新增资产</el-button>
      </div>
    </div>

    <el-alert type="warning" :closable="false" show-icon title="完整数据接口待后端补,本会话数据刷新后清空" />

    <el-table :data="assets" empty-text="暂无资产卡片" stripe show-summary :summary-method="summary">
      <el-table-column prop="asset_code" label="编码" width="140" />
      <el-table-column prop="asset_name" label="名称" min-width="180" />
      <el-table-column prop="category" label="分类" width="120" />
      <el-table-column label="原值" width="140" align="right">
        <template #default="{ row }">{{ money(row.original_value) }}</template>
      </el-table-column>
      <el-table-column label="累计折旧" width="140" align="right">
        <template #default="{ row }">{{ money(row.accumulated_depreciation) }}</template>
      </el-table-column>
      <el-table-column label="净值" width="140" align="right">
        <template #default="{ row }">{{ money(row.net_value) }}</template>
      </el-table-column>
      <el-table-column prop="purchase_date" label="购入日期" width="130" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.status === 'in_use' ? 'success' : 'info'" size="small">{{ row.status === 'in_use' ? '在用' : '已处置' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button link type="primary" size="small" :disabled="row.status === 'disposed'" @click="openDepreciate(row)">折旧</el-button>
          <el-popconfirm title="确认处置该资产?" @confirm="dispose(row)">
            <template #reference>
              <el-button link type="warning" size="small" :disabled="row.status === 'disposed'">处置</el-button>
            </template>
          </el-popconfirm>
          <el-popconfirm title="确定删除该资产?" @confirm="remove(row)">
            <template #reference>
              <el-button link type="danger" size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增资产" width="520px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="资产编码">
          <el-input v-model="form.asset_code" placeholder="如 FA-2026-001" />
        </el-form-item>
        <el-form-item label="资产名称">
          <el-input v-model="form.asset_name" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width:100%">
            <el-option label="电子设备" value="电子设备" />
            <el-option label="办公设备" value="办公设备" />
            <el-option label="车辆" value="车辆" />
            <el-option label="家具" value="家具" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item label="原值">
          <el-input-number v-model="form.original_value" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="购入日期">
          <el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="折旧年限">
          <el-input-number v-model="form.useful_life" :min="1" :max="50" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="depDialogVisible" title="计提折旧" width="420px">
      <el-form :model="depForm" label-width="100px">
        <el-form-item label="资产">
          <span>{{ depForm.asset_name }}</span>
        </el-form-item>
        <el-form-item label="当前净值">
          <span>{{ money(depForm.current_net) }}</span>
        </el-form-item>
        <el-form-item label="折旧金额">
          <el-input-number v-model="depForm.amount" :min="0" :precision="2" :controls="false" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="depDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="applyDepreciation">确认</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";

interface AssetCard {
  id: number;
  asset_code: string;
  asset_name: string;
  category: string;
  original_value: number;
  purchase_date: string;
  useful_life: number;
  accumulated_depreciation: number;
  net_value: number;
  status: "in_use" | "disposed";
  created_at: string;
}

const assets = ref<AssetCard[]>([]);
const dialogVisible = ref(false);
const depDialogVisible = ref(false);
let seed = 1;

const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);

const form = reactive({
  asset_code: "",
  asset_name: "",
  category: "电子设备",
  original_value: 0,
  purchase_date: new Date().toISOString().slice(0, 10),
  useful_life: 5,
});

const depForm = reactive({
  asset_id: 0,
  asset_name: "",
  current_net: 0,
  amount: 0,
});

const openCreate = () => {
  form.asset_code = "";
  form.asset_name = "";
  form.category = "电子设备";
  form.original_value = 0;
  form.purchase_date = new Date().toISOString().slice(0, 10);
  form.useful_life = 5;
  dialogVisible.value = true;
};

const save = () => {
  if (!form.asset_code || !form.asset_name) {
    ElMessage.warning("请填写资产编码与名称");
    return;
  }
  const original = Number(form.original_value || 0);
  assets.value.push({
    id: seed++,
    asset_code: form.asset_code,
    asset_name: form.asset_name,
    category: form.category,
    original_value: original,
    purchase_date: form.purchase_date,
    useful_life: Number(form.useful_life || 0),
    accumulated_depreciation: 0,
    net_value: original,
    status: "in_use",
    created_at: new Date().toISOString(),
  });
  dialogVisible.value = false;
  ElMessage.success("资产已新增");
};

const openDepreciate = (row: AssetCard) => {
  depForm.asset_id = row.id;
  depForm.asset_name = `${row.asset_code} ${row.asset_name}`;
  depForm.current_net = row.net_value;
  depForm.amount = 0;
  depDialogVisible.value = true;
};

const applyDepreciation = () => {
  const row = assets.value.find((a) => a.id === depForm.asset_id);
  if (!row) return;
  const amount = Number(depForm.amount || 0);
  if (amount <= 0) {
    ElMessage.warning("折旧金额需大于 0");
    return;
  }
  if (amount > row.net_value) {
    ElMessage.warning("折旧金额不能超过净值");
    return;
  }
  row.accumulated_depreciation += amount;
  row.net_value = row.original_value - row.accumulated_depreciation;
  depDialogVisible.value = false;
  ElMessage.success("折旧已计提");
};

const dispose = (row: AssetCard) => {
  row.status = "disposed";
  ElMessage.success("资产已处置");
};

const remove = (row: AssetCard) => {
  const idx = assets.value.findIndex((a) => a.id === row.id);
  if (idx >= 0) assets.value.splice(idx, 1);
  ElMessage.success("已删除");
};

const summary = ({ columns, data }: { columns: any[]; data: AssetCard[] }) => {
  const sums: (string | number)[] = [];
  columns.forEach((_, i) => {
    sums[i] = i === 0 ? "合计" : "";
  });
  const idxOriginal = columns.findIndex((c) => c.label === "原值");
  const idxDep = columns.findIndex((c) => c.label === "累计折旧");
  const idxNet = columns.findIndex((c) => c.label === "净值");
  if (idxOriginal >= 0) sums[idxOriginal] = money(data.reduce((s, a) => s + Number(a.original_value || 0), 0));
  if (idxDep >= 0) sums[idxDep] = money(data.reduce((s, a) => s + Number(a.accumulated_depreciation || 0), 0));
  if (idxNet >= 0) sums[idxNet] = money(data.reduce((s, a) => s + Number(a.net_value || 0), 0));
  return sums;
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
