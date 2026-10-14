import type { PlcTrafficEntry, PlcTrafficLog, PlcTrafficValue } from '@/types/plc'

export const MAX_TRAFFIC_ENTRIES = 500
export const MAX_FREQUENT_TRAFFIC_ENTRIES = 200

export interface TrafficState {
  /** 重要记录（最新在前） */
  entries: PlcTrafficEntry[]
  /** 心跳、转速 / 温度等高频记录（最新在前），单独限量，避免挤掉重要记录 */
  frequent: PlcTrafficEntry[]
  lastSeq: number
}

export const createTrafficState = (): TrafficState => ({ entries: [], frequent: [], lastSeq: 0 })

/**
 * 把一次增量拉取的结果合并进本地记录。
 * 后端重启后序号从头开始（latest_seq 小于本地已处理的序号），此时清空重来。
 */
export function mergeTrafficLog(state: TrafficState, log: PlcTrafficLog): TrafficState {
  if (log.latest_seq < state.lastSeq) {
    return mergeTrafficLog(createTrafficState(), log)
  }
  if (log.entries.length === 0) return state

  const newestFirst = [...log.entries].sort((a, b) => b.seq - a.seq)
  return {
    entries: [...newestFirst.filter((e) => !e.frequent), ...state.entries].slice(
      0,
      MAX_TRAFFIC_ENTRIES,
    ),
    frequent: [...newestFirst.filter((e) => e.frequent), ...state.frequent].slice(
      0,
      MAX_FREQUENT_TRAFFIC_ENTRIES,
    ),
    lastSeq: log.latest_seq,
  }
}

/** 要显示的记录：默认隐藏心跳，打开开关后按序号合并显示 */
export function visibleTrafficEntries(state: TrafficState, showFrequent: boolean) {
  return showFrequent
    ? [...state.entries, ...state.frequent].sort((a, b) => b.seq - a.seq)
    : state.entries
}

const RESULT_LABELS: Record<number, string> = { 0: '未判定', 1: '合格', 2: 'NG' }

export function formatTrafficValue(name: string, value: PlcTrafficValue | undefined): string {
  if (value === null || value === undefined) return '—'
  if (name === 'sn') return value === '' ? '（空）' : String(value)
  if (name === 'result') return `${value}（${RESULT_LABELS[Number(value)] ?? '未知'}）`
  return String(value)
}
