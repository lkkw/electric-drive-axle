import { describe, expect, it } from 'vitest'

import type { TestRecord } from '@/types/testRecords'
import { formatDuration, formatValue, localDateText, summarizeRecords } from './testRecordUtils'

function record(result: 1 | 2): TestRecord {
  return {
    id: 1,
    timestamp: '2026-10-14T03:00:00+00:00',
    sn: null,
    result,
    remark: '',
    started_at: null,
    duration_s: null,
    max_speed_rpm: null,
    max_torque_nm: null,
    max_motor_temp_c: null,
    max_controller_temp_c: null,
    max_bus_current_a: null,
    fault_codes: '',
    safety_trips: 0,
    plc_result_written: true,
  }
}

describe('testRecordUtils', () => {
  it('试车时长按分秒显示', () => {
    expect(formatDuration(null)).toBe('--')
    expect(formatDuration(42.4)).toBe('42秒')
    expect(formatDuration(185)).toBe('3分05秒')
  })

  it('数值带单位与小数位，未知为 --', () => {
    expect(formatValue(null, 'RPM')).toBe('--')
    expect(formatValue(3000, 'RPM')).toBe('3000 RPM')
    expect(formatValue(35.46, 'Nm', 1)).toBe('35.5 Nm')
  })

  it('本地日期补零', () => {
    expect(localDateText(new Date(2026, 0, 5))).toBe('2026-01-05')
  })

  it('统计合格率', () => {
    expect(summarizeRecords([]).passRate).toBe('--')
    const summary = summarizeRecords([record(1), record(1), record(2)])
    expect(summary).toEqual({ total: 3, passed: 2, failed: 1, passRate: '66.7%' })
  })
})
