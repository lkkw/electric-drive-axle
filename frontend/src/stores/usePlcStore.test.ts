import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getPlcStatus, plcPowerOff, plcPowerOn } from '@/api/plc'
import { createInitialPlcStatus, usePlcStore } from './usePlcStore'

vi.mock('@/api/plc', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/plc')>()
  return {
    ...actual,
    getPlcStatus: vi.fn(),
    plcPowerOn: vi.fn(),
    plcPowerOff: vi.fn(),
  }
})

const mockSend = <T>(value: Promise<T>) => ({ send: () => value }) as never

describe('usePlcStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('上电成功后用接口返回的最终快照更新状态，并清除进行中标记', async () => {
    const store = usePlcStore()
    const powered = { ...createInitialPlcStatus(), connected: true, power_state: 'powered' as const }
    vi.mocked(plcPowerOn).mockReturnValue(
      mockSend(Promise.resolve({ status: 'success', message: '已上电', plc: powered })),
    )

    const request = store.powerOn()
    expect(store.pending['power-on']).toBe(true)
    expect(store.isBusy).toBe(true)
    const result = await request

    expect(result.message).toBe('已上电')
    expect(store.isPowered).toBe(true)
    expect(store.isBusy).toBe(false)
  })

  it('下电失败时抛出原因，并恢复为非进行中', async () => {
    const store = usePlcStore()
    vi.mocked(plcPowerOff).mockReturnValue(
      mockSend(Promise.reject(new Error('PLC 未连接，请先连接 PLC'))),
    )

    await expect(store.powerOff()).rejects.toThrow('PLC 未连接')
    expect(store.pending['power-off']).toBe(false)
  })

  it('状态轮询在上一次请求未返回时不叠加请求', async () => {
    const store = usePlcStore()
    let resolve: (value: unknown) => void = () => {}
    vi.mocked(getPlcStatus).mockReturnValue(
      mockSend(new Promise((r) => { resolve = r })),
    )

    const first = store.refresh()
    void store.refresh()
    void store.refresh()
    expect(getPlcStatus).toHaveBeenCalledTimes(1)

    resolve({ ...createInitialPlcStatus(), connected: true })
    await first
    expect(store.status.connected).toBe(true)
  })

  it('上电进行中被下电打断时，两个操作的进行中标记互不覆盖', async () => {
    const store = usePlcStore()
    let finishOn: (value: unknown) => void = () => {}
    const idle = createInitialPlcStatus()
    vi.mocked(plcPowerOn).mockReturnValue(mockSend(new Promise((r) => { finishOn = r })))
    vi.mocked(plcPowerOff).mockReturnValue(
      mockSend(Promise.resolve({ status: 'success', message: '已下电', plc: idle })),
    )

    const on = store.powerOn().catch(() => undefined)
    await store.powerOff()
    expect(store.pending['power-off']).toBe(false)
    expect(store.pending['power-on']).toBe(true) // 上电请求仍在等待后端返回

    finishOn({ status: 'success', message: '已中止', plc: idle })
    await on
    expect(store.isBusy).toBe(false)
  })
})
