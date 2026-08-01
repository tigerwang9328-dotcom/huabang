<template>
  <div class="baison-api-page">
    <section class="api-hero">
      <div>
        <p class="eyebrow">BAISON OPEN API</p>
        <h2>百胜 API 管理</h2>
        <p class="hero-desc">统一维护百胜 E3ERP 接口目录，支持 method + JSON 参数快速联调，不落库、不暴露密钥。</p>
      </div>
      <div class="hero-actions">
        <el-button :loading="catalogLoading" @click="loadCatalog">刷新目录</el-button>
        <el-button type="primary" :loading="testing" @click="runApiTest">执行联调</el-button>
      </div>
    </section>

    <el-row :gutter="16">
      <el-col :span="10">
        <el-card class="panel-card" shadow="never">
          <template #header>
            <div class="card-title">
              <span>接口目录</span>
              <el-tag size="small" type="info">{{ catalog.length }} 个接口</el-tag>
            </div>
          </template>

          <el-table
            v-loading="catalogLoading"
            :data="catalog"
            stripe
            size="small"
            class="catalog-table"
            @row-click="selectCatalogItem"
          >
            <el-table-column prop="module" label="模块" width="92" />
            <el-table-column label="接口">
              <template #default="{ row }">
                <div class="api-name">{{ row.name }}</div>
                <div class="api-method">{{ row.method }}</div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="88">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'connected' ? 'success' : 'info'">
                  {{ row.status === 'connected' ? '已接入' : row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="同步" width="108">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="primary"
                  plain
                  :loading="syncingKey === row.sync_key"
                  :disabled="!row.sync_key"
                  @click.stop="syncToModule(row)"
                >
                  同步
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="14">
        <el-card class="panel-card" shadow="never">
          <template #header>
            <div class="card-title">
              <span>通用接口联调</span>
              <el-tag size="small" type="warning">不落库</el-tag>
            </div>
          </template>

          <el-form label-width="90px">
            <el-form-item label="Method">
              <el-input v-model="testForm.method" placeholder="例如：base.shop.get_list" clearable />
            </el-form-item>
            <el-form-item label="JSON参数">
              <el-input
                v-model="testForm.paramsText"
                type="textarea"
                :rows="8"
                spellcheck="false"
                placeholder='{"page":1,"page_size":20}'
                class="json-editor"
              />
            </el-form-item>
            <el-form-item label="选项">
              <el-checkbox v-model="testForm.includeRaw">返回原始响应</el-checkbox>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="testing" @click="runApiTest">执行联调</el-button>
              <el-button @click="formatParams">格式化 JSON</el-button>
              <el-button @click="resetForm">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="panel-card" shadow="never">
          <template #header>
            <div class="card-title">
              <span>同步参数</span>
              <el-tag size="small" type="info">写入中台模块</el-tag>
            </div>
          </template>

          <el-form label-width="92px">
            <el-row :gutter="12">
              <el-col :span="8">
                <el-form-item label="同步模式">
                  <el-switch v-model="syncForm.full_sync" active-text="全量" inactive-text="试跑" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="每页数量">
                  <el-input-number v-model="syncForm.page_size" :min="1" :max="200" style="width:100%" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="门店上限">
                  <el-input-number v-model="syncForm.store_limit" :min="1" :max="200" style="width:100%" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="开始时间">
                  <el-input v-model="syncForm.start_date" placeholder="销售同步用，如 2026-06-26 00:00:00" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="结束时间">
                  <el-input v-model="syncForm.end_date" placeholder="销售同步用，如 2026-06-26 23:59:59" />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>

          <el-alert
            type="info"
            show-icon
            :closable="false"
            title="SKU、库存、销售全量同步会自动转入后台执行；门店、仓库、商品会直接返回同步结果。"
          />
        </el-card>

        <el-card class="panel-card result-card" shadow="never">
          <template #header>
            <div class="card-title">
              <span>联调结果</span>
              <el-tag v-if="testResult" size="small" :type="testResult.success ? 'success' : 'danger'">
                {{ testResult.success ? '成功' : '失败' }}
              </el-tag>
            </div>
          </template>

          <el-empty v-if="!testResult" description="执行联调后将在这里展示响应结果" />
          <pre v-else class="result-json">{{ prettyResult }}</pre>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { baisonApi } from "@/api/baison";

const catalogLoading = ref(false);
const testing = ref(false);
const syncingKey = ref("");
const catalog = ref<any[]>([]);
const testResult = ref<any>(null);

const testForm = reactive({
  method: "base.shop.get_list",
  paramsText: JSON.stringify({ page: 1, page_size: 1 }, null, 2),
  includeRaw: false,
});

const syncForm = reactive({
  full_sync: false,
  page_size: 20,
  store_limit: 3,
  start_date: "",
  end_date: "",
});

const prettyResult = computed(() => JSON.stringify(testResult.value, null, 2));

const loadCatalog = async () => {
  catalogLoading.value = true;
  try {
    const res = await baisonApi.getCatalog();
    catalog.value = res.data.data?.items || [];
  } catch (e: any) {
    ElMessage.error(`接口目录加载失败：${e.message || "未知错误"}`);
  } finally {
    catalogLoading.value = false;
  }
};

const parseParams = () => {
  try {
    return testForm.paramsText.trim() ? JSON.parse(testForm.paramsText) : {};
  } catch {
    ElMessage.error("JSON 参数格式不正确，请检查逗号、引号和括号");
    return null;
  }
};

const runApiTest = async () => {
  const method = testForm.method.trim();
  if (!method) {
    ElMessage.warning("请先填写百胜接口 method");
    return;
  }
  const params = parseParams();
  if (params === null) return;

  testing.value = true;
  testResult.value = null;
  try {
    const res = await baisonApi.testApi({
      method,
      params,
      include_raw_response: testForm.includeRaw,
    });
    testResult.value = res.data;
    if (res.data.success) ElMessage.success("百胜接口联调成功");
    else ElMessage.warning(res.data.message || "百胜接口返回失败");
  } catch (e: any) {
    testResult.value = { success: false, message: e.message || "调用失败" };
  } finally {
    testing.value = false;
  }
};

const selectCatalogItem = (row: any) => {
  testForm.method = row.method;
  testForm.paramsText = JSON.stringify({ page: 1, page_size: 1 }, null, 2);
  testResult.value = null;
};

const syncToModule = async (row: any) => {
  if (!row.sync_key) {
    ElMessage.warning("该接口尚未配置同步模块");
    return;
  }
  syncingKey.value = row.sync_key;
  testResult.value = null;
  try {
    const payload: any = {
      full_sync: syncForm.full_sync,
      page_size: syncForm.page_size,
      store_limit: syncForm.store_limit,
    };
    if (syncForm.start_date) payload.start_date = syncForm.start_date;
    if (syncForm.end_date) payload.end_date = syncForm.end_date;
    const res = await baisonApi.syncModule(row.sync_key, payload);
    testResult.value = res.data;
    if (res.data.success) {
      ElMessage.success(res.data.message || "同步任务已提交");
    } else {
      ElMessage.warning(res.data.message || "同步失败");
    }
  } catch (e: any) {
    testResult.value = { success: false, message: e.message || "同步失败" };
  } finally {
    syncingKey.value = "";
  }
};

const formatParams = () => {
  const params = parseParams();
  if (params === null) return;
  testForm.paramsText = JSON.stringify(params, null, 2);
};

const resetForm = () => {
  testForm.method = "base.shop.get_list";
  testForm.paramsText = JSON.stringify({ page: 1, page_size: 1 }, null, 2);
  testForm.includeRaw = false;
  testResult.value = null;
};

onMounted(loadCatalog);
</script>

<style scoped>
.baison-api-page {
  padding: 0;
}

.api-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 24px 28px;
  margin-bottom: 16px;
  border-radius: 16px;
  background: #f8fafc;
  color: #334155;
  border: 1px solid #e5eaf2;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.035);
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.18em;
  color: #d4af37;
  font-weight: 700;
}

.api-hero h2 {
  margin: 0;
  font-size: 24px;
  letter-spacing: 0.02em;
}

.hero-desc {
  margin: 8px 0 0;
  color: #64748b;
}

.hero-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.panel-card {
  border: 1px solid #e8edf5;
  border-radius: 14px;
  margin-bottom: 16px;
}

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 700;
  color: #0f172a;
}

.catalog-table {
  cursor: pointer;
}

.api-name {
  font-weight: 700;
  color: #0f172a;
}

.api-method {
  margin-top: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: #64748b;
}

.json-editor :deep(textarea),
.result-json {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.result-card {
  min-height: 300px;
}

.result-json {
  max-height: 460px;
  overflow: auto;
  padding: 14px;
  margin: 0;
  border-radius: 8px;
  background: #f8fafc;
  color: #334155;
  border: 1px solid #e5eaf2;
  font-size: 12px;
  line-height: 1.7;
}
</style>
