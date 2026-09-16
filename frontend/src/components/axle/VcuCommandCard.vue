<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { AlertOctagonIcon, SendIcon } from "@lucide/vue";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { useAxleStore } from "@/stores/useAxleStore";
import {
  GEAR_MAP,
  WORK_MODE_MAP,
  type VcuCommandState,
} from "@/types/axle";

const axleStore = useAxleStore();
const SELECTABLE_GEAR_IDS = [1, 2, 3, 4] as const;
const TARGET_INPUT_ID = "motor-target-value";

// 本地控制指令表单
const form = reactive({
  target_value: 0,
  work_mode_req: 3, // 速度模式
  mcu_en_cmd: 0, // 0: 未使能, 1: 使能
  gear_sts: 3, // 3: 空挡 N
  active_discharge: 0,
});

// 目标值编辑状态：编辑期间不让实时推送覆盖尚未下发的模式和目标值。
const isTargetEditing = ref(false);

// 范围极值常量
const TORQUE_MIN = -3000.0;
const TORQUE_MAX = 3000.0;
const SPEED_MIN = -12000;
const SPEED_MAX = 12000;

const isTorqueMode = computed(() => form.work_mode_req === 1);
const targetConfig = computed(() =>
  isTorqueMode.value
    ? {
        label: "目标扭矩",
        unit: "Nm",
        min: TORQUE_MIN,
        max: TORQUE_MAX,
        step: 0.1,
        placeholder: "0.0",
        actionLabel: "下发扭矩",
      }
    : {
        label: "目标速度",
        unit: "RPM",
        min: SPEED_MIN,
        max: SPEED_MAX,
        step: 1,
        placeholder: "0",
        actionLabel: "下发速度",
      },
);

const isTargetInvalid = computed(() => {
  const target = form.target_value;
  return (
    !Number.isFinite(target) ||
    target < targetConfig.value.min ||
    target > targetConfig.value.max ||
    (!isTorqueMode.value && !Number.isInteger(target))
  );
});

function syncTargetFromCommand(command: VcuCommandState) {
  form.work_mode_req = command.work_mode_req === 1 ? 1 : 3;
  form.target_value =
    form.work_mode_req === 1 ? command.torque_req : command.speed_req;
}

// 控制状态始终跟随后端；仅在未编辑目标时同步模式和目标值。
watch(
  () => axleStore.telemetry.command,
  (newCmd) => {
    form.mcu_en_cmd = newCmd.mcu_en_cmd;
    form.gear_sts = newCmd.gear_sts;
    form.active_discharge = newCmd.active_discharge;

    if (!isTargetEditing.value) {
      syncTargetFromCommand(newCmd);
    }
  },
  { immediate: true },
);

/** 下发所选工作模式及对应目标值，非当前模式目标强制归零。 */
async function handleApplyTarget() {
  if (
    !axleStore.isConnected ||
    axleStore.loading ||
    isTargetInvalid.value
  ) {
    return;
  }

  const target = form.target_value;
  await axleStore.sendCommand({
    torque_req: isTorqueMode.value ? target : 0,
    speed_req: isTorqueMode.value ? 0 : target,
    work_mode_req: form.work_mode_req,
  });

  isTargetEditing.value = false;
  syncTargetFromCommand(axleStore.telemetry.command);
}

/** 切换使能状态（带防飞车保护） */
async function handleToggleEnable() {
  if (form.mcu_en_cmd === 0) {
    // 安全使能保护：从未使能切换到使能时强制归零转矩与转速，防止上电电机飞车冲击
    form.mcu_en_cmd = 1;
    form.target_value = 0;
    isTargetEditing.value = false;
    await axleStore.sendCommand({
      mcu_en_cmd: 1,
      torque_req: 0,
      speed_req: 0,
    });
    syncTargetFromCommand(axleStore.telemetry.command);
  } else {
    form.mcu_en_cmd = 0;
    await axleStore.sendCommand({ mcu_en_cmd: 0 });
  }
}

/** 挡位切换 */
async function handleSetGear(value: unknown) {
  const gear = Number(value);
  if (!SELECTABLE_GEAR_IDS.some((gearId) => gearId === gear)) {
    return;
  }
  if (!axleStore.isConnected || axleStore.loading) {
    return;
  }

  form.gear_sts = gear;
  await axleStore.sendCommand({ gear_sts: gear });
}

/**
 * 切换工作模式：立即下发至下位机。
 * 电控防冲击保护：模式切换时强制将目标扭矩与目标速度归零同步下发，杜绝带载突变飞车或急刹风险。
 */
async function handleSetMode(value: unknown) {
  const mode = Number(value);
  if (mode !== 1 && mode !== 3) {
    return;
  }
  if (!axleStore.isConnected || axleStore.loading) {
    return;
  }

  form.work_mode_req = mode;
  form.target_value = 0;
  isTargetEditing.value = false;

  await axleStore.sendCommand({
    work_mode_req: mode,
    torque_req: 0,
    speed_req: 0,
  });
  syncTargetFromCommand(axleStore.telemetry.command);
}

/** 主动放电只提交自身状态，避免顺带下发尚未确认的目标值。 */
async function handleToggleDischarge() {
  form.active_discharge = form.active_discharge === 1 ? 0 : 1;
  await axleStore.sendCommand({
    active_discharge: form.active_discharge,
  });
}

/** 一键紧急停机 */
async function handleEmergencyStop() {
  isTargetEditing.value = false;
  form.mcu_en_cmd = 0;
  form.target_value = 0;
  form.gear_sts = 3; // N
  form.active_discharge = 0;
  await axleStore.triggerEmergencyStop();
  syncTargetFromCommand(axleStore.telemetry.command);
}
</script>

<template>
  <Card class="border-border shadow-xs h-full flex flex-col">
    <CardHeader class="pb-3 border-b bg-muted/20">
      <div
        class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <CardTitle class="text-base font-semibold"> 电驱控制 </CardTitle>
        <Button
          size="sm"
          variant="destructive"
          class="w-full shrink-0 justify-center font-bold tracking-widest sm:w-auto sm:min-w-32"
          :disabled="!axleStore.isConnected"
          @click="handleEmergencyStop"
        >
          <AlertOctagonIcon data-icon="inline-start" />
          紧急停机
        </Button>
      </div>
    </CardHeader>

    <CardContent class="p-4 sm:p-5 flex-1 flex flex-col gap-4">
      <!-- 使能与主动放电操作：实际反馈集中展示在 MCU 实时反馈卡片。 -->
      <div
        class="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 bg-muted/25 rounded-xl border border-border/60"
      >
        <Button
          size="sm"
          :variant="form.mcu_en_cmd === 1 ? 'success' : 'outline'"
          class="h-10 w-full px-4 font-semibold transition-all"
          :disabled="!axleStore.isConnected"
          @click="handleToggleEnable"
        >
          {{ form.mcu_en_cmd === 1 ? "关闭使能" : "开启使能" }}
        </Button>

        <Button
          size="sm"
          :variant="form.active_discharge === 1 ? 'warning' : 'outline'"
          class="h-10 w-full px-4 font-semibold transition-all"
          :disabled="!axleStore.isConnected"
          @click="handleToggleDischarge"
        >
          {{ form.active_discharge === 1 ? "停止放电" : "触发放电" }}
        </Button>
      </div>

      <FieldGroup class="flex flex-col gap-4">
        <!-- 挡位选择 -->
        <Field>
          <div class="flex items-center justify-between">
            <FieldLabel class="text-xs font-semibold text-muted-foreground">
              挡位选择
            </FieldLabel>
            <span class="text-xs font-mono text-info font-semibold">
              当前: {{ GEAR_MAP[form.gear_sts] ?? "未知" }}
            </span>
          </div>
          <Select
            :model-value="String(form.gear_sts)"
            :disabled="!axleStore.isConnected"
            @update:model-value="handleSetGear"
          >
            <SelectTrigger class="h-9 w-full" aria-label="挡位选择">
              <SelectValue placeholder="请选择挡位" />
            </SelectTrigger>
            <SelectContent position="popper" side="bottom" align="start">
              <SelectGroup>
                <SelectItem
                  v-for="gearKey in SELECTABLE_GEAR_IDS"
                  :key="gearKey"
                  :value="String(gearKey)"
                >
                  {{ GEAR_MAP[gearKey] }}
                </SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>

        <!-- 控制工作模式 -->
        <Field>
          <div class="flex items-center justify-between">
            <FieldLabel class="text-xs font-semibold text-muted-foreground">
              工作模式
            </FieldLabel>
            <span class="text-xs font-mono text-info font-semibold">
              当前: {{ WORK_MODE_MAP[axleStore.telemetry.command.work_mode_req] ?? "未知" }}
            </span>
          </div>
          <Select
            :model-value="String(form.work_mode_req)"
            :disabled="!axleStore.isConnected"
            @update:model-value="handleSetMode"
          >
            <SelectTrigger class="h-9 w-full" aria-label="工作模式">
              <SelectValue placeholder="请选择工作模式" />
            </SelectTrigger>
            <SelectContent position="popper" side="bottom" align="start">
              <SelectGroup>
                <SelectItem value="1">
                  {{ WORK_MODE_MAP[1] }}
                </SelectItem>
                <SelectItem value="3">
                  {{ WORK_MODE_MAP[3] }}
                </SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>

        <!-- 根据工作模式展示目标值输入与下发 -->
        <Field
          :data-invalid="isTargetInvalid || undefined"
          :data-disabled="!axleStore.isConnected || undefined"
        >
          <div class="flex items-center justify-between">
            <FieldLabel
              :for="TARGET_INPUT_ID"
              class="text-xs font-semibold text-muted-foreground"
            >
              {{ targetConfig.label }}
            </FieldLabel>
            <span class="text-xs text-muted-foreground font-mono">
              范围: [{{ targetConfig.min }} ~ {{ targetConfig.max }}]
              {{ targetConfig.unit }}
            </span>
          </div>

          <div class="flex items-center gap-3">
            <div class="relative flex-1">
              <Input
                :id="TARGET_INPUT_ID"
                v-model.number="form.target_value"
                type="number"
                :step="targetConfig.step"
                :min="targetConfig.min"
                :max="targetConfig.max"
                :placeholder="targetConfig.placeholder"
                class="h-9 w-full px-3 pr-12 font-mono font-bold tracking-tight [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-inner-spin-button]:m-0"
                :aria-invalid="isTargetInvalid || undefined"
                :disabled="!axleStore.isConnected"
                @focus="isTargetEditing = true"
                @keydown.enter.prevent="handleApplyTarget"
                @wheel.prevent
              />
              <div
                class="absolute inset-y-0 right-3 flex items-center pointer-events-none text-xs font-semibold text-muted-foreground font-mono"
              >
                {{ targetConfig.unit }}
              </div>
            </div>

            <Button
              size="sm"
              variant="default"
              class="h-9 min-w-28 shrink-0 justify-center px-4 font-semibold sm:min-w-36"
              :disabled="
                isTargetInvalid || axleStore.loading || !axleStore.isConnected
              "
              @click="handleApplyTarget"
            >
              <SendIcon data-icon="inline-start" />
              {{ targetConfig.actionLabel }}
            </Button>
          </div>

          <FieldError v-if="isTargetInvalid">
            {{ targetConfig.label }}超出有效量程！请输入
            {{ targetConfig.min }} 至 {{ targetConfig.max }}
            {{ targetConfig.unit }}
            之间的{{ isTorqueMode ? "数值" : "整数" }}。
          </FieldError>
        </Field>
      </FieldGroup>
    </CardContent>
  </Card>
</template>
