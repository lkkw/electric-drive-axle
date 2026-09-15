import type { CanFrameItem } from '@/types/axle'

/**
 * 带有聚合计数的报文展示对象
 * 在 ID 聚合模式下，count 记录该 ID 出现的累积帧数
 */
export type ProcessedFrame = CanFrameItem & { count?: number }

export interface ProcessFramesOptions {
  /** 原始报文数据源 */
  frames: CanFrameItem[]
  /** 视图展示模式：'GROUP' 为 ID 聚合，'TRACE' 为按时间流水 */
  viewMode: 'TRACE' | 'GROUP'
  /** 传输方向过滤：全部、仅发送(TX)、仅接收(RX) */
  directionFilter: 'ALL' | 'TX' | 'RX'
  /** 检索关键字（支持 CAN ID、标识符名称、数据载荷 HEX） */
  searchFilter: string
  /** 界面最大保留与渲染的帧数上限（防止巨量报文导致浏览器卡顿） */
  maxFrames?: number
}

/**
 * 处理 CAN 原始报文列表
 *
 * 核心逻辑：
 * 1. 截取最新 N 帧（默认 200 帧），保证页面渲染性能；
 * 2. 结合方向（TX/RX）与模糊搜索条件进行过滤；
 * 3. 若为 GROUP 模式，按 `${direction}-${can_id_hex}` 聚合，保留最新报文内容并累加计数，
 *    最后按 CAN ID 十六进制数值升序排序；
 * 4. 若为 TRACE 模式，保持原始时间流水顺序输出。
 */
export function processFrames(options: ProcessFramesOptions): ProcessedFrame[] {
  const { frames, viewMode, directionFilter, searchFilter, maxFrames = 200 } = options
  const sliced = frames.slice(-maxFrames)
  const query = searchFilter.trim().toLowerCase()

  // 1. 方向与关键字过滤
  const result = sliced.filter((frame) => {
    if (directionFilter !== 'ALL' && frame.direction !== directionFilter) {
      return false
    }
    if (query) {
      const matchesId = frame.can_id_hex.toLowerCase().includes(query)
      const matchesName = frame.name.toLowerCase().includes(query)
      const matchesData = frame.data_hex.toLowerCase().includes(query)
      if (!matchesId && !matchesName && !matchesData) {
        return false
      }
    }
    return true
  })

  // 2. ID 聚合模式
  if (viewMode === 'GROUP') {
    const map = new Map<string, ProcessedFrame>()
    for (const frame of result) {
      // 区分发送(TX)与接收(RX)，相同 ID 但方向不同的报文独立统计
      const key = `${frame.direction}-${frame.can_id_hex}`
      const existing = map.get(key)
      if (existing) {
        const newCount = (existing.count ?? 1) + 1
        // Object.assign 覆写更新为最新一帧的时间戳、数据载荷与序号
        Object.assign(existing, frame)
        existing.count = newCount
      } else {
        map.set(key, { ...frame, count: 1 })
      }
    }

    // 按 CAN ID 数值大小升序排序（避免字符串字典序把 0x100 排在 0x20 前面），ID 相同时按方向排序
    return Array.from(map.values()).sort((a, b) => {
      const idA = parseInt(a.can_id_hex, 16) || 0
      const idB = parseInt(b.can_id_hex, 16) || 0
      const idDiff = idA - idB
      if (idDiff !== 0) {
        return idDiff
      }
      return a.direction.localeCompare(b.direction)
    })
  }

  // 3. 时间流模式（保持时间戳流水顺序）
  return result
}
