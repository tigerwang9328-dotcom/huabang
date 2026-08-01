<template>
  <MumarenFinanceCapabilityBoard
    v-if="item?.placeholder"
    :title="item.title"
    :summary="item.placeholder.summary"
    :capabilities="capabilitiesWithAvailability"
  />
  <el-empty v-else description="未配置占位信息" />
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { flattenMumarenFinanceNavigation, type MumarenFinanceCapability } from "@/config/mumarenFinanceCenter";
import MumarenFinanceCapabilityBoard from "./MumarenFinanceCapabilityBoard.vue";

const route = useRoute();

const item = computed(() => {
  const key = route.meta.placeholderKey as string | undefined;
  if (!key) return undefined;
  return flattenMumarenFinanceNavigation().find((it) => it.key === key);
});

const capabilitiesWithAvailability = computed<MumarenFinanceCapability[]>(() => {
  if (!item.value?.placeholder) return [];
  return item.value.placeholder.capabilities.map((c) => ({ ...c, availability: "planned_backend" as const }));
});
</script>
