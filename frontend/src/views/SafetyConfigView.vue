<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertTriangleIcon, SaveIcon, Trash2Icon } from '@lucide/vue'
import { toast } from 'vue-sonner'

import { getSafetyConfig, updateSafetyConfig } from '@/api/axle'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Spinner } from '@/components/ui/spinner'
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { SITE_HEADER_ACTIONS } from '@/components/layout/headerActions'
import { useAxleStore } from '@/stores/useAxleStore'
import type { AxleSafetyConfig, SafetyConfigRecord } from '@/types/axle'
import {
  SAFETY_HISTORY_STORAGE_KEY,
  parseSafetyHistory,
  prependSafetyHistory,
} from './safetyConfigHistory'

const axleStore = useAxleStore()

/** 历史表格列数，用于空状态跨列 */
const HISTORY_COLUMN_COUNT = 7

const config = ref<AxleSafetyConfig>({
  enabled: true,
  max_motor_speed_rpm: 3000,
  max_motor_torque_nm: 10,
  max_motor_temp_c: 150,
  feedback_timeout_ms: 500,
})
const isLoading = ref(true)
const isSaving = ref(false)
const saveError = ref<string | null>(null)
/** 配置保存与下发生效历史审计列表 (上限 100 条) */
const savedHistory = ref<SafetyConfigRecord[]>([])

function loadHistoryFromStorage(): SafetyConfigRecord[] {
  try {
    return parseSafetyHistory(localStorage.getItem(SAFETY_HISTORY_STORAGE_KEY))
  } catch {
    return []
  }
}

/** 持久化保存记录至 localStorage */
function saveHistoryToStorage(records: SafetyConfigRecord[]) {
  try {
    localStorage.setItem(SAFETY_HISTORY_STORAGE_KEY, JSON.stringify(records))
  } catch {
    // 忽略异常，防止无痕模式或存储空间满时阻塞操作
  }
}

/** 清空本地保存审计记录 */
function clearSavedHistory() {
  savedHistory.value = []
  try {
    localStorage.removeItem(SAFETY_HISTORY_STORAGE_KEY)
  } catch {
    // 忽略异常
  }
}

const isWithinRange = (value: unknown, minimum: number, maximum: number) => {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) && numericValue > minimum && numericValue <= maximum
}

const speedInvalid = computed(() =>
  !isWithinRange(config.value.max_motor_speed_rpm, 0, 12000),
)
const torqueInvalid = computed(() =>
  !isWithinRange(config.value.max_motor_torque_nm, 0, 3000),
)
const temperatureInvalid = computed(() =>
  !isWithinRange(config.value.max_motor_temp_c, 0, 210),
)
const feedbackTimeoutInvalid = computed(() => {
  const value = Number(config.value.feedback_timeout_ms)
  return !Number.isInteger(value) || value < 100 || value > 5000
})
const hasInvalidThreshold = computed(() =>
  speedInvalid.value ||
  torqueInvalid.value ||
  temperatureInvalid.value ||
  feedbackTimeoutInvalid.value,
)
const lastTrip = computed(() => axleStore.telemetry.safety.last_trip)

function formatTriggeredAt(timestamp: string) {
  return new Date(timestamp).toLocaleString('zh-CN', { hour12: false })
}

function formatFeedbackTimeout(value: number | undefined) {
  return value === undefined ? '—' : `${value} ms`
}

async function loadSafetyConfig() {
  isLoading.value = true
  saveError.value = null

  try {
    config.value = await getSafetyConfig().send()
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : '获取安全配置失败'
  } finally {
    isLoading.value = false
  }
}

async function saveSafetyConfig() {
  if (hasInvalidThreshold.value) {
    return
  }

  isSaving.value = true
  saveError.value = null

  try {
    const savedConfig = await updateSafetyConfig({
      enabled: config.value.enabled,
      max_motor_speed_rpm: Number(config.value.max_motor_speed_rpm),
      max_motor_torque_nm: Number(config.value.max_motor_torque_nm),
      max_motor_temp_c: Number(config.value.max_motor_temp_c),
      feedback_timeout_ms: Number(config.value.feedback_timeout_ms),
    }).send()
    config.value = savedConfig

    // 详细记录当前保存时间戳以及各项阈值
    const now = new Date()
    const record: SafetyConfigRecord = {
      id: `cfg-${now.getTime()}`,
      timestamp: now.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }),
      rawTimestamp: now.getTime(),
      enabled: savedConfig.enabled,
      max_motor_speed_rpm: savedConfig.max_motor_speed_rpm,
      max_motor_torque_nm: savedConfig.max_motor_torque_nm,
      max_motor_temp_c: savedConfig.max_motor_temp_c,
      feedback_timeout_ms: savedConfig.feedback_timeout_ms,
    }

    savedHistory.value = prependSafetyHistory(savedHistory.value, record)
    saveHistoryToStorage(savedHistory.value)
    toast.success(savedConfig.enabled ? '安全配置已保存并生效' : '安全监控已停用')

    if (!axleStore.sseConnected) await axleStore.refreshStatus()
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : '保存安全配置失败'
  } finally {
    isSaving.value = false
  }
}

onMounted(async () => {
  savedHistory.value = loadHistoryFromStorage()
  await loadSafetyConfig()
})
</script>

<template>
  <div class="flex w-full flex-col gap-6">
    <Teleport defer :to="SITE_HEADER_ACTIONS">
      <Badge :variant="config.enabled ? 'success' : 'secondary'">
        {{ config.enabled ? '安全监控已启用' : '安全监控未启用' }}
      </Badge>
      <Badge v-if="axleStore.isEmergencyLocked" variant="destructive">
        急停互锁中 · 请到控制台复位
      </Badge>
    </Teleport>

    <Card>
      <CardHeader class="border-b pb-4">
        <CardTitle>安全监控阈值</CardTitle>
        <CardDescription>
          转速与转矩按绝对值判断；配置保存在本机，重启后保留。
        </CardDescription>
      </CardHeader>

      <CardContent class="pt-5">
        <FieldGroup>
          <Field orientation="horizontal" class="rounded-lg border p-4">
            <Switch id="auto-emergency-stop" v-model="config.enabled" />
            <FieldContent>
              <FieldLabel for="auto-emergency-stop">启用安全监控</FieldLabel>
              <FieldDescription>
                任一阈值被实时反馈超过，或使能期间 MCU 反馈中断时，立即进入急停互锁。
              </FieldDescription>
            </FieldContent>
          </Field>

          <div class="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
            <Field :data-invalid="speedInvalid || undefined">
              <FieldLabel for="max-motor-speed">最大绝对转速 (RPM)</FieldLabel>
              <Input
                id="max-motor-speed"
                v-model.number="config.max_motor_speed_rpm"
                type="number"
                min="1"
                max="12000"
                step="1"
                :disabled="isLoading"
                :aria-invalid="speedInvalid || undefined"
              />
              <FieldError v-if="speedInvalid">请输入 1–12000 之间的数值。</FieldError>
            </Field>

            <Field :data-invalid="torqueInvalid || undefined">
              <FieldLabel for="max-motor-torque">最大绝对转矩 (Nm)</FieldLabel>
              <Input
                id="max-motor-torque"
                v-model.number="config.max_motor_torque_nm"
                type="number"
                min="0.1"
                max="3000"
                step="0.1"
                :disabled="isLoading"
                :aria-invalid="torqueInvalid || undefined"
              />
              <FieldError v-if="torqueInvalid">请输入大于 0 且不超过 3000 的数值。</FieldError>
            </Field>

            <Field :data-invalid="temperatureInvalid || undefined">
              <FieldLabel for="max-motor-temperature">最高电机温度 (℃)</FieldLabel>
              <Input
                id="max-motor-temperature"
                v-model.number="config.max_motor_temp_c"
                type="number"
                min="0.1"
                max="210"
                step="1"
                :disabled="isLoading"
                :aria-invalid="temperatureInvalid || undefined"
              />
              <FieldError v-if="temperatureInvalid">请输入大于 0 且不超过 210 的数值。</FieldError>
            </Field>

            <Field :data-invalid="feedbackTimeoutInvalid || undefined">
              <FieldLabel for="feedback-timeout">反馈中断超时 (ms)</FieldLabel>
              <Input
                id="feedback-timeout"
                v-model.number="config.feedback_timeout_ms"
                type="number"
                min="100"
                max="5000"
                step="50"
                :disabled="isLoading"
                :aria-invalid="feedbackTimeoutInvalid || undefined"
              />
              <FieldDescription v-if="!feedbackTimeoutInvalid">
                MCU_2 (0x35B) 周期 10 ms。
              </FieldDescription>
              <FieldError v-else>请输入 100–5000 之间的整数。</FieldError>
            </Field>
          </div>
        </FieldGroup>
      </CardContent>

      <CardFooter class="justify-end">
        <Button
          type="button"
          :disabled="isLoading || isSaving || hasInvalidThreshold"
          @click="saveSafetyConfig"
        >
          <Spinner v-if="isSaving" data-icon="inline-start" />
          <SaveIcon v-else data-icon="inline-start" />
          {{ isSaving ? '保存中…' : '保存配置' }}
        </Button>
      </CardFooter>
    </Card>

    <Alert v-if="saveError" variant="destructive">
      <AlertTriangleIcon />
      <AlertTitle>配置未保存</AlertTitle>
      <AlertDescription>{{ saveError }}</AlertDescription>
    </Alert>

    <!-- 配置保存与审计记录表格 -->
    <Card>
      <CardHeader class="border-b pb-3">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>配置保存记录</CardTitle>
          <div v-if="savedHistory.length > 0" class="flex items-center gap-2">
            <Badge variant="secondary">
              共 {{ savedHistory.length }} 条
            </Badge>
            <Button variant="outline" size="sm" @click="clearSavedHistory">
              <Trash2Icon data-icon="inline-start" />
              清空记录
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent class="p-0">
        <div class="max-h-[520px] overflow-auto">
          <Table>
            <TableHeader class="sticky top-0 z-10 bg-muted">
              <TableRow>
                <TableHead class="w-12 text-center">序号</TableHead>
                <TableHead class="min-w-44">保存时间戳</TableHead>
                <TableHead class="min-w-28">安全监控</TableHead>
                <TableHead class="min-w-28">绝对转速 (RPM)</TableHead>
                <TableHead class="min-w-28">绝对转矩 (Nm)</TableHead>
                <TableHead class="min-w-28">最高温度 (℃)</TableHead>
                <TableHead class="min-w-28">反馈超时</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <template v-if="savedHistory.length > 0">
                <TableRow v-for="(item, index) in savedHistory" :key="item.id">
                  <TableCell class="text-center font-mono text-muted-foreground">
                    {{ index + 1 }}
                  </TableCell>
                  <TableCell class="font-mono">
                    <div class="flex items-center gap-1.5">
                      <span>{{ item.timestamp }}</span>
                      <Badge v-if="index === 0" variant="success">最新生效</Badge>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge :variant="item.enabled ? 'success' : 'secondary'">
                      {{ item.enabled ? '已启用' : '已关闭' }}
                    </Badge>
                  </TableCell>
                  <TableCell class="font-mono">{{ item.max_motor_speed_rpm }}</TableCell>
                  <TableCell class="font-mono">{{ item.max_motor_torque_nm }}</TableCell>
                  <TableCell class="font-mono">{{ item.max_motor_temp_c }}</TableCell>
                  <TableCell class="font-mono">
                    {{ formatFeedbackTimeout(item.feedback_timeout_ms) }}
                  </TableCell>
                </TableRow>
              </template>
              <TableEmpty v-else :colspan="HISTORY_COLUMN_COUNT">
                <span class="text-muted-foreground">
                  暂无本地保存记录。修改参数并点击“保存配置”后将在此记录。
                </span>
              </TableEmpty>
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>

    <Alert v-if="lastTrip" variant="destructive">
      <AlertTriangleIcon />
      <AlertTitle>最近一次自动停机</AlertTitle>
      <AlertDescription class="flex flex-col gap-1">
        <p>{{ lastTrip.message }}</p>
        <p>触发时间：{{ formatTriggeredAt(lastTrip.triggered_at) }}</p>
      </AlertDescription>
    </Alert>
  </div>
</template>
