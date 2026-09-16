import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  clearCanFrames,
  connectCan,
  disconnectCan,
  emergencyStop,
  getAxleStatus,
  getAxleStreamUrl,
  sendRawCanFrame,
  updateCommand,
} from '@/api/axle'
import type {
  AxleTelemetry,
  CanConnectRequest,
  CanSendRawFrameRequest,
  VcuCommandUpdateRequest,
} from '@/types/axle'

const createInitialTelemetry = (): AxleTelemetry => ({
  connected: false,
  is_transmitting: false,
  is_emergency_locked: false,
  device_type: 4,
  device_index: 0,
  channel: 0,
  baud_rate: 500000,
  command: {
    torque_req: 0,
    speed_req: 0,
    work_mode_req: 3,
    mcu_en_cmd: 0,
    gear_sts: 3,
    active_discharge: 0,
    life: 0,
  },
  mcu_1: {
    mcu_dc_main_wire_volt: 0,
    mcu_dc_main_wire_curr: 0,
    mcu_integ_ctr_flt_num: 0,
    mcu_flt_code: 0,
    mcu_flt_levl: 0,
    mcu_life_1: 0,
    mcu_tbox_flt_levl: 0,
  },
  mcu_1_last_rx_timestamp: null,
  mcu_2: {
    mcu_motor_tor_max: 0,
    mcu_act_motor_spd: 0,
    mcu_act_motor_tq: 0,
    mcu_active_dischrg_sts: 3,
    mcu_motor_work_mod: 0,
    mcu_lv_sts: 0,
    mcu_en_sts: 0,
    mcu_motor_temp_extre_over: 0,
    mcu_mcu_temp_extre_over: 0,
    mcm_slope_sts: 0,
    mcu_life_2: 0,
  },
  mcu_2_last_rx_timestamp: null,
  mcu_tbox: {
    num_mtr: 1,
    num_mtr_srl: 1,
    st_mtr: 3,
    mcu_motor_temp: 25,
    mcu_ctller_temp: 25,
    mcu_tbox_life: 0,
  },
  mcu_tbox_last_rx_timestamp: null,
  safety: {
    config: {
      enabled: true,
      max_motor_speed_rpm: 3000,
      max_motor_torque_nm: 10,
      max_motor_temp_c: 150,
    },
    last_trip: null,
  },
  tx_frame_count: 0,
  rx_frame_count: 0,
  tx_error_count: 0,
  last_rx_timestamp: null,
  recent_frames: [],
  updated_at: '',
})

export interface HistoryPoint {
  time: string
  speed: number
  torque: number
  voltage: number
  current: number
}

export const useAxleStore = defineStore('axle', () => {
  const telemetry = ref<AxleTelemetry>(createInitialTelemetry())
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)
  const sseConnected = ref<boolean>(false)

  // 历史遥测序列（用于 ECharts 图表展示，保留最近 60 个点）
  const historySeries = ref<HistoryPoint[]>([])

  let eventSource: EventSource | null = null
  let shouldIncludeCanFrames = false
  let eventSourceIncludesCanFrames = false

  const isConnected = computed(() => telemetry.value.connected)
  const isTransmitting = computed(() => telemetry.value.is_transmitting)

  /** 开启 SSE 遥测实时流 */
  function startSse(includeCanFrames?: boolean) {
    if (includeCanFrames !== undefined) {
      shouldIncludeCanFrames = includeCanFrames
    }

    if (eventSource && eventSourceIncludesCanFrames === shouldIncludeCanFrames) {
      return
    }

    if (eventSource) {
      eventSource.close()
      eventSource = null
    }

    eventSourceIncludesCanFrames = shouldIncludeCanFrames
    const url = getAxleStreamUrl(shouldIncludeCanFrames)
    eventSource = new EventSource(url)

    eventSource.onopen = () => {
      sseConnected.value = true
      error.value = null
    }

    eventSource.addEventListener('telemetry', (event) => {
      try {
        const data = JSON.parse(event.data) as AxleTelemetry
        telemetry.value = data

        // 记录历史数据
        const now = new Date()
        const timeLabel = `${now.getMinutes().toString().padStart(2, '0')}:${now
          .getSeconds()
          .toString()
          .padStart(2, '0')}.${Math.floor(now.getMilliseconds() / 100)}`

        historySeries.value.push({
          time: timeLabel,
          speed: data.mcu_2.mcu_act_motor_spd,
          torque: data.mcu_2.mcu_act_motor_tq,
          voltage: data.mcu_1.mcu_dc_main_wire_volt,
          current: data.mcu_1.mcu_dc_main_wire_curr,
        })

        if (historySeries.value.length > 60) {
          historySeries.value.shift()
        }
      } catch (err) {
        console.error('解析遥测 SSE 数据异常:', err)
      }
    })

    eventSource.onerror = () => {
      sseConnected.value = false
    }
  }

  /** 关闭 SSE 流 */
  function stopSse() {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    sseConnected.value = false
  }

  /** 连接周立功 CAN 卡 */
  async function connect(config: CanConnectRequest) {
    loading.value = true
    error.value = null
    try {
      await connectCan(config).send()
      await refreshStatus()
      startSse()
    } catch (err) {
      error.value = err instanceof Error ? err.message : '连接硬件异常'
      throw err
    } finally {
      loading.value = false
    }
  }

  /** 断开 CAN 卡 */
  async function disconnect() {
    loading.value = true
    error.value = null
    stopSse()  // 断开连接时同步关闭 SSE 流
    try {
      await disconnectCan().send()
      await refreshStatus()
    } catch (err) {
      error.value = err instanceof Error ? err.message : '断开连接异常'
      throw err
    } finally {
      loading.value = false
    }
  }

  /** 发送上位机控制参数更新 */
  async function sendCommand(update: VcuCommandUpdateRequest) {
    loading.value = true
    error.value = null
    try {
      const updated = await updateCommand(update).send()
      telemetry.value.command = updated
    } catch (err) {
      error.value = err instanceof Error ? err.message : '下发控制指令异常'
      throw err
    } finally {
      loading.value = false
    }
  }

  /** 紧急停机 */
  async function triggerEmergencyStop() {
    loading.value = true
    error.value = null
    try {
      const updated = await emergencyStop().send()
      telemetry.value.command = updated
    } catch (err) {
      error.value = err instanceof Error ? err.message : '紧急停机异常'
      throw err
    } finally {
      loading.value = false
    }
  }

  /** 手动拉取一次系统状态快照 */
  async function refreshStatus() {
    try {
      const data = await getAxleStatus().send()
      telemetry.value = data
    } catch (err) {
      console.warn('获取状态异常:', err)
    }
  }

  /** 手动发送单帧测试/诊断报文 */
  async function sendRawFrame(req: CanSendRawFrameRequest) {
    loading.value = true
    error.value = null
    try {
      const res = await sendRawCanFrame(req).send()
      return res
    } catch (err) {
      error.value = err instanceof Error ? err.message : '发送原始报文异常'
      throw err
    } finally {
      loading.value = false
    }
  }

  /** 清空最近报文监控缓冲区 */
  async function clearFrames() {
    try {
      await clearCanFrames().send()
      telemetry.value.recent_frames = []
    } catch (err) {
      console.warn('清空报文缓冲区异常:', err)
    }
  }

  return {
    telemetry,
    loading,
    error,
    sseConnected,
    historySeries,
    isConnected,
    isTransmitting,
    startSse,
    stopSse,
    connect,
    disconnect,
    sendCommand,
    triggerEmergencyStop,
    refreshStatus,
    sendRawFrame,
    clearFrames,
  }
})
