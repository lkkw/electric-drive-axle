import { computed, ref } from 'vue'
import { toast } from 'vue-sonner'

import { useAxleStore } from '@/stores/useAxleStore'
import type { CycleGear, CycleTestStartRequest } from '@/types/axle'

export interface CycleStep {
  id: string
  name: string
  gear: CycleGear
  targetSpeed: number
  durationSeconds: number
}

export const DEFAULT_CYCLE_STEPS: readonly CycleStep[] = [
  { id: 'step-1', name: '正转运行', gear: 1, targetSpeed: 1000, durationSeconds: 60 },
  { id: 'step-2', name: '换向缓冲', gear: 3, targetSpeed: 0, durationSeconds: 5 },
  { id: 'step-3', name: '反转运行', gear: 2, targetSpeed: 1000, durationSeconds: 60 },
  { id: 'step-4', name: '换向缓冲', gear: 3, targetSpeed: 0, durationSeconds: 5 },
]

let nextStepId = 100

export function useCycleTest() {
  const axleStore = useAxleStore()
  const totalLoops = ref(1)
  const steps = ref<CycleStep[]>(DEFAULT_CYCLE_STEPS.map((step) => ({ ...step })))

  const status = computed(() => axleStore.telemetry.cycle_test.status)
  const isRunning = computed(() => status.value === 'running')
  const isPaused = computed(() => status.value === 'paused')
  const isIdle = computed(() => !isRunning.value && !isPaused.value)
  const currentLoop = computed(() => axleStore.telemetry.cycle_test.current_loop)
  const currentStepIndex = computed(() => axleStore.telemetry.cycle_test.current_step_index)
  const stepRemainingSeconds = computed(() => axleStore.telemetry.cycle_test.step_remaining_seconds)
  const totalElapsedSeconds = computed(() => axleStore.telemetry.cycle_test.total_elapsed_seconds)
  const currentStep = computed<CycleStep | undefined>(() => {
    const backendStatus = axleStore.telemetry.cycle_test
    if (backendStatus.control_owner === 'cycle' || ['completed', 'stopped', 'error'].includes(backendStatus.status)) {
      return {
        id: `backend-step-${backendStatus.current_step_index}`,
        name: backendStatus.current_step_name,
        gear: backendStatus.current_step_gear,
        targetSpeed: backendStatus.current_step_target_speed,
        durationSeconds: backendStatus.current_step_duration_seconds,
      }
    }
    return steps.value[currentStepIndex.value]
  })
  const executionTotalLoops = computed(() =>
    isRunning.value || isPaused.value || status.value === 'completed'
      ? axleStore.telemetry.cycle_test.total_loops
      : totalLoops.value,
  )
  const executionTotalSteps = computed(() =>
    isRunning.value || isPaused.value || status.value === 'completed'
      ? axleStore.telemetry.cycle_test.total_steps
      : steps.value.length,
  )

  const singleLoopTotalDuration = computed(() =>
    steps.value.reduce((sum, step) => sum + Math.max(1, step.durationSeconds), 0),
  )
  const stepProgressPercent = computed(() => {
    if (!currentStep.value || currentStep.value.durationSeconds <= 0) return 0
    const elapsed = currentStep.value.durationSeconds - stepRemainingSeconds.value
    return Math.min(100, Math.max(0, Math.round((elapsed / currentStep.value.durationSeconds) * 100)))
  })
  const overallProgressPercent = computed(() => {
    const backendTotal = axleStore.telemetry.cycle_test.planned_total_seconds
    const totalDuration = isRunning.value || isPaused.value || status.value === 'completed'
      ? backendTotal
      : singleLoopTotalDuration.value * executionTotalLoops.value
    if (totalDuration <= 0) return 0
    return Math.min(100, Math.max(0, Math.round((totalElapsedSeconds.value / totalDuration) * 100)))
  })

  function addStep() {
    const lastStep = steps.value.at(-1)
    const gear: CycleGear = lastStep?.gear === 1 ? 2 : 1
    const newStep: CycleStep = {
      id: `step-${nextStepId++}`,
      name: gear === 1 ? '正转运行' : '反转运行',
      gear,
      targetSpeed: 1000,
      durationSeconds: 60,
    }
    steps.value.push(newStep)
    toast.success('已添加工况步骤', {
      description: `步骤 ${steps.value.length}：${newStep.name} (${newStep.gear === 1 ? 'D挡正向' : 'R挡反向'} ${newStep.targetSpeed} RPM, ${newStep.durationSeconds}s)`,
    })
  }

  function removeStep(index: number) {
    if (steps.value.length <= 1) {
      toast.warning('至少需要保留一个测试步骤')
      return
    }
    steps.value.splice(index, 1)
  }

  function resetTest() {
    totalLoops.value = 1
  }

  function resetToDefault() {
    steps.value = DEFAULT_CYCLE_STEPS.map((step) => ({
      ...step,
      id: `step-${nextStepId++}`,
    }))
    totalLoops.value = 1
    toast.success('已恢复默认工况配置')
  }

  function buildRequest(): CycleTestStartRequest | null {
    if (!Number.isInteger(totalLoops.value) || totalLoops.value < 1 || totalLoops.value > 999) {
      toast.warning('循环圈数必须是 1 至 999 的整数')
      return null
    }
    for (const [index, step] of steps.value.entries()) {
      const prefix = `步骤 ${index + 1}`
      if (!step.name.trim()) {
        toast.warning(`${prefix} 的名称不能为空`)
        return null
      }
      if (!Number.isInteger(step.durationSeconds) || step.durationSeconds < 1 || step.durationSeconds > 3600) {
        toast.warning(`${prefix} 的时长必须是 1 至 3600 秒的整数`)
        return null
      }
      if (!Number.isInteger(step.targetSpeed) || step.targetSpeed < 0 || step.targetSpeed > 12000) {
        toast.warning(`${prefix} 的目标转速必须是 0 至 12000 RPM 的正整数`)
        return null
      }
      if ((step.gear === 1 || step.gear === 2) && step.targetSpeed <= 0) {
        toast.warning(`${prefix} 为 ${step.gear === 1 ? 'D 挡正转' : 'R 挡反转'}时目标转速必须大于 0 RPM`)
        return null
      }
      if (step.gear === 3 && step.targetSpeed !== 0) {
        toast.warning(`${prefix} 为 N 挡时目标转速必须为 0`)
        return null
      }
    }
    const adjacentPairs = steps.value.slice(1).map((step, index) => [steps.value[index], step] as const)
    if (totalLoops.value > 1 && steps.value.length > 1) {
      adjacentPairs.push([steps.value.at(-1)!, steps.value[0]])
    }
    if (adjacentPairs.some(([previous, current]) =>
      (previous.gear === 1 && current.gear === 2)
      || (previous.gear === 2 && current.gear === 1))) {
      toast.warning('正反转切换之间必须配置 N 挡缓冲步骤')
      return null
    }
    return {
      total_loops: totalLoops.value,
      steps: steps.value.map((step) => ({
        id: step.id,
        name: step.name.trim(),
        gear: step.gear,
        target_speed: step.targetSpeed,
        duration_seconds: step.durationSeconds,
      })),
    }
  }

  async function startTest() {
    if (!axleStore.isConnected) {
      toast.error('CAN 未连接，无法启动循环测试')
      return
    }
    const request = buildRequest()
    if (!request) return
    try {
      await axleStore.runCycleTest(request)
      toast.success('循环测试已由后端启动', {
        description: `共 ${request.steps.length} 个步骤，计划循环 ${request.total_loops} 圈`,
      })
    } catch (error) {
      toast.error('循环测试启动失败', {
        description: error instanceof Error ? error.message : '请检查通信链路',
      })
    }
  }

  async function pauseTest() {
    try {
      await axleStore.pauseCycle()
      toast.info('循环测试已暂停，安全命令已写入')
    } catch (error) {
      toast.error('暂停循环测试失败', {
        description: error instanceof Error ? error.message : '请立即使用急停',
      })
    }
  }

  async function resumeTest() {
    try {
      await axleStore.resumeCycle()
      toast.success('循环测试已继续')
    } catch (error) {
      toast.error('继续循环测试失败', {
        description: error instanceof Error ? error.message : '请检查 CAN 和急停状态',
      })
    }
  }

  async function stopTest(reason?: string) {
    try {
      await axleStore.stopCycle()
      toast.info(reason ?? '循环测试已终止，控制权已释放')
    } catch (error) {
      toast.error('终止循环测试失败', {
        description: error instanceof Error ? error.message : '请立即使用急停',
      })
    }
  }

  return {
    status,
    isRunning,
    isPaused,
    isIdle,
    steps,
    totalLoops,
    currentLoop,
    currentStepIndex,
    currentStep,
    executionTotalLoops,
    executionTotalSteps,
    stepRemainingSeconds,
    totalElapsedSeconds,
    singleLoopTotalDuration,
    stepProgressPercent,
    overallProgressPercent,
    addStep,
    removeStep,
    startTest,
    pauseTest,
    resumeTest,
    stopTest,
    resetTest,
    resetToDefault,
  }
}
