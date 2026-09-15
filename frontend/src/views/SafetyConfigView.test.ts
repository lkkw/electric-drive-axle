import { describe, expect, it } from 'vitest'
import type { SafetyConfigRecord } from '@/types/axle'

describe('SafetyConfigRecord specifications', () => {
  it('validates a complete safety config record snapshot', () => {
    const record: SafetyConfigRecord = {
      id: 'cfg-1726140000000',
      timestamp: '2026-09-12 22:15:30',
      rawTimestamp: 1726140000000,
      enabled: true,
      max_motor_speed_rpm: 3500,
      max_motor_torque_nm: 25.5,
      max_motor_temp_c: 120.0,
    }

    expect(record.id).toBe('cfg-1726140000000')
    expect(record.timestamp).toBe('2026-09-12 22:15:30')
    expect(record.enabled).toBe(true)
    expect(record.max_motor_speed_rpm).toBe(3500)
    expect(record.max_motor_torque_nm).toBe(25.5)
    expect(record.max_motor_temp_c).toBe(120.0)
  })

  it('filters invalid storage records correctly', () => {
    const rawList: unknown = [
      {
        id: 'cfg-1',
        timestamp: '2026-09-12 22:00:00',
        enabled: true,
        max_motor_speed_rpm: 3000,
        max_motor_torque_nm: 10,
        max_motor_temp_c: 150,
      },
      {
        // 缺少必要的转速字段
        id: 'cfg-invalid',
        timestamp: 'invalid',
      },
      null,
      'corrupted-string',
    ]

    const parsed = (rawList as unknown[]).filter(
      (item): item is SafetyConfigRecord =>
        typeof item === 'object' &&
        item !== null &&
        typeof (item as Record<string, unknown>).id === 'string' &&
        typeof (item as Record<string, unknown>).timestamp === 'string' &&
        typeof (item as Record<string, unknown>).enabled === 'boolean' &&
        typeof (item as Record<string, unknown>).max_motor_speed_rpm === 'number' &&
        typeof (item as Record<string, unknown>).max_motor_torque_nm === 'number' &&
        typeof (item as Record<string, unknown>).max_motor_temp_c === 'number',
    )

    expect(parsed.length).toBe(1)
    expect(parsed[0].id).toBe('cfg-1')
    expect(parsed[0].max_motor_speed_rpm).toBe(3000)
  })

  it('truncates history records when exceeding capacity of 100', () => {
    const list: SafetyConfigRecord[] = Array.from({ length: 120 }, (_, index) => ({
      id: `cfg-${index}`,
      timestamp: `2026-09-12 22:00:${index.toString().padStart(2, '0')}`,
      rawTimestamp: Date.now() + index,
      enabled: true,
      max_motor_speed_rpm: 3000,
      max_motor_torque_nm: 10,
      max_motor_temp_c: 150,
    }))

    const MAX_HISTORY_RECORDS = 100
    const truncated = list.slice(0, MAX_HISTORY_RECORDS)
    expect(truncated.length).toBe(100)
    expect(truncated[0].id).toBe('cfg-0')
    expect(truncated[99].id).toBe('cfg-99')
  })
})
