<template><MumarenFinanceCapabilityBoard v-bind="mumarenFinanceCapabilityGroups.assets" /></template>
<script setup lang="ts">
import { mumarenFinanceCapabilityGroups } from "@/config/mumarenFinanceCenter";
import MumarenFinanceCapabilityBoard from "./MumarenFinanceCapabilityBoard.vue";
</script>
