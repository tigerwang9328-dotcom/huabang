<template>
  <section class="panel">
    <div class="heading">
      <div><p class="panel-kicker">凭证流程</p><h2>查凭证</h2><p>{{ isReadonly ? "金蝶迁移账簿凭证；永久只读，仅供核对。" : "按凭证或分录检索；写入、审核和人工过账仍沿用原有流程。" }}</p></div>
      <div class="heading-actions"><el-button :loading="loading" :disabled="!bookId" @click="() => load()">查询</el-button><el-button :disabled="!currentItems.length" @click="exportCsv">导出当前筛选</el-button><router-link to="/app/finance-center/mumaren/vouchers/create"><el-button type="primary" :disabled="isReadonly">录入新凭证</el-button></router-link></div>
    </div>
    <el-radio-group v-model="viewMode" @change="() => load()"><el-radio-button label="voucher">按凭证</el-radio-button><el-radio-button label="line">按分录</el-radio-button></el-radio-group>
    <div class="filters">
      <el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange"><el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" /></el-select>
      <el-date-picker v-model="dateFrom" type="date" value-format="YYYY-MM-DD" placeholder="开始日期" @change="onDateChange" />
      <el-date-picker v-model="dateTo" type="date" value-format="YYYY-MM-DD" placeholder="结束日期" @change="onDateChange" />
      <el-input v-model="period" clearable placeholder="会计期间（YYYY-MM）" @change="onPeriodChange" />
      <el-select v-model="status" clearable placeholder="全部状态"><el-option label="草稿" value="draft" /><el-option label="已审核" value="reviewed" /><el-option label="已过账" value="posted" /></el-select>
      <el-input v-model="voucherType" clearable placeholder="凭证字" />
      <el-input v-model="keyword" clearable placeholder="凭证号或总摘要" @keyup.enter="() => load()" />
      <el-select v-model="accountId" clearable placeholder="会计科目"><el-option v-for="account in accounts" :key="account.id" :label="`${account.account_code} ${account.account_name}`" :value="account.id" /></el-select>
      <el-button @click="resetFilters">重置</el-button>
    </div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-empty v-else-if="!bookId" description="请先选择独立账簿" />
    <template v-else-if="viewMode === 'voucher'">
      <el-table :data="voucherPage.items" v-loading="loading" stripe empty-text="暂无符合条件的凭证"><el-table-column prop="voucher_type" label="凭证字" width="78" /><el-table-column prop="voucher_no" label="凭证号" min-width="130" /><el-table-column prop="voucher_date" label="日期" width="112" /><el-table-column prop="summary" label="总摘要" min-width="200" show-overflow-tooltip /><el-table-column label="状态" width="94"><template #default="scope"><el-tag size="small" :type="statusTagType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag></template></el-table-column><el-table-column label="借方" width="130" align="right"><template #default="scope">{{ money(scope.row.total_debit) }}</template></el-table-column><el-table-column label="贷方" width="130" align="right"><template #default="scope">{{ money(scope.row.total_credit) }}</template></el-table-column><el-table-column label="操作" width="220"><template #default="scope"><el-button size="small" link type="primary" @click="openVoucher(scope.row.id)">查看凭证</el-button><el-button v-if="scope.row.status === 'draft'" size="small" link :disabled="isReadonly" :loading="actingId === scope.row.id" @click="review(scope.row)">审核</el-button><el-popconfirm v-if="scope.row.status === 'draft' && !isReadonly" title="确定删除该草稿凭证？此操作不可恢复。" @confirm="remove(scope.row)"><template #reference><el-button size="small" link type="danger" :loading="actingId === scope.row.id">删除</el-button></template></el-popconfirm><el-button v-if="scope.row.status === 'reviewed'" size="small" link type="success" :disabled="isReadonly" :loading="actingId === scope.row.id" @click="post(scope.row)">人工过账</el-button></template></el-table-column></el-table>
    </template>
    <template v-else>
      <el-table :data="linePage.items" v-loading="loading" stripe empty-text="暂无符合条件的分录"><el-table-column prop="voucher_date" label="日期" width="112" /><el-table-column label="凭证" min-width="125"><template #default="scope">{{ scope.row.voucher_type }} {{ scope.row.voucher_no }}</template></el-table-column><el-table-column prop="line_no" label="行" width="58" /><el-table-column prop="line_summary" label="有效摘要" min-width="180"><template #default="scope">{{ scope.row.line_summary || '—' }}</template></el-table-column><el-table-column label="会计科目" min-width="180"><template #default="scope">{{ scope.row.account_code }} {{ scope.row.account_name }}</template></el-table-column><el-table-column prop="auxiliaries" label="辅助核算" min-width="130" /><el-table-column label="借方" width="120" align="right"><template #default="scope">{{ money(scope.row.debit_amount) }}</template></el-table-column><el-table-column label="贷方" width="120" align="right"><template #default="scope">{{ money(scope.row.credit_amount) }}</template></el-table-column><el-table-column label="操作" width="96"><template #default="scope"><el-button size="small" link type="primary" @click="openVoucher(scope.row.voucher_id)">查看凭证</el-button></template></el-table-column></el-table>
    </template>
    <el-pagination v-if="bookId" background layout="prev, pager, next, total" :page-size="currentPage.limit" :current-page="Math.floor(currentPage.offset / currentPage.limit) + 1" :total="currentPage.total" @current-change="changePage" />
    <MumarenVoucherDetailDrawer v-model="detailVisible" :book-id="bookId" :voucher-id="detailVoucherId" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { useMumarenFinanceBook } from "@/composables/useMumarenFinanceBook";
import MumarenVoucherDetailDrawer from "./MumarenVoucherDetailDrawer.vue";
import { mumarenFinanceCenterApi, type MumarenFinanceAccount, type MumarenFinanceVoucher, type MumarenVoucherQueryLine, type MumarenVoucherQueryPage } from "@/api/mumarenFinanceCenter";

const { books, bookId, isReadonly, loadBooks } = useMumarenFinanceBook();
const route = useRoute();
const viewMode = ref<"voucher" | "line">("voucher");
const dateFrom = ref(""); const dateTo = ref(""); const period = ref(""); const status = ref<MumarenFinanceVoucher["status"]>(); const voucherType = ref(""); const keyword = ref(""); const accountId = ref<number>();
const accounts = ref<MumarenFinanceAccount[]>([]);
const voucherPage = ref<MumarenVoucherQueryPage<MumarenFinanceVoucher>>({ items: [], total: 0, offset: 0, limit: 50 });
const linePage = ref<MumarenVoucherQueryPage<MumarenVoucherQueryLine>>({ items: [], total: 0, offset: 0, limit: 50 });
const loading = ref(false); const error = ref(""); const actingId = ref<number>(); const detailVisible = ref(false); const detailVoucherId = ref<number>();
let loadRequestVersion = 0; let accountRequestVersion = 0;
const currentPage = computed(() => viewMode.value === "voucher" ? voucherPage.value : linePage.value);
const currentItems = computed(() => currentPage.value.items);
const money = (value?: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
const statusLabel = (value: string) => ({ draft: "草稿", reviewed: "已审核", posted: "已过账" }[value] || value);
const statusTagType = (value: string): "" | "warning" | "success" => value === "draft" ? "" : value === "reviewed" ? "warning" : "success";
const params = (offset = 0) => ({ book_id: bookId.value!, date_from: dateFrom.value || undefined, date_to: dateTo.value || undefined, period: period.value || undefined, status: status.value, voucher_type: voucherType.value.trim() || undefined, keyword: keyword.value.trim() || undefined, account_id: accountId.value, offset, limit: 50 });

const load = async (offset = 0) => {
  if (!bookId.value) return;
  const version = ++loadRequestVersion; const selectedBook = bookId.value; loading.value = true; error.value = "";
  try {
    const response = viewMode.value === "voucher" ? await mumarenFinanceCenterApi.queryVouchers(params(offset)) : await mumarenFinanceCenterApi.queryVoucherLines(params(offset));
    if (version !== loadRequestVersion || selectedBook !== bookId.value) return;
    if (viewMode.value === "voucher") voucherPage.value = response.data.data as MumarenVoucherQueryPage<MumarenFinanceVoucher>;
    else linePage.value = response.data.data as MumarenVoucherQueryPage<MumarenVoucherQueryLine>;
  } catch (caught: unknown) {
    if (version === loadRequestVersion && selectedBook === bookId.value) error.value = "无法加载凭证查询结果。";
  } finally { if (version === loadRequestVersion && selectedBook === bookId.value) loading.value = false; }
};
const loadAccounts = async () => { const version = ++accountRequestVersion; const selectedBook = bookId.value; accounts.value = []; if (!selectedBook) return; const response = await mumarenFinanceCenterApi.listAccounts(selectedBook); if (version === accountRequestVersion && selectedBook === bookId.value) accounts.value = response.data.data; };
const onBookChange = async () => { const selectedBook = bookId.value; accountId.value = undefined; voucherPage.value = { items: [], total: 0, offset: 0, limit: 50 }; linePage.value = { items: [], total: 0, offset: 0, limit: 50 }; detailVisible.value = false; detailVoucherId.value = undefined; await loadAccounts(); if (selectedBook === bookId.value) await load(); };
const onDateChange = () => { if (dateFrom.value || dateTo.value) period.value = ""; };
const onPeriodChange = () => { if (period.value) { dateFrom.value = ""; dateTo.value = ""; } };
const changePage = (page: number) => { void load((page - 1) * currentPage.value.limit); };
const resetFilters = () => { dateFrom.value = ""; dateTo.value = ""; period.value = ""; status.value = undefined; voucherType.value = ""; keyword.value = ""; accountId.value = undefined; void load(); };
const openVoucher = (voucherId: number) => { detailVoucherId.value = voucherId; detailVisible.value = true; };
const quote = (value: unknown) => { let text = String(value ?? ""); if (/^[=+@-]/.test(text)) text = `'${text}`; return `"${text.replace(/"/g, '""')}"`; };
const exportCsv = () => { const rows = viewMode.value === "voucher" ? [["凭证字", "凭证号", "日期", "总摘要", "状态", "借方", "贷方"], ...voucherPage.value.items.map(row => [row.voucher_type, row.voucher_no, row.voucher_date, row.summary, statusLabel(row.status), money(row.total_debit), money(row.total_credit)])] : [["日期", "凭证字", "凭证号", "行号", "有效摘要", "会计科目", "辅助核算", "借方", "贷方", "状态"], ...linePage.value.items.map(row => [row.voucher_date, row.voucher_type, row.voucher_no, row.line_no, row.line_summary, `${row.account_code} ${row.account_name}`, row.auxiliaries, money(row.debit_amount), money(row.credit_amount), statusLabel(row.status)])]; const url = URL.createObjectURL(new Blob([`\uFEFF${rows.map(row => row.map(quote).join(",")).join("\r\n")}`], { type: "text/csv;charset=utf-8" })); const link = document.createElement("a"); link.href = url; link.download = `凭证查询-${viewMode.value}-${bookId.value}.csv`; link.click(); URL.revokeObjectURL(url); };
const review = async (row: MumarenFinanceVoucher) => { if (isReadonly.value) return; actingId.value = row.id; try { await mumarenFinanceCenterApi.reviewVoucher(row.id); ElMessage.success("凭证已审核"); await load(voucherPage.value.offset); } catch { ElMessage.error("审核失败"); } finally { actingId.value = undefined; } };
const remove = async (row: MumarenFinanceVoucher) => { if (isReadonly.value || row.status !== "draft") return; actingId.value = row.id; try { await mumarenFinanceCenterApi.deleteVoucher(row.id); ElMessage.success("草稿凭证已删除"); await load(voucherPage.value.offset); } catch { ElMessage.error("删除失败"); } finally { actingId.value = undefined; } };
const post = async (row: MumarenFinanceVoucher) => { if (isReadonly.value) return; actingId.value = row.id; try { await mumarenFinanceCenterApi.postVoucher(row.id); ElMessage.success("凭证已人工过账"); await load(voucherPage.value.offset); } catch { ElMessage.error("过账失败"); } finally { actingId.value = undefined; } };
onMounted(async () => { try { await loadBooks(); const routeBook = Number(route.query.book_id); if (Number.isSafeInteger(routeBook) && books.value.some(book => book.id === routeBook)) bookId.value = routeBook; await loadAccounts(); await load(); const voucherId = Number(route.query.voucher_id); if (bookId.value && Number.isSafeInteger(voucherId) && voucherId > 0) openVoucher(voucherId); } catch { error.value = "无法加载独立账簿。"; } });
</script>

<style scoped>
.panel { padding: 30px; border: 1px solid #e1e7ef; border-radius: 14px; background: #fff; display: grid; gap: 16px; }.heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }.heading-actions, .filters { display: flex; gap: 10px; flex-wrap: wrap; }.filters > * { width: 175px; }.filters > .el-date-editor { width: 150px; }.panel-kicker { margin: 0; color: #176b97; font-size: 12px; font-weight: 700; letter-spacing: .08em; }h2 { margin: 8px 0; }p { color: #5d6b7e; }@media (max-width: 768px) { .heading { flex-direction: column; }.filters > *, .filters > .el-date-editor { width: 100%; } }
</style>
