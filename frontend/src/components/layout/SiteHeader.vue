<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import EmergencyStopButton from '@/components/axle/EmergencyStopButton.vue'
import { Badge, type BadgeVariants } from '@/components/ui/badge'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { usePlcStore } from '@/stores/usePlcStore'
import { POWER_STATE_LABEL } from '@/types/plc'
import { SITE_HEADER_ACTIONS_ID } from './headerActions'

const route = useRoute()

const pageTitle = computed(() => (route.meta.title as string | undefined) ?? '')

const plc = usePlcStore()
/** 高压标识：仅在已上电、上电/下电中或供电故障时显示，空闲时不占位 */
const highVoltageBadge = computed<{ label: string; variant: BadgeVariants['variant'] } | null>(() => {
  const { connected, power_state: state, target_voltage: voltage } = plc.status
  if (!connected || state === 'idle') return null
  if (state === 'powered') return { label: `高压 ${voltage} V 已接通`, variant: 'warning' }
  if (state === 'fault') return { label: POWER_STATE_LABEL.fault, variant: 'destructive' }
  return { label: `高压${POWER_STATE_LABEL[state]}`, variant: 'info' }
})
</script>

<template>
  <header
    class="flex h-16 shrink-0 items-center gap-3 px-4 transition-[width,height] ease-linear sm:px-6 group-has-data-[collapsible=icon]/sidebar-wrapper:h-12"
  >
    <SidebarTrigger class="-ml-1" />
    <h1 class="truncate text-lg font-semibold text-foreground">{{ pageTitle }}</h1>
    <div :id="SITE_HEADER_ACTIONS_ID" class="ml-auto flex shrink-0 items-center gap-2" />
    <RouterLink v-if="highVoltageBadge" to="/power" title="前往台架供电">
      <Badge :variant="highVoltageBadge.variant">{{ highVoltageBadge.label }}</Badge>
    </RouterLink>
    <!-- 全局急停：任何页面都可一键触发 -->
    <EmergencyStopButton />
  </header>
</template>
