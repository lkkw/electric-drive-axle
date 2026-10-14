import { describe, expect, it } from 'vitest'
import type { CanFrameItem } from '@/types/axle'
import { listFrameGroups, mergeFrameGroups, processFrames, type ProcessedFrame } from './canCommUtils'

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

  describe('ID 聚合需跨推送累积（低频报文不能闪烁）', () => {
    function frame(sequence: number, canId: number, direction: 'TX' | 'RX' = 'RX'): CanFrameItem {
      const hex = `0x${canId.toString(16).toUpperCase().padStart(3, '0')}`
      return {
        sequence,
        timestamp: `t${sequence}`,
        direction,
        can_id: canId,
        can_id_hex: hex,
        dlc: 8,
        data_hex: '00',
        name: hex,
      }
    }

    /** 后端每次推送最近 200 帧：模拟 0x258/0x35B 各 10 ms 一帧的高频总线 */
    function busWindow(fromSeq: number, count: number): CanFrameItem[] {
      return Array.from({ length: count }, (_, i) =>
        frame(fromSeq + i, i % 2 === 0 ? 0x258 : 0x35b, i % 2 === 0 ? 'TX' : 'RX'),
      )
    }

    it('1 秒周期的 0x5EF 被挤出最近 200 帧窗口后仍保留在聚合列表中', () => {
      const groups = new Map<string, ProcessedFrame>()
      let last = 0

      // 第一次推送：窗口内包含一帧 0x5EF
      const first = [...busWindow(1, 150), frame(151, 0x5ef), ...busWindow(152, 49)]
      last = mergeFrameGroups(groups, first, last)
      expect(listFrameGroups(groups, 'ALL', '').some((g) => g.can_id === 0x5ef)).toBe(true)

      // 0.9 秒后：新窗口全是高频报文，0x5EF 已不在最近 200 帧内
      last = mergeFrameGroups(groups, busWindow(201, 200), last)
      const ef = listFrameGroups(groups, 'ALL', '').find((g) => g.can_id === 0x5ef)
      expect(ef).toBeDefined()
      expect(ef?.count).toBe(1)
      expect(ef?.timestamp).toBe('t151') // 显示最近一次收到的时间
    })

    it('重复推送的重叠帧不重复计数，计数为监视期间累计值', () => {
      const groups = new Map<string, ProcessedFrame>()
      let last = mergeFrameGroups(groups, busWindow(1, 200), 0)
      // 后端窗口滑动：第 101~300 帧，其中 101~200 已处理过
      last = mergeFrameGroups(groups, busWindow(101, 200), last)
      const total = listFrameGroups(groups, 'ALL', '').reduce((sum, g) => sum + (g.count ?? 0), 0)
      expect(total).toBe(300)
      expect(last).toBe(300)
    })

    it('后端重启导致序号回退时重新开始统计', () => {
      const groups = new Map<string, ProcessedFrame>()
      let last = mergeFrameGroups(groups, busWindow(1000, 10), 0)
      last = mergeFrameGroups(groups, [frame(1, 0x35a)], last)
      expect(last).toBe(1)
      expect(listFrameGroups(groups, 'ALL', '').map((g) => g.can_id)).toEqual([0x35a])
    })
  })
})
