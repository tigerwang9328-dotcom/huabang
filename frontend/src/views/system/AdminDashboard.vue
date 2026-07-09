<template>
  <div class="sys-page">
    <div class="page-header"><h2>管理后台</h2><p>系统运行、用户权限、数据集成与安全治理总入口</p></div>
    <div class="admin-grid">
      <el-card v-for="item in cards" :key="item.title" class="admin-card">
        <span>{{ item.kicker }}</span><strong>{{ item.title }}</strong><p>{{ item.desc }}</p>
      </el-card>
    </div>
  </div>
</template>
<script setup lang="ts">
const cards = [
  { kicker: 'USER', title: '用户与岗位', desc: '统一管理账号、注册审核、岗位角色与模块权限。' },
  { kicker: 'RBAC', title: '权限矩阵', desc: '按经营概览、销售、商品、库存、财务等模块授权。' },
  { kicker: 'DATA', title: '数据权限', desc: '按全公司、部门、门店、个人控制可见数据范围。' },
  { kicker: 'SECURITY', title: '安全审计', desc: '登录日志、操作日志、密码策略与接口安全。' },
]
</script>
<style scoped>
.sys-page{padding:0}.page-header{margin-bottom:18px}.page-header h2{font-size:20px;margin:0 0 6px;color:#0f172a}.page-header p{margin:0;color:#64748b}.admin-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.admin-card span{font-size:11px;color:#c0762a;font-weight:800;letter-spacing:.12em}.admin-card strong{display:block;margin:8px 0;font-size:18px;color:#0f172a}.admin-card p{margin:0;color:#64748b;line-height:1.6}@media(max-width:1100px){.admin-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.admin-grid{grid-template-columns:1fr}}
</style>
