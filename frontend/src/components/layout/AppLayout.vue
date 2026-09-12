<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

import SafetyTripDialog from '@/components/axle/SafetyTripDialog.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import SiteHeader from '@/components/layout/SiteHeader.vue'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { useAxleStore } from '@/stores/useAxleStore'

const axleStore = useAxleStore()

onMounted(() => {
  axleStore.startSse()
  void axleStore.refreshStatus()
})

onBeforeUnmount(() => {
  axleStore.stopSse()
})
</script>

<template>
  <SidebarProvider>
    <AppSidebar />
    <SidebarInset>
      <SiteHeader />
      <!-- 内容区：自适应宽屏工控布局 -->
      <main class="flex min-w-0 w-full flex-1 flex-col gap-4 px-4 sm:px-6 pb-6 pt-0">
        <RouterView />
      </main>
    </SidebarInset>
    <SafetyTripDialog />
  </SidebarProvider>
</template>
