<script setup lang="ts">
import { markRaw, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { UnplugIcon } from '@lucide/vue'
import { toast } from 'vue-sonner'

import SafetyTripDialog from '@/components/axle/SafetyTripDialog.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import SiteHeader from '@/components/layout/SiteHeader.vue'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { useAxleStore } from '@/stores/useAxleStore'
import { usePlcStore } from '@/stores/usePlcStore'

const axleStore = useAxleStore()
// PLC 供电状态在所有页面都要可见（顶部栏高压标识），在布局层统一轮询
const plcStore = usePlcStore()
const router = useRouter()
let cancelControlViewPreload: (() => void) | undefined

// 链路失效是唯一的全局提示：不自动消失（操作员可能不在屏幕前），点“去连接”或重新连接成功后收起。
// 详细原因（通道、超时时长等）已写入 events.log，提示里只保留操作员需要的信息。
const LINK_ERROR_TOAST_ID = 'can-link-error'
watch(
  () => axleStore.linkError,
  (reason, previous) => {
    if (reason && reason !== previous) {
      toast.error('CAN 链路中断，已自动停止通信', {
        id: LINK_ERROR_TOAST_ID,
        description: '请检查 USBCAN 连接、控制器供电与 CAN 线束',
        icon: markRaw(UnplugIcon),
        duration: Number.POSITIVE_INFINITY,
        action: {
          label: '去连接',
          onClick: () => void router.push('/can'),
        },
      })
    } else if (!reason && previous) {
      toast.dismiss(LINK_ERROR_TOAST_ID)
    }
  },
  { immediate: true },
)

onMounted(() => {
  axleStore.startSse()
  plcStore.startPolling()
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
  plcStore.stopPolling()
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
