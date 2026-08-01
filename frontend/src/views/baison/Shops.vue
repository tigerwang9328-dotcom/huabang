<template>
  <div class="baison-shops">
    <div class="page-toolbar">
      <div class="filters">
        <el-input v-model="filters.keyword" placeholder="店铺代码/名称" clearable style="width:200px" @keyup.enter="handleSearch" />
        <el-select v-model="filters.area_name" placeholder="区域" clearable filterable style="width:150px">
          <el-option v-for="a in options.areas" :key="a" :label="a" :value="a" />
        </el-select>
        <el-select v-model="filters.shop_type" placeholder="店铺性质" clearable style="width:130px">
          <el-option v-for="t in options.shopTypes" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select v-model="filters.online_type" placeholder="线上/线下" clearable style="width:130px">
          <el-option v-for="o in options.onlineTypes" :key="o" :label="o" :value="o" />
        </el-select>
        <el-select v-model="filters.is_enabled" placeholder="启用状态" clearable style="width:120px">
          <el-option label="启用" value="1" />
          <el-option label="停用" value="0" />
        </el-select>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>
      <div class="actions">
        <span class="last-sync" v-if="lastSyncedAt">最后同步：{{ formatTime(lastSyncedAt) }}</span>
        <el-button type="success" :loading="syncing" @click="handleSync">
          <el-icon style="margin-right:4px"><Refresh /></el-icon>同步门店数据
        </el-button>
      </div>
    </div>

    <el-table :data="list" v-loading="loading" border stripe size="small" style="width:100%">
      <el-table-column prop="shop_code" label="店铺代码" width="100" fixed />
      <el-table-column prop="shop_name" label="店铺名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="shop_type" label="店铺性质" width="90" />
      <el-table-column prop="category_name" label="店铺类别" width="100" />
      <el-table-column prop="area_name" label="区域" width="100" />
      <el-table-column prop="online_type" label="线上/线下" width="100" />
      <el-table-column prop="province" label="省" width="70" />
      <el-table-column prop="city" label="市" width="90" />
      <el-table-column prop="county" label="区县" width="90" />
      <el-table-column prop="address" label="地址" min-width="200" show-overflow-tooltip />
      <el-table-column label="启用状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_enabled === '1' ? 'success' : 'info'" size="small">
            {{ row.is_enabled === '1' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_changed" label="百胜最后更新" width="160" />
      <el-table-column label="中台同步时间" width="160">
        <template #default="{ row }">{{ formatTime(row.synced_at) }}</template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        background layout="total, sizes, prev, pager, next, jumper"
        :total="total" :current-page="page" :page-size="page_size"
        :page-sizes="[20, 50, 100]"
        @current-change="handlePageChange" @size-change="handleSizeChange" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import { baisonApi } from "@/api/baison";

const loading = ref(false);
const syncing = ref(false);
const list = ref<any[]>([]);
const total = ref(0);
const page = ref(1);
const page_size = ref(20);
const lastSyncedAt = ref<string | null>(null);
const filters = reactive({ keyword: "", area_name: "", shop_type: "", online_type: "", is_enabled: "" });
const options = reactive<{ areas: string[]; shopTypes: string[]; onlineTypes: string[] }>({ areas: [], shopTypes: [], onlineTypes: [] });

function formatTime(t: string | null) {
  if (!t) return "-";
  return String(t).replace("T", " ").slice(0, 19);
}

async function fetchList() {
  loading.value = true;
  try {
    const params: any = { page: page.value, page_size: page_size.value };
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    const { data } = await baisonApi.listShops(params);
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
    const { data } = await baisonApi.listShops({ page: 1, page_size: 200 });
    const items = (data && data.data && data.data.items) || [];
    options.areas = [...new Set(items.map((x: any) => x.area_name).filter(Boolean))] as string[];
    options.shopTypes = [...new Set(items.map((x: any) => x.shop_type).filter(Boolean))] as string[];
    options.onlineTypes = [...new Set(items.map((x: any) => x.online_type).filter(Boolean))] as string[];
  } catch (_) { /* 忽略选项加载失败 */ }
}

function handleSearch() { page.value = 1; fetchList(); }
function handleReset() {
  filters.keyword = ""; filters.area_name = ""; filters.shop_type = "";
  filters.online_type = ""; filters.is_enabled = "";
  page.value = 1; fetchList();
}
function handlePageChange(p: number) { page.value = p; fetchList(); }
function handleSizeChange(s: number) { page_size.value = s; page.value = 1; fetchList(); }

async function handleSync() {
  syncing.value = true;
  try {
    const { data } = await baisonApi.syncShops({ full_sync: true, page_size: 20 });
    if (data && data.success) {
      const d = data.data || {};
      ElMessage.success(`同步完成：共${d.total_records ?? "-"}家，新增${d.inserted ?? 0}，更新${d.updated ?? 0}`);
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
.baison-shops { padding: 16px; }
.page-toolbar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:12px; }
.filters { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.actions { display:flex; align-items:center; gap:12px; }
.last-sync { color:#909399; font-size:13px; }
.pager { margin-top:12px; display:flex; justify-content:flex-end; }
</style>
