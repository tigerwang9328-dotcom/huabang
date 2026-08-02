<template>
  <section
    v-if="item?.placeholder"
    class="historical-source-unavailable"
    :data-availability="availability"
  >
    <el-empty description="历史来源未迁入">
      <template #description>
        <p>历史来源未迁入</p>
        <p>{{ unavailableReason }}</p>
      </template>
    </el-empty>
  </section>
  <el-empty v-else description="未配置占位信息" />
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { flattenMumarenFinanceNavigation } from "@/config/mumarenFinanceCenter";

const route = useRoute();

const item = computed(() => {
  const key = route.meta.placeholderKey as string | undefined;
  if (!key) return undefined;
  return flattenMumarenFinanceNavigation().find((it) => it.key === key);
});

const availability = "historical_source_unavailable";
const unavailableReason = "该类历史来源未迁入；历史凭证、余额快照和报表不受影响。";
</script>

<style scoped>
.historical-source-unavailable {
  display: grid;
  min-height: 280px;
  place-items: center;
  border: 1px solid #e1e7ef;
  border-radius: 14px;
  background: #fff;
}
</style>
