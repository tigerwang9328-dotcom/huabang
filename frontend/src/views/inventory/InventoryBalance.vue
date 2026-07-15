<template>
  <div class="inv-balance">
    <div class="page-header">
      <h2>库存余额</h2>
      <p class="page-desc">华邦标准库存余额，来源：百胜 E3ERP 实物库存。可用=库存−占用；库存金额按标准进价计算，缺标准进价不计金额。</p>
    </div>
    <div class="toolbar">
      <div class="filters">
        <el-input v-model="filters.keyword" placeholder="货号/SKU/条码/品名" clearable style="width:200px" @keyup.enter="handleSearch" />
        <el-input v-model="filters.warehouse_code" placeholder="仓库编码" clearable style="width:120px" @keyup.enter="handleSearch" />
        <el-input v-model="filters.product_code" placeholder="货号精确" clearable style="width:120px" @keyup.enter="handleSearch" />
        <el-checkbox v-model="onlyPositive" @change="handleSearch" style="margin:0 4px">仅有货</el-checkbox>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>
      <div class="actions">
        <span class="last-sync" v-if="lastSyncedAt">最后同步：{{ formatTime(lastSyncedAt) }}</span>
        <el-button type="success" :loading="syncing" @click="handleSync">
          <el-icon style="margin-right:4px"><Refresh /></el-icon>同步库存余额
        </el-button>
      </div>
    </div>
    <el-table :data="list" v-loading="loading" border stripe size="small" style="width:100%">
      <el-table-column prop="warehouse_code" label="仓库" width="100" fixed />
      <el-table-column prop="warehouse_name" label="仓库名称" min-width="130" show-overflow-tooltip />
      <el-table-column prop="product_code" label="货号" width="110" />
      <el-table-column prop="sku_code" label="SKU" width="130" show-overflow-tooltip />
      <el-table-column prop="barcode" label="条码" width="120" show-overflow-tooltip />
      <el-table-column prop="goods_name" label="商品名称" min-width="130" show-overflow-tooltip />
      <el-table-column prop="color_name" label="颜色" width="90" />
      <el-table-column prop="size_name" label="尺码" width="70" />
      <el-table-column prop="qty" label="库存数量" width="90" align="right" />
      <el-table-column prop="lock_qty" label="占用" width="80" align="right" />
      <el-table-column prop="road_qty" label="在途" width="80" align="right" />
      <el-table-column prop="available_qty" label="可用" width="90" align="right">
        <template #default="{ row }"><span :class="{ neg: row.available_qty < 0 }">{{ row.available_qty }}</span></template>
      </el-table-column>
      <el-table-column label="标准进价" width="100" align="right">
        <template #default="{ row }">{{ row.standard_purchase_price == null ? "-" : formatMoney(row.standard_purchase_price) }}</template>
      </el-table-column>
      <el-table-column label="库存金额" width="110" align="right">
        <template #default="{ row }">{{ row.inventory_amount == null ? "-" : formatMoney(row.inventory_amount) }}</template>
      </el-table-column>
      <el-table-column prop="location_name" label="库位" width="100" />
      <el-table-column prop="source_system" label="来源" width="80" />
      <el-table-column label="同步时间" width="160"><template #default="{ row }">{{ formatTime(row.synced_at) }}</template></el-table-column>
    </el-table>
    <div class="pager">
      <el-pagination background layout="total, sizes, prev, pager, next, jumper"
        :total="total" :current-page="page" :page-size="page_size" :page-sizes="[20, 50, 100]"
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
const onlyPositive = ref(true);
const lastSyncedAt = ref<string | null>(null);
const filters = reactive<any>({ keyword: "", warehouse_code: "", product_code: "" });

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
    if (onlyPositive.value) params.only_positive = 1;
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    const { data } = await inventoryApi.listInventory(params);
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

function handleSearch() { page.value = 1; fetchList(); }
function handleReset() {
  filters.keyword = ""; filters.warehouse_code = ""; filters.product_code = "";
  onlyPositive.value = true; page.value = 1; fetchList();
}
function handlePageChange(p: number) { page.value = p; fetchList(); }
function handleSizeChange(s: number) { page_size.value = s; page.value = 1; fetchList(); }

async function handleSync() {
  syncing.value = true;
  try {
    const { data } = await inventoryApi.syncInventory({ full_sync: true, page_size: 20 });
    if (data && data.success) {
      ElMessage.success(data.message || "库存同步已在后台启动，稍后刷新查看");
      setTimeout(() => fetchList(), 1500);
    } else {
      ElMessage.error((data && data.message) || "同步失败");
    }
  } catch (e: any) {
    ElMessage.error((e && e.message) || "同步失败");
  } finally {
    syncing.value = false;
  }
}

onMounted(() => { fetchList(); });
</script>

<style scoped>
.inv-balance { padding: 16px; }
.page-header { margin-bottom: 12px; }
.page-header h2 { font-size: 18px; color: #333; margin-bottom: 4px; }
.page-desc { color: #999; font-size: 13px; }
.toolbar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:12px; }
.filters { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.actions { display:flex; align-items:center; gap:12px; }
.last-sync { color:#909399; font-size:13px; }
.pending { color:#c0c4cc; font-size:12px; }
.neg { color:#f56c6c; }
.pager { margin-top:12px; display:flex; justify-content:flex-end; }
</style>
