import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { emergencyReset, emergencyStop, getAxleStatus, softStop } from '@/api/axle'
import type { AxleTelemetry } from '@/types/axle'
import {
  HISTORY_SAMPLE_INTERVAL_MS,
  HISTORY_WINDOW_MS,
  useAxleStore,
} from './useAxleStore'

vi.mock('@/api/axle', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/axle')>()
  return {
    ...actual,
    emergencyReset: vi.fn(),
    emergencyStop: vi.fn(),
    getAxleStatus: vi.fn(),
    softStop: vi.fn(),
  }
})

describe('useAxleStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('initializes with default disconnected telemetry state', () => {
    const store = useAxleStore()
    expect(store.isConnected).toBe(false)
    expect(store.isTransmitting).toBe(false)
    expect(store.telemetry.baud_rate).toBe(500000)
    expect(store.telemetry.command.torque_req).toBe(0)
    expect(store.telemetry.command.speed_req).toBe(0)
    expect(store.telemetry.command.gear_sts).toBe(3) // N
    expect(store.telemetry.command.mcu_en_cmd).toBe(0)
    expect(store.telemetry.recent_frames).toEqual([])
  })

  it('records history points from telemetry snapshots', () => {
    const store = useAxleStore()
    expect(store.historySeries.length).toBe(0)

    const snapshot = JSON.parse(JSON.stringify(store.telemetry)) as AxleTelemetry
    snapshot.mcu_2.mcu_act_motor_spd = 1200
    snapshot.mcu_2.mcu_act_motor_tq = 50.5
    store.recordHistory(snapshot, 1_000)

    expect(store.historySeries.length).toBe(1)
    expect(store.historySeries[0].speed).toBe(1200)
    expect(store.historySeries[0].torque).toBe(50.5)
  })

  it('downsamples history and keeps only the configured time window', () => {
    const store = useAxleStore()
    const snapshot = JSON.parse(JSON.stringify(store.telemetry)) as AxleTelemetry

    // 20Hz 推送持续 40 秒
    for (let t = 0; t <= 40_000; t += 50) {
      store.recordHistory(snapshot, t)
    }

    const series = store.historySeries
    expect(series.length).toBeLessThanOrEqual(
      HISTORY_WINDOW_MS / HISTORY_SAMPLE_INTERVAL_MS + 1,
    )
    expect(series[series.length - 1].timestamp).toBe(40_000)
    expect(series[0].timestamp).toBeGreaterThanOrEqual(40_000 - HISTORY_WINDOW_MS)
    for (let i = 1; i < series.length; i += 1) {
      expect(series[i].timestamp - series[i - 1].timestamp).toBeGreaterThanOrEqual(
        HISTORY_SAMPLE_INTERVAL_MS,
      )
    }
  })

  it('SSE 在线时急停不重复拉取状态快照', async () => {
    const store = useAxleStore()
    store.sseConnected = true

    vi.mocked(emergencyStop).mockReturnValue({
      send: () => Promise.resolve(store.telemetry.command),
    } as unknown as ReturnType<typeof emergencyStop>)

    await store.triggerEmergencyStop()

    expect(store.isEmergencyLocked).toBe(true)
    expect(getAxleStatus).not.toHaveBeenCalled()
  })

  it('handles recent CAN frame buffer updates', () => {
    const store = useAxleStore()
    expect(store.telemetry.recent_frames.length).toBe(0)

    store.telemetry.recent_frames.push({
      sequence: 1,
      timestamp: '12:30:00.123',
      direction: 'TX',
      can_id: 0x258,
      can_id_hex: '0x258',
      dlc: 8,
      data_hex: '00 00 00 00 00 00 00 00',
      name: 'VCU_11',
    })

    expect(store.telemetry.recent_frames.length).toBe(1)
    expect(store.telemetry.recent_frames[0].can_id_hex).toBe('0x258')
  })

  it('复位急停互锁后同步后端解锁状态', async () => {
    const store = useAxleStore()
    store.telemetry.is_emergency_locked = true
    expect(store.isEmergencyLocked).toBe(true)

    vi.mocked(emergencyReset).mockReturnValue({
      send: () => Promise.resolve(store.telemetry.command),
    } as unknown as ReturnType<typeof emergencyReset>)
    vi.mocked(getAxleStatus).mockReturnValue({
      send: () =>
        Promise.resolve({ ...store.telemetry, is_emergency_locked: false }),
    } as unknown as ReturnType<typeof getAxleStatus>)

    await store.resetEmergencyStop()

    expect(store.isEmergencyLocked).toBe(false)
    expect(store.error).toBeNull()
    expect(store.loading).toBe(false)
  })

  it('复位失败时保留互锁并记录错误信息', async () => {
    const store = useAxleStore()
    store.telemetry.is_emergency_locked = true

    vi.mocked(emergencyReset).mockReturnValue({
      send: () => Promise.reject(new Error('解除急停互锁失败')),
    } as unknown as ReturnType<typeof emergencyReset>)

    await expect(store.resetEmergencyStop()).rejects.toThrow('解除急停互锁失败')

    expect(store.isEmergencyLocked).toBe(true)
    expect(store.error).toBe('解除急停互锁失败')
    expect(store.loading).toBe(false)
  })

  it('平稳停机：已使能时进入减速停机状态，目标值归零', async () => {
    const store = useAxleStore()
    store.telemetry.command = { ...store.telemetry.command, mcu_en_cmd: 1, speed_req: 1000 }

    vi.mocked(softStop).mockReturnValue({
      send: () => Promise.resolve({ ...store.telemetry.command, speed_req: 0, torque_req: 0 }),
    } as unknown as ReturnType<typeof softStop>)

    await store.startSoftStop()

    expect(store.telemetry.command.speed_req).toBe(0)
    expect(store.telemetry.soft_stopping).toBe(true)
    expect(store.loading).toBe(false)
  })

  it('平稳停机失败时记录错误且不进入停机状态', async () => {
    const store = useAxleStore()
    vi.mocked(softStop).mockReturnValue({
      send: () => Promise.reject(new Error('CAN 未连接，无法执行停机。')),
    } as unknown as ReturnType<typeof softStop>)

    await expect(store.startSoftStop()).rejects.toThrow('CAN 未连接')
    expect(store.telemetry.soft_stopping).toBe(false)
    expect(store.error).toBe('CAN 未连接，无法执行停机。')
  })
})
