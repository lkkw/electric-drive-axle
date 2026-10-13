<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { toast } from 'vue-sonner'

import SafetyTripDialog from '@/components/axle/SafetyTripDialog.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import SiteHeader from '@/components/layout/SiteHeader.vue'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { useAxleStore } from '@/stores/useAxleStore'

const axleStore = useAxleStore()
let cancelControlViewPreload: (() => void) | undefined

// 链路失效可能发生在任意页面，全局提示一次；页面内的 Alert 负责持续展示。
watch(
  () => axleStore.linkError,
  (reason, previous) => {
    if (reason && reason !== previous) {
      toast.error('CAN 硬件链路中断，通信已自动停止', {
        description: reason,
        duration: 8000,
      })
    }
  },
)

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
