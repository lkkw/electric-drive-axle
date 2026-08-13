<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import {
  ActivityIcon,
  InboxIcon,
  PlugZapIcon,
  RadioIcon,
  RefreshCwIcon,
  ServerIcon,
  TriangleAlertIcon,
  UnplugIcon,
} from '@lucide/vue'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import { useRealtimeSeries } from '@/composables/useRealtimeSeries'
import { useDemoStore } from '@/stores/useDemoStore'
import { API_BASE_URL } from '@/utils/alova'

interface SseMessage {
  sequence: number
  message: string
  timestamp: string
}

interface DisplayedSseMessage extends SseMessage {
  clientKey: number
}

type ConnectionState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed' | 'error'

const RealtimeLineChart = defineAsyncComponent(
  () => import('@/components/charts/RealtimeLineChart.vue'),
)
const demoStore = useDemoStore()
const { demo, loading, error: restError } = storeToRefs(demoStore)

const messages = ref<DisplayedSseMessage[]>([])
const connectionState = ref<ConnectionState>('idle')
const sseError = ref<string | null>(null)
const {
  points: chartPoints,
  append: appendChartPoint,
  clear: clearChartPoints,
  dispose: disposeChartSeries,
} = useRealtimeSeries({ maxPoints: 1_000, refreshIntervalMs: 100 })
let eventSource: EventSource | null = null
let nextMessageKey = 1
let hasChartData = false
let breakBeforeNextPoint = false

const statusMeta = computed(() => {
  const states = {
    idle: { label: '尚未连接', variant: 'outline' },
    connecting: { label: '连接中', variant: 'secondary' },
    open: { label: '已连接', variant: 'default' },
    reconnecting: { label: '自动重连中', variant: 'secondary' },
    closed: { label: '已断开', variant: 'outline' },
    error: { label: '连接异常', variant: 'destructive' },
  } as const

  return states[connectionState.value]
})

const isConnected = computed(() => connectionState.value === 'open')
const isConnecting = computed(
  () => connectionState.value === 'connecting' || connectionState.value === 'reconnecting',
)

const dateFormatter = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium',
  timeStyle: 'medium',
})

function formatTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateFormatter.format(date)
}

function parseSseMessage(data: string): { message: SseMessage; timestamp: number } | null {
  try {
    const value: unknown = JSON.parse(data)
    if (
      typeof value !== 'object' ||
      value === null ||
      !('sequence' in value) ||
      !('message' in value) ||
      !('timestamp' in value) ||
      typeof value.sequence !== 'number' ||
      !Number.isFinite(value.sequence) ||
      typeof value.message !== 'string' ||
      typeof value.timestamp !== 'string'
    ) {
      return null
    }

    const timestamp = Date.parse(value.timestamp)
    if (!Number.isFinite(timestamp)) {
      return null
    }

    return { message: value as SseMessage, timestamp }
  } catch {
    return null
  }
}

function handleDemoEvent(event: MessageEvent<string>): void {
  const parsed = parseSseMessage(event.data)
  if (!parsed) {
    sseError.value = '收到了一条结构不正确的 SSE 消息'
    connectionState.value = 'error'
    return
  }

  const { message, timestamp } = parsed
  if (breakBeforeNextPoint && hasChartData) {
    // A null value prevents ECharts from connecting two independent SSE sessions.
    appendChartPoint({ timestamp: timestamp - 1, value: null })
  }
  breakBeforeNextPoint = false

  appendChartPoint({ timestamp, value: message.sequence })
  hasChartData = true
  messages.value = [{ ...message, clientKey: nextMessageKey++ }, ...messages.value].slice(0, 50)
  sseError.value = null
}

function connect(): void {
  if (eventSource && eventSource.readyState !== EventSource.CLOSED) {
    return
  }

  sseError.value = null
  connectionState.value = 'connecting'
  breakBeforeNextPoint = hasChartData

  const source = new EventSource(`${API_BASE_URL}/sse/events`)
  eventSource = source

  source.onopen = () => {
    connectionState.value = 'open'
    sseError.value = null
  }

  // 后端发送的是命名事件 `event: demo`，因此不能只使用 onmessage。
  source.addEventListener('demo', handleDemoEvent as EventListener)

  source.onerror = () => {
    if (source.readyState === EventSource.CONNECTING) {
      connectionState.value = 'reconnecting'
      sseError.value = '连接暂时中断，浏览器正在自动重连'
      breakBeforeNextPoint = hasChartData
      return
    }

    connectionState.value = source.readyState === EventSource.CLOSED ? 'closed' : 'error'
    sseError.value = 'SSE 连接异常，请确认后端服务是否已启动'
  }
}

function disconnect(): void {
  if (eventSource) {
    eventSource.removeEventListener('demo', handleDemoEvent as EventListener)
    eventSource.close()
    eventSource = null
  }

  connectionState.value = 'closed'
  sseError.value = null
}

function clearMessages(): void {
  messages.value = []
  clearChartPoints()
  hasChartData = false
  breakBeforeNextPoint = false
}

onMounted(() => {
  void demoStore.fetchDemo()
  connect()
})

onBeforeUnmount(() => {
  disposeChartSeries()
  disconnect()
})
</script>

<template>
  <main class="flex flex-col gap-4 md:gap-6">
    <header class="flex flex-col gap-2">
      <div class="flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <ActivityIcon class="size-4" aria-hidden="true" />
        FastAPI + Vue 3 Full-stack Starter
      </div>
      <h1 class="text-3xl font-semibold tracking-tight sm:text-4xl">
        REST 与 SSE 联动示例
      </h1>
      <p class="max-w-3xl text-muted-foreground">
        Alova 负责标准 HTTP 请求，Pinia 管理共享状态，原生 EventSource 接收 FastAPI
        持续推送的实时消息。
      </p>
    </header>

    <div class="grid items-start gap-6 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <Card>
          <CardHeader>
            <div class="flex items-start gap-3">
              <div class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                <ServerIcon class="size-5" aria-hidden="true" />
              </div>
              <div class="flex min-w-0 flex-1 flex-col gap-1">
                <CardTitle>REST API</CardTitle>
                <CardDescription>Pinia Store 通过 Alova 请求后端演示数据。</CardDescription>
              </div>
            </div>
            <CardAction>
              <Badge :variant="demo ? 'default' : 'outline'">
                {{ demo ? '数据已同步' : '等待数据' }}
              </Badge>
            </CardAction>
          </CardHeader>

          <CardContent class="flex flex-col gap-4">
            <Alert v-if="restError" variant="destructive">
              <TriangleAlertIcon aria-hidden="true" />
              <AlertTitle>REST 请求失败</AlertTitle>
              <AlertDescription>{{ restError }}</AlertDescription>
            </Alert>

            <div v-if="demo" class="flex flex-col gap-4 rounded-lg border p-4">
              <div class="flex flex-col gap-1">
                <span class="text-sm text-muted-foreground">服务消息</span>
                <strong class="font-medium">{{ demo.message }}</strong>
              </div>
              <Separator />
              <dl class="grid gap-3 text-sm">
                <div class="grid gap-1">
                  <dt class="text-muted-foreground">服务端时间</dt>
                  <dd>{{ formatTime(demo.server_time) }}</dd>
                </div>
                <div class="grid gap-1">
                  <dt class="text-muted-foreground">请求 ID</dt>
                  <dd class="break-all font-mono text-xs">{{ demo.request_id }}</dd>
                </div>
              </dl>
            </div>

            <Empty v-else-if="!loading" class="border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <InboxIcon aria-hidden="true" />
                </EmptyMedia>
                <EmptyTitle>暂无 REST 数据</EmptyTitle>
                <EmptyDescription>点击刷新按钮重新向 FastAPI 发起请求。</EmptyDescription>
              </EmptyHeader>
            </Empty>

            <div v-else class="flex min-h-40 items-center justify-center gap-2 text-muted-foreground">
              <Spinner />
              正在读取后端数据…
            </div>
          </CardContent>

          <CardFooter class="flex justify-end bg-muted/30">
            <Button variant="outline" :disabled="loading" @click="demoStore.fetchDemo">
              <Spinner v-if="loading" data-icon="inline-start" />
              <RefreshCwIcon v-else data-icon="inline-start" />
              {{ loading ? '刷新中' : '刷新 REST 数据' }}
            </Button>
          </CardFooter>
        </Card>

        <Card>
          <CardHeader>
            <div class="flex items-start gap-3">
              <div class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                <RadioIcon class="size-5" aria-hidden="true" />
              </div>
              <div class="flex min-w-0 flex-1 flex-col gap-1">
                <CardTitle>SSE 实时消息</CardTitle>
                <CardDescription>浏览器保持单向长连接，服务端每秒推送一条消息。</CardDescription>
              </div>
            </div>
            <CardAction>
              <Badge :variant="statusMeta.variant">{{ statusMeta.label }}</Badge>
            </CardAction>
          </CardHeader>

          <CardContent class="flex flex-col gap-4">
            <Alert v-if="sseError" :variant="connectionState === 'error' ? 'destructive' : 'default'">
              <TriangleAlertIcon aria-hidden="true" />
              <AlertTitle>SSE 状态提示</AlertTitle>
              <AlertDescription>{{ sseError }}</AlertDescription>
            </Alert>

            <ScrollArea v-if="messages.length > 0" class="h-80 rounded-lg border">
              <ul class="flex flex-col gap-3 p-4" aria-live="polite">
                <li
                  v-for="message in messages"
                  :key="message.clientKey"
                  class="grid gap-2 rounded-lg border bg-card p-3"
                >
                  <div class="flex items-center justify-between gap-3">
                    <Badge variant="secondary">#{{ message.sequence }}</Badge>
                    <time class="text-xs text-muted-foreground" :datetime="message.timestamp">
                      {{ formatTime(message.timestamp) }}
                    </time>
                  </div>
                  <p class="text-sm font-medium">{{ message.message }}</p>
                </li>
              </ul>
            </ScrollArea>

            <Empty v-else class="min-h-80 border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <RadioIcon aria-hidden="true" />
                </EmptyMedia>
                <EmptyTitle>等待实时消息</EmptyTitle>
                <EmptyDescription>
                  启动后端并建立连接后，新消息会自动显示在这里。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          </CardContent>

          <CardFooter class="flex flex-wrap justify-between gap-2 bg-muted/30">
            <Button variant="ghost" :disabled="messages.length === 0" @click="clearMessages">
              清空消息
            </Button>
            <div class="flex gap-2">
              <Button v-if="isConnected || isConnecting" variant="outline" @click="disconnect">
                <UnplugIcon data-icon="inline-start" />
                断开连接
              </Button>
              <Button v-else @click="connect">
                <PlugZapIcon data-icon="inline-start" />
                建立连接
              </Button>
            </div>
          </CardFooter>
        </Card>

        <Card class="min-w-0 lg:col-span-2">
          <CardHeader>
            <div class="flex items-start gap-3">
              <div class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                <ActivityIcon class="size-5" aria-hidden="true" />
              </div>
              <div class="flex min-w-0 flex-1 flex-col gap-1">
                <CardTitle>SSE 实时曲线</CardTitle>
                <CardDescription>
                  以服务端时间为横轴、消息序号为纵轴，演示有界缓存与批量刷新。
                </CardDescription>
              </div>
            </div>
            <CardAction>
              <Badge variant="secondary">{{ chartPoints.length }} / 1000 点</Badge>
            </CardAction>
          </CardHeader>

          <CardContent class="min-w-0">
            <RealtimeLineChart
              v-if="chartPoints.length > 0"
              class="h-80"
              :points="chartPoints"
              series-name="消息序号"
              y-axis-name="序号"
            />

            <Empty v-else class="min-h-72 border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <ActivityIcon aria-hidden="true" />
                </EmptyMedia>
                <EmptyTitle>等待曲线数据</EmptyTitle>
                <EmptyDescription>
                  SSE 消息到达后，数值会按固定频率批量绘制到这里。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          </CardContent>

          <CardFooter class="text-sm text-muted-foreground">
            滚轮可缩放，拖动底部滑块可查看历史区间；清空消息会同时清空曲线。
          </CardFooter>
        </Card>
      </div>
  </main>
</template>
