<script setup lang="ts">
import { AlertOctagonIcon } from '@lucide/vue'
import { toast } from 'vue-sonner'

import { Button } from '@/components/ui/button'
import { useAxleStore } from '@/stores/useAxleStore'

/**
 * 全局紧急停机按钮：常驻顶部栏，任何页面都可一键急停。
 * 仅在 CAN 未连接时禁用，不受其他请求的加载状态影响。
 */
const axleStore = useAxleStore()

async function handleEmergencyStop() {
  if (!axleStore.isConnected) return
  try {
    await axleStore.triggerEmergencyStop()
    toast.warning('紧急停机指令已下发')
  } catch (error) {
    toast.error('紧急停机失败，请立即使用硬件急停', {
      description: error instanceof Error ? error.message : undefined,
      duration: 8000,
    })
  }
}
</script>

<template>
  <Button
    variant="destructive"
    size="sm"
    :disabled="!axleStore.isConnected"
    @click="handleEmergencyStop"
  >
    <AlertOctagonIcon data-icon="inline-start" />
    紧急停机
  </Button>
</template>
