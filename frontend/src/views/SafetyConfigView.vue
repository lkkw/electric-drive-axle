<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ClockIcon,
  HistoryIcon,
  SaveIcon,
  ShieldCheckIcon,
  Trash2Icon,
} from '@lucide/vue'

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
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useAxleStore } from '@/stores/useAxleStore'
import type { AxleSafetyConfig, SafetyConfigRecord } from '@/types/axle'

const axleStore = useAxleStore()

const STORAGE_KEY = 'axle_safety_config_history'
/** 最大历史保存记录上限条数 */
const MAX_HISTORY_RECORDS = 100

const config = ref<AxleSafetyConfig>({
  enabled: true,
  max_motor_speed_rpm: 3000,
  max_motor_torque_nm: 10,
  max_motor_temp_c: 150,
})
const isLoading = ref(true)
const isSaving = ref(false)
const saveError = ref<string | null>(null)
const saved = ref(false)

/** 最近一次保存生成的详细记录快照 */
const lastSavedRecord = ref<SafetyConfigRecord | null>(null)

/** 配置保存与下发生效历史审计列表 (上限 100 条) */
const savedHistory = ref<SafetyConfigRecord[]>([])

/** 从本地 localStorage 加载保存记录 */
function loadHistoryFromStorage(): SafetyConfigRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (item): item is SafetyConfigRecord =>
        typeof item === 'object' &&
        item !== null &&
        typeof item.id === 'string' &&
        typeof item.timestamp === 'string' &&
        typeof item.enabled === 'boolean' &&
        typeof item.max_motor_speed_rpm === 'number' &&
        typeof item.max_motor_torque_nm === 'number' &&
        typeof item.max_motor_temp_c === 'number',
    )
  } catch {
    return []
  }
}

/** 持久化保存记录至 localStorage */
function saveHistoryToStorage(records: SafetyConfigRecord[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(records))
  } catch {
    // 忽略异常，防止无痕模式或存储空间满时阻塞操作
  }
}

/** 清空本地保存审计记录 */
function clearSavedHistory() {
  savedHistory.value = []
  lastSavedRecord.value = null
  try {
    localStorage.removeItem(STORAGE_KEY)
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
const hasInvalidThreshold = computed(() =>
  speedInvalid.value || torqueInvalid.value || temperatureInvalid.value,
)
const lastTrip = computed(() => axleStore.telemetry.safety.last_trip)

function formatTriggeredAt(timestamp: string) {
  return new Date(timestamp).toLocaleString('zh-CN', { hour12: false })
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
  saved.value = false

  try {
    const savedConfig = await updateSafetyConfig({
      enabled: config.value.enabled,
      max_motor_speed_rpm: Number(config.value.max_motor_speed_rpm),
      max_motor_torque_nm: Number(config.value.max_motor_torque_nm),
      max_motor_temp_c: Number(config.value.max_motor_temp_c),
    }).send()
    config.value = savedConfig
    saved.value = true

    // 详细记录当前保存时间戳以及转速、扭矩、温度参数值
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
    }

    lastSavedRecord.value = record
    savedHistory.value = [record, ...savedHistory.value.filter((r) => r.id !== record.id)].slice(0, MAX_HISTORY_RECORDS)
    saveHistoryToStorage(savedHistory.value)

    await axleStore.refreshStatus()
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : '保存安全配置失败'
  } finally {
    isSaving.value = false
  }
}

onMounted(async () => {
  savedHistory.value = loadHistoryFromStorage().slice(0, MAX_HISTORY_RECORDS)
  if (savedHistory.value.length > 0) {
    lastSavedRecord.value = savedHistory.value[0]
  }
  await loadSafetyConfig()
})
</script>

<template>
  <div class="flex w-full flex-col gap-6">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div class="flex items-center gap-2">
          <ShieldCheckIcon class="size-5 text-primary" />
          <h1 class="text-2xl font-bold tracking-tight text-foreground">
            安全配置
          </h1>
        </div>
        <p class="mt-1 text-sm text-muted-foreground">
          设置实时反馈越限后的安全监控条件。
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <Badge :variant="config.enabled ? 'success' : 'secondary'">
          {{ config.enabled ? '安全监控已启用' : '安全监控未启用' }}
        </Badge>
        <Badge v-if="axleStore.telemetry.is_emergency_locked" variant="destructive">
          急停互锁中
        </Badge>
      </div>
    </div>

    <Card>
      <CardHeader class="border-b pb-4">
        <CardTitle>安全监控阈值</CardTitle>
        <CardDescription>
          转速与转矩按绝对值判断，正反转和驱动/回馈转矩均受保护。
        </CardDescription>
      </CardHeader>

      <CardContent class="pt-5">
        <FieldGroup>
          <Field orientation="horizontal" class="rounded-lg border p-4">
            <Switch id="auto-emergency-stop" v-model="config.enabled" />
            <FieldContent>
              <FieldLabel for="auto-emergency-stop">启用安全监控</FieldLabel>
              <FieldDescription>
                任一已配置阈值被实时反馈超过时，立即进入急停互锁。
              </FieldDescription>
            </FieldContent>
          </Field>

          <div class="grid grid-cols-1 gap-5 md:grid-cols-3">
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

    <!-- 配置保存成功详细凭据 -->
    <Alert v-else-if="saved && lastSavedRecord" class="border-success/30 bg-success/5">
      <ShieldCheckIcon class="text-success" />
      <div class="flex flex-col gap-2.5 w-full">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5">
          <AlertTitle class="text-success font-bold flex items-center gap-1.5">
            安全配置已保存并生效
          </AlertTitle>
          <span class="text-xs font-mono text-muted-foreground flex items-center gap-1">
            <ClockIcon class="size-3.5" />
            保存时间戳: {{ lastSavedRecord.timestamp }}
          </span>
        </div>

        <AlertDescription class="flex flex-col gap-2">
          <p class="text-xs text-foreground/85">
            {{ lastSavedRecord.enabled ? '参数已下发并生效。' : '安全监控已停用。' }}
          </p>

          <!-- 详细记录快照徽章展示 -->
          <div class="flex flex-wrap items-center gap-2 pt-1 text-xs">
            <Badge :variant="lastSavedRecord.enabled ? 'success' : 'secondary'">
              {{ lastSavedRecord.enabled ? '监控已启用' : '监控已关闭' }}
            </Badge>
            <Badge variant="outline" class="font-mono bg-background text-foreground border-border">
              转速阈值: {{ lastSavedRecord.max_motor_speed_rpm }} RPM
            </Badge>
            <Badge variant="outline" class="font-mono bg-background text-foreground border-border">
              扭矩阈值: {{ lastSavedRecord.max_motor_torque_nm }} Nm
            </Badge>
            <Badge variant="outline" class="font-mono bg-background text-foreground border-border">
              温度阈值: {{ lastSavedRecord.max_motor_temp_c }} ℃
            </Badge>
          </div>
        </AlertDescription>
      </div>
    </Alert>

    <!-- 配置保存与审计记录表格 -->
    <Card>
      <CardHeader class="border-b pb-3 bg-muted/20">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <CardTitle class="text-base font-semibold flex items-center gap-2">
              <HistoryIcon class="size-4 text-primary" />
              配置保存与审计记录
            </CardTitle>
            <CardDescription class="mt-0.5">
              记录上位机安全保护阈值的历史下发时间戳及参数快照。
            </CardDescription>
          </div>
          <div v-if="savedHistory.length > 0" class="flex items-center gap-2">
            <Badge variant="secondary" class="font-mono text-xs">
              共 {{ savedHistory.length }} 条记录 (上限 {{ MAX_HISTORY_RECORDS }} 条)
            </Badge>
            <Button
              variant="outline"
              size="sm"
              class="h-7 px-2 text-xs text-muted-foreground hover:text-destructive"
              @click="clearSavedHistory"
            >
              <Trash2Icon data-icon="inline-start" />
              清空记录
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent class="p-0">
        <div v-if="savedHistory.length > 0" class="max-h-[520px] overflow-auto">
          <Table>
            <TableHeader class="bg-muted/95 sticky top-0 z-10 backdrop-blur-xs">
              <TableRow>
                <TableHead class="w-12 text-center">序号</TableHead>
                <TableHead class="min-w-44">保存时间戳</TableHead>
                <TableHead class="min-w-28">安全监控状态</TableHead>
                <TableHead class="min-w-32">绝对转速 (RPM)</TableHead>
                <TableHead class="min-w-32">绝对转矩 (Nm)</TableHead>
                <TableHead class="min-w-32">最高温度 (℃)</TableHead>
                <TableHead class="text-right pr-4">生效状态</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow
                v-for="(item, index) in savedHistory"
                :key="item.id"
                :class="index === 0 ? 'bg-muted/20 font-medium' : undefined"
              >
                <TableCell class="text-center font-mono text-xs text-muted-foreground">
                  {{ index + 1 }}
                </TableCell>
                <TableCell class="font-mono text-xs">
                  <div class="flex items-center gap-1.5">
                    <span>{{ item.timestamp }}</span>
                    <Badge
                      v-if="index === 0"
                      variant="success"
                      class="text-[10px] px-1 py-0 h-4"
                    >
                      最新生效
                    </Badge>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge
                    :variant="item.enabled ? 'success' : 'secondary'"
                    class="text-xs"
                  >
                    {{ item.enabled ? '已启用' : '已关闭' }}
                  </Badge>
                </TableCell>
                <TableCell class="font-mono text-xs">
                  {{ item.max_motor_speed_rpm }} RPM
                </TableCell>
                <TableCell class="font-mono text-xs">
                  {{ item.max_motor_torque_nm }} Nm
                </TableCell>
                <TableCell class="font-mono text-xs">
                  {{ item.max_motor_temp_c }} ℃
                </TableCell>
                <TableCell class="text-right pr-4 text-xs">
                  <span class="text-success font-semibold inline-flex items-center gap-1">
                    <CheckCircle2Icon class="size-3.5" />
                    已成功生效
                  </span>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>

        <div
          v-else
          class="py-8 text-center text-xs text-muted-foreground"
        >
          暂无本地保存记录。在上方表单修改参数并点击“保存配置”后将在此详细记录。
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
