<template>
  <section class="panel">
    <div class="heading">
      <div>
        <p class="panel-kicker">固定资产</p>
        <h2>资产</h2>
        <p>资产卡片、折旧与净值管理;按独立账簿隔离,数据持久化。</p>
      </div>
      <div class="heading-actions">
        <el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :disabled="!bookId" @click="openCreate">新增资产</el-button>
      </div>
    </div>

    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange">
        <el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" />
      </el-select>
    </div>

    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />

    <el-table v-loading="loading" :data="assets" empty-text="暂无资产卡片" stripe show-summary :summary-method="summary">
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
          <el-button link type="primary" size="small" :disabled="row.status === 'disposed'" :loading="actingId === row.id" @click="depreciate(row)">折旧</el-button>
          <el-popconfirm title="确认处置该资产?" @confirm="dispose(row)">
            <template #reference>
              <el-button link type="warning" size="small" :disabled="row.status === 'disposed'" :loading="actingId === row.id">处置</el-button>
            </template>
          </el-popconfirm>
          <el-popconfirm title="确定删除该资产?" @confirm="remove(row)">
            <template #reference>
              <el-button link type="danger" size="small" :loading="actingId === row.id">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增资产" width="520px" :close-on-click-modal="false">
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
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  fixedAssetsApi,
  mumarenFinanceCenterApi,
  type MumarenFinanceBook,
  type MumarenFixedAsset,
} from "@/api/mumarenFinanceCenter";

const books = ref<MumarenFinanceBook[]>([]);
const bookId = ref<number>();
const assets = ref<MumarenFixedAsset[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const actingId = ref<number>();
const dialogVisible = ref(false);

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

const load = async () => {
  if (!bookId.value) return;
  loading.value = true;
  error.value = "";
  try {
    assets.value = (await fixedAssetsApi.list({ book_id: bookId.value })).data.data;
  } catch {
    error.value = "无法加载资产卡片。";
  } finally {
    loading.value = false;
  }
};

const onBookChange = () => {
  assets.value = [];
  load();
};

onMounted(async () => {
  try {
    books.value = (await mumarenFinanceCenterApi.listBooks()).data.data;
    bookId.value = books.value[0]?.id;
    if (bookId.value) await load();
  } catch {
    error.value = "无法加载独立账簿。";
  }
});

const openCreate = () => {
  if (!bookId.value) {
    ElMessage.warning("请先选择独立账簿");
    return;
  }
  form.asset_code = "";
  form.asset_name = "";
  form.category = "电子设备";
  form.original_value = 0;
  form.purchase_date = new Date().toISOString().slice(0, 10);
  form.useful_life = 5;
  dialogVisible.value = true;
};

const save = async () => {
  if (!bookId.value) return;
  if (!form.asset_code || !form.asset_name) {
    ElMessage.warning("请填写资产编码与名称");
    return;
  }
  saving.value = true;
  try {
    await fixedAssetsApi.create({
      book_id: bookId.value,
      asset_code: form.asset_code,
      asset_name: form.asset_name,
      category: form.category,
      original_value: Number(form.original_value || 0),
      purchase_date: form.purchase_date,
      useful_life: Number(form.useful_life || 0),
    });
    ElMessage.success("资产已新增");
    dialogVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
};

const depreciate = async (row: MumarenFixedAsset) => {
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await fixedAssetsApi.depreciate(row.id, bookId.value);
    ElMessage.success("折旧已计提");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "折旧失败");
  } finally {
    actingId.value = undefined;
  }
};

const dispose = async (row: MumarenFixedAsset) => {
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await fixedAssetsApi.dispose(row.id, bookId.value);
    ElMessage.success("资产已处置");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "处置失败");
  } finally {
    actingId.value = undefined;
  }
};

const remove = async (row: MumarenFixedAsset) => {
  if (!bookId.value) return;
  actingId.value = row.id;
  try {
    await fixedAssetsApi.delete(row.id, bookId.value);
    ElMessage.success("已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || "删除失败");
  } finally {
    actingId.value = undefined;
  }
};

const summary = ({ columns, data }: { columns: any[]; data: MumarenFixedAsset[] }) => {
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
.filters { display: flex; gap: 12px; }
.filters > * { max-width: 280px; }
.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 8px 0; }
p { color: #5d6b7e; }
@media (max-width: 640px) { .filters { flex-direction: column; } .heading { flex-direction: column; } }
</style>
