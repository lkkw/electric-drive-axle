import { describe, expect, it } from 'vitest'

import { cycleControlLock } from './controlLock'

describe('cycleControlLock', () => {
  it('循环运行、暂停时锁定手动控制', () => {
    expect(cycleControlLock({ status: 'running', auto_judge: 'none' })).toMatchObject({
      locked: true,
      label: '运行中',
    })
    expect(cycleControlLock({ status: 'paused', auto_judge: 'none' })).toMatchObject({
      locked: true,
      label: '已暂停',
    })
  })

  it('循环结束后自动判定 / 下电期间仍锁定手动控制', () => {
    for (const status of ['completed', 'stopped', 'error'] as const) {
      expect(cycleControlLock({ status, auto_judge: 'pending' })).toMatchObject({
        locked: true,
        label: '判定中',
      })
    }
  })

  it('空闲或自动判定完成后解除锁定', () => {
    expect(cycleControlLock({ status: 'idle', auto_judge: 'none' }).locked).toBe(false)
    expect(cycleControlLock({ status: 'completed', auto_judge: 'done' })).toMatchObject({
      locked: false,
      label: null,
    })
  })
})
