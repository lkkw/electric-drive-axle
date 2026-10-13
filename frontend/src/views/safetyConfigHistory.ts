import type { SafetyConfigRecord } from '@/types/axle'

export const SAFETY_HISTORY_STORAGE_KEY = 'axle_safety_config_history'
/** 最大历史保存记录上限条数 */
export const MAX_HISTORY_RECORDS = 100

function isSafetyConfigRecord(item: unknown): item is SafetyConfigRecord {
  if (typeof item !== 'object' || item === null) return false
  const record = item as Record<string, unknown>
  return (
    typeof record.id === 'string' &&
    typeof record.timestamp === 'string' &&
    typeof record.enabled === 'boolean' &&
    typeof record.max_motor_speed_rpm === 'number' &&
    typeof record.max_motor_torque_nm === 'number' &&
    typeof record.max_motor_temp_c === 'number' &&
    // 旧版本记录没有反馈超时字段，允许缺省
    (record.feedback_timeout_ms === undefined || typeof record.feedback_timeout_ms === 'number')
  )
}

/** 解析 localStorage 中的历史记录，丢弃损坏项并截断到上限 */
export function parseSafetyHistory(raw: string | null): SafetyConfigRecord[] {
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isSafetyConfigRecord).slice(0, MAX_HISTORY_RECORDS)
  } catch {
    return []
  }
}

/** 将新记录置顶并截断到上限 */
export function prependSafetyHistory(
  history: SafetyConfigRecord[],
  record: SafetyConfigRecord,
): SafetyConfigRecord[] {
  return [record, ...history.filter((item) => item.id !== record.id)].slice(
    0,
    MAX_HISTORY_RECORDS,
  )
}
