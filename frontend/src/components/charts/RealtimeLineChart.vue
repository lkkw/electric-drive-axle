<script setup lang="ts">
import type { LineSeriesOption } from 'echarts/charts'
import type {
  DataZoomComponentOption,
  GridComponentOption,
  LegendComponentOption,
  TooltipComponentOption,
} from 'echarts/components'
import type { ComposeOption } from 'echarts/core'
import { nextTick, onMounted, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import 'vue-echarts/style.css'

import '@/components/charts/echarts'
import { resolveCssColor } from '@/lib/chart-theme'
import type { RealtimeLinePoint } from '@/types/chart'

type RealtimeLineChartOption = ComposeOption<
  | LineSeriesOption
  | GridComponentOption
  | TooltipComponentOption
  | LegendComponentOption
  | DataZoomComponentOption
>

interface Props {
  points: readonly RealtimeLinePoint[]
  seriesName?: string
  yAxisName?: string
  valueDecimals?: number
}

interface ChartColors {
  series: string
  seriesFill: string
  border: string
  muted: string
}

const props = withDefaults(defineProps<Props>(), {
  seriesName: '实时数据',
  yAxisName: '',
  valueDecimals: 0,
})

const chartRef = ref<InstanceType<typeof VChart> | null>(null)
const fallbackColors: ChartColors = {
  series: '#e76f36',
  seriesFill: 'rgba(231, 111, 54, 0.18)',
  border: '#e5e7eb',
  muted: '#6b7280',
}

function createChartOption(colors: ChartColors): RealtimeLineChartOption {
  return {
    animation: false,
    color: [colors.series],
    grid: {
      top: 42,
      right: 20,
      bottom: 64,
      left: props.yAxisName ? 64 : 52,
      containLabel: true,
    },
    legend: {
      top: 4,
      textStyle: { color: colors.muted },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      valueFormatter: formatTooltipValue,
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: colors.border } },
      axisLabel: { color: colors.muted, hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      name: props.yAxisName,
      nameTextStyle: { color: colors.muted },
      axisLabel: { color: colors.muted },
      splitLine: { lineStyle: { color: colors.border, type: 'dashed' } },
      scale: true,
    },
    dataZoom: [
      {
        type: 'inside',
        filterMode: 'none',
      },
      {
        type: 'slider',
        filterMode: 'none',
        height: 20,
        bottom: 10,
        borderColor: colors.border,
        fillerColor: colors.seriesFill,
        dataBackground: {
          lineStyle: { color: colors.muted },
          areaStyle: { color: 'transparent' },
        },
        selectedDataBackground: {
          lineStyle: { color: colors.series },
          areaStyle: { color: 'transparent' },
        },
        textStyle: { color: colors.muted },
        moveHandleStyle: { color: colors.muted },
      },
    ],
    series: [
      {
        id: 'realtime-signal',
        name: props.seriesName,
        type: 'line',
        data: [],
        showSymbol: false,
        sampling: 'minmax',
        connectNulls: false,
        lineStyle: { width: 2 },
        emphasis: { focus: 'series' },
      },
    ],
  }
}

const initialOption = createChartOption(fallbackColors)

function formatTooltipValue(value: unknown): string {
  const numericValue = Array.isArray(value) ? value[1] : value
  return typeof numericValue === 'number' && Number.isFinite(numericValue)
    ? numericValue.toFixed(props.valueDecimals)
    : '—'
}

function resolveThemeColors(): ChartColors {
  return {
    series: resolveCssColor('--chart-1', fallbackColors.series),
    seriesFill: resolveCssColor('--chart-1', fallbackColors.seriesFill, 0.18),
    border: resolveCssColor('--border', fallbackColors.border),
    muted: resolveCssColor('--muted-foreground', fallbackColors.muted),
  }
}

function updateSeries(): void {
  chartRef.value?.setOption(
    {
      series: [
        {
          id: 'realtime-signal',
          name: props.seriesName,
          data: props.points.map((point) => [point.timestamp, point.value]),
        },
      ],
    },
    {
      lazyUpdate: true,
      silent: true,
    },
  )
}

onMounted(async () => {
  await nextTick()
  chartRef.value?.setOption(createChartOption(resolveThemeColors()), {
    notMerge: true,
    silent: true,
  })
  updateSeries()
})

watch(
  () => props.points,
  () => {
    updateSeries()
  },
)

watch(
  () => [props.seriesName, props.yAxisName, props.valueDecimals] as const,
  () => {
    chartRef.value?.setOption({
      tooltip: {
        valueFormatter: formatTooltipValue,
      },
      yAxis: { name: props.yAxisName },
      series: [{ id: 'realtime-signal', name: props.seriesName }],
    })
  },
)
</script>

<template>
  <div
    class="h-80 min-h-72 w-full"
    role="img"
    :aria-label="`${seriesName}实时曲线，共${points.length}个数据点`"
  >
    <VChart
      ref="chartRef"
      class="size-full"
      :option="initialOption"
      :init-options="{ renderer: 'canvas' }"
      :autoresize="{ throttle: 100 }"
      manual-update
    />
  </div>
</template>
