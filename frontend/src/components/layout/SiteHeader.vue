<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import EmergencyStopButton from '@/components/axle/EmergencyStopButton.vue'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { SITE_HEADER_ACTIONS_ID } from './headerActions'

const route = useRoute()

const pageTitle = computed(() => (route.meta.title as string | undefined) ?? '')
</script>

<template>
  <header
    class="flex h-16 shrink-0 items-center gap-3 px-4 transition-[width,height] ease-linear sm:px-6 group-has-data-[collapsible=icon]/sidebar-wrapper:h-12"
  >
    <SidebarTrigger class="-ml-1" />
    <h1 class="truncate text-lg font-semibold text-foreground">{{ pageTitle }}</h1>
    <div :id="SITE_HEADER_ACTIONS_ID" class="ml-auto flex shrink-0 items-center gap-2" />
    <!-- 全局急停：任何页面都可一键触发 -->
    <EmergencyStopButton />
  </header>
</template>
