<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  AlertTriangleIcon,
  ArrowDownToLineIcon,
  CheckCircle2Icon,
  CircleOffIcon,
  PauseIcon,
  PlayIcon,
  Trash2Icon,
} from '@lucide/vue'

import { cn } from '@/lib/utils'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Field,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useAxleStore } from '@/stores/useAxleStore'
import type { CanConnectRequest, CanFrameItem } from '@/types/axle'
import { processFrames, type ProcessedFrame } from './canCommUtils'

const axleStore = useAxleStore()

// 连接表单
const connForm = reactive<CanConnectRequest>({
  device_type: 4, // 默认 USBCAN2
  device_index: 0,
  channel: 0,
  baud_rate: 500000,
})

// 报文监视过滤器与状态
const isPaused = ref(false)
const directionFilter = ref<'ALL' | 'TX' | 'RX'>('ALL')
const searchFilter = ref('')
const viewMode = ref<'TRACE' | 'GROUP'>('GROUP') // 报文展示模式：默认采用 ID 聚合模式 (GROUP)，亦可切换为时间流 (TRACE)
const MAX_RENDERED_FRAMES = 200

function setViewMode(value: unknown) {
  if (value === 'TRACE' || value === 'GROUP') {
    viewMode.value = value
  }
}

function setDirectionFilter(value: unknown) {
  if (value === 'ALL' || value === 'TX' || value === 'RX') {
    directionFilter.value = value
  }
}

// 本地帧缓冲（暂停时固定当前画面）
const displayedFrames = ref<CanFrameItem[]>([])

// 自动滚动状态与视口引用（时间流模式下默认自动滚动锁定至最新帧）
const autoScroll = ref(true)
const scrollAreaRef = ref<{ $el: HTMLElement } | null>(null)

function getScrollAreaViewport(): HTMLElement | null {
  const el = scrollAreaRef.value?.$el as HTMLElement | undefined
  return el?.querySelector('[data-slot="scroll-area-viewport"]') ?? null
}

function scrollToBottom() {
  if (!autoScroll.value || isPaused.value || viewMode.value !== 'TRACE') {
    return
  }
  nextTick(() => {
    const el = getScrollAreaViewport()
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  })
}

function handleViewportScroll(event: Event) {
  const target = event.target as HTMLElement | null
  if (!target || viewMode.value !== 'TRACE') return
  // 若距离底部在 32px 以内，视为处于底部，恢复自动滚动；
  // 若用户主动向上回翻查看历史帧，自动暂停跟随，避免画面被反复拉到底部
  const isNearBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 32
  autoScroll.value = isNearBottom
}

function toggleAutoScroll() {
  autoScroll.value = !autoScroll.value
  if (autoScroll.value) {
    scrollToBottom()
  }
}

watch(() => axleStore.telemetry.recent_frames.length, () => {
  scrollToBottom()
})

watch(viewMode, (newMode) => {
  if (newMode === 'TRACE') {
    nextTick(scrollToBottom)
  }
})

// 监听 store 变化，先过滤再按需分组
const processedFrames = computed<ProcessedFrame[]>(() => {
  return processFrames({
    frames: isPaused.value ? displayedFrames.value : axleStore.telemetry.recent_frames,
    viewMode: viewMode.value,
    directionFilter: directionFilter.value,
    searchFilter: searchFilter.value,
    maxFrames: MAX_RENDERED_FRAMES,
  })
})

function togglePause() {
  if (!isPaused.value) {
    displayedFrames.value = axleStore.telemetry.recent_frames.slice(-MAX_RENDERED_FRAMES)
    isPaused.value = true
  } else {
    isPaused.value = false
    scrollToBottom()
  }
}

async function handleClearFrames() {
  displayedFrames.value = []
  await axleStore.clearFrames()
}

async function handleConnect() {
  try {
    await axleStore.connect({ ...connForm })
  } catch {
    // 错误在 store.error 中展示
  }
}

async function handleDisconnect() {
  try {
    await axleStore.disconnect()
  } catch {
    // 错误在 store.error 中展示
  }
}

onMounted(async () => {
  await axleStore.refreshStatus()
  axleStore.startSse(true)

  // 从 store 的遥测快照恢复表单，避免组件重建后硬编码默认值覆盖用户选择
  const t = axleStore.telemetry
  connForm.device_type = t.device_type
  connForm.device_index = t.device_index
  connForm.channel = t.channel
  connForm.baud_rate = t.baud_rate

  nextTick(() => {
    const el = getScrollAreaViewport()
    el?.addEventListener('scroll', handleViewportScroll, { passive: true })
  })
})

onBeforeUnmount(() => {
  const el = getScrollAreaViewport()
  el?.removeEventListener('scroll', handleViewportScroll)
  // 其他页面仍保留核心遥测流，但不再搬运原始报文列表。
  axleStore.startSse(false)
})
</script>

<template>
  <div class="flex flex-col gap-6 w-full">
    <!-- 顶部导航标题栏 -->
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b pb-4 shrink-0">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-foreground">
          CAN 通讯配置与诊断
        </h1>
      </div>
    </div>

    <!-- 错误异常提示条 -->
    <Alert v-if="axleStore.error" variant="destructive" class="shrink-0">
      <AlertTriangleIcon />
      <AlertDescription>{{ axleStore.error }}</AlertDescription>
    </Alert>

    <!-- 顶部网格：硬件配置 + 通信状态与统计 -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 shrink-0">
      <!-- 硬件配置卡片 (占 7 列) -->
      <div class="lg:col-span-7">
        <Card class="border-border shadow-xs h-full flex flex-col justify-between">
          <CardHeader class="pb-3 border-b bg-muted/20">
            <div class="flex items-center justify-between">
              <div>
                <CardTitle class="text-base font-semibold">USBCAN 硬件参数配置</CardTitle>
              </div>
              <Badge
                :variant="axleStore.isConnected ? 'success' : 'outline'"
                :class="cn(!axleStore.isConnected && 'text-muted-foreground')"
              >
                <component
                  :is="axleStore.isConnected ? CheckCircle2Icon : CircleOffIcon"
                  data-icon="inline-start"
                />
                {{ axleStore.isConnected ? '硬件在线' : '未连接' }}
              </Badge>
            </div>
          </CardHeader>

          <CardContent class="p-4 sm:p-5 flex flex-col gap-4">
            <FieldGroup class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3.5">
              <!-- 设备型号 -->
              <Field>
                <FieldLabel class="text-xs font-semibold text-muted-foreground">设备型号</FieldLabel>
                <Select
                  :model-value="String(connForm.device_type)"
                  @update:model-value="(v) => connForm.device_type = Number(v)"
                  :disabled="axleStore.isConnected || axleStore.loading"
                >
                  <SelectTrigger class="w-full font-mono">
                    <SelectValue placeholder="选择设备型号" />
                  </SelectTrigger>
                  <SelectContent
                    position="popper"
                    side="bottom"
                    align="start"
                  >
                    <SelectGroup>
                      <SelectItem value="4">USBCAN2</SelectItem>
                      <SelectItem value="3">USBCAN1</SelectItem>
                      <SelectItem value="21">USBCAN-2E-U</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>

              <!-- 设备索引 -->
              <Field>
                <FieldLabel class="text-xs font-semibold text-muted-foreground">设备索引 (Index)</FieldLabel>
                <Input
                  v-model.number="connForm.device_index"
                  type="number"
                  min="0"
                  max="15"
                  :disabled="axleStore.isConnected || axleStore.loading"
                  class="font-mono"
                />
              </Field>

              <!-- 通道号 -->
              <Field>
                <FieldLabel class="text-xs font-semibold text-muted-foreground">CAN 通道</FieldLabel>
                <Select
                  :model-value="String(connForm.channel)"
                  @update:model-value="(v) => connForm.channel = Number(v)"
                  :disabled="axleStore.isConnected || axleStore.loading"
                >
                  <SelectTrigger class="w-full font-mono">
                    <SelectValue placeholder="选择通道" />
                  </SelectTrigger>
                  <SelectContent
                    position="popper"
                    side="bottom"
                    align="start"
                  >
                    <SelectGroup>
                      <SelectItem value="0">CAN 通道 0</SelectItem>
                      <SelectItem value="1">CAN 通道 1</SelectItem>
                      <SelectItem value="-1">双通道 (全部)</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>

              <!-- 波特率 -->
              <Field>
                <FieldLabel class="text-xs font-semibold text-muted-foreground">通信波特率</FieldLabel>
                <Select
                  :model-value="String(connForm.baud_rate)"
                  @update:model-value="(v) => connForm.baud_rate = Number(v)"
                  :disabled="axleStore.isConnected || axleStore.loading"
                >
                  <SelectTrigger class="w-full font-mono">
                    <SelectValue placeholder="选择波特率" />
                  </SelectTrigger>
                  <SelectContent
                    position="popper"
                    side="bottom"
                    align="start"
                  >
                    <SelectGroup>
                      <SelectItem value="500000">500 kbps</SelectItem>
                      <SelectItem value="250000">250 kbps</SelectItem>
                      <SelectItem value="1000000">1000 kbps (1M)</SelectItem>
                      <SelectItem value="125000">125 kbps</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
            </FieldGroup>

            <!-- 操作按钮 -->
            <div class="pt-2 flex items-center justify-end">
              <div class="flex items-center gap-2">
                <Button
                  v-if="!axleStore.isConnected"
                  class="h-11 px-5 font-semibold shadow-xs text-sm"
                  :disabled="axleStore.loading"
                  @click="handleConnect"
                >
                  <Spinner v-if="axleStore.loading" data-icon="inline-start" />
                  打开设备并启动通道
                </Button>

                <Button
                  v-else
                  variant="destructive"
                  class="h-11 px-5 font-semibold shadow-xs text-sm"
                  :disabled="axleStore.loading"
                  @click="handleDisconnect"
                >
                  <Spinner v-if="axleStore.loading" data-icon="inline-start" />
                  停止通信并释放设备
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <!-- 通信状态与统计指标 (占 5 列) -->
      <div class="lg:col-span-5">
        <Card class="border-border shadow-xs h-full flex flex-col justify-between">
          <CardHeader class="pb-3 border-b bg-muted/20">
            <div class="flex items-center justify-between">
              <div>
                <CardTitle class="text-base font-semibold">总线收发统计</CardTitle>
              </div>
            </div>
          </CardHeader>

          <CardContent class="p-4 sm:p-5 flex flex-col gap-3">
            <div class="grid grid-cols-3 gap-2.5">
              <div class="p-2.5 rounded-lg bg-muted/30 border border-border/50 text-center">
                <div class="text-[11px] text-muted-foreground font-semibold">发送帧数 (TX)</div>
                <div class="text-lg font-bold font-mono text-info mt-0.5">
                  {{ axleStore.telemetry.tx_frame_count }}
                </div>
              </div>

              <div class="p-2.5 rounded-lg bg-muted/30 border border-border/50 text-center">
                <div class="text-[11px] text-muted-foreground font-semibold">接收帧数 (RX)</div>
                <div class="text-lg font-bold font-mono text-success mt-0.5">
                  {{ axleStore.telemetry.rx_frame_count }}
                </div>
              </div>

              <div class="p-2.5 rounded-lg bg-muted/30 border border-border/50 text-center">
                <div class="text-[11px] text-muted-foreground font-semibold">发送错误 (ERR)</div>
                <div
                  class="text-lg font-bold font-mono mt-0.5"
                  :class="cn(
                    axleStore.telemetry.tx_error_count > 0
                      ? 'text-destructive font-extrabold'
                      : 'text-foreground',
                  )"
                >
                  {{ axleStore.telemetry.tx_error_count }}
                </div>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-2.5 pt-1 text-xs">
              <div class="p-2 rounded bg-background border border-border/50">
                <span class="text-muted-foreground">当前波特率:</span>
                <span class="font-mono font-bold ml-1.5">{{ axleStore.telemetry.baud_rate / 1000 }} kbps</span>
              </div>
              <div class="p-2 rounded bg-background border border-border/50">
                <span class="text-muted-foreground">最近接收:</span>
                <span class="font-mono ml-1.5">
                  {{
                    axleStore.telemetry.last_rx_timestamp
                      ? new Date(axleStore.telemetry.last_rx_timestamp * 1000).toTimeString().slice(0, 8)
                      : '未接收'
                  }}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>

    <!-- 原始报文监视器 (Bus Monitor) -->
    <Card class="border-border shadow-xs flex flex-col">
      <CardHeader class="pb-3 border-b bg-muted/20 shrink-0">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <CardTitle class="text-base font-semibold flex items-center gap-2">
              CAN 原始报文实时监视
            </CardTitle>
          </div>

            <!-- 工具栏：暂停/继续、清空、过滤 -->
          <div class="flex flex-wrap items-center gap-2">
            <!-- 视图模式切换 -->
            <ToggleGroup
              :model-value="viewMode"
              type="single"
              variant="outline"
              size="sm"
              aria-label="报文视图模式"
              @update:model-value="setViewMode"
            >
              <ToggleGroupItem value="GROUP">
                ID 聚合
              </ToggleGroupItem>
              <ToggleGroupItem value="TRACE">
                时间流
              </ToggleGroupItem>
            </ToggleGroup>

            <!-- 方向筛选 -->
            <ToggleGroup
              :model-value="directionFilter"
              type="single"
              variant="outline"
              size="sm"
              aria-label="报文方向筛选"
              @update:model-value="setDirectionFilter"
            >
              <ToggleGroupItem value="ALL">
                全部
              </ToggleGroupItem>
              <ToggleGroupItem value="TX" class="data-[state=on]:bg-info/10 data-[state=on]:text-info">
                TX 发送
              </ToggleGroupItem>
              <ToggleGroupItem value="RX" class="data-[state=on]:bg-success/10 data-[state=on]:text-success">
                RX 接收
              </ToggleGroupItem>
            </ToggleGroup>

            <!-- 搜索框 -->
            <Input
              v-model="searchFilter"
              type="text"
              placeholder="过滤 ID / 报文..."
              class="w-32 sm:w-44 font-mono"
            />

            <!-- 自动跟随滚屏（时间流模式） -->
            <Button
              v-if="viewMode === 'TRACE'"
              size="sm"
              variant="outline"
              class="h-8 px-2.5 text-xs transition-none"
              :class="autoScroll ? 'bg-primary/10 text-primary border-primary/30 font-medium' : 'text-muted-foreground'"
              :title="autoScroll ? '当前正在自动跟随最新报文滚动' : '已暂停跟随，点击恢复自动滚到底部'"
              @click="toggleAutoScroll"
            >
              <component :is="autoScroll ? ArrowDownToLineIcon : PauseIcon" data-icon="inline-start" />
              {{ autoScroll ? '滚屏跟随' : '暂停跟随' }}
            </Button>

            <!-- 暂停/继续按钮 -->
            <Button
              size="sm"
              variant="outline"
              class="h-8 px-2.5 text-xs transition-none"
              @click="togglePause"
            >
              <component :is="isPaused ? PlayIcon : PauseIcon" data-icon="inline-start" />
              {{ isPaused ? '继续监视' : '暂停刷新' }}
            </Button>

            <!-- 清空按钮 -->
            <Button
              size="sm"
              variant="outline"
              class="h-8 px-2.5 text-xs text-destructive hover:text-destructive transition-none"
              @click="handleClearFrames"
            >
              <Trash2Icon data-icon="inline-start" />
              清空
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent class="p-0 overflow-hidden">
        <!-- 监视表格：使用 ScrollArea 约束视口高度，配合 overflow-visible 保证 TableHeader 粘性吸顶 -->
        <ScrollArea
          ref="scrollAreaRef"
          class="h-[460px] xl:h-[540px] w-full font-mono text-xs [&_[data-slot=table-container]]:overflow-visible"
        >
          <Table class="w-full table-fixed text-left">
            <TableHeader class="sticky top-0 z-10 bg-muted/95 backdrop-blur-xs text-muted-foreground text-[11px] uppercase border-b border-border/80 shadow-xs">
              <TableRow class="hover:bg-transparent">
                <TableHead class="w-12 px-2 py-2.5 font-semibold sm:w-20 sm:px-3">{{ viewMode === 'TRACE' ? '序号' : '计数' }}</TableHead>
                <TableHead class="hidden px-3 py-2.5 font-semibold sm:table-cell sm:w-32">时间戳</TableHead>
                <TableHead class="w-16 px-2 py-2.5 font-semibold sm:w-24 sm:px-4">方向</TableHead>
                <TableHead class="w-20 px-2 py-2.5 font-semibold sm:w-24 sm:px-3">CAN ID</TableHead>
                <TableHead class="hidden px-3 py-2.5 font-semibold sm:table-cell sm:w-40">报文标识</TableHead>
                <TableHead class="hidden px-3 py-2.5 font-semibold sm:table-cell sm:w-16">DLC</TableHead>
                <TableHead class="px-2 py-2.5 font-semibold sm:px-3">
                  <span class="sm:hidden">数据</span>
                  <span class="hidden sm:inline">数据载荷 (DATA HEX)</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody class="divide-y divide-border/40">
              <TableRow
                v-for="item in processedFrames"
                :key="viewMode === 'TRACE' ? item.sequence : `${item.direction}-${item.can_id_hex}`"
                class="hover:bg-muted/40 transition-none"
              >
                <TableCell class="px-2 py-2 text-muted-foreground sm:px-3">
                  <span v-if="viewMode === 'TRACE'">#{{ item.sequence }}</span>
                  <Badge v-else variant="outline" class="bg-background px-1.5 py-0 font-mono text-[10px] font-normal text-muted-foreground">
                    {{ item.count }}
                  </Badge>
                </TableCell>
                <TableCell class="hidden whitespace-nowrap px-3 py-2 font-normal text-muted-foreground sm:table-cell">{{ item.timestamp }}</TableCell>
                <TableCell class="px-2 py-2 sm:px-4">
                  <Badge
                    :variant="item.direction === 'TX' ? 'info' : 'success'"
                    class="px-1.5 py-0 font-mono text-[10px] font-normal"
                  >
                    {{ item.direction }}
                  </Badge>
                </TableCell>
                <TableCell class="px-2 py-2 font-normal text-foreground sm:px-3">
                  {{ item.can_id_hex }}
                </TableCell>
                <TableCell class="hidden px-3 py-2 font-sans text-xs text-foreground truncate sm:table-cell">
                  {{ item.name || '—' }}
                </TableCell>
                <TableCell class="hidden px-3 py-2 text-muted-foreground sm:table-cell">{{ item.dlc }}</TableCell>
                <TableCell class="truncate px-2 py-2 font-mono font-normal tracking-normal text-foreground sm:px-3">
                  {{ item.data_hex }}
                </TableCell>
              </TableRow>

              <TableRow v-if="processedFrames.length === 0">
                <TableCell colspan="4" class="py-8 text-center text-muted-foreground font-sans sm:hidden">
                  暂无报文流
                </TableCell>
                <TableCell colspan="7" class="hidden py-8 text-center text-muted-foreground font-sans sm:table-cell">
                  暂无报文流
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </ScrollArea>
      </CardContent>
    </Card>
  </div>
</template>
