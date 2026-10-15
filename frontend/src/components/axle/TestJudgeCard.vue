<script setup lang="ts">
/**
 * 试车判定：展示当前这台电驱桥的试车统计，操作员判定合格 / NG。
 * 判定时后端把结果写入 PLC Result 上传 MES、保存试车记录，并清零统计开始下一台。
 * 循环测试结束后由后端自动判定，循环执行中与自动判定期间不允许手动判定。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { CircleCheckIcon, CircleXIcon, HistoryIcon } from '@lucide/vue'
import { toast } from 'vue-sonner'

import { getTestSession, judgeTest } from '@/api/testRecords'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { useAxleStore } from '@/stores/useAxleStore'
import { usePlcStore } from '@/stores/usePlcStore'
import type { TestResult, TestSessionStats } from '@/types/testRecords'
import { formatDuration, formatValue } from '@/views/testRecordUtils'

const POLL_INTERVAL_MS = 1000

const plc = usePlcStore()
const axleStore = useAxleStore()

const session = ref<TestSessionStats | null>(null)
const remark = ref('')
const confirmResult = ref<TestResult | null>(null)
const submitting = ref(false)
let timer: ReturnType<typeof setInterval> | undefined

const confirmOpen = computed({
  get: () => confirmResult.value !== null,
  set: (open: boolean) => {
    if (!open) confirmResult.value = null
  },
})

/** 手动判定被禁止的原因；与后端 judge_blocker 一致 */
const judgeBlockedReason = computed(() => {
  const cycle = axleStore.telemetry.cycle_test
  if (cycle.status === 'running' || cycle.status === 'paused') {
    return '循环测试执行中，结束后自动判定'
  }
  if (cycle.auto_judge === 'pending') return '正在自动判定 / 下电，请稍候'
  return null
})

const serialNumber = computed(() => plc.status.serial_number || '')
const hasData = computed(() => Boolean(session.value?.started_at))

const stats = computed(() => {
  const s = session.value
  return [
    { label: '试车时长', value: formatDuration(s?.duration_s) },
    { label: '最高转速', value: formatValue(s?.max_speed_rpm, 'RPM') },
    { label: '最大转矩', value: formatValue(s?.max_torque_nm, 'Nm', 1) },
    { label: '最高电机温度', value: formatValue(s?.max_motor_temp_c, '℃') },
    { label: '最高控制器温度', value: formatValue(s?.max_controller_temp_c, '℃') },
    { label: '最大母线电流', value: formatValue(s?.max_bus_current_a, 'A', 1) },
  ]
})

async function refresh() {
  try {
    session.value = await getTestSession()
  } catch {
    // 后端暂时不可达时保留上次数据，下一轮再试
  }
}

async function handleJudge() {
  const result = confirmResult.value
  if (result === null) return
  submitting.value = true
  try {
    const response = await judgeTest(result, remark.value.trim())
    const notify = response.record.plc_result_written ? toast.success : toast.warning
    notify(result === 1 ? '已判定合格' : '已判定 NG', { description: response.message })
    remark.value = ''
    confirmResult.value = null
    await refresh()
  } catch (error) {
    toast.error('判定失败', {
      description: error instanceof Error ? error.message : '请稍后重试',
    })
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  void refresh()
  timer = setInterval(() => void refresh(), POLL_INTERVAL_MS)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <Card>
    <CardHeader class="border-b pb-3">
      <div class="flex items-center justify-between gap-2">
        <CardTitle>试车判定</CardTitle>
        <Button as-child variant="ghost" size="sm">
          <RouterLink to="/records">
            <HistoryIcon data-icon="inline-start" />
            试车记录
          </RouterLink>
        </Button>
      </div>
      <CardDescription>
        循环测试跑完后自动判定并下电；手动测试时在此判定。判定结果写入 PLC 上传 MES 并保存试车记录，统计清零开始下一台。
      </CardDescription>
    </CardHeader>

    <CardContent class="flex flex-col gap-4 pt-1">
      <div class="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <span class="text-muted-foreground">产品序列号</span>
        <span class="font-mono text-foreground">{{ serialNumber || '--（PLC 未提供）' }}</span>
        <template v-if="session?.fault_codes.length">
          <span class="text-muted-foreground">故障码</span>
          <span class="flex flex-wrap gap-1">
            <Badge v-for="code in session.fault_codes" :key="code" variant="destructive">
              {{ code }}
            </Badge>
          </span>
        </template>
        <template v-if="session?.safety_trips">
          <span class="text-muted-foreground">安全停机</span>
          <Badge variant="warning">{{ session.safety_trips }} 次</Badge>
        </template>
      </div>

      <dl class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <div v-for="item in stats" :key="item.label" class="rounded-lg border px-3 py-2">
          <dt class="text-xs text-muted-foreground">{{ item.label }}</dt>
          <dd class="mt-1 font-mono text-base text-foreground">{{ item.value }}</dd>
        </div>
      </dl>

      <p v-if="!hasData" class="text-sm text-muted-foreground">
        尚未收到 MCU 反馈：连接 CAN 后开始统计这一台的试车数据。
      </p>
    </CardContent>

    <CardFooter class="flex-wrap gap-3">
      <Input
        v-model="remark"
        maxlength="200"
        placeholder="备注（可选，例如 NG 原因）"
        class="h-10 min-w-48 flex-1"
      />
      <span v-if="judgeBlockedReason" class="w-full text-sm text-muted-foreground">
        {{ judgeBlockedReason }}
      </span>
      <Button
        class="h-10 w-28"
        variant="success"
        :disabled="Boolean(judgeBlockedReason)"
        @click="confirmResult = 1"
      >
        <CircleCheckIcon data-icon="inline-start" />
        合格
      </Button>
      <Button
        class="h-10 w-28"
        variant="destructive"
        :disabled="Boolean(judgeBlockedReason)"
        @click="confirmResult = 2"
      >
        <CircleXIcon data-icon="inline-start" />
        NG
      </Button>
    </CardFooter>

    <Dialog v-model:open="confirmOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>确认判定为{{ confirmResult === 1 ? '合格' : ' NG' }}</DialogTitle>
          <DialogDescription>
            序列号 {{ serialNumber || '未提供' }}，试车时长
            {{ formatDuration(session?.duration_s) }}。判定后结果写入 PLC，并保存试车记录。
          </DialogDescription>
        </DialogHeader>
        <p v-if="!hasData" class="text-sm text-muted-foreground">
          当前没有试车数据，记录中各项统计将为空。
        </p>
        <DialogFooter>
          <Button variant="outline" :disabled="submitting" @click="confirmResult = null">
            取消
          </Button>
          <Button
            :variant="confirmResult === 1 ? 'success' : 'destructive'"
            :disabled="submitting"
            @click="handleJudge"
          >
            <Spinner v-if="submitting" data-icon="inline-start" />
            确认{{ confirmResult === 1 ? '合格' : ' NG' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </Card>
</template>
