import { describe, expect, it } from 'vitest'
import type { CanFrameItem } from '@/types/axle'
import { processFrames } from './canCommUtils'

describe('CanCommView - processFrames & ID 聚合逻辑测试', () => {
  const mockFrames: CanFrameItem[] = [
    {
      sequence: 1,
      timestamp: '14:00:00.100',
      direction: 'RX',
      can_id: 0x100,
      can_id_hex: '0x100',
      dlc: 8,
      data_hex: '01 02 03 04 05 06 07 08',
      name: 'MCU_Status',
    },
    {
      sequence: 2,
      timestamp: '14:00:00.200',
      direction: 'RX',
      can_id: 0x20,
      can_id_hex: '0x20',
      dlc: 8,
      data_hex: 'AA BB CC DD EE FF 00 11',
      name: 'BMS_Status',
    },
    {
      sequence: 3,
      timestamp: '14:00:00.300',
      direction: 'RX',
      can_id: 0x100,
      can_id_hex: '0x100',
      dlc: 8,
      data_hex: '11 22 33 44 55 66 77 88',
      name: 'MCU_Status',
    },
    {
      sequence: 4,
      timestamp: '14:00:00.400',
      direction: 'TX',
      can_id: 0x100,
      can_id_hex: '0x100',
      dlc: 8,
      data_hex: 'FF FF FF FF 00 00 00 00',
      name: 'VCU_Command',
    },
  ]

  it('默认 GROUP 模式下正确按 CAN ID 和方向聚合，并更新最新载荷与累积计数', () => {
    const result = processFrames({
      frames: mockFrames,
      viewMode: 'GROUP',
      directionFilter: 'ALL',
      searchFilter: '',
    })

    // 应该聚合为 3 项：RX-0x20, RX-0x100, TX-0x100
    expect(result).toHaveLength(3)

    // 第一项应为数值较小的 0x20
    expect(result[0].can_id_hex).toBe('0x20')
    expect(result[0].direction).toBe('RX')
    expect(result[0].count).toBe(1)

    // RX-0x100 出现了 2 次，最新数据为 sequence 3 的数据
    const rx100 = result.find((f) => f.can_id_hex === '0x100' && f.direction === 'RX')
    expect(rx100).toBeDefined()
    expect(rx100?.count).toBe(2)
    expect(rx100?.data_hex).toBe('11 22 33 44 55 66 77 88')
    expect(rx100?.timestamp).toBe('14:00:00.300')

    // TX-0x100 与 RX-0x100 独立分组
    const tx100 = result.find((f) => f.can_id_hex === '0x100' && f.direction === 'TX')
    expect(tx100).toBeDefined()
    expect(tx100?.count).toBe(1)
  })

  it('CAN ID 升序排序必须遵循十六进制数值顺序，而非字符串字典序', () => {
    const mixedFrames: CanFrameItem[] = [
      {
        sequence: 1,
        timestamp: '14:00:00.100',
        direction: 'RX',
        can_id: 0x100,
        can_id_hex: '0x100',
        dlc: 8,
        data_hex: '00',
        name: 'FrameA',
      },
      {
        sequence: 2,
        timestamp: '14:00:00.200',
        direction: 'RX',
        can_id: 0x20,
        can_id_hex: '0x20',
        dlc: 8,
        data_hex: '00',
        name: 'FrameB',
      },
      {
        sequence: 3,
        timestamp: '14:00:00.300',
        direction: 'RX',
        can_id: 0x0c0,
        can_id_hex: '0x0C0',
        dlc: 8,
        data_hex: '00',
        name: 'FrameC',
      },
    ]

    const result = processFrames({
      frames: mixedFrames,
      viewMode: 'GROUP',
      directionFilter: 'ALL',
      searchFilter: '',
    })

    // 数值顺序: 0x20 (32) < 0x0C0 (192) < 0x100 (256)
    // 如果按字典序，"0x0C0" < "0x100" < "0x20"，0x20 会被错误排在最后
    expect(result.map((f) => f.can_id_hex)).toEqual(['0x20', '0x0C0', '0x100'])
  })

  it('方向过滤 (TX/RX) 正常生效', () => {
    const rxOnly = processFrames({
      frames: mockFrames,
      viewMode: 'GROUP',
      directionFilter: 'RX',
      searchFilter: '',
    })
    expect(rxOnly.every((f) => f.direction === 'RX')).toBe(true)
    expect(rxOnly).toHaveLength(2)

    const txOnly = processFrames({
      frames: mockFrames,
      viewMode: 'GROUP',
      directionFilter: 'TX',
      searchFilter: '',
    })
    expect(txOnly.every((f) => f.direction === 'TX')).toBe(true)
    expect(txOnly).toHaveLength(1)
  })

  it('关键字检索正确过滤 ID、标识名称或数据内容', () => {
    const searchById = processFrames({
      frames: mockFrames,
      viewMode: 'GROUP',
      directionFilter: 'ALL',
      searchFilter: '0x20',
    })
    expect(searchById).toHaveLength(1)
    expect(searchById[0].can_id_hex).toBe('0x20')

    const searchByName = processFrames({
      frames: mockFrames,
      viewMode: 'GROUP',
      directionFilter: 'ALL',
      searchFilter: 'vcu',
    })
    expect(searchByName).toHaveLength(1)
    expect(searchByName[0].name).toBe('VCU_Command')
  })

  it('切换到 TRACE 模式时保持流水顺序且不合并', () => {
    const traceResult = processFrames({
      frames: mockFrames,
      viewMode: 'TRACE',
      directionFilter: 'ALL',
      searchFilter: '',
    })

    expect(traceResult).toHaveLength(4)
    expect(traceResult.map((f) => f.sequence)).toEqual([1, 2, 3, 4])
  })
})
