<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  AlertOctagonIcon,
  SendIcon,
} from '@lucide/vue'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useAxleStore } from '@/stores/useAxleStore'
import { GEAR_MAP, WORK_MODE_MAP } from '@/types/axle'

const axleStore = useAxleStore()

// 本地控制指令表单
const form = reactive({
  torque_req: 0.0,
  speed_req: 0,
  work_mode_req: 1, // 转矩模式
  mcu_en_cmd: 0, // 0: 未使能, 1: 使能
  gear_sts: 3, // 3: 空挡 N
  active_discharge: 0,
})

// 用户编辑状态跟踪
const isUserEditing = ref(false)

// 范围极值常量
const TORQUE_MIN = -3000.0
const TORQUE_MAX = 3000.0
const SPEED_MIN = -12000
const SPEED_MAX = 12000

// 校验转矩与转速输入范围
const isTorqueInvalid = computed(() => {
  return (
    Number.isNaN(form.torque_req) ||
    form.torque_req < TORQUE_MIN ||
    form.torque_req > TORQUE_MAX
  )
})

const isSpeedInvalid = computed(() => {
  return (
    Number.isNaN(form.speed_req) ||
    form.speed_req < SPEED_MIN ||
    form.speed_req > SPEED_MAX
  )
})

// 当后端推送新的命令状态时同步表单初值（若用户未处于编辑状态）
watch(
  () => axleStore.telemetry.command,
  (newCmd) => {
    if (!isUserEditing.value) {
      form.torque_req = newCmd.torque_req
      form.speed_req = newCmd.speed_req
      form.work_mode_req = newCmd.work_mode_req
      form.mcu_en_cmd = newCmd.mcu_en_cmd
      form.gear_sts = newCmd.gear_sts
      form.active_discharge = newCmd.active_discharge
    }
  },
  { immediate: true },
)



/** 下发控制指令至后端 */
async function handleApplyCommand() {
  isUserEditing.value = false
  await axleStore.sendCommand({
    torque_req: Number.isNaN(form.torque_req) ? 0 : form.torque_req,
    speed_req: Number.isNaN(form.speed_req) ? 0 : form.speed_req,
    work_mode_req: form.work_mode_req,
    mcu_en_cmd: form.mcu_en_cmd,
    gear_sts: form.gear_sts,
    active_discharge: form.active_discharge,
  })
}

/** 切换使能状态（带防飞车保护） */
async function handleToggleEnable() {
  if (form.mcu_en_cmd === 0) {
    // 安全使能保护：从未使能切换到使能时强制归零转矩与转速，防止上电电机飞车冲击
    form.mcu_en_cmd = 1
    form.torque_req = 0.0
    form.speed_req = 0
  } else {
    form.mcu_en_cmd = 0
  }
  await handleApplyCommand()
}

/** 挡位切换 */
async function handleSetGear(gear: number) {
  form.gear_sts = gear
  await handleApplyCommand()
}

/** 工作模式切换 */
async function handleSetMode(mode: number) {
  form.work_mode_req = mode
  await handleApplyCommand()
}

/** 一键紧急停机 */
async function handleEmergencyStop() {
  isUserEditing.value = false
  form.mcu_en_cmd = 0
  form.torque_req = 0.0
  form.speed_req = 0
  form.gear_sts = 3 // N
  form.active_discharge = 0
  await axleStore.triggerEmergencyStop()
}
</script>

<template>
  <Card class="border-border shadow-xs h-full flex flex-col">
    <CardHeader class="pb-3 border-b bg-muted/20">
      <div class="flex items-center justify-between">
        <div>
          <CardTitle class="text-base font-semibold">
            电驱控制
          </CardTitle>
        </div>
      </div>
    </CardHeader>

    <CardContent class="p-4 sm:p-5 flex-1 flex flex-col justify-between gap-4">
      <!-- 使能与主动放电控制行 -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 p-4 bg-muted/25 rounded-xl border border-border/60">
        <!-- MCU 使能控制 -->
        <div class="flex items-center justify-between gap-3">
          <div class="flex flex-col gap-1">
            <div class="text-xs font-semibold text-muted-foreground">
              驱动使能
            </div>
            <div class="text-sm font-bold flex items-center gap-2">
              <span
                class="size-2.5 rounded-full shrink-0 transition-colors"
                :class="cn(
                  form.mcu_en_cmd === 1
                    ? 'bg-success shadow-xs shadow-success/50 animate-pulse'
                    : 'bg-muted-foreground/50',
                )"
              />
              <span :class="cn(form.mcu_en_cmd === 1 ? 'text-success' : 'text-foreground')">
                {{ form.mcu_en_cmd === 1 ? '已使能' : '未使能' }}
              </span>
            </div>
          </div>
          <Button
            size="sm"
            :variant="form.mcu_en_cmd === 1 ? 'success' : 'outline'"
            class="h-9 min-w-[92px] px-4 font-semibold transition-all"
            :disabled="!axleStore.isConnected"
            @click="handleToggleEnable"
          >
            {{ form.mcu_en_cmd === 1 ? '关闭使能' : '开启使能' }}
          </Button>
        </div>

        <!-- 主动放电控制 -->
        <div class="flex items-center justify-between gap-3 sm:border-l sm:pl-4 border-border/60">
          <div class="flex flex-col gap-1">
            <div class="text-xs font-semibold text-muted-foreground">
              母线放电
            </div>
            <div class="text-sm font-bold flex items-center gap-2">
              <span
                class="size-2.5 rounded-full shrink-0 transition-colors"
                :class="cn(
                  form.active_discharge === 1
                    ? 'bg-warning shadow-xs shadow-warning/50 animate-pulse'
                    : 'bg-success',
                )"
              />
              <span :class="cn(form.active_discharge === 1 ? 'text-warning' : 'text-foreground')">
                {{ form.active_discharge === 1 ? '放电中' : '正常' }}
              </span>
            </div>
          </div>
          <Button
            size="sm"
            :variant="form.active_discharge === 1 ? 'warning' : 'outline'"
            class="h-9 min-w-[92px] px-4 font-semibold transition-all"
            :disabled="!axleStore.isConnected"
            @click="form.active_discharge = form.active_discharge === 1 ? 0 : 1; handleApplyCommand()"
          >
            {{ form.active_discharge === 1 ? '停止放电' : '触发放电' }}
          </Button>
        </div>
      </div>

      <!-- 挡位选择 -->
      <div class="flex flex-col gap-2">
        <div class="flex items-center justify-between">
          <label class="text-xs font-semibold text-muted-foreground">
            挡位选择
          </label>
          <span class="text-xs font-mono text-info font-semibold">
            当前: {{ GEAR_MAP[form.gear_sts] ?? '未知' }}
          </span>
        </div>
        <div class="grid grid-cols-5 gap-2">
          <Button
            v-for="(label, gearKey) in GEAR_MAP"
            :key="gearKey"
            size="sm"
            class="h-9 font-semibold transition-all"
            :variant="form.gear_sts === Number(gearKey) ? 'default' : 'outline'"
            @click="handleSetGear(Number(gearKey))"
          >
            <span class="font-mono text-sm font-bold">{{ label.split(' ')[0] }}</span>
            <span
              class="text-xs ml-1 transition-colors"
              :class="cn(
                form.gear_sts === Number(gearKey)
                  ? 'text-primary-foreground font-medium opacity-100'
                  : 'text-muted-foreground font-normal opacity-75',
              )"
            >
              {{ label.split(' ')[1] }}
            </span>
          </Button>
        </div>
      </div>

      <!-- 控制工作模式 -->
      <div class="flex flex-col gap-2">
        <div class="flex items-center justify-between">
          <label class="text-xs font-semibold text-muted-foreground">
            工作模式
          </label>
          <span class="text-xs font-mono text-info font-semibold">
            当前: {{ WORK_MODE_MAP[form.work_mode_req] ?? '未知模式' }}
          </span>
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Button
            v-for="modeId in [1, 3, 2, 0]"
            :key="modeId"
            size="sm"
            class="h-9 font-semibold transition-all"
            :variant="form.work_mode_req === modeId ? 'default' : 'outline'"
            @click="handleSetMode(modeId)"
          >
            <span class="text-xs font-semibold">{{ WORK_MODE_MAP[modeId] }}</span>
          </Button>
        </div>
      </div>

      <!-- 目标转矩设定输入框 -->
      <div
        class="flex flex-col gap-3 p-4 rounded-xl border transition-colors"
        :class="cn(
          isTorqueInvalid
            ? 'border-destructive/40 bg-destructive/5'
            : 'border-border/80 bg-muted/20',
        )"
      >
        <div class="flex items-center justify-between">
          <label class="text-sm font-semibold text-foreground">
            目标转矩
          </label>
          <span class="text-xs text-muted-foreground font-mono">
            范围: [{{ TORQUE_MIN }} ~ {{ TORQUE_MAX }}] Nm
          </span>
        </div>

        <div class="flex items-center gap-3">
          <!-- 高精度数字输入框 -->
          <div class="relative flex-1">
            <Input
              v-model.number="form.torque_req"
              type="number"
              step="0.1"
              :min="TORQUE_MIN"
              :max="TORQUE_MAX"
              placeholder="0.0"
              class="h-11 w-full px-3 pr-12 text-center text-lg font-mono font-bold tracking-tight shadow-2xs transition-all [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-inner-spin-button]:m-0"
              :aria-invalid="isTorqueInvalid || undefined"
              :disabled="!axleStore.isConnected"
              @focus="isUserEditing = true"
              @keydown.enter.prevent="handleApplyCommand"
              @wheel.prevent
            />
            <div class="absolute inset-y-0 right-3 flex items-center pointer-events-none text-xs font-semibold text-muted-foreground font-mono">
              Nm
            </div>
          </div>

          <!-- 快速回车下发提示 -->
          <Button
            size="sm"
            variant="warning"
            class="h-11 shrink-0 px-3.5 font-semibold"
            :disabled="isTorqueInvalid || axleStore.loading"
            @click="handleApplyCommand"
          >
            <SendIcon data-icon="inline-start" />
            下发转矩
          </Button>
        </div>

        <!-- 转矩校验错误提示 -->
        <p v-if="isTorqueInvalid" class="text-xs text-destructive font-medium">
          转矩超出有效量程！请输入 {{ TORQUE_MIN }} 至 {{ TORQUE_MAX }} Nm 之间的数值。
        </p>
      </div>

      <!-- 目标转速设定输入框 -->
      <div
        class="flex flex-col gap-3 p-4 rounded-xl border transition-colors"
        :class="cn(
          isSpeedInvalid
            ? 'border-destructive/40 bg-destructive/5'
            : 'border-border/80 bg-muted/20',
        )"
      >
        <div class="flex items-center justify-between">
          <label class="text-sm font-semibold text-foreground">
            目标转速
          </label>
          <span class="text-xs text-muted-foreground font-mono">
            范围: [{{ SPEED_MIN }} ~ {{ SPEED_MAX }}] RPM
          </span>
        </div>

        <div class="flex items-center gap-3">
          <!-- 高精度数字输入框 -->
          <div class="relative flex-1">
            <Input
              v-model.number="form.speed_req"
              type="number"
              step="50"
              :min="SPEED_MIN"
              :max="SPEED_MAX"
              placeholder="0"
              class="h-11 w-full px-3 pr-14 text-center text-lg font-mono font-bold tracking-tight shadow-2xs transition-all [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-inner-spin-button]:m-0"
              :aria-invalid="isSpeedInvalid || undefined"
              :disabled="!axleStore.isConnected"
              @focus="isUserEditing = true"
              @keydown.enter.prevent="handleApplyCommand"
              @wheel.prevent
            />
            <div class="absolute inset-y-0 right-3 flex items-center pointer-events-none text-xs font-semibold text-muted-foreground font-mono">
              RPM
            </div>
          </div>

          <!-- 快速回车下发提示 -->
          <Button
            size="sm"
            variant="info"
            class="h-11 shrink-0 px-3.5 font-semibold"
            :disabled="isSpeedInvalid || axleStore.loading"
            @click="handleApplyCommand"
          >
            <SendIcon data-icon="inline-start" />
            下发转速
          </Button>
        </div>

        <!-- 转速校验错误提示 -->
        <p v-if="isSpeedInvalid" class="text-xs text-destructive font-medium">
          转速超出有效量程！请输入 {{ SPEED_MIN }} 至 {{ SPEED_MAX }} RPM 之间的数值。
        </p>
      </div>

      <!-- 紧急制动按钮 -->
      <Button
        size="lg"
        variant="destructive"
        class="w-full font-bold tracking-widest gap-2 h-11 text-base mt-2"
        :disabled="!axleStore.isConnected"
        @click="handleEmergencyStop"
      >
        <AlertOctagonIcon data-icon="inline-start" />
        紧急停机
      </Button>

    </CardContent>
  </Card>
</template>

