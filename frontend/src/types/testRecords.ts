/** 试车记录，与后端 schemas/test_records.py 一一对应 */

/** 1=合格 2=NG */
export type TestResult = 1 | 2

/** 当前这台电驱桥的试车统计：从上次判定后第一次收到 MCU 反馈开始累计 */
export interface TestSessionStats {
  started_at: string | null
  duration_s: number | null
  max_speed_rpm: number | null
  max_torque_nm: number | null
  max_motor_temp_c: number | null
  max_controller_temp_c: number | null
  max_bus_current_a: number | null
  fault_codes: string[]
  safety_trips: number
}

export interface TestRecord {
  id: number
  /** 判定时间 (ISO 8601, UTC) */
  timestamp: string
  sn: string | null
  result: TestResult
  remark: string
  started_at: string | null
  duration_s: number | null
  max_speed_rpm: number | null
  max_torque_nm: number | null
  max_motor_temp_c: number | null
  max_controller_temp_c: number | null
  max_bus_current_a: number | null
  /** 故障码，逗号分隔 */
  fault_codes: string
  safety_trips: number
  plc_result_written: boolean
}

export interface TestRecordJudgeResponse {
  record: TestRecord
  message: string
}

export interface TestRecordFilters {
  /** 本地日期 YYYY-MM-DD（含） */
  date_from?: string
  date_to?: string
  sn?: string
  result?: TestResult
}

export interface TestRecordExportResponse {
  path: string
  count: number
}
