import { computed, getCurrentInstance, onBeforeUnmount, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { useAxleStore } from '@/stores/useAxleStore'

export interface CycleStep {
  id: string
  name: string
  gear: number // 1: D, 2: R, 3: N
  targetSpeed: number // RPM (-12000 ~ 12000)
  durationSeconds: number // 持续秒数
}

export const DEFAULT_CYCLE_STEPS: readonly CycleStep[] = [
  { id: 'step-1', name: '正转运行', gear: 1, targetSpeed: 1000, durationSeconds: 60 },
  { id: 'step-2', name: '换向缓冲', gear: 3, targetSpeed: 0, durationSeconds: 5 },
  { id: 'step-3', name: '反转运行', gear: 2, targetSpeed: -1000, durationSeconds: 60 },
  { id: 'step-4', name: '换向缓冲', gear: 3, targetSpeed: 0, durationSeconds: 5 },
]

export type CycleTestStatus = 'idle' | 'running' | 'paused' | 'stopped' | 'completed'

let nextStepId = 100

export function useCycleTest() {
  const axleStore = useAxleStore()

  const status = ref<CycleTestStatus>('idle')
  const totalLoops = ref<number>(1) // 默认1圈，即单次循环完成即停止
  const currentLoop = ref<number>(1)
  const currentStepIndex = ref<number>(0)
  const stepRemainingSeconds = ref<number>(0)
  const totalElapsedSeconds = ref<number>(0)

  // 初始化步骤列表（深拷贝默认步骤）
  const steps = ref<CycleStep[]>(
    DEFAULT_CYCLE_STEPS.map((s) => ({ ...s })),
  )

  let timer: ReturnType<typeof setInterval> | undefined

  const isRunning = computed(() => status.value === 'running')
  const isPaused = computed(() => status.value === 'paused')
  const isIdle = computed(() => status.value === 'idle' || status.value === 'stopped' || status.value === 'completed')

  const currentStep = computed<CycleStep | undefined>(() => steps.value[currentStepIndex.value])

  const singleLoopTotalDuration = computed(() =>
    steps.value.reduce((sum, s) => sum + Math.max(1, s.durationSeconds), 0),
  )

  const stepProgressPercent = computed(() => {
    if (!currentStep.value || currentStep.value.durationSeconds <= 0) return 0
    const elapsed = currentStep.value.durationSeconds - stepRemainingSeconds.value
    return Math.min(100, Math.max(0, Math.round((elapsed / currentStep.value.durationSeconds) * 100)))
  })

  const overallProgressPercent = computed(() => {
    if (totalLoops.value === 0) return 0 // 无限循环不显示总进度
    const totalDuration = singleLoopTotalDuration.value * totalLoops.value
    if (totalDuration <= 0) return 0
    return Math.min(100, Math.max(0, Math.round((totalElapsedSeconds.value / totalDuration) * 100)))
  })

  function addStep() {
    const lastStep = steps.value[steps.value.length - 1]
    const isLastD = lastStep?.gear === 1
    const newGear = isLastD ? 2 : 1
    steps.value.push({
      id: `step-${nextStepId++}`,
      name: newGear === 1 ? '正转运行' : '反转运行',
      gear: newGear,
      targetSpeed: newGear === 1 ? 1000 : -1000,
      durationSeconds: 60,
    })
  }

  function resetToDefault() {
    steps.value = DEFAULT_CYCLE_STEPS.map((s) => ({ ...s, id: `step-${nextStepId++}` }))
    totalLoops.value = 1
    resetTest()
    toast.success('已恢复为默认工况配置', {
      description: '正转 60s → 缓冲 5s → 反转 60s → 缓冲 5s (1圈)',
    })
  }

  function removeStep(index: number) {
    if (steps.value.length <= 1) {
      toast.warning('至少需要保留一个测试步骤')
      return
    }
    steps.value.splice(index, 1)
  }

  async function executeCurrentStep() {
    const step = currentStep.value
    if (!step) return

    try {
      // 1. 确保 MCU 处于使能状态与速度模式 (work_mode_req: 3)
      await axleStore.sendCommand({
        mcu_en_cmd: 1,
        work_mode_req: 3,
        gear_sts: step.gear,
        speed_req: step.targetSpeed,
        torque_req: 0,
      })
    } catch (error) {
      stopTest('指令下发失败，安全中止测试')
      toast.error('工况指令下发失败', {
        description: error instanceof Error ? error.message : '请检查通信链路',
      })
    }
  }

  function onTick() {
    totalElapsedSeconds.value++
    stepRemainingSeconds.value--

    if (stepRemainingSeconds.value <= 0) {
      // 当前步骤结束，进入下一步
      if (currentStepIndex.value < steps.value.length - 1) {
        currentStepIndex.value++
        stepRemainingSeconds.value = currentStep.value?.durationSeconds ?? 0
        executeCurrentStep()
      } else {
        // 本圈循环结束
        if (totalLoops.value === 0 || currentLoop.value < totalLoops.value) {
          // 继续下一圈循环
          currentLoop.value++
          currentStepIndex.value = 0
          stepRemainingSeconds.value = currentStep.value?.durationSeconds ?? 0
          executeCurrentStep()
        } else {
          // 全部循环执行完毕
          completeTest()
        }
      }
    }
  }

  async function startTest() {
    if (!axleStore.isConnected) {
      toast.error('CAN 未连接，无法启动自动化测试')
      return
    }
    if (steps.value.length === 0) {
      toast.warning('请至少添加一个工况测试步骤')
      return
    }

    // 校验步骤时长合法性
    for (const step of steps.value) {
      if (step.durationSeconds <= 0) {
        toast.warning(`步骤 "${step.name}" 持续时间必须大于 0 秒`)
        return
      }
    }

    currentLoop.value = 1
    currentStepIndex.value = 0
    totalElapsedSeconds.value = 0
    stepRemainingSeconds.value = steps.value[0].durationSeconds
    status.value = 'running'

    await executeCurrentStep()

    if (timer) clearInterval(timer)
    timer = setInterval(onTick, 1000)

    toast.success('自动化工况测试已启动', {
      description: `共 ${steps.value.length} 个步骤，计划循环 ${totalLoops.value === 0 ? '无限' : totalLoops.value} 圈`,
    })
  }

  async function pauseTest() {
    if (status.value !== 'running') return
    if (timer) clearInterval(timer)
    status.value = 'paused'

    // 安全暂停：将转速归零，挂入空挡缓冲
    try {
      await axleStore.sendCommand({
        gear_sts: 3,
        speed_req: 0,
      })
    } catch {
      // 忽略暂停下发的微小网络抖动
    }

    toast.info('工况测试已暂停', {
      description: '电机已降速并挂入空挡，点击继续可恢复执行',
    })
  }

  async function resumeTest() {
    if (status.value !== 'paused') return
    status.value = 'running'
    await executeCurrentStep()

    if (timer) clearInterval(timer)
    timer = setInterval(onTick, 1000)

    toast.success('工况测试已继续')
  }

  async function stopTest(reason?: string) {
    if (status.value === 'idle' || status.value === 'stopped') return
    if (timer) clearInterval(timer)
    status.value = 'stopped'

    // 安全停止：速度归零挂空挡
    try {
      await axleStore.sendCommand({
        gear_sts: 3,
        speed_req: 0,
        torque_req: 0,
      })
    } catch {
      // ignore
    }

    if (reason) {
      toast.warning(reason)
    } else {
      toast.info('工况测试已安全终止')
    }
  }

  async function completeTest() {
    if (timer) clearInterval(timer)
    status.value = 'completed'

    // 正常完成：速度归零挂空挡
    try {
      await axleStore.sendCommand({
        gear_sts: 3,
        speed_req: 0,
      })
    } catch {
      // ignore
    }

    toast.success('🎉 自动化工况循环测试全部完成！', {
      description: `累计完成 ${currentLoop.value} 圈，总耗时 ${totalElapsedSeconds.value} 秒`,
      duration: 5000,
    })
  }

  function resetTest() {
    if (timer) clearInterval(timer)
    status.value = 'idle'
    currentLoop.value = 1
    currentStepIndex.value = 0
    stepRemainingSeconds.value = steps.value[0]?.durationSeconds ?? 0
    totalElapsedSeconds.value = 0
  }

  // 安全联锁 1：监听上位机使能与急停。如果外部紧急停机使能断开，必须强制立即打断测试！
  watch(
    () => axleStore.telemetry.command.mcu_en_cmd,
    (en) => {
      if (en === 0 && (status.value === 'running' || status.value === 'paused')) {
        stopTest('检测到使能断开或紧急停机，自动化测试已安全中止！')
      }
    },
  )

  // 安全联锁 2：监听 CAN 离线
  watch(
    () => axleStore.isConnected,
    (connected) => {
      if (!connected && (status.value === 'running' || status.value === 'paused')) {
        stopTest('CAN 通信断开，自动化测试已安全中止！')
      }
    },
  )

  if (getCurrentInstance()) {
    onBeforeUnmount(() => {
      if (timer) clearInterval(timer)
    })
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
