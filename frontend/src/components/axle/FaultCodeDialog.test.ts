import { describe, expect, it } from 'vitest'

import {
  getMcuFaultInfo,
  MCM_SLOPE_STATE_MAP,
  MCU_FAULT_CODES,
  MCU_FAULT_MAP,
} from '@/types/axle'

describe('FaultCodeDialog & Fault Code Mapping Specifications', () => {
  it('MCU_FAULT_CODES 完整收录 22 项故障码且仅呈现 DEF 三列核心信息', () => {
    // 校验数量恰好等于 Excel 表中解析出的 22 条故障定义
    expect(MCU_FAULT_CODES.length).toBe(22)

    // 每条记录都必须具有 code (E列 仪表显示), meaning (D列 含义), level (F列 故障级别)
    for (const item of MCU_FAULT_CODES) {
      expect(item.code).toMatch(/^MCU_\d+$/)
      expect(item.meaning.length).toBeGreaterThan(0)
      expect(item.level).toMatch(/^(二级|三级)/)
      expect(item.raw_code).toBeGreaterThan(0)

      // 验证 raw_code 与 code 中的数值一致
      const parsedNum = Number.parseInt(item.code.replace('MCU_', ''), 10)
      expect(item.raw_code).toBe(parsedNum)
    }

    // 验证所有 raw_code 均唯一无重复
    const rawCodes = MCU_FAULT_CODES.map((item) => item.raw_code)
    const uniqueRawCodes = new Set(rawCodes)
    expect(uniqueRawCodes.size).toBe(MCU_FAULT_CODES.length)
  })

  it('getMcuFaultInfo 正确根据 CAN 原始故障码反查详细信息', () => {
    // 正常状态 (0) 应返回 undefined
    expect(getMcuFaultInfo(0)).toBeUndefined()

    // 典型故障码 MCU_64 (VCE过流故障)
    const flt64 = getMcuFaultInfo(64)
    expect(flt64).toBeDefined()
    expect(flt64?.code).toBe('MCU_64')
    expect(flt64?.meaning).toBe('VCE过流故障')
    expect(flt64?.level).toBe('三级 (Fault)')

    // 典型故障码 MCU_11 (IGBT采样温度降额)
    const flt11 = getMcuFaultInfo(11)
    expect(flt11).toBeDefined()
    expect(flt11?.code).toBe('MCU_11')
    expect(flt11?.meaning).toBe('IGBT采样温度降额')
    expect(flt11?.level).toBe('二级 (Derat)')

    // 典型故障码 MCU_105 (电机定子温度传感器1电路输出电压高(断路))
    const flt105 = getMcuFaultInfo(105)
    expect(flt105).toBeDefined()
    expect(flt105?.code).toBe('MCU_105')
    expect(flt105?.meaning).toBe('电机定子温度传感器1电路输出电压高(断路)')
    expect(flt105?.level).toBe('二级 (Limp)')

    // 未知故障码
    expect(getMcuFaultInfo(255)).toBeUndefined()
  })

  it('MCU_FAULT_MAP 字典与 MCU_FAULT_CODES 保持完全同步', () => {
    expect(Object.keys(MCU_FAULT_MAP).length).toBe(22)
    for (const item of MCU_FAULT_CODES) {
      expect(MCU_FAULT_MAP[item.raw_code]).toEqual(item)
    }
  })

  it('驻坡状态 (MCM_Slope_Sts) 映射正确', () => {
    expect(MCM_SLOPE_STATE_MAP[0]).toBe('未驻坡')
    expect(MCM_SLOPE_STATE_MAP[1]).toBe('驻坡中')
  })

  it('检索过滤逻辑能够准确匹配故障码、十进制数值、十六进制及含义描述', () => {
    // 模拟 FaultCodeDialog.vue 中的 filteredFaultCodes 过滤算法
    const filterCodes = (queryStr: string) => {
      const query = queryStr.trim().toLowerCase()
      if (!query) return MCU_FAULT_CODES
      return MCU_FAULT_CODES.filter((item) => {
        const codeMatch = item.code.toLowerCase().includes(query)
        const meaningMatch = item.meaning.toLowerCase().includes(query)
        const levelMatch = item.level.toLowerCase().includes(query)
        const rawStr = item.raw_code.toString()
        const rawMatch = rawStr.includes(query)

        const hexRaw = item.raw_code.toString(16).toLowerCase()
        const hexPadded = hexRaw.padStart(2, '0')
        const hexMatch =
          hexRaw.includes(query) ||
          hexPadded.includes(query) ||
          `0x${hexRaw}`.includes(query) ||
          `0x${hexPadded}`.includes(query)

        return codeMatch || meaningMatch || levelMatch || rawMatch || hexMatch
      })
    }

    // 空检索应返回全部 22 条
    expect(filterCodes('')).toHaveLength(22)

    // 关键词 "mcu_64" 检索
    const resMcu64 = filterCodes('mcu_64')
    expect(resMcu64).toHaveLength(1)
    expect(resMcu64[0].code).toBe('MCU_64')

    // 十六进制检索: 64 对应十六进制 0x40
    const resHex40 = filterCodes('0x40')
    expect(resHex40.some((i) => i.code === 'MCU_64')).toBe(true)

    // 单数字十六进制补零检索: 7 (0x07) 与 11 (0x0b)
    const resHex07 = filterCodes('07')
    expect(resHex07.some((i) => i.code === 'MCU_7')).toBe(true)
    const resHex0x07 = filterCodes('0x07')
    expect(resHex0x07.some((i) => i.code === 'MCU_7')).toBe(true)

    const resHex0b = filterCodes('0b')
    expect(resHex0b.some((i) => i.code === 'MCU_11')).toBe(true)
    const resHex0x0b = filterCodes('0x0b')
    expect(resHex0x0b.some((i) => i.code === 'MCU_11')).toBe(true)

    // 故障等级检索: "三级", "Derat", "Limp"
    expect(filterCodes('三级').length).toBe(11)
    expect(filterCodes('Derat').length).toBe(6)
    expect(filterCodes('Limp').length).toBe(5)

    // 中文含义模糊检索: "过温"
    const resOverTemp = filterCodes('过温')
    expect(resOverTemp.length).toBeGreaterThanOrEqual(2)
    expect(resOverTemp.map((i) => i.code)).toContain('MCU_72') // IGBT采样温度过温故障
    expect(resOverTemp.map((i) => i.code)).toContain('MCU_31') // L2电机定子温度过温

    // 中文含义检索: "堵转"
    const resLockedRotor = filterCodes('堵转')
    expect(resLockedRotor).toHaveLength(1)
    expect(resLockedRotor[0].code).toBe('MCU_144')
    expect(resLockedRotor[0].meaning).toBe('控制器堵转过载降额')

    // 无匹配结果
    const resNone = filterCodes('不存在的故障关键字xyz')
    expect(resNone).toHaveLength(0)
  })
})
