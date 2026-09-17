import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAxleStore } from '@/stores/useAxleStore'
import { useCycleTest } from './useCycleTest'

describe('useCycleTest composable', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
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
    expect(cycle.steps.value[2].targetSpeed).toBe(-1000)
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
    const cycle = useCycleTest()
    const initialLen = cycle.steps.value.length
    cycle.addStep()
    expect(cycle.steps.value.length).toBe(initialLen + 1)

    while (cycle.steps.value.length > 1) {
      cycle.removeStep(0)
    }
    expect(cycle.steps.value.length).toBe(1)
    // 再次删除应该被拦截，至少保留1项
    cycle.removeStep(0)
    expect(cycle.steps.value.length).toBe(1)
  })

  it('启动测试后按时间步进并在完成时归零', async () => {
    const store = useAxleStore()
    store.telemetry.connected = true
    const sendCommandSpy = vi.spyOn(store, 'sendCommand').mockResolvedValue(undefined)

    const cycle = useCycleTest()
    // 配置简单测试：1 步，运行 2 秒，循环 1 圈
    cycle.steps.value = [
      { id: 's1', name: '单步测试', gear: 1, targetSpeed: 500, durationSeconds: 2 },
    ]
    cycle.totalLoops.value = 1

    await cycle.startTest()
    expect(cycle.status.value).toBe('running')
    expect(sendCommandSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        mcu_en_cmd: 1,
        work_mode_req: 3,
        gear_sts: 1,
        speed_req: 500,
      }),
    )

    // 步进 1 秒
    vi.advanceTimersByTime(1000)
    expect(cycle.stepRemainingSeconds.value).toBe(1)
    expect(cycle.totalElapsedSeconds.value).toBe(1)

    // 再步进 1 秒，测试应当顺利完成
    vi.advanceTimersByTime(1000)
    expect(cycle.status.value).toBe('completed')
  })

  it('紧急停机（使能归零）时能安全联锁中断测试', async () => {
    const store = useAxleStore()
    store.telemetry.connected = true
    store.telemetry.command.mcu_en_cmd = 1
    vi.spyOn(store, 'sendCommand').mockResolvedValue(undefined)

    const cycle = useCycleTest()
    await cycle.startTest()
    expect(cycle.status.value).toBe('running')

    // 模拟外部点击了紧急停机（mcu_en_cmd 变为 0）
    store.telemetry.command.mcu_en_cmd = 0
    await vi.waitFor(() => {
      expect(cycle.status.value).toBe('stopped')
    })
  })
})
