<template>
  <section class="panel">
    <p class="panel-kicker">当前账</p>
    <div class="heading"><div><h2>工作台</h2><p>正式记账仅在人工审核后由财务人员过账。</p></div><el-button :loading="loading" @click="load">刷新</el-button></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-descriptions v-else :column="1" border>
      <el-descriptions-item label="模块">{{ catalog.module || "加载中" }}</el-descriptions-item>
      <el-descriptions-item label="已接入能力">{{ catalog.capabilities?.join("、") || "暂无" }}</el-descriptions-item>
    </el-descriptions>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { mumarenFinanceCenterApi, type FinanceCenterCatalog } from "@/api/mumarenFinanceCenter";
const catalog = ref<Partial<FinanceCenterCatalog>>({}); const error = ref(""); const loading = ref(false);
const load = async () => { loading.value = true; error.value = ""; try { catalog.value = (await mumarenFinanceCenterApi.getCatalog()).data.data; } catch { error.value = "无法加载独立财务中心目录。"; } finally { loading.value = false; } };
onMounted(load);
</script>
<style scoped>.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; }.heading { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }.panel-kicker { margin:0; color:#176b97; font-size:12px; font-weight:700; letter-spacing:.08em; }h2 { margin:8px 0; }p { color:#5d6b7e; }</style>
