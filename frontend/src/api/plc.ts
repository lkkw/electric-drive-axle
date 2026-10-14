import type {
  PlcActionResponse,
  PlcConfig,
  PlcStatus,
  PlcTrafficLog,
  PlcTrafficSnapshot,
} from '@/types/plc'
import { alova } from '@/utils/alova'

/** PLC 连接与供电状态（后端内存快照，不产生 PLC 通讯） */
export const getPlcStatus = () => alova.Get<PlcStatus>('/plc/status', { cacheFor: 0 })

/** 上次保存的 PLC 连接参数 */
export const getPlcConfig = () => alova.Get<PlcConfig>('/plc/config', { cacheFor: 0 })

/** 连接 PLC（参数会被保存） */
export const connectPlc = (config: PlcConfig) => alova.Post<PlcStatus>('/plc/connect', config)

/** 断开 PLC（台架供电中会被拒绝） */
export const disconnectPlc = () => alova.Post<PlcStatus>('/plc/disconnect', {})

/** PLC 自动上电（340 V），最长等待 30 s */
export const plcPowerOn = () => alova.Post<PlcActionResponse>('/plc/power-on', {})

/** PLC 下电：先关闭电机使能，再复位上电请求 */
export const plcPowerOff = () => alova.Post<PlcActionResponse>('/plc/power-off', {})

/** 仿真模式下模拟安全回路闭合 / 断开 */
export const setSimulatedSafe = (safe: boolean) =>
  alova.Post<PlcStatus>('/plc/simulation/safe', { safe })

/** PLC 通信监视：1 号工位全部点位的最新值 */
export const getPlcTrafficSnapshot = () =>
  alova.Get<PlcTrafficSnapshot>('/plc/traffic/snapshot', { cacheFor: 0 })

/** PLC 通信记录：只返回序号大于 afterSeq 的新记录 */
export const getPlcTrafficLog = (afterSeq: number) =>
  alova.Get<PlcTrafficLog>('/plc/traffic/log', { params: { after_seq: afterSeq }, cacheFor: 0 })

/** 清空 PLC 通信记录 */
export const clearPlcTrafficLog = () => alova.Delete('/plc/traffic/log')
