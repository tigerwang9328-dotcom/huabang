<template>
  <div class="sys-page">
    <div class="page-header"><h2>DataPermissions</h2><p>{{ desc }}</p></div>
    <el-card><el-empty :description="desc + '：已预留菜单与权限码，下一阶段接入配置表单。'" /></el-card>
  </div>
</template>
<script setup lang="ts">
const map:any = {
  RegisterAudit: '注册审核',
  DataPermissions: '数据权限',
  FieldPermissions: '字段权限',
  Security: '安全设置',
}
const desc = map['DataPermissions']
</script>
<style scoped>.sys-page{padding:0}.page-header{margin-bottom:18px}.page-header h2{font-size:20px;margin:0 0 6px;color:#0f172a}.page-header p{margin:0;color:#64748b}</style>
