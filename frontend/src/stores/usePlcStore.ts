import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  connectPlc,
  disconnectPlc,
  getPlcStatus,
  plcPowerOff,
  plcPowerOn,
  setSimulatedSafe,
} from '@/api/plc'
import type { PlcActionResponse, PlcConfig, PlcStatus } from '@/types/plc'

export const PLC_STATUS_POLL_MS = 500

export type PlcOperation = 'connect' | 'disconnect' | 'power-on' | 'power-off'

export const createInitialPlcStatus = (): PlcStatus => ({
  connected: false,
  simulation: false,
  ip: '192.168.8.1',
  rack: 0,
  slot: 1,
  communication_ok: false,
  communication_error: null,
  plc_heartbeat_alive: false,
  safe: false,
  request_power: false,
  power_on: false,
  contactor_closed: false,
  product_type_expected: 1,
  product_type_feedback: 0,
  target_voltage: 340,
  output_voltage: 0,
  output_current: 0,
  serial_number: '',
  power_state: 'idle',
  fault_reason: null,
  last_message: null,
})

export const usePlcStore = defineStore('plc', () => {
  const status = ref<PlcStatus>(createInitialPlcStatus())
  /**
   * 各操作是否进行中。上电最长要等 30 s，期间允许下电打断上电，
   * 两者可能同时进行，所以分别记录而不是只记一个“当前操作”。
   */
  const pending = ref<Record<PlcOperation, boolean>>({
    connect: false,
    disconnect: false,
    'power-on': false,
    'power-off': false,
  })

  let pollTimer: ReturnType<typeof setInterval> | undefined
  let refreshing = false

  const isPowered = computed(() => status.value.power_state === 'powered')
  const isBusy = computed(() => Object.values(pending.value).some(Boolean))

  /** 拉取后端内存快照；上一次未返回时跳过，避免请求堆积 */
  async function refresh() {
    if (refreshing) return
    refreshing = true
    try {
      status.value = await getPlcStatus().send()
    } catch {
      // 后端暂不可用时保留上一次状态，下次轮询再试
    } finally {
      refreshing = false
    }
  }

  function startPolling(intervalMs = PLC_STATUS_POLL_MS) {
    if (pollTimer) return
    void refresh()
    pollTimer = setInterval(() => void refresh(), intervalMs)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = undefined
    }
  }

  async function run<T>(name: PlcOperation, action: () => Promise<T>): Promise<T> {
    pending.value[name] = true
    try {
      return await action()
    } finally {
      pending.value[name] = false
    }
  }

  const connect = (config: PlcConfig) =>
    run('connect', async () => {
      status.value = await connectPlc(config).send()
    })

  const disconnect = () =>
    run('disconnect', async () => {
      status.value = await disconnectPlc().send()
    })

  const powerOn = () =>
    run('power-on', async (): Promise<PlcActionResponse> => {
      const result = await plcPowerOn().send()
      status.value = result.plc
      return result
    })

  const powerOff = () =>
    run('power-off', async (): Promise<PlcActionResponse> => {
      const result = await plcPowerOff().send()
      status.value = result.plc
      return result
    })

  async function setSafeSimulation(safe: boolean) {
    status.value = await setSimulatedSafe(safe).send()
  }

  return {
    status,
    pending,
    isPowered,
    isBusy,
    refresh,
    startPolling,
    stopPolling,
    connect,
    disconnect,
    powerOn,
    powerOff,
    setSafeSimulation,
  }
})
