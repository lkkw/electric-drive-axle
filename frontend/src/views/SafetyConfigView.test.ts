import { describe, expect, it } from 'vitest'

import type { SafetyConfigRecord } from '@/types/axle'
import {
  MAX_HISTORY_RECORDS,
  parseSafetyHistory,
  prependSafetyHistory,
} from './safetyConfigHistory'

function makeRecord(index: number, extra: Partial<SafetyConfigRecord> = {}): SafetyConfigRecord {
  return {
    id: `cfg-${index}`,
    timestamp: `2026-09-12 22:00:${(index % 60).toString().padStart(2, '0')}`,
    rawTimestamp: 1726140000000 + index,
    enabled: true,
    max_motor_speed_rpm: 3000,
    max_motor_torque_nm: 10,
    max_motor_temp_c: 150,
    feedback_timeout_ms: 500,
    ...extra,
  }
}

describe('safety config history storage', () => {
  it('keeps valid records, including legacy ones without feedback timeout', () => {
    const legacy = { ...makeRecord(1) } as Record<string, unknown>
    delete legacy.feedback_timeout_ms

    const raw = JSON.stringify([
      makeRecord(0),
      legacy,
      { id: 'cfg-invalid', timestamp: 'invalid' },
      { ...makeRecord(2), feedback_timeout_ms: 'fast' },
      null,
      'corrupted-string',
    ])

    const parsed = parseSafetyHistory(raw)
    expect(parsed.map((item) => item.id)).toEqual(['cfg-0', 'cfg-1'])
    expect(parsed[1].feedback_timeout_ms).toBeUndefined()
  })

  it('returns an empty list for missing or corrupted storage', () => {
    expect(parseSafetyHistory(null)).toEqual([])
    expect(parseSafetyHistory('{not json')).toEqual([])
    expect(parseSafetyHistory('{"id":"cfg-0"}')).toEqual([])
  })

  it('truncates parsed and prepended history to the capacity limit', () => {
    const list = Array.from({ length: 120 }, (_, index) => makeRecord(index))
    expect(parseSafetyHistory(JSON.stringify(list))).toHaveLength(MAX_HISTORY_RECORDS)

    const next = prependSafetyHistory(list.slice(0, MAX_HISTORY_RECORDS), makeRecord(999))
    expect(next).toHaveLength(MAX_HISTORY_RECORDS)
    expect(next[0].id).toBe('cfg-999')
    expect(next[MAX_HISTORY_RECORDS - 1].id).toBe('cfg-98')
  })

  it('moves a re-saved record to the top without duplicating it', () => {
    const history = [makeRecord(0), makeRecord(1), makeRecord(2)]
    const next = prependSafetyHistory(history, makeRecord(1, { max_motor_temp_c: 90 }))
    expect(next.map((item) => item.id)).toEqual(['cfg-1', 'cfg-0', 'cfg-2'])
    expect(next[0].max_motor_temp_c).toBe(90)
  })
})
