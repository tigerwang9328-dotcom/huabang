<template>
  <div class="store-overview">
    <div class="page-header">
      <h2>门店总览</h2>
      <p class="page-desc">华邦标准门店维（dim_store），当前数据来源：百胜 E3ERP。经营指标待销售/库存数据接入后展示。</p>
    </div>

    <div class="toolbar">
      <div class="filters">
        <el-input v-model="filters.keyword" placeholder="店铺代码/名称" clearable style="width:200px" @keyup.enter="handleSearch" />
        <el-select v-model="filters.region_name" placeholder="区域" clearable filterable style="width:140px">
          <el-option v-for="a in options.regions" :key="a" :label="a" :value="a" />
        </el-select>
        <el-select v-model="filters.store_type" placeholder="店铺性质" clearable style="width:130px">
          <el-option v-for="t in options.storeTypes" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select v-model="filters.business_type" placeholder="线上/线下" clearable style="width:130px">
          <el-option v-for="o in options.bizTypes" :key="o" :label="o" :value="o" />
        </el-select>
        <el-select v-model="filters.status" placeholder="状态" clearable style="width:110px">
          <el-option label="营业" value="营业" />
          <el-option label="停用" value="停用" />
        </el-select>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>
      <span class="last-sync" v-if="lastSyncedAt">最后同步：{{ formatTime(lastSyncedAt) }}</span>
    </div>

    <el-table :data="list" v-loading="loading" border stripe size="small" style="width:100%">
      <el-table-column prop="store_code" label="店铺代码" width="100" fixed />
      <el-table-column prop="store_name" label="店铺名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="region_name" label="区域" width="110" />
      <el-table-column prop="store_type" label="店铺性质" width="90" />
      <el-table-column prop="business_type" label="线上/线下" width="100" />
      <el-table-column prop="province" label="省" width="70" />
      <el-table-column prop="city" label="市" width="90" />
      <el-table-column prop="county" label="区县" width="90" />
      <el-table-column prop="address" label="地址" min-width="180" show-overflow-tooltip />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.status === '营业' ? 'success' : 'info'" size="small">{{ row.status || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="月销售额" width="100">
        <template #default><span class="pending">待接入</span></template>
      </el-table-column>
      <el-table-column label="客单价" width="90">
        <template #default><span class="pending">待接入</span></template>
      </el-table-column>
      <el-table-column label="库存金额" width="100">
        <template #default><span class="pending">待接入</span></template>
      </el-table-column>
      <el-table-column prop="source_system" label="数据来源" width="90" />
      <el-table-column label="同步时间" width="160">
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
import { storeApi } from "@/api/store";

const loading = ref(false);
const list = ref<any[]>([]);
const total = ref(0);
const page = ref(1);
const page_size = ref(20);
const lastSyncedAt = ref<string | null>(null);
const filters = reactive({ keyword: "", region_name: "", store_type: "", business_type: "", status: "" });
const options = reactive<{ regions: string[]; storeTypes: string[]; bizTypes: string[] }>({ regions: [], storeTypes: [], bizTypes: [] });

function formatTime(t: string | null) {
  if (!t) return "-";
  return String(t).replace("T", " ").slice(0, 19);
}

async function fetchList() {
  loading.value = true;
  try {
    const params: any = { page: page.value, page_size: page_size.value };
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    const { data } = await storeApi.listStores(params);
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
    const { data } = await storeApi.listStores({ page: 1, page_size: 200 });
    const items = (data && data.data && data.data.items) || [];
    options.regions = [...new Set(items.map((x: any) => x.region_name).filter(Boolean))] as string[];
    options.storeTypes = [...new Set(items.map((x: any) => x.store_type).filter(Boolean))] as string[];
    options.bizTypes = [...new Set(items.map((x: any) => x.business_type).filter(Boolean))] as string[];
  } catch (_) { /* 忽略 */ }
}

function handleSearch() { page.value = 1; fetchList(); }
function handleReset() {
  filters.keyword = ""; filters.region_name = ""; filters.store_type = "";
  filters.business_type = ""; filters.status = "";
  page.value = 1; fetchList();
}
function handlePageChange(p: number) { page.value = p; fetchList(); }
function handleSizeChange(s: number) { page_size.value = s; page.value = 1; fetchList(); }

onMounted(() => { loadOptions(); fetchList(); });
</script>

<style scoped>
.store-overview { padding: 16px; }
.page-header { margin-bottom: 12px; }
.page-header h2 { font-size: 18px; color: #333; margin-bottom: 4px; }
.page-desc { color: #999; font-size: 13px; }
.toolbar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:12px; }
.filters { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.last-sync { color:#909399; font-size:13px; }
.pending { color:#c0c4cc; font-size:12px; }
.pager { margin-top:12px; display:flex; justify-content:flex-end; }
</style>
