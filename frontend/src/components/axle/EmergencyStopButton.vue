<script setup lang="ts">
import { computed } from 'vue'
import { toast } from 'vue-sonner'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useAxleStore } from '@/stores/useAxleStore'
import { usePlcStore } from '@/stores/usePlcStore'

/**
 * 全局紧急停机按钮：常驻顶部栏，任何页面都可一键急停。
 * 仅在 CAN 未连接时禁用，不受其他请求的加载状态影响。
 *
 * 外观按危险程度切换：台架安全时为描边红，避免常驻鲜红刺眼；
 * 高压已接通（或正在上 / 下电、接触器吸合）、电机已使能或循环试车运行中时变为实心红。
 */
const axleStore = useAxleStore()
const plc = usePlcStore()

const isHighVoltageActive = computed(() => {
  const s = plc.status
  if (!s.connected) return false
  return (
    s.power_state === 'powered' ||
    s.power_state === 'powering_on' ||
    s.power_state === 'powering_off' ||
    s.power_on ||
    s.contactor_closed
  )
})

const isMotorActive = computed(() => {
  const { command, cycle_test: cycle } = axleStore.telemetry
  return command.mcu_en_cmd === 1 || cycle.status === 'running' || cycle.status === 'paused'
})

/** 存在危险源：高压或电机处于可动作状态 */
const isHazardActive = computed(
  () => axleStore.isConnected && (isHighVoltageActive.value || isMotorActive.value),
)

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
  <!--
    整数字号 (14px) + 半粗体，中文笔画更清晰；
    禁用时不用半透明（白字叠在半透明红底上发虚、有锯齿感），改为浅红底 + 红字，仍能看清。
  -->
  <Button
    :variant="isHazardActive ? 'destructive' : 'outline'"
    :class="cn(
      'h-8 px-3.5 text-sm font-semibold tracking-wide',
      !isHazardActive && 'border-destructive/60 bg-background text-destructive hover:bg-destructive hover:text-white',
      'disabled:border-transparent disabled:bg-destructive/10 disabled:text-destructive disabled:opacity-100 disabled:shadow-none',
    )"
    :disabled="!axleStore.isConnected"
    :title="axleStore.isConnected ? '立即关闭电机使能并切断高压' : 'CAN 未连接，无法下发急停'"
    @click="handleEmergencyStop"
  >
    紧急停机
  </Button>
</template>
