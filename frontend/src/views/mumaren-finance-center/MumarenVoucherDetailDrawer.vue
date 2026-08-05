<template>
  <el-drawer :model-value="modelValue" title="凭证详情" direction="rtl" size="960px" @update:model-value="emit('update:modelValue', $event)">
    <el-skeleton v-if="loading" :rows="8" animated />
    <el-alert v-else-if="error" type="error" :title="error" :closable="false" show-icon />
    <template v-else-if="detail">
      <div class="meta-grid">
        <div><span>凭证日期</span><strong>{{ detail.voucher_date }}</strong></div>
        <div><span>凭证字 / 号</span><strong>{{ detail.voucher_type || '—' }} {{ detail.voucher_no }}</strong></div>
        <div><span>状态</span><strong>{{ statusLabel(detail.status) }}</strong></div>
        <div><span>摘要</span><strong>{{ detail.summary || '—' }}</strong></div>
      </div>
      <div class="audit-grid">
        <div><span>审核人 / 时间</span><strong>{{ audit(detail.reviewed_by, detail.reviewed_at) }}</strong></div>
        <div><span>过账人 / 时间</span><strong>{{ audit(detail.posted_by, detail.posted_at) }}</strong></div>
        <div><span>来源账套</span><strong>{{ detail.source_database || '—' }}</strong></div>
        <div><span>历史来源</span><strong>{{ detail.source_system || '—' }}</strong></div>
        <div><span>只读</span><strong>{{ detail.is_readonly ? '是' : '否' }}</strong></div>
        <div><span>已规范化</span><strong>{{ detail.is_normalized ? '是' : '否' }}</strong></div>
      </div>
      <el-table :data="detail.lines" size="small" stripe>
        <el-table-column prop="line_no" label="行" width="58" />
        <el-table-column prop="line_summary" label="有效摘要" min-width="170"><template #default="scope">{{ scope.row.line_summary || '—' }}</template></el-table-column>
        <el-table-column label="会计科目" min-width="180"><template #default="scope">{{ scope.row.account_code }} {{ scope.row.account_name }}</template></el-table-column>
        <el-table-column prop="auxiliaries" label="辅助核算" min-width="160" />
        <el-table-column label="借方" width="130" align="right"><template #default="scope">{{ money(scope.row.debit_amount) }}</template></el-table-column>
        <el-table-column label="贷方" width="130" align="right"><template #default="scope">{{ money(scope.row.credit_amount) }}</template></el-table-column>
      </el-table>
      <div class="totals"><span>借方合计：{{ money(detail.total_debit) }}</span><span>贷方合计：{{ money(detail.total_credit) }}</span><el-tag :type="detail.is_balanced ? 'success' : 'danger'">{{ detail.is_balanced ? '借贷平衡' : '借贷不平' }}</el-tag></div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { mumarenFinanceCenterApi, type MumarenVoucherDetail } from "@/api/mumarenFinanceCenter";

const props = defineProps<{ modelValue: boolean; bookId?: number; voucherId?: number }>();
const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();
const detail = ref<MumarenVoucherDetail>();
const loading = ref(false);
const error = ref("");
let requestVersion = 0;

const money = (value?: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
const statusLabel = (status: string) => ({ draft: "草稿", reviewed: "已审核", posted: "已过账" }[status] || status);
const audit = (user?: number | null, at?: string | null) => user || at ? `${user ?? '—'} / ${at ?? '—'}` : "—";

const load = async () => {
  const version = ++requestVersion;
  detail.value = undefined;
  error.value = "";
  if (!props.modelValue || !props.bookId || !props.voucherId) {
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    const response = await mumarenFinanceCenterApi.getVoucherDetail(props.voucherId, props.bookId);
    if (version === requestVersion) detail.value = response.data.data;
  } catch {
    if (version === requestVersion) error.value = "无法加载该账簿中的凭证详情。";
  } finally {
    if (version === requestVersion) loading.value = false;
  }
};

watch(() => [props.modelValue, props.bookId, props.voucherId], () => { void load(); }, { immediate: true });
</script>

<style scoped>
.meta-grid, .audit-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 16px; }
.meta-grid > div, .audit-grid > div { padding: 10px 12px; background: #f8fafc; border-radius: 8px; display: grid; gap: 4px; }
span { color: #66758a; font-size: 12px; } strong { color: #23354d; font-weight: 600; overflow-wrap: anywhere; }
.totals { display: flex; justify-content: flex-end; align-items: center; flex-wrap: wrap; gap: 20px; margin-top: 16px; font-weight: 600; }
@media (max-width: 640px) { .meta-grid, .audit-grid { grid-template-columns: 1fr; } }
</style>
