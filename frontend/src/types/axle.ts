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
  acc_position?: number
  work_mode_req?: number
  mcu_en_cmd?: number
  hand_brk_sts?: number
  brk_sts?: number
  abs_work_sts?: number
  gear_sts?: number
  active_discharge?: number
}

export interface VcuCommandState {
  torque_req: number
  speed_req: number
  acc_position?: number
  work_mode_req: number
  mcu_en_cmd: number
  hand_brk_sts?: number
  brk_sts?: number
  abs_work_sts?: number
  gear_sts: number
  active_discharge: number
  life: number
}

export type CycleGear = 1 | 2 | 3
export type CycleTestState = 'idle' | 'running' | 'paused' | 'stopped' | 'completed' | 'error'

export interface CycleTestStepRequest {
  id: string
  name: string
  gear: CycleGear
  target_speed: number
  duration_seconds: number
}

export interface CycleTestStartRequest {
  steps: CycleTestStepRequest[]
  total_loops: number
}

export interface CycleTestStatus {
  status: CycleTestState
  control_owner: 'none' | 'cycle'
  total_loops: number
  current_loop: number
  current_step_index: number
  total_steps: number
  current_step_name: string
  current_step_gear: CycleGear
  current_step_target_speed: number
  current_step_duration_seconds: number
  planned_total_seconds: number
  step_remaining_seconds: number
  total_elapsed_seconds: number
  last_error: string | null
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
  mcm_slope_sts: number
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
  cycle_test: CycleTestStatus
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

/** 驻坡状态反馈 */
export const MCM_SLOPE_STATE_MAP: Record<number, string> = {
  0: '未驻坡',
  1: '驻坡中',
}

/**
 * MCU 故障代码表单项定义 (对应《DFAC 控制器故障代码-AMB2(2).xlsx》DEF 三列)
 * - 列 E: 故障码 (DisplayCode 仪表显示码，如 "MCU_64")
 * - 列 D: 含义 (DTC Meaning，如 "VCE过流故障")
 * - 列 F: 故障级别 (FaultLevel，如 "三级 (Fault)")
 */
export interface McuFaultCodeItem {
  code: string
  meaning: string
  level: string
  raw_code: number
}

/**
 * 完整 MCU 故障代码表 (共 22 项，仅呈现 DEF 三列核心信息)
 */
export const MCU_FAULT_CODES: readonly McuFaultCodeItem[] = [
  { code: 'MCU_64', meaning: 'VCE过流故障', level: '三级 (Fault)', raw_code: 64 },
  { code: 'MCU_79', meaning: '相电流值零漂故障', level: '三级 (Fault)', raw_code: 79 },
  { code: 'MCU_85', meaning: '相电流值零漂故障', level: '三级 (Fault)', raw_code: 85 },
  { code: 'MCU_170', meaning: 'HVDC软件过压故障', level: '三级 (Fault)', raw_code: 170 },
  { code: 'MCU_135', meaning: 'HVDC欠压故障', level: '三级 (Fault)', raw_code: 135 },
  { code: 'MCU_88', meaning: '低压蓄电池过压故障', level: '三级 (Fault)', raw_code: 88 },
  { code: 'MCU_89', meaning: '低压蓄电池欠压故障', level: '三级 (Fault)', raw_code: 89 },
  { code: 'MCU_73', meaning: 'IGBT模块温度检测电路输出电压高(断路)', level: '二级 (Limp)', raw_code: 73 },
  { code: 'MCU_74', meaning: 'IGBT模块温度检测电路输出电压低(短路)', level: '二级 (Limp)', raw_code: 74 },
  { code: 'MCU_72', meaning: 'IGBT采样温度过温故障', level: '二级 (Limp)', raw_code: 72 },
  { code: 'MCU_11', meaning: 'IGBT采样温度降额', level: '二级 (Derat)', raw_code: 11 },
  { code: 'MCU_106', meaning: '电机定子温度传感器1电路输出电压低(短路)', level: '二级 (Limp)', raw_code: 106 },
  { code: 'MCU_105', meaning: '电机定子温度传感器1电路输出电压高(断路)', level: '二级 (Limp)', raw_code: 105 },
  { code: 'MCU_31', meaning: 'L2电机定子温度过温', level: '三级 (Fault)', raw_code: 31 },
  { code: 'MCU_7', meaning: '电机定子温度降额', level: '二级 (Derat)', raw_code: 7 },
  { code: 'MCU_46', meaning: 'VCU节点丢失故障', level: '三级 (Fault)', raw_code: 46 },
  { code: 'MCU_104', meaning: '电机超速故障', level: '三级 (Fault)', raw_code: 104 },
  { code: 'MCU_144', meaning: '控制器堵转过载降额', level: '二级 (Derat)', raw_code: 144 },
  { code: 'MCU_103', meaning: '输出缺相故障', level: '三级 (Fault)', raw_code: 103 },
  { code: 'MCU_139', meaning: 'HVDC过压降额故障', level: '二级 (Derat)', raw_code: 139 },
  { code: 'MCU_140', meaning: 'HVDC欠压降额故障', level: '二级 (Derat)', raw_code: 140 },
  { code: 'MCU_142', meaning: '超速降额故障', level: '二级 (Derat)', raw_code: 142 },
] as const

/** 原始故障数值映射字典 */
export const MCU_FAULT_MAP: Record<number, McuFaultCodeItem> = Object.fromEntries(
  MCU_FAULT_CODES.map((item) => [item.raw_code, item]),
)

/** 根据 CAN 故障码数值获取故障详细信息 */
export function getMcuFaultInfo(rawCode: number): McuFaultCodeItem | undefined {
  return MCU_FAULT_MAP[rawCode]
}
