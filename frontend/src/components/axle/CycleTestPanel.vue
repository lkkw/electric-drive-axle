<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  CircleCheckIcon,
  CircleXIcon,
  ClockIcon,
  PauseIcon,
  PlayIcon,
  PlusIcon,
  RotateCcwIcon,
  SquareIcon,
  Trash2Icon,
} from '@lucide/vue'

import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, FieldLabel } from '@/components/ui/field'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from '@/components/ui/input-group'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  type CycleStep,
  type useCycleTest,
} from '@/composables/useCycleTest'
import { Spinner } from '@/components/ui/spinner'
import { cn } from '@/lib/utils'
import { useAxleStore } from '@/stores/useAxleStore'

interface Props {
  cycle: ReturnType<typeof useCycleTest>
}

const props = defineProps<Props>()

const axleStore = useAxleStore()
const cycle = props.cycle

function formatDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

function handleGearChange(step: CycleStep, newGear: unknown) {
  const gear = Number(newGear)
  if (gear !== 1 && gear !== 2 && gear !== 3) return
  step.gear = gear
  if (gear === 3) {
    // 空挡缓冲，转速强制为 0
    step.targetSpeed = 0
  } else if ((gear === 1 || gear === 2) && step.targetSpeed <= 0) {
    // D挡正转与R挡反转均给正转速，反转方向由 R 挡请求控制
    step.targetSpeed = Math.abs(step.targetSpeed) || 1000
  }
}

const statusBadgeVariant = computed(() => {
  switch (cycle.status.value) {
    case 'running':
      return 'success'
    case 'paused':
      return 'warning'
    case 'completed':
      return 'success'
    case 'stopped':
      return 'destructive'
    case 'error':
      return 'destructive'
    default:
      return 'secondary'
  }
})

const statusText = computed(() => {
  switch (cycle.status.value) {
    case 'running':
      return '正在执行工况'
    case 'paused':
      return '测试已暂停'
    case 'completed':
      return '工况全部完成'
    case 'stopped':
      return '测试已终止'
    case 'error':
      return '测试异常终止'
    default:
      return '待命就绪'
  }
})

/**
 * 步骤序列的表头与每一行共用同一套列宽：序号 · 名称 · 挡位 · 目标转速 · 时长 · 删除。
 * 名称、挡位、转速、时长按比例分配剩余宽度（转速含 RPM 后缀稍宽，时长最短），并各有最小宽度。
 */
const STEP_GRID =
  'grid grid-cols-[1.25rem_minmax(4.5rem,1fr)_minmax(5.5rem,1fr)_minmax(6.5rem,1.2fr)_minmax(4.5rem,0.8fr)_1.75rem] items-center gap-1.5'

const GEAR_LABEL: Record<CycleStep['gear'], string> = {
  1: 'D 挡正转',
  2: 'R 挡反转',
  3: 'N 挡缓冲',
}

/** 反转在配置里填正值（方向由 R 挡决定），显示时带负号，与实际转向一致 */
const signedTargetSpeed = computed(() => {
  const step = cycle.currentStep.value
  if (!step) return 0
  return step.gear === 2 ? -step.targetSpeed : step.targetSpeed
})

const actualSpeed = computed(() => Math.round(axleStore.telemetry.mcu_2.mcu_act_motor_spd))

/** 运行期间以后端计划总时长为准，空闲时按当前配置估算 */
const plannedTotalSeconds = computed(() =>
  cycle.status.value === 'idle'
    ? cycle.singleLoopTotalDuration.value * cycle.totalLoops.value
    : axleStore.telemetry.cycle_test.planned_total_seconds,
)
const remainingTotalSeconds = computed(() =>
  Math.max(0, plannedTotalSeconds.value - cycle.totalElapsedSeconds.value),
)

/**
 * 运行中把高亮的当前步骤滚到步骤列表可视区内。
 * 只滚动列表自身的视口（不用 scrollIntoView，避免带动整页滚动）；已在可视区内则不动。
 */
const stepListEl = ref<HTMLElement | null>(null)

function scrollCurrentStepIntoView() {
  const list = stepListEl.value
  const viewport = list?.closest<HTMLElement>('[data-slot="scroll-area-viewport"]')
  const row = list?.querySelector<HTMLElement>(`[data-step-index="${cycle.currentStepIndex.value}"]`)
  if (!viewport || !row) return
  const viewportRect = viewport.getBoundingClientRect()
  const rowRect = row.getBoundingClientRect()
  if (rowRect.top >= viewportRect.top && rowRect.bottom <= viewportRect.bottom) return
  const offset = rowRect.top - viewportRect.top - (viewportRect.height - rowRect.height) / 2
  viewport.scrollBy({ top: offset, behavior: 'smooth' })
}

watch(
  [cycle.currentStepIndex, cycle.isRunning],
  ([, running]) => {
    if (running) void nextTick(scrollCurrentStepIntoView)
  },
  { immediate: true },
)

function handleResetToDefault() {
  cycle.resetToDefault()
}

const cycleTest = computed(() => axleStore.telemetry.cycle_test)

/**
 * 自动判定结论只保留在面板上（循环结束时操作员多半不在屏幕前，不再弹出会自动消失的提示）。
 * 后端消息以判定备注开头（“自动判定 NG：…”，试车记录里需要这个前缀），标题已写明结论，此处去掉重复前缀。
 */
const autoJudgeDetail = computed(() =>
  (cycleTest.value.auto_judge_message ?? '').replace(/^自动判定\s*(?:NG|合格)：/, ''),
)
</script>

<template>
  <div class="flex flex-col gap-4 flex-1">
    <!-- 圈数与时长：单行排布（圈数输入 · 单圈 / 总计时长 · 恢复默认） -->
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
      <Field
        orientation="horizontal"
        class="w-auto gap-2"
        :data-disabled="cycle.isRunning.value || cycle.isPaused.value || undefined"
      >
        <FieldLabel for="cycle-total-loops" class="shrink-0">循环圈数</FieldLabel>
        <InputGroup class="h-8 w-24">
          <InputGroupInput
            id="cycle-total-loops"
            v-model.number="cycle.totalLoops.value"
            type="number"
            min="1"
            max="999"
            class="font-mono"
            :disabled="cycle.isRunning.value || cycle.isPaused.value"
          />
          <InputGroupAddon align="inline-end">
            <InputGroupText>圈</InputGroupText>
          </InputGroupAddon>
        </InputGroup>
      </Field>

      <span class="text-xs text-muted-foreground">
        单圈
        <span class="font-mono font-semibold text-foreground">{{ formatDuration(cycle.singleLoopTotalDuration.value) }}</span>
        · 总计
        <span class="font-mono font-semibold text-foreground">
          {{ formatDuration(cycle.singleLoopTotalDuration.value * cycle.totalLoops.value) }}
        </span>
      </span>

      <Button
        v-if="cycle.isIdle.value"
        size="sm"
        variant="ghost"
        class="ml-auto text-muted-foreground"
        title="恢复初始的正反转标准步骤"
        @click="handleResetToDefault"
      >
        <RotateCcwIcon data-icon="inline-start" />
        <span>恢复默认</span>
      </Button>
    </div>

    <!-- 运行状态：当前工况三项大读数 + 本步进度 + 总进度 -->
    <section
      v-if="!cycle.isIdle.value || cycle.status.value === 'completed'"
      class="flex flex-col gap-3 rounded-xl border bg-card p-4"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <Badge :variant="statusBadgeVariant">{{ statusText }}</Badge>
          <span class="text-xs text-muted-foreground">
            第 {{ cycle.currentLoop.value }}/{{ cycle.executionTotalLoops.value }} 圈 ·
            步骤 {{ cycle.currentStepIndex.value + 1 }}/{{ cycle.executionTotalSteps.value }}
          </span>
        </div>
        <div class="flex items-center gap-1 font-mono text-xs text-muted-foreground">
          <ClockIcon class="size-3.5" />
          <span>
            {{ formatDuration(cycle.totalElapsedSeconds.value) }} / {{ formatDuration(plannedTotalSeconds) }}
          </span>
        </div>
      </div>

      <div v-if="cycle.currentStep.value" class="grid grid-cols-3 divide-x rounded-lg border bg-muted/30">
        <div class="flex min-w-0 flex-col gap-1 p-3">
          <span class="text-xs text-muted-foreground">当前工况</span>
          <span class="truncate text-base font-semibold text-foreground">{{ cycle.currentStep.value.name }}</span>
          <Badge variant="outline" class="w-fit">{{ GEAR_LABEL[cycle.currentStep.value.gear] }}</Badge>
        </div>
        <div class="flex min-w-0 flex-col gap-1 p-3">
          <span class="text-xs text-muted-foreground">目标转速</span>
          <span class="font-mono text-2xl font-semibold tabular-nums text-foreground">
            {{ signedTargetSpeed }}<span class="ml-1 text-xs font-normal text-muted-foreground">RPM</span>
          </span>
          <span class="font-mono text-xs text-muted-foreground tabular-nums">实际 {{ actualSpeed }}</span>
        </div>
        <div class="flex min-w-0 flex-col gap-1 p-3">
          <span class="text-xs text-muted-foreground">本步剩余</span>
          <span class="font-mono text-2xl font-semibold tabular-nums text-foreground">
            {{ cycle.stepRemainingSeconds.value }}<span class="ml-1 text-xs font-normal text-muted-foreground">s</span>
          </span>
          <span class="font-mono text-xs text-muted-foreground tabular-nums">
            共 {{ cycle.currentStep.value.durationSeconds }} s
          </span>
        </div>
      </div>

      <Progress :model-value="cycle.stepProgressPercent.value" class="h-2" />

      <div class="flex flex-col gap-1.5">
        <div class="flex items-center justify-between text-xs text-muted-foreground">
          <span>总进度 {{ cycle.overallProgressPercent.value }}%</span>
          <span class="font-mono">剩余 {{ formatDuration(remainingTotalSeconds) }}</span>
        </div>
        <Progress :model-value="cycle.overallProgressPercent.value" class="h-1.5 opacity-70" />
      </div>
    </section>

    <Alert
      v-if="axleStore.telemetry.cycle_test.last_error"
      variant="destructive"
    >
      <AlertTitle>循环测试已停止</AlertTitle>
      <AlertDescription>{{ axleStore.telemetry.cycle_test.last_error }}</AlertDescription>
    </Alert>

    <!-- 循环跑完 / 异常中断后的自动判定与下电 -->
    <Alert v-if="cycleTest.auto_judge === 'pending'">
      <Spinner />
      <AlertTitle>正在自动判定并下电</AlertTitle>
      <AlertDescription>等待电机停转后写入判定结果，随后自动请求下电。</AlertDescription>
    </Alert>
    <Alert
      v-else-if="cycleTest.auto_judge === 'done'"
      :variant="cycleTest.auto_judge_result === 1 ? 'default' : 'destructive'"
    >
      <CircleCheckIcon v-if="cycleTest.auto_judge_result === 1" class="text-success" />
      <CircleXIcon v-else />
      <AlertTitle>
        自动判定：{{ cycleTest.auto_judge_result === 1 ? '合格' : cycleTest.auto_judge_result === 2 ? 'NG' : '未完成' }}
      </AlertTitle>
      <AlertDescription>{{ autoJudgeDetail }}</AlertDescription>
    </Alert>

    <!-- 步骤配置序列列表 -->
    <div class="flex min-h-0 flex-1 flex-col gap-2">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold text-muted-foreground">步骤序列</span>
          <span class="text-[11px] text-muted-foreground font-mono">
            (共 {{ cycle.steps.value.length }} 步)
          </span>
        </div>

        <Button
          size="sm"
          variant="outline"
          class="h-6.5 px-2 text-xs font-semibold"
          :disabled="cycle.isRunning.value || cycle.isPaused.value"
          @click="cycle.addStep"
        >
          <PlusIcon data-icon="inline-start" />
          <span>添加步骤</span>
        </Button>
      </div>

      <!-- 列标签表头 (与每一步单行输入严格对齐) -->
      <div :class="cn(STEP_GRID, 'px-2 text-[11px] font-semibold text-muted-foreground select-none')">
        <span aria-hidden="true"></span>
        <span>步骤名称</span>
        <span>挡位</span>
        <span>目标转速</span>
        <span>时长</span>
        <span aria-hidden="true"></span>
      </div>

      <!-- 步骤单行滚动容器 -->
      <!-- 步骤列表填满左侧剩余高度（与右侧卡片等高时多出的空间用来多显示几步），最少 185 px；basis-0 使它不反过来撑高页面 -->
      <ScrollArea class="min-h-[185px] flex-1 basis-0 pr-2 rounded-lg border border-border/60 bg-muted/10 p-1.5">
        <div ref="stepListEl" class="flex flex-col gap-1.5">
          <div
            v-for="(step, index) in cycle.steps.value"
            :key="step.id"
            :data-step-index="index"
            :class="cn(
              STEP_GRID,
              'px-2 py-1.5 rounded-lg border transition-all',
              cycle.isRunning.value && cycle.currentStepIndex.value === index
                ? 'border-primary bg-primary/5 ring-1 ring-primary/40'
                : 'border-border/60 bg-background/80 hover:border-border',
            )"
          >
            <!-- 序号 -->
            <Badge
              :variant="cycle.isRunning.value && cycle.currentStepIndex.value === index ? 'default' : 'outline'"
              class="size-5 shrink-0 p-0 flex items-center justify-center font-mono text-[11px]"
            >
              {{ index + 1 }}
            </Badge>

            <!-- 步骤名称 -->
            <Input
              v-model="step.name"
              placeholder="名称"
              class="h-7 w-full min-w-0 px-2 text-xs"
              :disabled="cycle.isRunning.value || cycle.isPaused.value"
            />

            <!-- 挡位选择 -->
            <Select
              :model-value="String(step.gear)"
              :disabled="cycle.isRunning.value || cycle.isPaused.value"
              @update:model-value="(val) => handleGearChange(step, val)"
            >
              <SelectTrigger class="h-7 w-full min-w-0 px-2 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper" side="bottom" align="end">
                <SelectGroup>
                  <SelectItem value="1" class="text-xs">D 挡正转</SelectItem>
                  <SelectItem value="2" class="text-xs">R 挡反转</SelectItem>
                  <SelectItem value="3" class="text-xs">N 挡缓冲</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>

            <!-- 目标转速 -->
            <InputGroup class="h-7 min-w-0">
              <InputGroupInput
                v-model.number="step.targetSpeed"
                type="number"
                step="50"
                min="0"
                max="12000"
                :disabled="cycle.isRunning.value || cycle.isPaused.value || step.gear === 3"
              />
              <InputGroupAddon align="inline-end">
                <InputGroupText>RPM</InputGroupText>
              </InputGroupAddon>
            </InputGroup>

            <!-- 持续时间 -->
            <InputGroup class="h-7 min-w-0">
              <InputGroupInput
                v-model.number="step.durationSeconds"
                type="number"
                min="1"
                max="3600"
                :disabled="cycle.isRunning.value || cycle.isPaused.value"
              />
              <InputGroupAddon align="inline-end">
                <InputGroupText>s</InputGroupText>
              </InputGroupAddon>
            </InputGroup>

            <!-- 删除按钮 -->
            <Button
              size="icon"
              variant="ghost"
              class="size-7 shrink-0 text-muted-foreground hover:text-destructive"
              :disabled="cycle.isRunning.value || cycle.isPaused.value || cycle.steps.value.length <= 1"
              title="删除该步骤"
              @click="cycle.removeStep(index)"
            >
              <Trash2Icon data-icon="inline-start" />
            </Button>
          </div>
        </div>
      </ScrollArea>
    </div>

    <!-- 底部操作按钮区域 -->
    <div class="flex items-center gap-3 pt-1">
      <!-- 待命 / 终止 / 完成 状态下：开始测试与重置 -->
      <template v-if="cycle.isIdle.value">
        <Button
          size="sm"
          variant="default"
          class="h-10 w-full"
          :disabled="!axleStore.isConnected || axleStore.cycleLoading || axleStore.isEmergencyLocked || cycle.isAutoJudging.value"
          @click="cycle.startTest"
        >
          <Spinner v-if="axleStore.cycleLoading || cycle.isAutoJudging.value" data-icon="inline-start" />
          <PlayIcon v-else data-icon="inline-start" />
          <span>{{ axleStore.cycleLoading ? '正在启动' : '开始自动试车' }}</span>
        </Button>
      </template>

      <!-- 运行中状态下：暂停与安全终止 -->
      <template v-else-if="cycle.isRunning.value">
        <Button
          size="sm"
          variant="warning"
          class="h-10 flex-1"
          :disabled="axleStore.cycleLoading"
          @click="cycle.pauseTest"
        >
          <PauseIcon data-icon="inline-start" />
          <span>暂停测试</span>
        </Button>

        <Button
          size="sm"
          variant="destructive"
          class="h-10 flex-1"
          :disabled="axleStore.cycleLoading"
          @click="() => cycle.stopTest('操作员手动终止工况测试')"
        >
          <SquareIcon data-icon="inline-start" />
          <span>终止并归零</span>
        </Button>
      </template>

      <!-- 暂停状态下：继续测试与安全终止 -->
      <template v-else-if="cycle.isPaused.value">
        <Button
          size="sm"
          variant="default"
          class="h-10 flex-1"
          :disabled="axleStore.cycleLoading"
          @click="cycle.resumeTest"
        >
          <PlayIcon data-icon="inline-start" />
          <span>继续测试</span>
        </Button>

        <Button
          size="sm"
          variant="destructive"
          class="h-10 flex-1"
          :disabled="axleStore.cycleLoading"
          @click="() => cycle.stopTest('操作员手动终止工况测试')"
        >
          <SquareIcon data-icon="inline-start" />
          <span>终止并归零</span>
        </Button>
      </template>
    </div>
  </div>
</template>
