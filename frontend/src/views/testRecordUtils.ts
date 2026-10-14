import type { TestRecord } from '@/types/testRecords'

/** 秒数 → “3分05秒” / “42秒”；未知为 “--” */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '--'
  const total = Math.round(seconds)
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return minutes ? `${minutes}分${String(rest).padStart(2, '0')}秒` : `${rest}秒`
}

/** 数值带单位；未知为 “--” */
export function formatValue(value: number | null | undefined, unit = '', digits = 0): string {
  if (value === null || value === undefined) return '--'
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ''}`
}

/** ISO 时间 → 本地 “YYYY-MM-DD HH:mm:ss” */
export function formatLocalTime(value: string | null | undefined): string {
  if (!value) return '--'
  const d = new Date(value)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/** 本地日期 “YYYY-MM-DD”（用于日期筛选默认值） */
export function localDateText(date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 合计、合格、NG 与合格率 */
export function summarizeRecords(records: TestRecord[]) {
  const total = records.length
  const passed = records.filter((r) => r.result === 1).length
  return {
    total,
    passed,
    failed: total - passed,
    passRate: total ? `${((passed / total) * 100).toFixed(1)}%` : '--',
  }
}
