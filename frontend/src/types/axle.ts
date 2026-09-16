/**
 * 电驱桥控制系统 TypeScript 接口定义
 * 严格对齐 DBC 及通信矩阵规范
 */

export interface CanConnectRequest {
  device_type: number
  device_index: number
  channel: number
  baud_rate: number
}

export interface VcuCommandUpdateRequest {
  torque_req?: number
  speed_req?: number
  work_mode_req?: number
  mcu_en_cmd?: number
  gear_sts?: number
  active_discharge?: number
}

export interface VcuCommandState {
  torque_req: number
  speed_req: number
  work_mode_req: number
  mcu_en_cmd: number
  gear_sts: number
  active_discharge: number
  life: number
}

export interface McuDriveMotor1Telemetry {
  mcu_dc_main_wire_volt: number
  mcu_dc_main_wire_curr: number
  mcu_integ_ctr_flt_num: number
  mcu_flt_code: number
  mcu_flt_levl: number
  mcu_life_1: number
  mcu_tbox_flt_levl: number
}

export interface McuDriveMotor2Telemetry {
  mcu_motor_tor_max: number
  mcu_act_motor_spd: number
  mcu_act_motor_tq: number
  mcu_active_dischrg_sts: number
  mcu_motor_work_mod: number
  mcu_lv_sts: number
  mcu_en_sts: number
  mcu_motor_temp_extre_over: number
  mcu_mcu_temp_extre_over: number
  mcu_life_2: number
}

export interface McuTboxTelemetry {
  num_mtr: number
  num_mtr_srl: number
  st_mtr: number
  mcu_motor_temp: number
  mcu_ctller_temp: number
  mcu_tbox_life: number
}

export interface AxleSafetyConfig {
  enabled: boolean
  max_motor_speed_rpm: number
  max_motor_torque_nm: number
  max_motor_temp_c: number
}

export interface AxleSafetyTrip {
  trip_id: number
  metric: 'motor_speed' | 'motor_torque' | 'motor_temperature'
  actual_value: number
  threshold: number
  unit: 'RPM' | 'Nm' | '℃'
  message: string
  triggered_at: string
}

export interface AxleSafetyStatus {
  config: AxleSafetyConfig
  last_trip: AxleSafetyTrip | null
}

export interface CanFrameItem {
  sequence: number
  timestamp: string
  direction: 'TX' | 'RX'
  can_id: number
  can_id_hex: string
  dlc: number
  data_hex: string
  name: string
}

export interface CanSendRawFrameRequest {
  can_id: number
  data_hex: string
  is_extended?: boolean
  is_remote?: boolean
}

export interface AxleTelemetry {
  connected: boolean
  is_transmitting: boolean
  is_emergency_locked: boolean
  device_type: number
  device_index: number
  channel: number
  baud_rate: number
  command: VcuCommandState
  mcu_1: McuDriveMotor1Telemetry
  mcu_1_last_rx_timestamp: number | null
  mcu_2: McuDriveMotor2Telemetry
  mcu_2_last_rx_timestamp: number | null
  mcu_tbox: McuTboxTelemetry
  mcu_tbox_last_rx_timestamp: number | null
  safety: AxleSafetyStatus
  tx_frame_count: number
  rx_frame_count: number
  tx_error_count: number
  last_rx_timestamp: number | null
  recent_frames: CanFrameItem[]
  updated_at: string
}

export interface AxleActionResponse {
  success: boolean
  message: string
  data?: Record<string, string | number | boolean>
}

export const WORK_MODE_MAP: Record<number, string> = {
  0: '关闭',
  1: '扭矩模式',
  2: '零扭矩模式',
  3: '速度模式',
  4: '制动模式',
  5: '前进模式',
  6: '倒车模式',
}

export const GEAR_MAP: Record<number, string> = {
  1: 'D (前进)',
  2: 'R (倒退)',
  3: 'N (空挡)',
  4: 'L (爬坡)',
  5: 'P (驻车)',
}

export const FAULT_LEVEL_MAP: Record<number, { text: string }> = {
  0: { text: '无故障' },
  1: { text: '一级故障(轻微)' },
  2: { text: '二级故障(中度)' },
  3: { text: '三级故障(严重)' },
  4: { text: '四级故障(致命)' },
}

export const TBOX_FAULT_LEVEL_MAP: Record<number, string> = {
  0: '温度正常',
  1: '温度一级故障',
  2: '温度故障（限功）',
  3: '温度故障（下高压）',
}

/** 安全配置保存生效记录快照 */
export interface SafetyConfigRecord {
  id: string
  timestamp: string
  rawTimestamp: number
  enabled: boolean
  max_motor_speed_rpm: number
  max_motor_torque_nm: number
  max_motor_temp_c: number
}

export const MOTOR_STATE_MAP: Record<number, string> = {
  1: '耗电驱动',
  2: '发电制动',
  3: '停机关闭',
  4: '系统就绪',
  255: '无效状态',
}
