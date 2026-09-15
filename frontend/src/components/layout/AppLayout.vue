<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

import SafetyTripDialog from '@/components/axle/SafetyTripDialog.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import SiteHeader from '@/components/layout/SiteHeader.vue'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { useAxleStore } from '@/stores/useAxleStore'

const axleStore = useAxleStore()
let cancelControlViewPreload: (() => void) | undefined

onMounted(() => {
  axleStore.startSse()
  void axleStore.refreshStatus()

  if (window.location.pathname !== '/axle') {
    const preloadControlView = () => {
      void import('@/views/AxleControlView.vue')
    }

    if ('requestIdleCallback' in window) {
      const preloadId = window.requestIdleCallback(preloadControlView, { timeout: 1500 })
      cancelControlViewPreload = () => window.cancelIdleCallback(preloadId)
    } else {
      const preloadId = setTimeout(preloadControlView, 300)
      cancelControlViewPreload = () => clearTimeout(preloadId)
    }
  }
})

onBeforeUnmount(() => {
  cancelControlViewPreload?.()
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
