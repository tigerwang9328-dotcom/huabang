<template>
  <!-- 登录页布局：登录页自带全屏视觉，这里仅作为路由容器外壳 -->
  <div class="auth-layout">
    <router-view />
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.auth-layout { min-height: 100vh; }
</style>
