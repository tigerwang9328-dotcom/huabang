<template>
  <!--
    REARE 纯 SVG 字标。
    工业切角几何无衬线字形（仅 R / E / A 三个独体），偏扁平粗壮。
    fill="currentColor" —— 颜色随父级 color 自适配（深色背景哑光白/拉丝金，浅色背景炭黑）。
  -->
  <svg
    class="reare-logo"
    viewBox="0 0 346 80"
    role="img"
    aria-label="REARE"
    fill="currentColor"
    xmlns="http://www.w3.org/2000/svg"
  >
    <!-- R -->
    <g transform="translate(0,0)">
      <rect x="0" y="0" width="16" height="80" />
      <polygon points="0,0 46,0 58,12 58,16 0,16" />
      <rect x="42" y="16" width="16" height="24" />
      <rect x="16" y="40" width="42" height="16" />
      <polygon points="28,46 45,46 58,80 41,80" />
    </g>
    <!-- E -->
    <g transform="translate(72,0)">
      <rect x="0" y="0" width="16" height="80" />
      <polygon points="0,0 46,0 58,12 58,16 0,16" />
      <rect x="16" y="32" width="32" height="16" />
      <rect x="16" y="64" width="42" height="16" />
    </g>
    <!-- A -->
    <g transform="translate(144,0)">
      <polygon points="0,80 18,80 33,0 25,0" />
      <polygon points="58,80 40,80 25,0 33,0" />
      <rect x="15" y="48" width="28" height="15" />
    </g>
    <!-- R -->
    <g transform="translate(216,0)">
      <rect x="0" y="0" width="16" height="80" />
      <polygon points="0,0 46,0 58,12 58,16 0,16" />
      <rect x="42" y="16" width="16" height="24" />
      <rect x="16" y="40" width="42" height="16" />
      <polygon points="28,46 45,46 58,80 41,80" />
    </g>
    <!-- E -->
    <g transform="translate(288,0)">
      <rect x="0" y="0" width="16" height="80" />
      <polygon points="0,0 46,0 58,12 58,16 0,16" />
      <rect x="16" y="32" width="32" height="16" />
      <rect x="16" y="64" width="42" height="16" />
    </g>
  </svg>
</template>

<script setup lang="ts"></script>

<style scoped>
.reare-logo {
  display: block;
  height: 100%;
  width: auto;
}
</style>
