<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  AlertTriangleIcon,
  SaveIcon,
  ShieldCheckIcon,
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
import { useAxleStore } from '@/stores/useAxleStore'
import type { AxleSafetyConfig } from '@/types/axle'

const axleStore = useAxleStore()

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
    await axleStore.refreshStatus()
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : '保存安全配置失败'
  } finally {
    isSaving.value = false
  }
}

onMounted(async () => {
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
          <SaveIcon data-icon="inline-start" />
          {{ isSaving ? '保存中…' : '保存配置' }}
        </Button>
      </CardFooter>
    </Card>

    <Alert v-if="saveError" variant="destructive">
      <AlertTriangleIcon />
      <AlertTitle>配置未保存</AlertTitle>
      <AlertDescription>{{ saveError }}</AlertDescription>
    </Alert>

    <Alert v-else-if="saved">
      <ShieldCheckIcon />
      <AlertTitle>配置已保存</AlertTitle>
      <AlertDescription>
        {{ config.enabled ? '安全监控已开始等待新鲜 MCU 反馈。' : '安全监控已关闭，不会自动介入控制。' }}
      </AlertDescription>
    </Alert>

    <Alert v-if="lastTrip" variant="destructive">
      <AlertTriangleIcon />
      <AlertTitle>最近一次自动停机</AlertTitle>
      <AlertDescription class="space-y-1">
        <p>{{ lastTrip.message }}</p>
        <p>触发时间：{{ formatTriggeredAt(lastTrip.triggered_at) }}</p>
      </AlertDescription>
    </Alert>
  </div>
</template>
