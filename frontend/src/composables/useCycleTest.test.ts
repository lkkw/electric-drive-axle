import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'vue-sonner'
import { useAxleStore } from '@/stores/useAxleStore'
import { useCycleTest } from './useCycleTest'

describe('useCycleTest composable', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('初始状态为 idle 并默认装载标准正反转出厂步骤', () => {
    const cycle = useCycleTest()
    expect(cycle.status.value).toBe('idle')
    expect(cycle.steps.value.length).toBe(4)
    expect(cycle.steps.value[0].gear).toBe(1) // D
    expect(cycle.steps.value[0].targetSpeed).toBe(1000)
    expect(cycle.steps.value[1].gear).toBe(3) // N 换向缓冲
    expect(cycle.steps.value[1].targetSpeed).toBe(0)
    expect(cycle.steps.value[2].gear).toBe(2) // R
    expect(cycle.steps.value[2].targetSpeed).toBe(1000)
    expect(cycle.steps.value[3].gear).toBe(3) // N 换向缓冲
    expect(cycle.steps.value[3].targetSpeed).toBe(0)
    expect(cycle.totalLoops.value).toBe(1)
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
})
