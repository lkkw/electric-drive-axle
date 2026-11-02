import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { toast } from 'vue-sonner'
import { getCycleTestConfig, saveCycleTestConfig } from '@/api/axle'
import { useAxleStore } from '@/stores/useAxleStore'
import type { CycleTestConfig } from '@/types/axle'
import { useCycleTest } from './useCycleTest'

vi.mock('@/api/axle', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/axle')>()
  return {
    ...actual,
    getCycleTestConfig: vi.fn(),
    saveCycleTestConfig: vi.fn(),
  }
})

const SAVE_DEBOUNCE_MS = 300

describe('useCycleTest composable', () => {
  /** 模拟后端保存的配置 */
  let savedConfig: CycleTestConfig | null

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    savedConfig = null
    vi.mocked(getCycleTestConfig).mockImplementation(
      () => ({ send: async () => savedConfig }) as unknown as ReturnType<typeof getCycleTestConfig>,
    )
    vi.mocked(saveCycleTestConfig).mockImplementation(
      (config) =>
        ({
          send: async () => {
            savedConfig = config
            return config
          },
        }) as unknown as ReturnType<typeof saveCycleTestConfig>,
    )
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  async function flushSave() {
    await vi.advanceTimersByTimeAsync(SAVE_DEBOUNCE_MS)
  }

  it('修改工况后自动保存，重新进入页面时恢复', async () => {
    const cycle = useCycleTest()
    await flushSave()
    cycle.steps.value[0].targetSpeed = 1500
    cycle.steps.value[0].name = '正转 1500'
    cycle.totalLoops.value = 5
    cycle.removeStep(7)
    await flushSave()

    const restored = useCycleTest()
    await flushSave()
    expect(restored.steps.value).toHaveLength(7)
    expect(restored.steps.value[0]).toMatchObject({
      name: '正转 1500',
      gear: 1,
      targetSpeed: 1500,
      durationSeconds: 60,
    })
    expect(restored.totalLoops.value).toBe(5)
  })

  it('未修改时不写入，恢复已保存配置也不重复写入', async () => {
    useCycleTest()
    await flushSave()
    expect(saveCycleTestConfig).not.toHaveBeenCalled()

    savedConfig = {
      total_loops: 2,
      steps: [{ name: '正转', gear: 1, target_speed: 1000, duration_seconds: 60 }],
    }
    useCycleTest()
    await flushSave()
    expect(saveCycleTestConfig).not.toHaveBeenCalled()
  })

  it('连续输入只保存一次', async () => {
    const cycle = useCycleTest()
    await flushSave()
    for (const speed of [1, 15, 150, 1500]) {
      cycle.steps.value[0].targetSpeed = speed
      await vi.advanceTimersByTimeAsync(50)
    }
    await flushSave()

    expect(saveCycleTestConfig).toHaveBeenCalledOnce()
    expect(savedConfig?.steps[0].target_speed).toBe(1500)
  })

  it('离开页面时立即写入未落盘的修改', async () => {
    const scope = effectScope()
    const cycle = scope.run(() => useCycleTest())!
    await flushSave()
    cycle.steps.value[0].targetSpeed = 1500
    await vi.advanceTimersByTimeAsync(0)
    scope.stop()

    expect(saveCycleTestConfig).toHaveBeenCalledOnce()
  })

  it('恢复后的步骤 id 不与新增步骤冲突', async () => {
    savedConfig = {
      total_loops: 1,
      steps: [{ name: '正转', gear: 1, target_speed: 1000, duration_seconds: 60 }],
    }
    const cycle = useCycleTest()
    await flushSave()
    cycle.addStep()

    const ids = cycle.steps.value.map((step) => step.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('恢复默认会覆盖已保存的工况', async () => {
    const cycle = useCycleTest()
    await flushSave()
    cycle.steps.value[0].targetSpeed = 1500
    await flushSave()
    cycle.resetToDefault()
    await flushSave()

    expect(savedConfig?.steps[0].target_speed).toBe(1000)
  })

  it('输入框清空时不覆盖上一次完整配置', async () => {
    const cycle = useCycleTest()
    await flushSave()
    cycle.steps.value[0].targetSpeed = 1500
    await flushSave()
    // v-model.number 在输入框清空时给出空字符串
    ;(cycle.steps.value[0] as { targetSpeed: unknown }).targetSpeed = ''
    await flushSave()

    expect(saveCycleTestConfig).toHaveBeenCalledOnce()
    expect(savedConfig?.steps[0].target_speed).toBe(1500)
  })

  it('读取失败时沿用默认工况，保存失败时提示且下次修改重试', async () => {
    vi.mocked(getCycleTestConfig).mockImplementation(
      () =>
        ({ send: () => Promise.reject(new Error('offline')) }) as unknown as ReturnType<
          typeof getCycleTestConfig
        >,
    )
    vi.mocked(saveCycleTestConfig).mockImplementationOnce(
      () =>
        ({ send: () => Promise.reject(new Error('磁盘已满')) }) as unknown as ReturnType<
          typeof saveCycleTestConfig
        >,
    )
    const toastWarningSpy = vi.spyOn(toast, 'warning')

    const cycle = useCycleTest()
    await flushSave()
    expect(cycle.steps.value).toHaveLength(8)

    cycle.steps.value[0].targetSpeed = 1500
    await flushSave()
    expect(toastWarningSpy).toHaveBeenCalledWith('工况配置保存失败', {
      description: '磁盘已满',
    })

    cycle.steps.value[0].targetSpeed = 1600
    await flushSave()
    expect(saveCycleTestConfig).toHaveBeenCalledTimes(2)
    expect(savedConfig?.steps[0].target_speed).toBe(1600)
  })

  it('初始状态为 idle 并默认装载正转 1000/2000/3000、反转 1000/2000/3000 工况', () => {
    const cycle = useCycleTest()
    expect(cycle.status.value).toBe('idle')
    expect(cycle.steps.value.map((step) => [step.gear, step.targetSpeed])).toEqual([
      [1, 1000],
      [1, 2000],
      [1, 3000],
      [3, 0], // N 换向缓冲
      [2, 1000],
      [2, 2000],
      [2, 3000],
      [3, 0], // N 换向缓冲（多圈时反转接回正转）
    ])
    expect(cycle.totalLoops.value).toBe(1)
  })

  it('默认工况多圈运行也满足正反转之间必须有 N 挡缓冲', async () => {
    const store = useAxleStore()
    store.telemetry.connected = true
    const runCycleSpy = vi.spyOn(store, 'runCycleTest').mockResolvedValue(undefined)
    const cycle = useCycleTest()
    cycle.totalLoops.value = 3

    await cycle.startTest()
    expect(runCycleSpy).toHaveBeenCalledOnce()
  })

  it('支持自定义修改工况步骤与重置状态', () => {
    const cycle = useCycleTest()
    cycle.steps.value[0].targetSpeed = 3000
    cycle.totalLoops.value = 3
    expect(cycle.steps.value[0].targetSpeed).toBe(3000)
    expect(cycle.totalLoops.value).toBe(3)
    cycle.resetToDefault()
    expect(cycle.steps.value[0].targetSpeed).toBe(1000)
    expect(cycle.totalLoops.value).toBe(1)
    expect(cycle.status.value).toBe('idle')
  })

  it('支持步骤的增加与删除，并阻止删除最后一个步骤', () => {
    const toastSuccessSpy = vi.spyOn(toast, 'success')
    const cycle = useCycleTest()
    const initialLen = cycle.steps.value.length
    cycle.addStep()
    expect(cycle.steps.value.length).toBe(initialLen + 1)
    expect(toastSuccessSpy).toHaveBeenCalledWith(
      '已添加工况步骤',
      expect.objectContaining({
        description: expect.stringContaining(`步骤 ${initialLen + 1}`),
      }),
    )

    while (cycle.steps.value.length > 1) {
      cycle.removeStep(0)
    }
    expect(cycle.steps.value.length).toBe(1)
    // 再次删除应该被拦截，至少保留1项
    cycle.removeStep(0)
    expect(cycle.steps.value.length).toBe(1)
  })

  it('启动时向后端提交完整工况快照，状态以后端为准', async () => {
    const store = useAxleStore()
    store.telemetry.connected = true
    const runCycleSpy = vi.spyOn(store, 'runCycleTest').mockImplementation(async (request) => {
      store.telemetry.cycle_test = {
        ...store.telemetry.cycle_test,
        status: 'running',
        control_owner: 'cycle',
        total_loops: request.total_loops,
        total_steps: request.steps.length,
        current_step_name: request.steps[0].name,
        current_step_gear: request.steps[0].gear,
        current_step_target_speed: request.steps[0].target_speed,
        current_step_duration_seconds: request.steps[0].duration_seconds,
        planned_total_seconds: request.steps[0].duration_seconds,
        step_remaining_seconds: request.steps[0].duration_seconds,
      }
    })

    const cycle = useCycleTest()
    cycle.steps.value = [
      { id: 's1', name: '单步测试', gear: 1, targetSpeed: 500, durationSeconds: 2 },
    ]
    cycle.totalLoops.value = 1

    await cycle.startTest()
    expect(cycle.status.value).toBe('running')
    expect(runCycleSpy).toHaveBeenCalledWith({
      total_loops: 1,
      steps: [
        {
          id: 's1',
          name: '单步测试',
          gear: 1,
          target_speed: 500,
          duration_seconds: 2,
        },
      ],
    })
  })

  it('后端终止状态能立即映射到前端循环状态', () => {
    const store = useAxleStore()
    const cycle = useCycleTest()
    store.telemetry.cycle_test.status = 'running'
    store.telemetry.cycle_test.control_owner = 'cycle'
    expect(cycle.status.value).toBe('running')

    store.telemetry.cycle_test.status = 'stopped'
    store.telemetry.cycle_test.control_owner = 'none'
    store.telemetry.cycle_test.last_error = '急停已触发。'
    expect(cycle.status.value).toBe('stopped')
    expect(cycle.isIdle.value).toBe(true)
  })

  it('拒绝非法负转速配置', async () => {
    const store = useAxleStore()
    store.telemetry.connected = true
    const runCycleSpy = vi.spyOn(store, 'runCycleTest')
    const cycle = useCycleTest()
    cycle.steps.value = [
      { id: 'invalid', name: '反转', gear: 2, targetSpeed: -500, durationSeconds: 2 },
    ]

    await cycle.startTest()
    expect(runCycleSpy).not.toHaveBeenCalled()
  })

  it('急停互锁期间拒绝启动循环测试', async () => {
    const store = useAxleStore()
    store.telemetry.connected = true
    store.telemetry.is_emergency_locked = true
    const runCycleSpy = vi.spyOn(store, 'runCycleTest')
    const toastErrorSpy = vi.spyOn(toast, 'error')

    const cycle = useCycleTest()
    await cycle.startTest()

    expect(runCycleSpy).not.toHaveBeenCalled()
    expect(toastErrorSpy).toHaveBeenCalledWith(
      '系统处于急停互锁状态，请先在控制台解除急停互锁',
    )
  })
})
