<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import VChart from 'vue-echarts'
import 'vue-echarts/style.css'
import '@/components/charts/echarts'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { resolveCssColor } from '@/lib/chart-theme'
import { useAxleStore } from '@/stores/useAxleStore'

const axleStore = useAxleStore()

interface ChartColors {
  muted: string
  border: string
  speed: string
  torque: string
}

const fallbackColors: ChartColors = {
  muted: '#737373',
  border: '#e5e5e5',
  speed: '#2563eb',
  torque: '#d97706',
}

const chartColors = ref<ChartColors>(fallbackColors)

function resolveThemeColors(): ChartColors {
  return {
    muted: resolveCssColor('--muted-foreground', fallbackColors.muted),
    border: resolveCssColor('--border', fallbackColors.border),
    speed: resolveCssColor('--info', fallbackColors.speed),
    torque: resolveCssColor('--warning', fallbackColors.torque),
  }
}

const chartOption = computed(() => {
  const colors = chartColors.value
  const times = axleStore.historySeries.map((p) => p.time)
  const speeds = axleStore.historySeries.map((p) => p.speed)
  const torques = axleStore.historySeries.map((p) => p.torque)

  return {
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
      },
    },
    legend: {
      data: ['实际转速 (RPM)', '实际转矩 (Nm)'],
      top: 0,
      textStyle: {
        color: colors.muted,
        fontSize: 12,
      },
    },
    grid: {
      top: 36,
      left: 55,
      right: 55,
      bottom: 25,
    },
    xAxis: {
      type: 'category',
      data: times,
      boundaryGap: false,
      axisLine: { lineStyle: { color: colors.border } },
      axisLabel: { fontSize: 10, color: colors.muted },
    },
    yAxis: [
      {
        type: 'value',
        name: '转速 (RPM)',
        position: 'left',
        axisLine: { show: true, lineStyle: { color: colors.speed } },
        axisLabel: { color: colors.speed, fontSize: 11 },
        splitLine: { lineStyle: { color: colors.border } },
      },
      {
        type: 'value',
        name: '转矩 (Nm)',
        position: 'right',
        axisLine: { show: true, lineStyle: { color: colors.torque } },
        axisLabel: { color: colors.torque, fontSize: 11 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '实际转速 (RPM)',
        type: 'line',
        yAxisIndex: 0,
        data: speeds,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2, color: colors.speed },
      },
      {
        name: '实际转矩 (Nm)',
        type: 'line',
        yAxisIndex: 1,
        data: torques,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2, color: colors.torque },
      },
    ],
  }
})

onMounted(() => {
  chartColors.value = resolveThemeColors()
})
</script>

<template>
  <Card class="border-border shadow-xs">
    <CardHeader class="pb-3 border-b bg-muted/20">
      <CardTitle class="text-base font-semibold">
        实时转速与转矩曲线
      </CardTitle>
    </CardHeader>

    <CardContent>
      <div class="h-[280px] w-full">
        <VChart
          :option="chartOption"
          autoresize
          class="size-full"
        />
      </div>
    </CardContent>
  </Card>
</template>
