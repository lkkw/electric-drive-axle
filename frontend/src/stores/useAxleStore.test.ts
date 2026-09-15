import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useAxleStore } from './useAxleStore'

describe('useAxleStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
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

  it('tracks historySeries when new points arrive', () => {
    const store = useAxleStore()
    expect(store.historySeries.length).toBe(0)

    store.historySeries.push({
      time: '12:00:00.1',
      speed: 1200,
      torque: 50.5,
      voltage: 540.2,
      current: 25.1,
    })

    expect(store.historySeries.length).toBe(1)
    expect(store.historySeries[0].speed).toBe(1200)
    expect(store.historySeries[0].torque).toBe(50.5)
  })

  it('handles recent CAN frame buffer updates', () => {
    const store = useAxleStore()
    expect(store.telemetry.recent_frames.length).toBe(0)

    store.telemetry.recent_frames.push({
      sequence: 1,
      timestamp: '12:30:00.123',
      direction: 'TX',
      can_id: 0x314,
      can_id_hex: '0x314',
      dlc: 8,
      data_hex: '00 00 00 00 00 00 00 00',
      name: 'VCU_11',
    })

    expect(store.telemetry.recent_frames.length).toBe(1)
    expect(store.telemetry.recent_frames[0].can_id_hex).toBe('0x314')
  })
})
