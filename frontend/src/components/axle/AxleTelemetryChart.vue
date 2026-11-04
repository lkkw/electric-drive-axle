<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import VChart from 'vue-echarts'
import 'vue-echarts/style.css'
import '@/components/charts/echarts'
import { resolveCssColor } from '@/lib/chart-theme'
import { useAxleStore, type HistoryPoint } from '@/stores/useAxleStore'

const axleStore = useAxleStore()
const DISPLAY_REFRESH_INTERVAL_MS = 500

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
const displayedHistorySeries = ref<HistoryPoint[]>([])
let displayRefreshTimer: ReturnType<typeof setInterval> | undefined

function refreshDisplayedHistory() {
  displayedHistorySeries.value = axleStore.historySeries.slice()
}

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
  const times = displayedHistorySeries.value.map((p) => p.time)
  const speeds = displayedHistorySeries.value.map((p) => p.speed)
  const torques = displayedHistorySeries.value.map((p) => p.torque)

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
    // 左右只留刻度文字所需的宽度（containLabel），横轴尽量贴近卡片两侧
    grid: {
      top: 32,
      left: 0,
      right: 0,
      bottom: 0,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: times,
      boundaryGap: false,
      axisLine: { lineStyle: { color: colors.border } },
      axisLabel: { fontSize: 10, color: colors.muted },
    },
    yAxis: [
      // 轴名省略：单位已在图例中，坐标轴颜色与曲线一致
      {
        type: 'value',
        position: 'left',
        axisLine: { show: true, lineStyle: { color: colors.speed } },
        axisLabel: { color: colors.speed, fontSize: 11 },
        splitLine: { lineStyle: { color: colors.border } },
      },
      {
        type: 'value',
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
  refreshDisplayedHistory()
  displayRefreshTimer = setInterval(
    refreshDisplayedHistory,
    DISPLAY_REFRESH_INTERVAL_MS,
  )
})

onBeforeUnmount(() => {
  if (displayRefreshTimer) {
    clearInterval(displayRefreshTimer)
  }
})
</script>

<template>
  <!-- 嵌在 MCU 实时反馈卡片底部，占满卡片剩余高度；左侧内容较短时保留最小高度 -->
  <section class="flex min-h-[220px] flex-1 flex-col gap-2">
    <h3 class="text-sm font-medium text-foreground">转速与转矩曲线</h3>
    <div class="min-h-0 w-full flex-1">
      <VChart
        :option="chartOption"
        autoresize
        class="size-full"
      />
    </div>
  </section>
</template>
