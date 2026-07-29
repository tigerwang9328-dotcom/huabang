<template>
  <section class="workspace">
    <el-card shadow="never" class="hero">
      <template #header>
        <div class="title-row">
          <div>
            <p class="eyebrow">财务中心 / V2.0</p>
            <h1>会计工作台</h1>
          </div>
          <el-tag type="warning" effect="light">当前为只读验收阶段</el-tag>
        </div>
      </template>
      <p>
        新账采用“草稿 → 财务人员审核 → 人工过账”。历史金蝶数据与当前账严格隔离；在最终切换 Gate 通过前，不开放 V2 制单、审核或过账。
      </p>
      <el-alert
        :title="gateMessage"
        :type="books.length ? 'warning' : 'info'"
        :closable="false"
        show-icon
      />
    </el-card>

    <el-card shadow="never" class="book-card">
      <template #header>
        <div class="title-row">
          <strong>当前账账簿</strong>
          <el-button :loading="loading" text type="primary" @click="loadBooks">刷新</el-button>
        </div>
      </template>
      <el-table v-loading="loading" :data="books" empty-text="尚未建立 V2 当前账账簿">
        <el-table-column prop="book_code" label="账簿编码" min-width="140" />
        <el-table-column prop="book_name" label="账簿名称" min-width="220" />
        <el-table-column prop="status" label="状态" min-width="120" />
        <el-table-column label="正式报表">
          <template #default="{ row }">
            <el-tag :type="row.formal_report_blocked ? 'danger' : 'success'" effect="plain">
              {{ row.formal_report_blocked ? "已阻断" : "可出具" }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="books.length" class="workspace-filter">
        <el-select v-model="selectedBookId" aria-label="选择 V2 当前账账簿" @change="loadWorkspace">
          <el-option v-for="book in books" :key="book.id" :label="`${book.book_code} · ${book.book_name}`" :value="book.id" />
        </el-select>
        <el-button :loading="workspaceLoading" text type="primary" @click="loadWorkspace">刷新账期与凭证</el-button>
      </div>
    </el-card>

    <el-card v-if="selectedBookId" v-loading="workspaceLoading" shadow="never">
      <template #header><strong>当前账工作区（只读）</strong></template>
      <el-alert title="这里展示的是 fin_current 的账期、可制单科目和凭证状态；写入仍受后端 Gate 强制控制。" type="info" :closable="false" show-icon />
      <div class="workspace-grid">
        <section>
          <h2>会计期间</h2>
          <el-table :data="periods" max-height="240" empty-text="当前账尚无会计期间">
            <el-table-column prop="period_code" label="期间" min-width="100" />
            <el-table-column prop="status" label="状态" min-width="90" />
            <el-table-column prop="start_date" label="开始" min-width="110" />
            <el-table-column prop="end_date" label="结束" min-width="110" />
          </el-table>
        </section>
        <section>
          <h2>可制单科目</h2>
          <el-table :data="accounts" max-height="240" empty-text="当前账尚无可制单科目">
            <el-table-column prop="account_code" label="编码" min-width="100" />
            <el-table-column prop="account_name" label="科目" min-width="150" />
            <el-table-column prop="normal_balance" label="余额方向" min-width="90" />
          </el-table>
        </section>
      </div>
      <section class="voucher-section">
        <h2>凭证工作流</h2>
        <el-table :data="vouchers" max-height="300" empty-text="当前账尚无凭证">
          <el-table-column prop="voucher_date" label="日期" min-width="110" />
          <el-table-column prop="voucher_no" label="凭证号" min-width="110"><template #default="{ row }">{{ row.voucher_no || "待人工过账编号" }}</template></el-table-column>
          <el-table-column prop="status" label="状态" min-width="100" />
          <el-table-column prop="total_debit" label="借方合计" min-width="110" />
          <el-table-column prop="total_credit" label="贷方合计" min-width="110" />
          <el-table-column prop="prepared_by" label="制单人" min-width="100" />
          <el-table-column prop="reviewer_id" label="审核人" min-width="100" />
          <el-table-column prop="posted_by" label="过账人" min-width="100" />
        </el-table>
      </section>
    </el-card>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  financeV2Api,
  type FinanceV2Account,
  type FinanceV2Book,
  type FinanceV2Period,
  type FinanceV2Voucher,
} from "@/api/financeV2";

const books = ref<FinanceV2Book[]>([]);
const selectedBookId = ref<number>();
const periods = ref<FinanceV2Period[]>([]);
const accounts = ref<FinanceV2Account[]>([]);
const vouchers = ref<FinanceV2Voucher[]>([]);
const loading = ref(false);
const workspaceLoading = ref(false);
const loadError = ref("");

const gateMessage = computed(() => {
  if (loadError.value) return `无法读取 V2 账簿：${loadError.value}`;
  if (!books.value.length) return "尚未导入或批准 V2 当前账数据；这不是零余额，也不代表可开始制单。";
  return "生产写入开关仍应保持关闭，直至历史核对、最终期初、旧入口冻结与人工验收全部通过。";
});

async function loadBooks() {
  loading.value = true;
  loadError.value = "";
  try {
    const response = await financeV2Api.listBooks();
    books.value = response.data || [];
    if (!selectedBookId.value && books.value.length) selectedBookId.value = books.value[0].id;
    await loadWorkspace();
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "请求失败";
  } finally {
    loading.value = false;
  }
}

async function loadWorkspace() {
  if (!selectedBookId.value) {
    periods.value = [];
    accounts.value = [];
    vouchers.value = [];
    return;
  }
  workspaceLoading.value = true;
  try {
    const [periodResponse, accountResponse, voucherResponse] = await Promise.all([
      financeV2Api.listPeriods(selectedBookId.value),
      financeV2Api.listAccounts(selectedBookId.value),
      financeV2Api.listVouchers(selectedBookId.value),
    ]);
    periods.value = periodResponse.data || [];
    accounts.value = accountResponse.data || [];
    vouchers.value = voucherResponse.data || [];
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "工作区读取失败";
  } finally {
    workspaceLoading.value = false;
  }
}

onMounted(loadBooks);
</script>

<style scoped>
.workspace { display: grid; gap: 16px; }
.hero p { margin: 0 0 16px; color: var(--el-text-color-regular); line-height: 1.7; }
.title-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.title-row h1 { margin: 2px 0 0; font-size: 22px; }
.eyebrow { margin: 0; color: var(--el-color-primary); font-size: 12px; font-weight: 600; }
.book-card { min-height: 260px; }
.workspace-filter { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.workspace-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }
.workspace-grid h2, .voucher-section h2 { margin: 0 0 10px; font-size: 15px; }
.voucher-section { margin-top: 20px; }
@media (max-width: 900px) { .workspace-grid { grid-template-columns: 1fr; } }
</style>
