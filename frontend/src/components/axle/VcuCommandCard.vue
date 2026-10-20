<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import {
  AlertOctagonIcon,
  LockIcon,
  RepeatIcon,
  RotateCcwIcon,
  SendIcon,
  SlidersHorizontalIcon,
  SquareIcon,
  TriangleAlertIcon,
} from "@lucide/vue";
import { toast } from "vue-sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from "@/components/ui/input-group";
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
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import CycleTestPanel from "@/components/axle/CycleTestPanel.vue";
import { cycleControlLock } from "@/components/axle/controlLock";
import { useCycleTest } from "@/composables/useCycleTest";
import { useAxleStore } from "@/stores/useAxleStore";
import {
  GEAR_MAP,
  WORK_MODE_MAP,
  type VcuCommandState,
} from "@/types/axle";

const axleStore = useAxleStore();
const cycleTest = useCycleTest();
const activeTab = ref("manual");
/** 循环测试运行、暂停或自动判定 / 下电期间，手动控制整体锁定 */
const cycleLock = computed(() => cycleControlLock(axleStore.telemetry.cycle_test));
const isManualLocked = computed(() => cycleLock.value.locked);
/** 急停互锁：后端已置位，会拒绝使能与所有非零控制量，必须显式复位 */
const isEmergencyLocked = computed(() => axleStore.isEmergencyLocked);
/** 手动控制整体受阻：循环测试持有控制权，或急停互锁尚未解除 */
const isCommandBlocked = computed(
  () => isManualLocked.value || isEmergencyLocked.value,
);
/** 空载台架只使用 D / R / N 三个挡位 */
const SELECTABLE_GEAR_IDS = [1, 2, 3] as const;
const TARGET_INPUT_ID = "motor-target-value";

// 本地控制指令表单
const form = reactive({
  target_value: 0,
  work_mode_req: 3, // 速度模式
  mcu_en_cmd: 0, // 0: 未使能, 1: 使能
  gear_sts: 3, // 3: 空挡 N
});

// 目标值编辑状态：编辑期间不让实时推送覆盖尚未下发的模式和目标值。
const isTargetEditing = ref(false);

// immediate：循环进行中切换页面再回来时组件重新创建，锁定状态没有“变化”，也要直接停在循环测试页签
watch(
  isManualLocked,
  (locked) => {
    if (locked) activeTab.value = "cycle";
  },
  { immediate: true },
);

// 范围极值常量
const TORQUE_MIN = -3000.0;
const TORQUE_MAX = 3000.0;
const SPEED_MIN = -12000;
const SPEED_MAX = 12000;

function notifyCommandError(action: string, error: unknown) {
  toast.error(`${action}失败`, {
    description: error instanceof Error ? error.message : "请稍后重试",
    duration: 4000,
  });
}

const isTorqueMode = computed(() => form.work_mode_req === 1);
/** 后端当前工作模式：急停或循环测试结束后会被统一归零为 0 (关闭) */
const backendWorkMode = computed(
  () => axleStore.telemetry.command.work_mode_req,
);
const backendWorkModeLabel = computed(
  () => WORK_MODE_MAP[backendWorkMode.value] ?? "未知",
);
/** 后端模式是否属于手动可选模式；归零后需提示操作员重新选择再下发 */
const isBackendWorkModeSelectable = computed(
  () => backendWorkMode.value === 1 || backendWorkMode.value === 3,
);
const targetConfig = computed(() =>
  isTorqueMode.value
    ? {
        label: "目标扭矩",
        unit: "Nm",
        min: TORQUE_MIN,
        max: TORQUE_MAX,
        step: 0.1,
        placeholder: "输入目标扭矩",
        actionLabel: "下发扭矩",
      }
    : {
        label: "目标速度",
        unit: "RPM",
        min: SPEED_MIN,
        max: SPEED_MAX,
        step: 1,
        placeholder: "输入目标速度",
        actionLabel: "下发速度",
      },
);

/** 输入框被清空（v-model.number 此时给出空字符串）：属于“还没输完”，不算错误 */
const isTargetEmpty = computed(() => String(form.target_value ?? "").trim() === "");

/** 已输入但不合法时的提示；空值或合法时为空字符串 */
const targetErrorMessage = computed(() => {
  if (isTargetEmpty.value) return "";
  const target = Number(form.target_value);
  const { label, min, max, unit } = targetConfig.value;
  if (!Number.isFinite(target) || target < min || target > max) {
    return `请输入 ${min} ~ ${max} ${unit} 之间的值`;
  }
  if (!isTorqueMode.value && !Number.isInteger(target)) {
    return `${label}须为整数`;
  }
  return "";
});

/** 空值或不合法都不能下发；只有后者才显示红色错误 */
const isTargetInvalid = computed(
  () => isTargetEmpty.value || targetErrorMessage.value !== "",
);

function syncTargetFromCommand(command: VcuCommandState) {
  form.work_mode_req = command.work_mode_req === 1 ? 1 : 3;
  form.target_value =
    form.work_mode_req === 1 ? command.torque_req : command.speed_req;
}

/**
 * 目标值输入框的编辑保护。
 *
 * SSE 每 50 ms 推送一次，未编辑时会把后端当前目标写回输入框。若只在获得焦点时标记
 * 编辑，回车下发等操作把标记清掉后光标仍留在框内，此时按删除键会被立即写回原值。
 * 因此每次实际输入都重新标记编辑；离开输入框时，若值与后端一致才恢复同步，
 * 改了但未下发的值保持不动。
 */
function markTargetEditing() {
  isTargetEditing.value = true;
}

function handleTargetBlur() {
  const command = axleStore.telemetry.command;
  const applied = isTorqueMode.value ? command.torque_req : command.speed_req;
  if (form.target_value === applied) {
    isTargetEditing.value = false;
  }
}

// 控制状态始终跟随后端；仅在未编辑目标时同步模式和目标值。
watch(
  () => axleStore.telemetry.command,
  (newCmd) => {
    form.mcu_en_cmd = newCmd.mcu_en_cmd;
    form.gear_sts = newCmd.gear_sts;

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
    isCommandBlocked.value ||
    isTargetInvalid.value
  ) {
    return;
  }

  const target = form.target_value;
  const targetIsTorque = isTorqueMode.value;
  const config = targetConfig.value;

  try {
    await axleStore.sendCommand({
      torque_req: targetIsTorque ? target : 0,
      speed_req: targetIsTorque ? 0 : target,
      work_mode_req: form.work_mode_req,
    });

    isTargetEditing.value = false;
    syncTargetFromCommand(axleStore.telemetry.command);
    toast.success(`${config.label}已下发`, {
      description: `${target} ${config.unit}`,
    });
  } catch (error) {
    notifyCommandError(config.actionLabel, error);
  }
}

/** 切换使能状态（带防飞车保护） */
async function handleToggleEnable(enabled?: boolean) {
  if (!axleStore.isConnected || axleStore.loading || isCommandBlocked.value) {
    return;
  }

  const previousEnable = form.mcu_en_cmd;
  const previousTarget = form.target_value;
  const previousEditing = isTargetEditing.value;
  const shouldEnable = enabled ?? form.mcu_en_cmd === 0;

  try {
    if (shouldEnable) {
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
      toast.success("使能指令已下发");
    } else {
      form.mcu_en_cmd = 0;
      await axleStore.sendCommand({ mcu_en_cmd: 0 });
      toast.success("关闭使能指令已下发");
    }
  } catch (error) {
    form.mcu_en_cmd = previousEnable;
    form.target_value = previousTarget;
    isTargetEditing.value = previousEditing;
    notifyCommandError(shouldEnable ? "开启使能" : "关闭使能", error);
  }
}

/** 挡位切换 */
async function handleSetGear(value: unknown) {
  const gear = Number(value);
  if (!SELECTABLE_GEAR_IDS.some((gearId) => gearId === gear)) {
    return;
  }
  if (!axleStore.isConnected || axleStore.loading || isCommandBlocked.value) {
    return;
  }

  const previousGear = form.gear_sts;
  form.gear_sts = gear;

  try {
    await axleStore.sendCommand({ gear_sts: gear });
    toast.success("挡位指令已下发", {
      description: GEAR_MAP[gear] ?? `挡位 ${gear}`,
    });
  } catch (error) {
    form.gear_sts = previousGear;
    notifyCommandError("切换挡位", error);
  }
}

/**
 * 切换工作模式：立即下发至下位机。
 * 电控防冲击保护：模式切换时强制将目标扭矩与目标速度归零同步下发，杜绝带载突变飞车或急刹风险。
 */
function handleSetMode(value: unknown) {
  const mode = Number(value);
  if (mode !== 1 && mode !== 3) {
    return;
  }
  if (!axleStore.isConnected || axleStore.loading || isCommandBlocked.value) {
    return;
  }
  // 空载台架切扭矩模式需二次确认；确认前选择框保持原模式
  if (mode === 1 && form.work_mode_req !== 1) {
    isTorqueConfirmOpen.value = true;
    return;
  }
  void applyMode(mode);
}

/** 空载扭矩模式二次确认弹窗 */
const isTorqueConfirmOpen = ref(false);

function handleConfirmTorqueMode() {
  isTorqueConfirmOpen.value = false;
  void applyMode(1);
}

async function applyMode(mode: number) {
  if (!axleStore.isConnected || axleStore.loading || isCommandBlocked.value) {
    return;
  }

  const previousMode = form.work_mode_req;
  const previousTarget = form.target_value;
  const previousEditing = isTargetEditing.value;

  form.work_mode_req = mode;
  form.target_value = 0;
  isTargetEditing.value = false;

  try {
    await axleStore.sendCommand({
      work_mode_req: mode,
      torque_req: 0,
      speed_req: 0,
    });
    syncTargetFromCommand(axleStore.telemetry.command);
    toast.success("工作模式指令已下发", {
      description: WORK_MODE_MAP[mode] ?? `模式 ${mode}`,
    });
  } catch (error) {
    form.work_mode_req = previousMode;
    form.target_value = previousTarget;
    isTargetEditing.value = previousEditing;
    notifyCommandError("切换工作模式", error);
  }
}

// 急停入口位于全局顶部栏；互锁生效时放弃尚未下发的目标值编辑，表单回到后端安全值。
watch(isEmergencyLocked, (locked) => {
  if (locked) {
    isTargetEditing.value = false;
    syncTargetFromCommand(axleStore.telemetry.command);
  }
});

/** 平稳停机流程进行中（后端等待电机减速后自动关闭使能） */
const isSoftStopping = computed(() => axleStore.telemetry.soft_stopping);

/** 平稳停机：目标归零让控制器主动减速，停稳后自动关闭使能并切 N 挡 */
async function handleSoftStop() {
  if (!axleStore.isConnected || axleStore.loading || isCommandBlocked.value) {
    return;
  }
  isTargetEditing.value = false;
  try {
    await axleStore.startSoftStop();
    syncTargetFromCommand(axleStore.telemetry.command);
    toast.info(
      axleStore.telemetry.soft_stopping
        ? "正在减速停机，转速降到 0 后自动关闭使能"
        : "已停机，挡位已切到 N",
    );
  } catch (error) {
    notifyCommandError("停机", error);
  }
}

// 停机流程结束（后端已关闭使能）时提示一次；被新指令接管时使能仍为开启，不提示。
watch(isSoftStopping, (stopping, wasStopping) => {
  if (wasStopping && !stopping && axleStore.telemetry.command.mcu_en_cmd === 0) {
    toast.success("已停机，使能已关闭");
  }
});

/**
 * 解除急停互锁：仅撤销后端封锁，不会重新使能或恢复停机前的控制量。
 * 复位成功后目标值与挡位仍需操作员重新下发。
 */
async function handleEmergencyReset() {
  try {
    await axleStore.resetEmergencyStop();
    syncTargetFromCommand(axleStore.telemetry.command);
    toast.success("急停互锁已解除", {
      description: "请重新选择工作模式与目标值后下发。",
    });
  } catch (error) {
    notifyCommandError("解除急停互锁", error);
  }
}
</script>

<template>
  <Tabs v-model="activeTab" class="h-full flex flex-col">
    <Card class="border-border shadow-xs h-full flex flex-col">
      <CardHeader class="pb-3 border-b bg-muted/20">
        <!-- 标题区域即手动控制 / 循环测试切换：整行等分的分段按钮，台架上便于点选 -->
        <CardTitle class="sr-only">电驱控制</CardTitle>
        <TabsList class="grid h-11 w-full grid-cols-2 gap-1 border border-border/50 bg-muted/60 p-1">
          <TabsTrigger
            value="manual"
            class="h-full gap-2 text-sm font-semibold"
            :disabled="isManualLocked"
          >
            <LockIcon v-if="isManualLocked" class="size-4" />
            <SlidersHorizontalIcon v-else class="size-4" />
            <span>手动控制</span>
          </TabsTrigger>
          <TabsTrigger value="cycle" class="h-full gap-2 text-sm font-semibold">
            <RepeatIcon class="size-4" />
            <span>循环测试</span>
            <Badge v-if="cycleLock.label" :variant="cycleLock.variant">
              {{ cycleLock.label }}
            </Badge>
          </TabsTrigger>
        </TabsList>

        <!-- 急停互锁状态条：互锁未解除前，后端会拒绝使能、非零控制量与循环测试 -->
        <Alert v-if="isEmergencyLocked" variant="destructive" class="mt-3">
          <AlertOctagonIcon />
          <AlertTitle>急停互锁已生效，控制输出已封锁</AlertTitle>
          <AlertDescription class="flex flex-col items-start gap-2">
            <span>
              使能已关闭，目标转矩与转速归零，挡位已挂空挡。互锁解除前无法使能、下发非零控制量或启动循环测试。
            </span>
            <Button
              size="sm"
              variant="outline"
              :disabled="axleStore.loading"
              @click="handleEmergencyReset"
            >
              <Spinner v-if="axleStore.loading" data-icon="inline-start" />
              <RotateCcwIcon v-else data-icon="inline-start" />
              <span>解除急停互锁</span>
            </Button>
          </AlertDescription>
        </Alert>
      </CardHeader>

      <TabsContent
        value="manual"
        :force-mount="true"
        class="data-[state=inactive]:hidden flex-1 flex flex-col m-0"
      >
        <CardContent class="px-4 pb-4 sm:px-5 sm:pb-5 flex-1 flex flex-col gap-4">
      <FieldGroup class="flex flex-col gap-4">
        <!-- MCU 使能：与下方挡位、工作模式统一为“标签在上 + 等高控件框”，整框可点击切换 -->
        <Field
          :data-disabled="
            !axleStore.isConnected || axleStore.loading || isCommandBlocked || undefined
          "
        >
          <FieldLabel for="mcu-enable">MCU 使能</FieldLabel>
          <label
            for="mcu-enable"
            class="flex h-9 w-full cursor-pointer items-center justify-between gap-2 rounded-lg border border-input bg-transparent py-2 pr-2.5 pl-2.5 text-sm transition-colors select-none dark:bg-input/30 has-data-checked:border-success/40 has-data-checked:bg-success/5 has-data-disabled:cursor-not-allowed has-data-disabled:opacity-50"
          >
            <span class="flex items-center gap-2">
              <span
                class="size-2 rounded-full"
                :class="form.mcu_en_cmd === 1 ? 'bg-success' : 'bg-muted-foreground/40'"
              />
              <span :class="form.mcu_en_cmd === 1 ? 'text-success font-medium' : 'text-muted-foreground'">
                {{ form.mcu_en_cmd === 1 ? "已使能" : "未使能" }}
              </span>
            </span>
            <Switch
              id="mcu-enable"
              :model-value="form.mcu_en_cmd === 1"
              :disabled="!axleStore.isConnected || axleStore.loading || isCommandBlocked"
              @update:model-value="handleToggleEnable"
            />
          </label>
        </Field>

        <!-- 挡位选择 -->
        <Field>
          <FieldLabel>挡位选择</FieldLabel>
          <Select
            :model-value="String(form.gear_sts)"
            :disabled="!axleStore.isConnected || axleStore.loading || isCommandBlocked"
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
            <FieldLabel>工作模式</FieldLabel>
            <!-- 仅在急停/循环结束后被归零为“关闭”时提示，正常情况下选择框即为当前模式 -->
            <span v-if="!isBackendWorkModeSelectable" class="text-xs text-warning">
              当前为{{ backendWorkModeLabel }}，需重新选择下发
            </span>
          </div>
          <Select
            :model-value="String(form.work_mode_req)"
            :disabled="!axleStore.isConnected || axleStore.loading || isCommandBlocked"
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
          :data-invalid="Boolean(targetErrorMessage) || undefined"
          :data-disabled="!axleStore.isConnected || isCommandBlocked || undefined"
        >
          <div class="flex items-center justify-between">
            <FieldLabel :for="TARGET_INPUT_ID">
              {{ targetConfig.label }}
            </FieldLabel>
            <span class="text-xs text-muted-foreground font-mono">
              范围: [{{ targetConfig.min }} ~ {{ targetConfig.max }}]
              {{ targetConfig.unit }}
            </span>
          </div>

          <InputGroup class="h-9">
            <InputGroupInput
              :id="TARGET_INPUT_ID"
              v-model.number="form.target_value"
              type="number"
              :step="targetConfig.step"
              :min="targetConfig.min"
              :max="targetConfig.max"
              :placeholder="targetConfig.placeholder"
              class="font-mono [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
              :aria-invalid="Boolean(targetErrorMessage) || undefined"
              :disabled="!axleStore.isConnected || isCommandBlocked"
              @focus="markTargetEditing"
              @input="markTargetEditing"
              @blur="handleTargetBlur"
              @keydown.enter.prevent="handleApplyTarget"
              @wheel.prevent
            />
            <InputGroupAddon align="inline-end">
              <InputGroupText class="font-mono">{{ targetConfig.unit }}</InputGroupText>
            </InputGroupAddon>
          </InputGroup>

          <FieldError v-if="targetErrorMessage">{{ targetErrorMessage }}</FieldError>
        </Field>

        <!-- 下发与平稳停机：停机会让控制器减速到 0，停稳后自动关闭使能，不触发急停互锁 -->
        <div class="grid grid-cols-2 gap-3">
          <Button
            class="h-10"
            :disabled="
              isTargetInvalid || axleStore.loading || !axleStore.isConnected || isCommandBlocked
            "
            @click="handleApplyTarget"
          >
            <SendIcon data-icon="inline-start" />
            <span>{{ targetConfig.actionLabel }}</span>
          </Button>
          <Button
            variant="outline"
            class="h-10"
            :disabled="
              isSoftStopping || axleStore.loading || !axleStore.isConnected || isCommandBlocked
            "
            @click="handleSoftStop"
          >
            <Spinner v-if="isSoftStopping" data-icon="inline-start" />
            <SquareIcon v-else data-icon="inline-start" />
            <span>{{ isSoftStopping ? "减速停机中…" : "停机" }}</span>
          </Button>
        </div>
      </FieldGroup>
        </CardContent>
      </TabsContent>

      <TabsContent
        value="cycle"
        :force-mount="true"
        class="data-[state=inactive]:hidden flex-1 flex flex-col m-0"
      >
        <CardContent class="px-4 pb-4 sm:px-5 sm:pb-5 flex-1 flex flex-col">
          <CycleTestPanel :cycle="cycleTest" />
        </CardContent>
      </TabsContent>
    </Card>

    <!-- 空载台架切换扭矩模式的二次确认 -->
    <Dialog v-model:open="isTorqueConfirmOpen">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2">
            <TriangleAlertIcon class="size-5 text-warning" />
            确认切换到扭矩模式？
          </DialogTitle>
          <DialogDescription>
            当前为空载测试，电机无负载，扭矩模式下较小的目标扭矩也可能使转速快速升高。确定要选择扭矩模式吗？
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose as-child>
            <Button variant="outline">取消</Button>
          </DialogClose>
          <Button @click="handleConfirmTorqueMode">确定切换</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </Tabs>
</template>
