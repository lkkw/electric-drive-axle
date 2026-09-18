<script setup lang="ts">
import { computed } from 'vue'
import {
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
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field'
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

function handleResetToDefault() {
  cycle.resetToDefault()
}
</script>

<template>
  <div class="flex flex-col gap-4 flex-1">
    <FieldGroup class="flex-row flex-wrap items-end justify-between gap-3 rounded-xl border bg-muted/25 p-3">
      <Field
        class="w-32"
        :data-disabled="cycle.isRunning.value || cycle.isPaused.value || undefined"
      >
        <FieldLabel for="cycle-total-loops">循环圈数</FieldLabel>
        <InputGroup>
          <InputGroupInput
            id="cycle-total-loops"
            v-model.number="cycle.totalLoops.value"
            type="number"
            min="1"
            max="999"
            :disabled="cycle.isRunning.value || cycle.isPaused.value"
          />
          <InputGroupAddon align="inline-end">
            <InputGroupText>圈</InputGroupText>
          </InputGroupAddon>
        </InputGroup>
      </Field>

      <!-- 单圈与总耗时统计 -->
      <div class="flex items-center gap-3 text-xs text-muted-foreground font-mono">
        <div class="flex items-center gap-1">
          <span>单圈:</span>
          <span class="font-bold text-foreground">{{ cycle.singleLoopTotalDuration.value }}s</span>
        </div>
        <div class="flex items-center gap-1">
          <span>总计:</span>
          <span class="font-bold text-foreground">
            {{ formatDuration(cycle.singleLoopTotalDuration.value * cycle.totalLoops.value) }}
          </span>
        </div>
        <Button
          v-if="cycle.isIdle.value"
          size="sm"
          variant="outline"
          title="恢复初始的正反转标准步骤"
          @click="handleResetToDefault"
        >
          <RotateCcwIcon data-icon="inline-start" />
          <span>恢复默认</span>
        </Button>
      </div>
    </FieldGroup>

    <Alert
      v-if="!cycle.isIdle.value || cycle.status.value === 'completed'"
    >
      <AlertTitle class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <Badge :variant="statusBadgeVariant">{{ statusText }}</Badge>
          <span class="text-xs text-muted-foreground font-mono">
            第 {{ cycle.currentLoop.value }} / {{ cycle.executionTotalLoops.value }} 圈
          </span>
        </div>

        <div class="flex items-center gap-1 text-xs text-muted-foreground font-mono">
          <ClockIcon class="size-3.5" />
          <span>累计: {{ formatDuration(cycle.totalElapsedSeconds.value) }}</span>
        </div>
      </AlertTitle>

      <AlertDescription v-if="cycle.currentStep.value" class="flex flex-col gap-2 pt-2">
        <div class="flex items-center justify-between text-xs">
          <div class="flex items-center gap-2">
            <span class="font-semibold text-foreground">
              [步骤 {{ cycle.currentStepIndex.value + 1 }}/{{ cycle.executionTotalSteps.value }}] {{ cycle.currentStep.value.name }}
            </span>
            <Badge variant="outline">
              {{ cycle.currentStep.value.gear === 1 ? 'D挡正向' : cycle.currentStep.value.gear === 2 ? 'R挡反向' : 'N挡缓冲' }}
            </Badge>
            <span class="font-mono text-primary font-bold">
              {{ cycle.currentStep.value.targetSpeed }} RPM
            </span>
          </div>
          <span class="font-mono font-bold text-foreground">
            倒计时: {{ cycle.stepRemainingSeconds.value }}s
          </span>
        </div>

        <Progress :model-value="cycle.stepProgressPercent.value" class="h-2" />

        <div class="flex flex-col gap-1 mt-1">
          <div class="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>总进度 ({{ cycle.currentLoop.value }}/{{ cycle.executionTotalLoops.value }} 圈)</span>
            <span class="font-mono font-semibold">{{ cycle.overallProgressPercent.value }}%</span>
          </div>
          <Progress :model-value="cycle.overallProgressPercent.value" class="h-1.5 opacity-80" />
        </div>
      </AlertDescription>
    </Alert>

    <Alert
      v-if="axleStore.telemetry.cycle_test.last_error"
      variant="destructive"
    >
      <AlertTitle>循环测试已停止</AlertTitle>
      <AlertDescription>{{ axleStore.telemetry.cycle_test.last_error }}</AlertDescription>
    </Alert>

    <!-- 步骤配置序列列表 -->
    <div class="flex flex-col gap-2 flex-1">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold text-muted-foreground">步骤序列</span>
          <span class="text-[11px] text-muted-foreground font-mono">
            (共 {{ cycle.steps.value.length }} 步 · 单圈 {{ cycle.singleLoopTotalDuration.value }}s)
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
      <div class="flex items-center gap-1.5 px-2 text-[11px] font-semibold text-muted-foreground select-none">
        <span class="w-5 shrink-0" aria-hidden="true"></span>
        <span class="min-w-20 flex-1">步骤名称</span>
        <span class="w-22 shrink-0">挡位</span>
        <span class="w-25 shrink-0">目标转速</span>
        <span class="w-17 shrink-0 text-center">时长</span>
        <span class="w-7 shrink-0"></span>
      </div>

      <!-- 步骤单行滚动容器 -->
      <ScrollArea class="h-[185px] pr-2 rounded-lg border border-border/60 bg-muted/10 p-1.5">
        <div class="flex flex-col gap-1.5">
          <div
            v-for="(step, index) in cycle.steps.value"
            :key="step.id"
            :class="cn(
              'px-2 py-1.5 rounded-lg border transition-all flex items-center gap-1.5',
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
              class="h-7 min-w-20 flex-1 px-2 text-xs"
              :disabled="cycle.isRunning.value || cycle.isPaused.value"
            />

            <!-- 挡位选择 -->
            <Select
              :model-value="String(step.gear)"
              :disabled="cycle.isRunning.value || cycle.isPaused.value"
              @update:model-value="(val) => handleGearChange(step, val)"
            >
              <SelectTrigger class="h-7 w-22 px-2 text-xs">
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
              <InputGroup class="w-28 shrink-0">
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
            <InputGroup class="w-17 shrink-0">
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
          :disabled="!axleStore.isConnected || axleStore.cycleLoading"
          @click="cycle.startTest"
        >
          <Spinner v-if="axleStore.cycleLoading" data-icon="inline-start" />
          <PlayIcon v-else data-icon="inline-start" />
          <span>{{ axleStore.cycleLoading ? '正在启动' : '开始工况测试' }}</span>
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
