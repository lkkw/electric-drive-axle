<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Trash2Icon } from '@lucide/vue'
import { toast } from 'vue-sonner'

import { clearPlcTrafficLog, getPlcTrafficLog, getPlcTrafficSnapshot } from '@/api/plc'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Field, FieldLabel } from '@/components/ui/field'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import type { PlcTrafficSnapshot, PlcTrafficValue } from '@/types/plc'
import {
  createTrafficState,
  formatTrafficValue,
  mergeTrafficLog,
  visibleTrafficEntries,
} from './plcTrafficUtils'

/**
 * PLC 通信监视（移植自 magmit）：联调时查看上位机与 PLC 双方的收发情况。
 * 上半部分为 1 号工位点表的实时值（刚变化的值高亮 2 s），下半部分为通信记录。
 */
const POLL_INTERVAL_MS = 1000
const HIGHLIGHT_MS = 2000

const snapshot = ref<PlcTrafficSnapshot | null>(null)
const traffic = ref(createTrafficState())
const showFrequent = ref(false)
const isClearing = ref(false)

const changedAt = new Map<string, number>()
const previousValues = new Map<string, PlcTrafficValue>()
const now = ref(Date.now())

const plcOnline = computed(() => Boolean(snapshot.value?.updated_at))
const visibleEntries = computed(() => visibleTrafficEntries(traffic.value, showFrequent.value))
const hiddenFrequentCount = computed(() => (showFrequent.value ? 0 : traffic.value.frequent.length))

const sides = computed(() => [
  {
    key: 'write' as const,
    title: '上位机 → PLC（我发给 PLC 的）',
    range: '+0 ~ +61',
    points: snapshot.value?.write ?? [],
  },
  {
    key: 'read' as const,
    title: 'PLC → 上位机（PLC 发给我的）',
    range: '+62 ~ +123',
    points: snapshot.value?.read ?? [],
  },
])

function isRecentlyChanged(name: string) {
  const at = changedAt.get(name)
  return at !== undefined && now.value - at < HIGHLIGHT_MS
}

function trackChanges(snap: PlcTrafficSnapshot) {
  if (!snap.updated_at) {
    previousValues.clear()
    return
  }
  for (const point of [...snap.write, ...snap.read]) {
    if (previousValues.has(point.name) && previousValues.get(point.name) !== point.value) {
      changedAt.set(point.name, Date.now())
    }
    previousValues.set(point.name, point.value)
  }
}

let timer: ReturnType<typeof setInterval> | undefined
let polling = false

async function poll() {
  if (polling) return
  polling = true
  try {
    const [snap, log] = await Promise.all([
      getPlcTrafficSnapshot().send(),
      getPlcTrafficLog(traffic.value.lastSeq).send(),
    ])
    trackChanges(snap)
    snapshot.value = snap
    traffic.value = mergeTrafficLog(traffic.value, log)
  } catch {
    // 轮询失败静默重试，不打断操作
  } finally {
    now.value = Date.now()
    polling = false
  }
}

async function handleClear() {
  isClearing.value = true
  try {
    await clearPlcTrafficLog().send()
    traffic.value = { ...createTrafficState(), lastSeq: traffic.value.lastSeq }
  } catch (err) {
    toast.error('清空失败', { description: err instanceof Error ? err.message : undefined })
  } finally {
    isClearing.value = false
  }
}

onMounted(() => {
  void poll()
  timer = setInterval(() => void poll(), POLL_INTERVAL_MS)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <Card>
    <CardHeader class="border-b pb-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <CardTitle>PLC 通信监视</CardTitle>
        <Badge :variant="plcOnline ? 'success' : 'secondary'">
          {{ plcOnline ? `已采样 ${snapshot?.updated_at}` : 'PLC 未连接，暂无数据' }}
        </Badge>
      </div>
    </CardHeader>

    <CardContent class="flex flex-col gap-5">
      <!-- 实时点表 -->
      <div class="flex flex-col gap-3">
        <span class="text-sm text-muted-foreground">实时点表（刚变化的值会高亮 2 秒）</span>
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <section v-for="side in sides" :key="side.key" class="flex flex-col rounded-lg border">
            <div class="flex items-center justify-between px-4 pt-3 pb-2">
              <h3 class="text-sm font-medium text-foreground">{{ side.title }}</h3>
              <span class="font-mono text-xs text-muted-foreground">{{ side.range }}</span>
            </div>
            <div
              v-for="point in side.points"
              :key="point.name"
              :class="
                cn(
                  'grid grid-cols-[1fr_auto_auto] items-center gap-3 px-4 py-1.5 text-sm transition-colors',
                  isRecentlyChanged(point.name) && 'bg-warning/15',
                )
              "
            >
              <span class="truncate text-foreground">{{ point.label }}</span>
              <span class="font-mono text-xs text-muted-foreground">{{ point.address }}</span>
              <span class="min-w-20 text-right font-mono text-foreground">
                {{ formatTrafficValue(point.name, point.value) }}
              </span>
            </div>
          </section>
        </div>
      </div>

      <!-- 通信记录 -->
      <div class="flex flex-col gap-3">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex flex-col gap-0.5">
            <span class="text-sm text-muted-foreground">通信记录（最新在上）</span>
            <span class="text-xs text-muted-foreground">
              上位机每次写入都会记录；PLC 发来的内容只在数值变化时记录。程序重启后清空。
            </span>
          </div>
          <div class="flex items-center gap-4">
            <Field orientation="horizontal" class="w-auto">
              <Switch id="plc-traffic-frequent" v-model="showFrequent" />
              <FieldLabel for="plc-traffic-frequent">显示心跳与转速温度</FieldLabel>
            </Field>
            <Button variant="outline" size="sm" :disabled="isClearing" @click="handleClear">
              <Trash2Icon data-icon="inline-start" />
              清空
            </Button>
          </div>
        </div>

        <ScrollArea class="h-80 rounded-lg border">
          <div
            v-if="visibleEntries.length === 0"
            class="flex h-80 items-center justify-center px-4 text-center text-sm text-muted-foreground"
          >
            {{
              hiddenFrequentCount > 0
                ? `暂无其他记录（已隐藏 ${hiddenFrequentCount} 条心跳与转速温度记录）`
                : '暂无记录。连接 PLC、上电、下电时，这里会出现收发内容。'
            }}
          </div>
          <div
            v-for="entry in visibleEntries"
            :key="entry.seq"
            class="grid grid-cols-[auto_auto_1fr_auto] items-center gap-3 border-b px-4 py-1.5 text-sm last:border-b-0"
          >
            <span class="font-mono text-xs text-muted-foreground">{{ entry.time }}</span>
            <Badge :variant="entry.direction === 'write' ? 'default' : 'info'">
              {{ entry.direction === 'write' ? '上位机 → PLC' : 'PLC → 上位机' }}
            </Badge>
            <span class="min-w-0 truncate">
              <span class="text-foreground">{{ entry.label }}</span>
              <span class="ml-1.5 font-mono text-xs text-muted-foreground">{{ entry.address }}</span>
              <span class="ml-2 font-mono text-foreground">
                <template v-if="entry.direction === 'read'">
                  {{ formatTrafficValue(entry.name, entry.previous) }} →
                  {{ formatTrafficValue(entry.name, entry.value) }}
                </template>
                <template v-else>= {{ formatTrafficValue(entry.name, entry.value) }}</template>
              </span>
            </span>
            <span class="text-xs text-muted-foreground">{{ entry.source }}</span>
          </div>
        </ScrollArea>
      </div>
    </CardContent>
  </Card>
</template>
