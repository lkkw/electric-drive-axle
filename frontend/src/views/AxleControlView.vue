<script setup lang="ts">
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  CircleOffIcon,
} from '@lucide/vue'
import { RouterLink } from 'vue-router'

import { cn } from '@/lib/utils'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import AxleTelemetryChart from '@/components/axle/AxleTelemetryChart.vue'
import McuTelemetryCard from '@/components/axle/McuTelemetryCard.vue'
import VcuCommandCard from '@/components/axle/VcuCommandCard.vue'
import { useAxleStore } from '@/stores/useAxleStore'

const axleStore = useAxleStore()
</script>

<template>
  <div class="flex flex-col gap-6 w-full">
    <!-- 顶部状态标题栏 -->
    <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-foreground">
          电驱桥控制台
        </h1>
      </div>

      <!-- 硬件在线状态入口 -->
      <div class="flex items-center gap-2">
        <Button
          as-child
          variant="outline"
          size="sm"
          :class="cn(
            'font-semibold',
            axleStore.isConnected
              ? 'border-success/50 text-success hover:bg-success/10 hover:text-success'
              : 'border-warning/50 text-warning hover:bg-warning/10 hover:text-warning',
          )"
        >
          <RouterLink to="/can">
          <component
            :is="axleStore.isConnected ? CheckCircle2Icon : CircleOffIcon"
            data-icon="inline-start"
          />
          <span>{{ axleStore.isConnected ? `CAN 在线 (通道 ${axleStore.telemetry.channel} · ${axleStore.telemetry.baud_rate / 1000}k)` : 'CAN 未连接 (点击前往配置)' }}</span>
          </RouterLink>
        </Button>
      </div>
    </div>

    <!-- 报警/错误异常提示条 -->
    <Alert v-if="axleStore.error" variant="destructive">
      <AlertTriangleIcon />
      <AlertDescription>
        <span class="font-semibold">通信异常警示: </span>
        <span>{{ axleStore.error }}</span>
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
