<script setup lang="ts">
import { UnplugIcon } from '@lucide/vue'
import { RouterLink } from 'vue-router'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { SITE_HEADER_ACTIONS } from '@/components/layout/headerActions'
import AxleTelemetryChart from '@/components/axle/AxleTelemetryChart.vue'
import McuTelemetryCard from '@/components/axle/McuTelemetryCard.vue'
import VcuCommandCard from '@/components/axle/VcuCommandCard.vue'
import { useAxleStore } from '@/stores/useAxleStore'

const axleStore = useAxleStore()
</script>

<template>
  <div class="flex flex-col gap-6 w-full">
    <!-- 硬件在线状态入口：放在顶部栏标题右侧，避免页面内再占一行 -->
    <Teleport defer :to="SITE_HEADER_ACTIONS">
      <Button as-child variant="outline" size="sm">
        <RouterLink to="/can">
          <Badge :variant="axleStore.isConnected ? 'success' : 'warning'">
            {{ axleStore.isConnected ? 'CAN 在线' : 'CAN 未连接' }}
          </Badge>
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

    <!-- 硬件链路失效：后端已自动停机并释放设备 -->
    <Alert v-if="axleStore.linkError && !axleStore.isConnected" variant="destructive">
      <UnplugIcon />
      <AlertTitle>CAN 硬件链路中断，通信已自动停止</AlertTitle>
      <AlertDescription>
        {{ axleStore.linkError }} 请检查 USBCAN 连接与供电后，前往 CAN 通信页重新连接。
      </AlertDescription>
    </Alert>

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

    <!-- 底部通栏：动力响应实时动态波形曲线 -->
    <div class="w-full">
      <AxleTelemetryChart />
    </div>
  </div>
</template>
