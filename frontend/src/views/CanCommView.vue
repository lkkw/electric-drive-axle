<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watchEffect } from 'vue'
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  CircleOffIcon,
  PauseIcon,
  PlayIcon,
  RefreshCwIcon,
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useAxleStore } from '@/stores/useAxleStore'
import type { CanConnectRequest, CanFrameItem } from '@/types/axle'

const axleStore = useAxleStore()

// 连接表单
const connForm = reactive<CanConnectRequest>({
  device_type: 4, // 默认 USBCAN2
  device_index: 0,
  channel: 0,
  baud_rate: 250000,
})

// 报文监视过滤器与状态
const isPaused = ref(false)
const directionFilter = ref<'ALL' | 'TX' | 'RX'>('ALL')
const searchFilter = ref('')
const viewMode = ref<'TRACE' | 'GROUP'>('TRACE') // 时间流 vs ID聚合

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

// 本地帧缓冲（当暂停滚动时固定画面，继续时同步 store）
const displayedFrames = ref<CanFrameItem[]>([])

// 响应式同步 store 帧数据至本地显示缓冲（暂停时冻结画面）
watchEffect(() => {
  if (!isPaused.value) {
    displayedFrames.value = [...axleStore.telemetry.recent_frames]
  }
})

type ProcessedFrame = CanFrameItem & { count?: number }

// 监听 store 变化，先过滤再按需分组
const processedFrames = computed<ProcessedFrame[]>(() => {
  const frames = isPaused.value ? displayedFrames.value : axleStore.telemetry.recent_frames
  
  let result = frames.filter((frame) => {
    if (directionFilter.value !== 'ALL' && frame.direction !== directionFilter.value) {
      return false
    }
    if (searchFilter.value.trim()) {
      const q = searchFilter.value.trim().toLowerCase()
      const matchesId = frame.can_id_hex.toLowerCase().includes(q)
      const matchesName = frame.name.toLowerCase().includes(q)
      const matchesData = frame.data_hex.toLowerCase().includes(q)
      if (!matchesId && !matchesName && !matchesData) {
        return false
      }
    }
    return true
  })

  if (viewMode.value === 'GROUP') {
    const map = new Map<string, ProcessedFrame>()
    for (const frame of result) {
      const key = `${frame.direction}-${frame.can_id_hex}`
      if (map.has(key)) {
        const existing = map.get(key)!
        const newCount = (existing.count || 1) + 1
        Object.assign(existing, frame)
        existing.count = newCount
      } else {
        map.set(key, { ...frame, count: 1 })
      }
    }
    return Array.from(map.values()).sort((a, b) => a.can_id_hex.localeCompare(b.can_id_hex))
  }

  return result
})

function togglePause() {
  if (!isPaused.value) {
    displayedFrames.value = [...axleStore.telemetry.recent_frames]
    isPaused.value = true
  } else {
    isPaused.value = false
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
  axleStore.startSse()
})

onBeforeUnmount(() => {
  // 不强制停止 SSE，若用户在控制台与诊断页切换保持流不断
})
</script>

<template>
  <div class="flex flex-col gap-6 w-full min-h-[calc(100vh-3rem)]">
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
            <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3.5">
              <!-- 设备型号 -->
              <div class="flex flex-col gap-1.5">
                <label class="text-xs font-semibold text-muted-foreground">设备型号</label>
                <Select
                  :model-value="String(connForm.device_type)"
                  @update:model-value="(v) => connForm.device_type = Number(v)"
                  :disabled="axleStore.isConnected || axleStore.loading"
                >
                  <SelectTrigger class="w-full font-mono">
                    <SelectValue placeholder="选择设备型号" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="4">USBCAN2</SelectItem>
                    <SelectItem value="3">USBCAN1</SelectItem>
                    <SelectItem value="21">USBCAN-2E-U</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <!-- 设备索引 -->
              <div class="flex flex-col gap-1.5">
                <label class="text-xs font-semibold text-muted-foreground">设备索引 (Index)</label>
                <Input
                  v-model.number="connForm.device_index"
                  type="number"
                  min="0"
                  max="15"
                  :disabled="axleStore.isConnected || axleStore.loading"
                  class="font-mono"
                />
              </div>

              <!-- 通道号 -->
              <div class="flex flex-col gap-1.5">
                <label class="text-xs font-semibold text-muted-foreground">CAN 通道</label>
                <Select
                  :model-value="String(connForm.channel)"
                  @update:model-value="(v) => connForm.channel = Number(v)"
                  :disabled="axleStore.isConnected || axleStore.loading"
                >
                  <SelectTrigger class="w-full font-mono">
                    <SelectValue placeholder="选择通道" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">CAN 通道 0</SelectItem>
                    <SelectItem value="1">CAN 通道 1</SelectItem>
                    <SelectItem value="-1">双通道 (全部)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <!-- 波特率 -->
              <div class="flex flex-col gap-1.5">
                <label class="text-xs font-semibold text-muted-foreground">通信波特率</label>
                <Select
                  :model-value="String(connForm.baud_rate)"
                  @update:model-value="(v) => connForm.baud_rate = Number(v)"
                  :disabled="axleStore.isConnected || axleStore.loading"
                >
                  <SelectTrigger class="w-full font-mono">
                    <SelectValue placeholder="选择波特率" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="250000">250 kbps</SelectItem>
                    <SelectItem value="500000">500 kbps</SelectItem>
                    <SelectItem value="1000000">1000 kbps (1M)</SelectItem>
                    <SelectItem value="125000">125 kbps</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="pt-2 flex items-center justify-end">
              <div class="flex items-center gap-2">
                <Button
                  v-if="!axleStore.isConnected"
                  class="h-11 px-5 font-semibold shadow-xs text-sm"
                  :disabled="axleStore.loading"
                  @click="handleConnect"
                >
                  <RefreshCwIcon v-if="axleStore.loading" data-icon="inline-start" class="animate-spin" />
                  打开设备并启动通道
                </Button>

                <Button
                  v-else
                  variant="destructive"
                  class="h-11 px-5 font-semibold shadow-xs text-sm"
                  :disabled="axleStore.loading"
                  @click="handleDisconnect"
                >
                  <RefreshCwIcon v-if="axleStore.loading" data-icon="inline-start" class="animate-spin" />
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
                  {{ axleStore.telemetry.last_rx_timestamp ? '毫秒级活跃' : '无数据' }}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>

    <!-- 原始报文监视器 (Bus Monitor) -->
    <Card class="border-border shadow-xs flex-1 flex flex-col min-h-[400px]">
      <CardHeader class="pb-3 border-b bg-muted/20 shrink-0">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <CardTitle class="text-base font-semibold flex items-center gap-2">
              CAN 原始报文实时监视
              <Badge variant="secondary" class="font-mono text-xs">
                {{ viewMode === 'TRACE' ? '共 ' + processedFrames.length + ' 帧' : '共 ' + processedFrames.length + ' 个 ID' }}
              </Badge>
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
              <ToggleGroupItem value="TRACE">
                时间流
              </ToggleGroupItem>
              <ToggleGroupItem value="GROUP">
                ID 聚合
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

            <!-- 暂停/继续按钮 -->
            <Button
              size="sm"
              variant="outline"
              class="h-8 px-2.5 text-xs"
              @click="togglePause"
            >
              <component :is="isPaused ? PlayIcon : PauseIcon" data-icon="inline-start" />
              {{ isPaused ? '继续监视' : '暂停滚动' }}
            </Button>

            <!-- 清空按钮 -->
            <Button
              size="sm"
              variant="outline"
              class="h-8 px-2.5 text-xs text-destructive hover:text-destructive"
              @click="handleClearFrames"
            >
              <Trash2Icon data-icon="inline-start" />
              清空
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent class="p-0 flex-1 overflow-hidden">
        <!-- 监视表格 -->
        <div class="h-full overflow-y-auto font-mono text-xs divide-y divide-border/60">
          <Table class="w-full text-left">
            <TableHeader class="sticky top-0 bg-muted/80 backdrop-blur-xs text-muted-foreground text-[11px] uppercase border-b border-border/80">
              <TableRow>
                <TableHead class="py-2.5 px-3 font-semibold w-20">{{ viewMode === 'TRACE' ? '序号' : '计数' }}</TableHead>
                <TableHead class="py-2.5 px-3 font-semibold w-24">时间戳</TableHead>
                <TableHead class="py-2.5 px-3 font-semibold w-20">方向</TableHead>
                <TableHead class="py-2.5 px-3 font-semibold w-24">CAN ID</TableHead>
                <TableHead class="py-2.5 px-3 font-semibold w-40">报文标识</TableHead>
                <TableHead class="py-2.5 px-3 font-semibold w-16">DLC</TableHead>
                <TableHead class="py-2.5 px-3 font-semibold">数据载荷 (DATA HEX)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody class="divide-y divide-border/40">
              <TableRow
                v-for="(item, idx) in processedFrames"
                :key="viewMode === 'TRACE' ? `${item.timestamp}-${idx}` : `${item.direction}-${item.can_id_hex}`"
                class="hover:bg-muted/30 transition-colors"
                :class="cn(item.direction === 'TX' && 'bg-info/5')"
              >
                <TableCell class="py-2 px-3 text-muted-foreground">
                  <span v-if="viewMode === 'TRACE'">#{{ idx + 1 }}</span>
                  <Badge v-else variant="outline" class="font-mono text-[10px] px-1.5 py-0 bg-background text-muted-foreground">
                    {{ item.count }}
                  </Badge>
                </TableCell>
                <TableCell class="py-2 px-3 text-muted-foreground">{{ item.timestamp }}</TableCell>
                <TableCell class="py-2 px-3">
                  <Badge
                    :variant="item.direction === 'TX' ? 'info' : 'success'"
                    class="font-mono text-[10px] px-1.5 py-0"
                  >
                    {{ item.direction }}
                  </Badge>
                </TableCell>
                <TableCell class="py-2 px-3 font-bold text-foreground">
                  {{ item.can_id_hex }}
                </TableCell>
                <TableCell class="py-2 px-3 font-sans text-xs text-foreground truncate max-w-[160px]">
                  {{ item.name || '—' }}
                </TableCell>
                <TableCell class="py-2 px-3 text-muted-foreground">{{ item.dlc }}</TableCell>
                <TableCell class="py-2 px-3 font-mono font-semibold tracking-wider text-foreground">
                  {{ item.data_hex }}
                </TableCell>
              </TableRow>

              <TableRow v-if="processedFrames.length === 0">
                <TableCell colspan="7" class="py-8 text-center text-muted-foreground font-sans">
                  暂无报文流
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
