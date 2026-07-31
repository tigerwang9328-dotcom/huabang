<template>
  <section class="styles-page" v-loading="loading">
    <div class="page-head">
      <div><el-button text @click="router.push({ name: 'DouyinColorVideoList' })">← 返回视频</el-button><p class="eyebrow">ANNOTATION CATALOG</p><h1>款号与颜色</h1><p>款色目录按当前启用账号隔离；不提供账号新增、启用或切换入口。</p></div>
      <el-button type="primary" @click="styleDialog = true">新增款号</el-button>
    </div>
    <el-alert v-if="loadError" title="款色目录读取或保存失败" :description="loadError" type="error" show-icon :closable="false" class="banner" />
    <el-alert v-else title="服务端控制" description="商品维护由服务端的 douyin.admin 权限和账号隔离校验控制；本页会展示返回错误，不将无权限误显示为空数据。" type="info" show-icon :closable="false" class="banner" />
    <el-table :data="styles" empty-text="当前账号尚无款号">
      <el-table-column prop="style_code" label="款号" width="150" />
      <el-table-column prop="style_name" label="名称" min-width="220" />
      <el-table-column prop="status" label="状态" width="120"><template #default="{ row }"><el-tag effect="plain">{{ row.status }}</el-tag></template></el-table-column>
      <el-table-column label="颜色" width="120"><template #default="{ row }"><el-button text type="primary" @click="showColors(row)">维护颜色</el-button></template></el-table-column>
    </el-table>

    <el-dialog v-model="styleDialog" title="新增款号" width="min(460px, 92vw)">
      <el-form label-position="top"><el-form-item label="款号"><el-input v-model="styleForm.style_code" /></el-form-item><el-form-item label="款号名称"><el-input v-model="styleForm.style_name" /></el-form-item></el-form>
      <template #footer><el-button @click="styleDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveStyle">保存</el-button></template>
    </el-dialog>
    <el-dialog v-model="colorDialog" :title="`颜色：${selectedStyle?.style_code || ''}`" width="min(620px, 92vw)">
      <el-table :data="colors" empty-text="尚未维护颜色"><el-table-column prop="color_code" label="颜色编码" /><el-table-column prop="color_name" label="颜色名称" /><el-table-column prop="status" label="状态" /></el-table>
      <el-form label-position="top" class="color-form"><el-form-item label="颜色编码"><el-input v-model="colorForm.color_code" /></el-form-item><el-form-item label="颜色名称"><el-input v-model="colorForm.color_name" /></el-form-item><el-button type="primary" :loading="saving" @click="saveColor">新增颜色</el-button></el-form>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";
import { douyinColorAnalyticsApi, type DouyinAnnotationContext, type DouyinGarmentColor, type DouyinGarmentStyle } from "@/api/douyinColorAnalytics";

const router = useRouter();
const loading = ref(false); const saving = ref(false); const loadError = ref("");
const context = ref<DouyinAnnotationContext | null>(null); const styles = ref<DouyinGarmentStyle[]>([]); const colors = ref<DouyinGarmentColor[]>([]); const selectedStyle = ref<DouyinGarmentStyle | null>(null);
const styleDialog = ref(false); const colorDialog = ref(false); const styleForm = ref({ style_code: "", style_name: "" }); const colorForm = ref({ color_code: "", color_name: "" });

async function load() { loading.value = true; loadError.value = ""; try { context.value = (await douyinColorAnalyticsApi.getAnnotationContext()).data; styles.value = (await douyinColorAnalyticsApi.listStyles(context.value.account.id)).data.items || []; } catch (error) { loadError.value = describeError(error); } finally { loading.value = false; } }
async function showColors(style: DouyinGarmentStyle) { if (!context.value) return; selectedStyle.value = style; colorDialog.value = true; try { colors.value = (await douyinColorAnalyticsApi.listColors(style.id, context.value.account.id)).data.items || []; } catch (error) { loadError.value = describeError(error); } }
async function saveStyle() { if (!context.value || !styleForm.value.style_code.trim() || !styleForm.value.style_name.trim()) { ElMessage.error("请填写款号和名称"); return; } saving.value = true; try { const created = (await douyinColorAnalyticsApi.createStyle({ account_id: context.value.account.id, style_code: styleForm.value.style_code.trim(), style_name: styleForm.value.style_name.trim() })).data; styles.value.unshift(created); styleForm.value = { style_code: "", style_name: "" }; styleDialog.value = false; ElMessage.success("已保存款号，服务端已记录操作"); } catch (error) { loadError.value = describeError(error); } finally { saving.value = false; } }
async function saveColor() { if (!context.value || !selectedStyle.value || !colorForm.value.color_code.trim() || !colorForm.value.color_name.trim()) { ElMessage.error("请填写颜色编码和名称"); return; } saving.value = true; try { const created = (await douyinColorAnalyticsApi.createColor(selectedStyle.value.id, { account_id: context.value.account.id, color_code: colorForm.value.color_code.trim(), color_name: colorForm.value.color_name.trim() })).data; colors.value.unshift(created); colorForm.value = { color_code: "", color_name: "" }; ElMessage.success("已保存颜色，服务端已记录操作"); } catch (error) { loadError.value = describeError(error); } finally { saving.value = false; } }
function describeError(error: unknown) { const response = (error as { response?: { data?: { detail?: string; message?: string } } })?.response?.data; return response?.detail || response?.message || (error instanceof Error ? error.message : "请求失败"); }
onMounted(load);
</script>

<style scoped>
.styles-page { padding: 24px; }.page-head { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 16px; }.page-head h1 { margin: 5px 0; color: #172033; }.page-head p { margin: 0; color: #667085; }.eyebrow { font-size: 11px; font-weight: 800; letter-spacing: .09em; color: #5266a6 !important; }.banner { margin-bottom: 16px; }.color-form { margin-top: 16px; border-top: 1px solid #edf0f5; padding-top: 12px; }@media(max-width: 640px) { .styles-page { padding: 16px; }.page-head { flex-direction: column; } }
</style>
