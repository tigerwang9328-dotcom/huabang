<template>
  <el-alert
    v-if="isUnavailable"
    type="warning"
    :closable="false"
    show-icon
    title="历史来源未迁入"
    :description="MUMAREN_HISTORICAL_SOURCE_UNAVAILABLE_REASON"
  />
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  MUMAREN_HISTORICAL_SOURCE_UNAVAILABLE_REASON,
  isMumarenHistoricalSourceUnavailable,
} from "@/config/mumarenFinanceCenter";

const props = defineProps<{
  moduleKey: string;
  readonly: boolean;
}>();

const isUnavailable = computed(
  () => props.readonly && isMumarenHistoricalSourceUnavailable(props.moduleKey),
);
</script>
