<template>
  <div class="warehouse-archive">
    <div class="page-header">
      <h2>仓库档案</h2>
      <p class="page-desc">华邦标准仓库维，当前数据来源：百胜 E3ERP。库存数量和金额来自百胜库存余额，金额按 SKU 成本计算。</p>
    </div>

    <div class="toolbar">
      <div class="filters">
        <el-input v-model="filters.keyword" placeholder="仓库编码/名称/区域" clearable style="width:200px" @keyup.enter="handleSearch" />
        <el-select v-model="filters.region_name" placeholder="区域" clearable filterable style="width:130px">
          <el-option v-for="r in options.regions" :key="r" :label="r" :value="r" />
        </el-select>
        <el-select v-model="filters.warehouse_nature" placeholder="仓库性质" clearable style="width:120px">
          <el-option v-for="n in options.natures" :key="n" :label="n" :value="n" />
        </el-select>
        <el-select v-model="filters.warehouse_category_name" placeholder="仓库类别" clearable filterable style="width:130px">
          <el-option v-for="c in options.categories" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="filters.status" placeholder="状态" clearable style="width:110px">
          <el-option label="启用" value="active" />
          <el-option label="停用" value="disabled" />
          <el-option label="未知" value="unknown" />
        </el-select>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>
      <div class="actions">
        <span class="last-sync" v-if="lastSyncedAt">最后同步：{{ formatTime(lastSyncedAt) }}</span>
        <el-button type="success" :loading="syncing" @click="handleSync">
          <el-icon style="margin-right:4px"><Refresh /></el-icon>同步仓库档案
        </el-button>
      </div>
    </div>

    <el-table :data="list" v-loading="loading" border stripe size="small" style="width:100%">
      <el-table-column prop="warehouse_code" label="仓库编码" width="120" fixed />
      <el-table-column prop="warehouse_name" label="仓库名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="warehouse_nature" label="仓库性质" width="90" />
      <el-table-column prop="warehouse_category_name" label="仓库类别" width="100" />
      <el-table-column prop="region_name" label="所属区域" width="110" />
      <el-table-column prop="channel_code" label="渠道代码" width="90" />
      <el-table-column prop="default_location_name" label="默认库位" width="110" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : (row.status === 'disabled' ? 'info' : 'warning')" size="small">
            {{ row.status === 'active' ? '启用' : (row.status === 'disabled' ? '停用' : '未知') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="inventory_qty" label="当前库存" width="90" align="right" />
      <el-table-column prop="sku_count" label="SKU数" width="80" align="right" />
      <el-table-column label="库存金额" width="110" align="right">
        <template #default="{ row }">{{ formatMoney(row.inventory_amount) }}</template>
      </el-table-column>
      <el-table-column label="预警数量" width="90"><template #default><span class="pending">待配置</span></template></el-table-column>
      <el-table-column label="AI建议" width="90"><template #default><span class="pending">待配置</span></template></el-table-column>
      <el-table-column prop="source_system" label="来源系统" width="90" />
      <el-table-column label="同步时间" width="160"><template #default="{ row }">{{ formatTime(row.synced_at) }}</template></el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination background layout="total, sizes, prev, pager, next, jumper"
        :total="total" v-model:current-page="page" v-model:page-size="page_size" :page-sizes="[20, 50, 100]"
        @current-change="handlePageChange" @size-change="handleSizeChange" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import { inventoryApi } from "@/api/inventory";

const loading = ref(false);
const syncing = ref(false);
const list = ref<any[]>([]);
const total = ref(0);
const page = ref(1);
const page_size = ref(20);
const lastSyncedAt = ref<string | null>(null);
const filters = reactive<any>({ keyword: "", region_name: "", warehouse_nature: "", warehouse_category_name: "", status: "" });
const options = reactive<{ regions: string[]; natures: string[]; categories: string[] }>({ regions: [], natures: [], categories: [] });

function formatTime(t: string | null) {
  if (!t) return "-";
  return String(t).replace("T", " ").slice(0, 19);
}
function formatMoney(v: any) {
  const n = Number(v || 0);
  return `¥${n.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}

async function fetchList() {
  loading.value = true;
  try {
    const params: any = { page: page.value, page_size: page_size.value };
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    const { data } = await inventoryApi.listWarehouses(params);
    if (data && data.success) {
      list.value = data.data.items || [];
      total.value = data.data.total || 0;
      const times = list.value.map((x) => x.synced_at).filter(Boolean).sort();
      if (times.length) lastSyncedAt.value = times[times.length - 1];
    } else {
      ElMessage.error((data && data.message) || "查询失败");
    }
  } catch (e: any) {
    ElMessage.error((e && e.message) || "查询失败");
  } finally {
    loading.value = false;
  }
}

async function loadOptions() {
  try {
    const { data } = await inventoryApi.listWarehouses({ page: 1, page_size: 200 });
    const items = (data && data.data && data.data.items) || [];
    options.regions = [...new Set(items.map((x: any) => x.region_name).filter(Boolean))] as string[];
    options.natures = [...new Set(items.map((x: any) => x.warehouse_nature).filter(Boolean))] as string[];
    options.categories = [...new Set(items.map((x: any) => x.warehouse_category_name).filter(Boolean))] as string[];
  } catch (_) { /* 忽略 */ }
}

function handleSearch() { page.value = 1; fetchList(); }
function handleReset() {
  Object.keys(filters).forEach((k) => (filters[k] = ""));
  page.value = 1; fetchList();
}
function handlePageChange(p: number) { page.value = p; fetchList(); }
function handleSizeChange(s: number) { page_size.value = s; page.value = 1; fetchList(); }

async function handleSync() {
  syncing.value = true;
  try {
    const { data } = await inventoryApi.syncWarehouses({ full_sync: true, page_size: 20 });
    if (data && data.success) {
      const d = data.data || {};
      ElMessage.success(`同步完成：共${d.record_count ?? "-"}个仓库，新增${d.dim_inserted ?? 0}，更新${d.dim_updated ?? 0}`);
      await loadOptions();
      await fetchList();
    } else {
      ElMessage.error((data && data.message) || "同步失败");
    }
  } catch (e: any) {
    ElMessage.error((e && e.message) || "同步失败");
  } finally {
    syncing.value = false;
  }
}

onMounted(() => { loadOptions(); fetchList(); });
</script>

<style scoped>
.warehouse-archive { padding: 16px; }
.page-header { margin-bottom: 12px; }
.page-header h2 { font-size: 18px; color: #333; margin-bottom: 4px; }
.page-desc { color: #999; font-size: 13px; }
.toolbar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:12px; }
.filters { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.actions { display:flex; align-items:center; gap:12px; }
.last-sync { color:#909399; font-size:13px; }
.pending { color:#c0c4cc; font-size:12px; }
.pager { margin-top:12px; display:flex; justify-content:flex-end; }
</style>
