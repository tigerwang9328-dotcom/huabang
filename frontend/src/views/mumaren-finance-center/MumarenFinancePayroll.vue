<template>
  <section class="panel">
    <div class="heading">
      <div><p class="panel-kicker">薪资管理</p><h2>工资</h2><p>工资草稿、人工发放与审计；按独立账簿隔离。</p></div>
      <div class="heading-actions"><el-button :disabled="!bookId" :loading="loading" @click="load">刷新</el-button><el-button type="primary" :disabled="!bookId" @click="openDialog">录入工资</el-button></div>
    </div>
    <div class="filters"><el-select v-model="bookId" placeholder="选择独立账簿" clearable @change="onBookChange"><el-option v-for="book in books" :key="book.id" :label="book.book_name" :value="book.id" /></el-select></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon />
    <el-table v-loading="loading" :data="records" empty-text="暂无工资记录" stripe show-summary :summary-method="summary">
      <el-table-column prop="employee_no" label="员工编号" min-width="120" /><el-table-column prop="employee_name" label="员工" min-width="120" /><el-table-column prop="period" label="期间" width="110" />
      <el-table-column label="应发" width="130" align="right"><template #default="{ row }">{{ money(row.gross_amount) }}</template></el-table-column>
      <el-table-column label="扣减" width="130" align="right"><template #default="{ row }">{{ money(row.deduction_amount) }}</template></el-table-column>
      <el-table-column label="实发" width="130" align="right"><template #default="{ row }">{{ money(row.net_amount) }}</template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.workflow_status === 'draft' ? 'warning' : 'success'" size="small">{{ row.workflow_status === "draft" ? "草稿" : "已发放" }}</el-tag></template></el-table-column>
      <el-table-column label="操作" width="140"><template #default="{ row }"><el-button v-if="row.workflow_status === 'draft'" link type="primary" size="small" :loading="actingId === row.id" @click="pay(row)">发放</el-button><el-popconfirm title="确定删除该工资记录?" @confirm="remove(row)"><template #reference><el-button link type="danger" size="small" :loading="actingId === row.id">删除</el-button></template></el-popconfirm></template></el-table-column>
    </el-table>
    <el-dialog v-model="dialogVisible" title="录入工资" width="520px" :close-on-click-modal="false"><el-form :model="form" label-width="100px">
      <el-form-item label="员工编号"><el-input v-model="form.employee_no" /></el-form-item><el-form-item label="员工姓名"><el-input v-model="form.employee_name" /></el-form-item><el-form-item label="期间"><el-date-picker v-model="form.period" type="month" value-format="YYYY-MM" style="width:100%" /></el-form-item>
      <el-form-item label="应发金额"><el-input-number v-model="form.gross_amount" :min="0" :precision="2" :controls="false" style="width:100%" /></el-form-item><el-form-item label="扣减金额"><el-input-number v-model="form.deduction_amount" :min="0" :precision="2" :controls="false" style="width:100%" /></el-form-item><el-form-item label="实发金额"><el-input-number v-model="form.net_amount" :min="0" :precision="2" :controls="false" style="width:100%" /></el-form-item>
    </el-form><template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template></el-dialog>
  </section>
</template>
<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { mumarenFinanceCenterApi, payrollsApi, type MumarenFinanceBook, type MumarenPayroll } from "@/api/mumarenFinanceCenter";
const books = ref<MumarenFinanceBook[]>([]); const bookId = ref<number>(); const records = ref<MumarenPayroll[]>([]); const loading = ref(false); const saving = ref(false); const error = ref(""); const actingId = ref<number>(); const dialogVisible = ref(false);
const money = (value: number) => new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
const form = reactive({ employee_no: "", employee_name: "", period: new Date().toISOString().slice(0, 7), gross_amount: 0, deduction_amount: 0, net_amount: 0 });
const load = async () => { if (!bookId.value) return; loading.value = true; error.value = ""; try { records.value = (await payrollsApi.list({ book_id: bookId.value })).data.data; } catch { error.value = "无法加载工资记录。"; } finally { loading.value = false; } };
const onBookChange = () => { records.value = []; void load(); };
onMounted(async () => { try { books.value = (await mumarenFinanceCenterApi.listBooks()).data.data; bookId.value = books.value[0]?.id; if (bookId.value) await load(); } catch { error.value = "无法加载独立账簿。"; } });
const openDialog = () => { if (!bookId.value) return; Object.assign(form, { employee_no: "", employee_name: "", period: new Date().toISOString().slice(0, 7), gross_amount: 0, deduction_amount: 0, net_amount: 0 }); dialogVisible.value = true; };
const save = async () => { if (!bookId.value) return; if (!form.employee_no.trim() || !form.employee_name.trim()) { ElMessage.warning("请填写员工编号和员工姓名"); return; } saving.value = true; try { await payrollsApi.create({ book_id: bookId.value, employee_no: form.employee_no.trim(), employee_name: form.employee_name.trim(), period: form.period, gross_amount: Number(form.gross_amount || 0), deduction_amount: Number(form.deduction_amount || 0), net_amount: Number(form.net_amount || 0) }); ElMessage.success("工资草稿已录入"); dialogVisible.value = false; await load(); } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "保存失败"); } finally { saving.value = false; } };
const pay = async (row: MumarenPayroll) => { if (!bookId.value || row.workflow_status !== "draft") return; actingId.value = row.id; try { await payrollsApi.pay(row.id, bookId.value); ElMessage.success("工资已发放"); await load(); } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "发放失败"); } finally { actingId.value = undefined; } };
const remove = async (row: MumarenPayroll) => { if (!bookId.value) return; actingId.value = row.id; try { await payrollsApi.delete(row.id, bookId.value); ElMessage.success("工资记录已删除"); await load(); } catch (e: any) { ElMessage.error(e?.response?.data?.detail || "删除失败"); } finally { actingId.value = undefined; } };
const summary = ({ columns, data }: { columns: any[]; data: MumarenPayroll[] }) => columns.map((column, index) => { if (index === 0) return "合计"; const field = ({ 应发: "gross_amount", 扣减: "deduction_amount", 实发: "net_amount" } as Record<string, keyof MumarenPayroll>)[column.label]; return field ? money(data.reduce((sum, row) => sum + Number(row[field] || 0), 0)) : ""; });
</script>
<style scoped>.panel { padding:30px; border:1px solid #e1e7ef; border-radius:14px; background:#fff; display:grid; gap:16px; }.heading { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }.heading-actions { display:flex; gap:8px; }.filters > * { max-width:280px; }.panel-kicker { margin:0; color:#176b97; font-size:12px; font-weight:700; letter-spacing:.08em; }h2 { margin:8px 0; }p { color:#5d6b7e; }</style>
