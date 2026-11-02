<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { SITE_HEADER_ACTIONS } from '@/components/layout/headerActions'
import McuTelemetryCard from '@/components/axle/McuTelemetryCard.vue'
import TestJudgeCard from '@/components/axle/TestJudgeCard.vue'
import VcuCommandCard from '@/components/axle/VcuCommandCard.vue'
import { useAxleStore } from '@/stores/useAxleStore'

const axleStore = useAxleStore()

/** “已连接”只代表 USBCAN 已打开，换台期间控制器不在线时要明确提示 */
const canBadge = computed(() => {
  if (!axleStore.isConnected) return { variant: 'warning', text: 'CAN 未连接' } as const
  if (axleStore.telemetry.waiting_for_controller) {
    return { variant: 'warning', text: '等待控制器' } as const
  }
  return { variant: 'success', text: 'CAN 在线' } as const
})
</script>

<template>
  <div class="flex flex-col gap-6 w-full">
    <!-- 硬件在线状态入口：放在顶部栏标题右侧，避免页面内再占一行 -->
    <Teleport defer :to="SITE_HEADER_ACTIONS">
      <Button as-child variant="outline" size="sm">
        <RouterLink to="/can">
          <Badge :variant="canBadge.variant">{{ canBadge.text }}</Badge>
          <span>
            {{
              axleStore.isConnected
                ? `通道 ${axleStore.telemetry.channel} · ${axleStore.telemetry.baud_rate / 1000}k`
                : '去连接'
            }}
          </span>
        </RouterLink>
      </Button>
    </Teleport>

    <!-- 中部双列布局：左侧 VCU 控制台，右侧 MCU 状态与诊断反馈 (等高对齐) -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
      <!-- 左侧：上位机 VCU 控制台 (占 6 列) -->
      <div class="lg:col-span-6 flex flex-col">
        <VcuCommandCard />
      </div>

      <!-- 右侧：MCU 驱动电机全量遥测与故障状态卡 (占 6 列) -->
      <div class="lg:col-span-6 flex flex-col">
        <McuTelemetryCard />
      </div>
    </div>

    <!-- 试车判定：合格 / NG 写入 PLC 并保存试车记录（转速与转矩曲线已并入右侧 MCU 卡片） -->
    <TestJudgeCard />
  </div>
</template>
