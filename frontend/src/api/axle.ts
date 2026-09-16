import type {
  AxleActionResponse,
  AxleSafetyConfig,
  AxleTelemetry,
  CanConnectRequest,
  CanSendRawFrameRequest,
  McuFaultCodeItem,
  VcuCommandState,
  VcuCommandUpdateRequest,
} from '@/types/axle'
import { alova, API_BASE_URL } from '@/utils/alova'

/** 获取 MCU 故障代码表 (DEF 三列) */
export const getFaultCodes = () =>
  alova.Get<McuFaultCodeItem[]>('/axle/fault-codes', { cacheFor: 3600000 })


/** 连接周立功 USBCAN 设备 */
export const connectCan = (config: CanConnectRequest) =>
  alova.Post<AxleActionResponse>('/axle/connect', config)

/** 断开周立功 USBCAN 设备 */
export const disconnectCan = () =>
  alova.Post<AxleActionResponse>('/axle/disconnect', {})

/** 手动下发单帧 CAN 原始报文 */
export const sendRawCanFrame = (request: CanSendRawFrameRequest) =>
  alova.Post<AxleActionResponse>('/axle/can/send', request)

/** 清空报文监视缓冲区 */
export const clearCanFrames = () =>
  alova.Post<AxleActionResponse>('/axle/can/clear-frames', {})

/** 更新上位机设定值 (转矩/转速/使能/模式/档位) */
export const updateCommand = (update: VcuCommandUpdateRequest) =>
  alova.Post<VcuCommandState>('/axle/command', update)

/** 紧急停机 */
export const emergencyStop = () =>
  alova.Post<VcuCommandState>('/axle/emergency-stop', {})

/** 获取上位机自动紧急停机阈值 */
export const getSafetyConfig = () =>
  alova.Get<AxleSafetyConfig>('/axle/safety/config', { cacheFor: 0 })

/** 更新上位机自动紧急停机阈值 */
export const updateSafetyConfig = (config: AxleSafetyConfig) =>
  alova.Put<AxleSafetyConfig>('/axle/safety/config', config)

/** 获取电驱桥当前遥测快照 (禁用缓存) */
export const getAxleStatus = () =>
  alova.Get<AxleTelemetry>('/axle/status', { cacheFor: 0 })

/** 获取 SSE 实时数据流 URL */
export const getAxleStreamUrl = (includeFrames = false) =>
  `${API_BASE_URL}/axle/stream?include_frames=${includeFrames}`
