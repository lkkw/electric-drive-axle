/** PLC 自动上电 / 下电（dbPC [DB40]，340 V），与后端 schemas/plc.py 一一对应 */

export interface PlcConfig {
  ip: string
  rack: number
  slot: number
  simulation: boolean
}

export type PowerState = 'idle' | 'powering_on' | 'powered' | 'powering_off' | 'fault'

export interface PlcStatus {
  connected: boolean
  simulation: boolean
  ip: string
  rack: number
  slot: number
  /** 最近 1 s 内成功读到过 PLC 反馈 */
  communication_ok: boolean
  communication_error: string | null
  /** 仅用于显示，不参与放行或停机判断 */
  plc_heartbeat_alive: boolean
  safe: boolean
  request_power: boolean
  power_on: boolean
  contactor_closed: boolean
  product_type_expected: number
  product_type_feedback: number
  target_voltage: number
  output_voltage: number
  output_current: number
  serial_number: string
  power_state: PowerState
  fault_reason: string | null
  last_message: string | null
}

export interface PlcActionResponse {
  status: 'success' | 'partial'
  message: string
  plc: PlcStatus
}

export const POWER_STATE_LABEL: Record<PowerState, string> = {
  idle: '未上电',
  powering_on: '上电中',
  powered: '已上电',
  powering_off: '下电中',
  fault: '供电故障',
}

/** PLC 通信监视（联调用） */
export type PlcTrafficValue = number | string | null

export interface PlcTrafficPoint {
  name: string
  label: string
  address: string
  value: PlcTrafficValue
}

export interface PlcTrafficSnapshot {
  /** PLC 未连接时为 null */
  updated_at: string | null
  write: PlcTrafficPoint[]
  read: PlcTrafficPoint[]
}

export interface PlcTrafficEntry {
  seq: number
  time: string
  direction: 'write' | 'read'
  name: string
  label: string
  address: string
  value: PlcTrafficValue
  previous: PlcTrafficValue
  source: string
  /** 心跳等每秒都有的记录 */
  frequent: boolean
}

export interface PlcTrafficLog {
  latest_seq: number
  entries: PlcTrafficEntry[]
}
