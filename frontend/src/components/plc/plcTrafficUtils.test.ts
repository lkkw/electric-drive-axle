import { describe, expect, it } from 'vitest'

import type { PlcTrafficEntry } from '@/types/plc'
import {
  createTrafficState,
  formatTrafficValue,
  MAX_FREQUENT_TRAFFIC_ENTRIES,
  mergeTrafficLog,
  visibleTrafficEntries,
} from './plcTrafficUtils'

function entry(seq: number, frequent = false, name = frequent ? 'plc_heart' : 'safe'): PlcTrafficEntry {
  return {
    seq,
    time: `t${seq}`,
    direction: 'read',
    name,
    label: name,
    address: 'DB40.DBX62.1',
    value: 1,
    previous: 0,
    source: '',
    frequent,
  }
}

describe('PLC 通信记录合并', () => {
  it('增量合并后最新记录在前，心跳单独存放', () => {
    let state = mergeTrafficLog(createTrafficState(), {
      latest_seq: 3,
      entries: [entry(1), entry(2, true), entry(3)],
    })
    state = mergeTrafficLog(state, { latest_seq: 4, entries: [entry(4)] })

    expect(state.entries.map((e) => e.seq)).toEqual([4, 3, 1])
    expect(state.frequent.map((e) => e.seq)).toEqual([2])
    expect(state.lastSeq).toBe(4)
  })

  it('默认隐藏心跳；打开后按序号合并显示', () => {
    const state = mergeTrafficLog(createTrafficState(), {
      latest_seq: 3,
      entries: [entry(1), entry(2, true), entry(3)],
    })
    expect(visibleTrafficEntries(state, false).map((e) => e.seq)).toEqual([3, 1])
    expect(visibleTrafficEntries(state, true).map((e) => e.seq)).toEqual([3, 2, 1])
  })

  it('大量心跳不会挤掉重要记录', () => {
    const heartbeats = Array.from({ length: 300 }, (_, i) => entry(i + 2, true))
    const state = mergeTrafficLog(createTrafficState(), {
      latest_seq: 301,
      entries: [entry(1), ...heartbeats],
    })
    expect(state.entries.map((e) => e.seq)).toEqual([1])
    expect(state.frequent).toHaveLength(MAX_FREQUENT_TRAFFIC_ENTRIES)
  })

  it('后端重启（序号回退）时清空重来', () => {
    let state = mergeTrafficLog(createTrafficState(), { latest_seq: 50, entries: [entry(50)] })
    state = mergeTrafficLog(state, { latest_seq: 2, entries: [entry(1), entry(2)] })
    expect(state.entries.map((e) => e.seq)).toEqual([2, 1])
    expect(state.lastSeq).toBe(2)
  })

  it('数值格式化', () => {
    expect(formatTrafficValue('safe', null)).toBe('—')
    expect(formatTrafficValue('sn', '')).toBe('（空）')
    expect(formatTrafficValue('result', 2)).toBe('2（NG）')
    expect(formatTrafficValue('out_voltage', 280)).toBe('280')
  })
})
