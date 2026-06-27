<template>
  <div class="product-master">
    <div class="page-header">
      <h2>商品主档</h2>
      <p class="page-desc">华邦标准商品维（dim_product），当前数据来源：百胜 E3ERP。销量/库存/生命周期等经营指标待销售、库存数据接入后展示。</p>
    </div>

    <div class="toolbar">
      <div class="filters">
        <el-input v-model="filters.keyword" placeholder="款号/商品名称" clearable style="width:180px" @keyup.enter="handleSearch" />
        <el-select v-model="filters.brand_name" placeholder="品牌" clearable filterable style="width:120px">
          <el-option v-for="b in options.brands" :key="b" :label="b" :value="b" />
        </el-select>
        <el-select v-model="filters.category_name" placeholder="品类" clearable filterable style="width:130px">
          <el-option v-for="c in options.categories" :key="c" :label="c" :value="c" />
        </el-select>
        <el-select v-model="filters.year" placeholder="年份" clearable style="width:100px">
          <el-option v-for="y in options.years" :key="y" :label="y" :value="y" />
        </el-select>
        <el-select v-model="filters.season" placeholder="季节" clearable style="width:100px">
          <el-option v-for="s in options.seasons" :key="s" :label="s" :value="s" />
        </el-select>
        <el-select v-model="filters.status" placeholder="状态" clearable style="width:100px">
          <el-option label="启用" value="active" />
          <el-option label="停用" value="disabled" />
        </el-select>
        <el-button type="primary" @click="handleSearch">搜索</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>
      <div class="actions">
        <span class="last-sync" v-if="lastSyncedAt">最后同步：{{ formatTime(lastSyncedAt) }}</span>
        <el-button type="success" :loading="syncing" @click="handleSync">
          <el-icon style="margin-right:4px"><Refresh /></el-icon>同步商品主档
        </el-button>
      </div>
    </div>

    <el-table :data="list" v-loading="loading" border stripe size="small" style="width:100%">
      <el-table-column prop="product_code" label="款号" width="120" fixed />
      <el-table-column prop="product_name" label="商品名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="top_category_name" label="一级品类" width="90" />
      <el-table-column prop="category_name" label="品类" width="100" />
      <el-table-column prop="brand_name" label="品牌" width="90" />
      <el-table-column prop="year" label="年份" width="70" />
      <el-table-column prop="season" label="季节" width="70" />
      <el-table-column prop="tag_price" label="吊牌价" width="90" />
      <el-table-column prop="supplier_name" label="供应商" min-width="140" show-overflow-tooltip />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">{{ row.status === 'active' ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="近7天销量" width="90"><template #default><span class="pending">待接入</span></template></el-table-column>
      <el-table-column label="当前库存" width="90"><template #default><span class="pending">待接入</span></template></el-table-column>
      <el-table-column label="生命周期" width="90"><template #default><span class="pending">待接入</span></template></el-table-column>
      <el-table-column label="AI建议" width="90"><template #default><span class="pending">待接入</span></template></el-table-column>
      <el-table-column prop="source_system" label="来源系统" width="90" />
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
import { productApi } from "@/api/product";

const loading = ref(false);
const syncing = ref(false);
const list = ref<any[]>([]);
const total = ref(0);
const page = ref(1);
const page_size = ref(20);
const lastSyncedAt = ref<string | null>(null);
const filters = reactive<any>({ keyword: "", brand_name: "", category_name: "", year: "", season: "", status: "" });
const options = reactive<{ brands: string[]; categories: string[]; years: any[]; seasons: string[] }>({ brands: [], categories: [], years: [], seasons: [] });

function formatTime(t: string | null) {
  if (!t) return "-";
  return String(t).replace("T", " ").slice(0, 19);
}

async function fetchList() {
  loading.value = true;
  try {
    const params: any = { page: page.value, page_size: page_size.value };
    Object.entries(filters).forEach(([k, v]) => { if (v !== "" && v !== null && v !== undefined) params[k] = v; });
    const { data } = await productApi.listProducts(params);
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
    const { data } = await productApi.listProducts({ page: 1, page_size: 200 });
    const items = (data && data.data && data.data.items) || [];
    options.brands = [...new Set(items.map((x: any) => x.brand_name).filter(Boolean))] as string[];
    options.categories = [...new Set(items.map((x: any) => x.category_name).filter(Boolean))] as string[];
    options.years = [...new Set(items.map((x: any) => x.year).filter((v: any) => v !== null && v !== undefined))].sort();
    options.seasons = [...new Set(items.map((x: any) => x.season).filter(Boolean))] as string[];
  } catch (_) { /* 忽略 */ }
}

function handleSearch() { page.value = 1; fetchList(); }
function handleReset() {
  filters.keyword = ""; filters.brand_name = ""; filters.category_name = "";
  filters.year = ""; filters.season = ""; filters.status = "";
  page.value = 1; fetchList();
}
function handlePageChange(p: number) { page.value = p; fetchList(); }
function handleSizeChange(s: number) { page_size.value = s; page.value = 1; fetchList(); }

async function handleSync() {
  syncing.value = true;
  try {
    const { data } = await productApi.syncProducts({ full_sync: true, page_size: 20 });
    if (data && data.success) {
      const d = data.data || {};
      ElMessage.success(`同步完成：共${d.total_result ?? "-"}款，新增${d.dim_inserted ?? 0}，更新${d.dim_updated ?? 0}`);
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
.product-master { padding: 16px; }
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
