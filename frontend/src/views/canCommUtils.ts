import type { CanFrameItem } from '@/types/axle'

/**
 * 带有聚合计数的报文展示对象
 * 在 ID 聚合模式下，count 记录该 ID 在监视期间累计收到的帧数
 */
export type ProcessedFrame = CanFrameItem & { count?: number }

export type DirectionFilter = 'ALL' | 'TX' | 'RX'

export interface ProcessFramesOptions {
  /** 原始报文数据源 */
  frames: CanFrameItem[]
  /** 视图展示模式：'GROUP' 为 ID 聚合，'TRACE' 为按时间流水 */
  viewMode: 'TRACE' | 'GROUP'
  /** 传输方向过滤：全部、仅发送(TX)、仅接收(RX) */
  directionFilter: DirectionFilter
  /** 检索关键字（支持 CAN ID、标识符名称、数据载荷 HEX） */
  searchFilter: string
  /** 界面最大保留与渲染的帧数上限（防止巨量报文导致浏览器卡顿） */
  maxFrames?: number
}

function matchesFilters(frame: CanFrameItem, directionFilter: DirectionFilter, query: string) {
  if (directionFilter !== 'ALL' && frame.direction !== directionFilter) {
    return false
  }
  if (!query) return true
  return (
    frame.can_id_hex.toLowerCase().includes(query)
    || frame.name.toLowerCase().includes(query)
    || frame.data_hex.toLowerCase().includes(query)
  )
}

/**
 * 把一次推送的报文合并进持久的 ID 聚合表，返回已处理到的最大序号。
 *
 * 后端每次只推送最近 200 帧（约 0.9 s 的总线流量）。如果每次都从这 200 帧重新聚合，
 * 1 s 周期的低频报文（如 0x5EF）会在被挤出窗口后从列表消失、下一帧到来时又出现，
 * 造成闪烁。因此聚合表在页面生命周期内持续累积：
 * - 只处理序号大于 lastSequence 的新帧，相邻两次推送的重叠部分不会重复计数；
 * - 同一“方向 + ID”保留最新一帧的内容与时间戳，count 为监视期间累计帧数；
 * - 若序号回退（后端重启），清空后重新统计。
 */
export function mergeFrameGroups(
  groups: Map<string, ProcessedFrame>,
  frames: CanFrameItem[],
  lastSequence: number,
): number {
  if (frames.length === 0) return lastSequence

  let processed = lastSequence
  const newest = frames[frames.length - 1].sequence
  if (newest < lastSequence) {
    groups.clear()
    processed = 0
  }

  for (const frame of frames) {
    if (frame.sequence <= processed) continue
    // 区分发送(TX)与接收(RX)，相同 ID 但方向不同的报文独立统计
    const key = `${frame.direction}-${frame.can_id_hex}`
    const existing = groups.get(key)
    if (existing) {
      const count = (existing.count ?? 1) + 1
      Object.assign(existing, frame)
      existing.count = count
    } else {
      groups.set(key, { ...frame, count: 1 })
    }
  }

  return Math.max(processed, newest)
}

/**
 * 按方向与关键字过滤聚合表，并按 CAN ID 数值升序排列
 * （避免字符串字典序把 0x100 排在 0x20 前面），ID 相同时按方向排序。
 */
export function listFrameGroups(
  groups: Map<string, ProcessedFrame>,
  directionFilter: DirectionFilter,
  searchFilter: string,
): ProcessedFrame[] {
  const query = searchFilter.trim().toLowerCase()
  return Array.from(groups.values())
    .filter((frame) => matchesFilters(frame, directionFilter, query))
    .sort((a, b) => {
      const idDiff = (parseInt(a.can_id_hex, 16) || 0) - (parseInt(b.can_id_hex, 16) || 0)
      return idDiff !== 0 ? idDiff : a.direction.localeCompare(b.direction)
    })
}

/**
 * 处理一组报文快照
 *
 * - TRACE 模式：截取最新 N 帧（默认 200）并过滤，保持时间流水顺序；
 * - GROUP 模式：只对这一组快照做聚合（实时监视页使用 mergeFrameGroups 持续累积）。
 */
export function processFrames(options: ProcessFramesOptions): ProcessedFrame[] {
  const { frames, viewMode, directionFilter, searchFilter, maxFrames = 200 } = options
  const sliced = frames.slice(-maxFrames)

  if (viewMode === 'GROUP') {
    const groups = new Map<string, ProcessedFrame>()
    mergeFrameGroups(groups, sliced, 0)
    return listFrameGroups(groups, directionFilter, searchFilter)
  }

  const query = searchFilter.trim().toLowerCase()
  return sliced.filter((frame) => matchesFilters(frame, directionFilter, query))
}
