<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { AlertTriangleIcon, PlugIcon, PowerIcon, PowerOffIcon, UnplugIcon } from '@lucide/vue'
import { toast } from 'vue-sonner'

import { getPlcConfig } from '@/api/plc'
import PlcTrafficMonitor from '@/components/plc/PlcTrafficMonitor.vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge, type BadgeVariants } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { usePlcStore } from '@/stores/usePlcStore'
import { POWER_STATE_LABEL, type PlcActionResponse, type PlcConfig } from '@/types/plc'

type BadgeVariant = NonNullable<BadgeVariants['variant']>

interface StatusRow {
  label: string
  value: string
  variant?: BadgeVariant
}

const IPV4_PATTERN = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/

const plc = usePlcStore()
const status = computed(() => plc.status)

const form = reactive<PlcConfig>({ ip: '192.168.8.1', rack: 0, slot: 1, simulation: false })
// 对话框开关与确认的操作分开记录：关闭动画期间内容保持不变，不会闪出另一个操作的文案
const confirmOpen = ref(false)
const confirmAction = ref<'power-on' | 'power-off'>('power-on')

function openConfirm(action: 'power-on' | 'power-off') {
  confirmAction.value = action
  confirmOpen.value = true
}

const ipInvalid = computed(() => !IPV4_PATTERN.test(String(form.ip).trim()))
const rackInvalid = computed(() => !Number.isInteger(form.rack) || form.rack < 0 || form.rack > 7)
const slotInvalid = computed(() => !Number.isInteger(form.slot) || form.slot < 0 || form.slot > 31)
const formInvalid = computed(() => ipInvalid.value || rackInvalid.value || slotInvalid.value)

const connectionBadge = computed<{ label: string; variant: BadgeVariant }>(() => {
  const s = status.value
  if (!s.connected) return { label: '未连接', variant: 'secondary' }
  if (!s.communication_ok) return { label: '通信中断', variant: 'destructive' }
  return s.simulation
    ? { label: '本地仿真', variant: 'info' }
    : { label: '已连接', variant: 'success' }
})

const powerBadge = computed<{ label: string; variant: BadgeVariant }>(() => {
  const state = status.value.power_state
  const variant: Record<typeof state, BadgeVariant> = {
    idle: 'secondary',
    powering_on: 'info',
    powered: 'warning',
    powering_off: 'info',
    fault: 'destructive',
  }
  return { label: POWER_STATE_LABEL[state], variant: variant[state] }
})

/** PLC 反馈；通信中断时显示“未知”，不展示陈旧值 */
const feedbackRows = computed<StatusRow[]>(() => {
  const s = status.value
  if (!s.connected || !s.communication_ok) {
    return ['安全回路 (Safe)', '上电请求', '上电完成', '主接触器'].map((label) => ({
      label,
      value: '未知',
      variant: 'secondary' as const,
    }))
  }
  return [
    {
      label: '安全回路 (Safe)',
      value: s.safe ? '闭合' : '断开',
      variant: s.safe ? 'success' : 'destructive',
    },
    {
      label: '上电请求',
      value: s.request_power ? '已请求' : '未请求',
      variant: s.request_power ? 'info' : 'secondary',
    },
    {
      label: '上电完成',
      value: s.power_on ? '是' : '否',
      variant: s.power_on ? 'warning' : 'secondary',
    },
    {
      label: '主接触器',
      value: s.contactor_closed ? '吸合' : '断开',
      variant: s.contactor_closed ? 'warning' : 'secondary',
    },
  ]
})

const readingRows = computed<StatusRow[]>(() => {
  const s = status.value
  const known = s.connected && s.communication_ok
  const productMismatch = known && s.power_on && s.product_type_feedback !== s.product_type_expected
  return [
    {
      label: `输出电压（目标 ${s.target_voltage} V）`,
      value: known ? `${s.output_voltage} V` : '--',
    },
    { label: '输出电流', value: known ? String(s.output_current) : '--' },
    {
      label: `产品编号反馈（应为 ${s.product_type_expected}）`,
      value: known ? String(s.product_type_feedback) : '--',
      variant: productMismatch ? 'destructive' : undefined,
    },
    { label: '产品序列号', value: known && s.serial_number ? s.serial_number : '--' },
  ]
})

const canPowerOn = computed(
  () =>
    status.value.connected &&
    status.value.communication_ok &&
    !plc.isBusy &&
    status.value.power_state !== 'powered',
)

/** 上电进行中也允许下电（下电优先，会中止上电） */
const canPowerOff = computed(() => {
  const s = status.value
  return (
    s.connected &&
    !plc.pending['power-off'] &&
    (plc.pending['power-on'] || s.request_power || s.power_on || s.contactor_closed)
  )
})

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : '请稍后重试'
}

function notifyResult(result: PlcActionResponse) {
  if (result.status === 'success') toast.success(result.message)
  else toast.warning(result.message, { duration: 8000 })
}

async function handleConnect() {
  if (formInvalid.value) return
  try {
    await plc.connect({ ...form, ip: form.ip.trim() })
    toast.success(form.simulation ? 'PLC 本地仿真已启动' : `PLC ${form.ip} 已连接`)
  } catch (err) {
    toast.error('连接 PLC 失败', { description: errorMessage(err), duration: 8000 })
  }
}

async function handleDisconnect() {
  try {
    await plc.disconnect()
    toast.success('PLC 已断开')
  } catch (err) {
    toast.error('断开 PLC 失败', { description: errorMessage(err) })
  }
}

async function handleConfirm() {
  const action = confirmAction.value
  confirmOpen.value = false
  try {
    const result = action === 'power-on' ? await plc.powerOn() : await plc.powerOff()
    notifyResult(result)
  } catch (err) {
    toast.error(action === 'power-on' ? '上电失败' : '下电失败', {
      description: errorMessage(err),
      duration: 8000,
    })
  }
}

async function handleSimulatedSafe(safe: boolean) {
  try {
    await plc.setSafeSimulation(safe)
  } catch (err) {
    toast.error('切换仿真安全回路失败', { description: errorMessage(err) })
  }
}

onMounted(async () => {
  try {
    Object.assign(form, await getPlcConfig().send())
  } catch {
    // 读取失败时保留默认值
  }
})
</script>

<template>
  <div class="grid w-full grid-cols-1 gap-6 lg:grid-cols-12">
    <!-- PLC 连接 -->
    <Card class="lg:col-span-5">
      <CardHeader class="border-b pb-3">
        <div class="flex items-center justify-between gap-2">
          <CardTitle>PLC 连接</CardTitle>
          <div class="flex items-center gap-2">
            <Badge v-if="status.connected && status.communication_ok" :variant="status.plc_heartbeat_alive ? 'outline' : 'secondary'">
              {{ status.plc_heartbeat_alive ? 'PLC 心跳正常' : 'PLC 心跳未跳变' }}
            </Badge>
            <Badge :variant="connectionBadge.variant">{{ connectionBadge.label }}</Badge>
          </div>
        </div>
        <CardDescription>西门子 S7-1500，DB40 · dbPC，参数保存在本机。</CardDescription>
      </CardHeader>

      <CardContent class="flex-1 pt-5">
        <FieldGroup>
          <Field :data-invalid="ipInvalid || undefined" :data-disabled="status.connected || undefined">
            <FieldLabel for="plc-ip">IP 地址</FieldLabel>
            <Input
              id="plc-ip"
              v-model="form.ip"
              class="font-mono"
              :disabled="status.connected || plc.isBusy"
              :aria-invalid="ipInvalid || undefined"
            />
            <FieldError v-if="ipInvalid">请输入有效的 IPv4 地址，例如 192.168.8.1</FieldError>
          </Field>

          <div class="grid grid-cols-2 gap-4">
            <Field :data-invalid="rackInvalid || undefined" :data-disabled="status.connected || undefined">
              <FieldLabel for="plc-rack">机架号 (Rack)</FieldLabel>
              <Input
                id="plc-rack"
                v-model.number="form.rack"
                type="number"
                min="0"
                max="7"
                class="font-mono"
                :disabled="status.connected || plc.isBusy"
                :aria-invalid="rackInvalid || undefined"
              />
            </Field>
            <Field :data-invalid="slotInvalid || undefined" :data-disabled="status.connected || undefined">
              <FieldLabel for="plc-slot">槽号 (Slot)</FieldLabel>
              <Input
                id="plc-slot"
                v-model.number="form.slot"
                type="number"
                min="0"
                max="31"
                class="font-mono"
                :disabled="status.connected || plc.isBusy"
                :aria-invalid="slotInvalid || undefined"
              />
            </Field>
          </div>

          <Field orientation="horizontal" :data-disabled="status.connected || undefined">
            <Switch
              id="plc-simulation"
              v-model="form.simulation"
              :disabled="status.connected || plc.isBusy"
            />
            <FieldContent>
              <FieldLabel for="plc-simulation">本地仿真</FieldLabel>
              <FieldDescription>不连接真实 PLC，用于演练和联调前检查。</FieldDescription>
            </FieldContent>
          </Field>

          <Field v-if="status.connected && status.simulation" orientation="horizontal">
            <Switch
              id="plc-sim-safe"
              :model-value="status.safe"
              @update:model-value="(v) => handleSimulatedSafe(Boolean(v))"
            />
            <FieldContent>
              <FieldLabel for="plc-sim-safe">仿真：安全回路闭合</FieldLabel>
              <FieldDescription>关闭即模拟 Safe 断开，验证自动切断高压与急停。</FieldDescription>
            </FieldContent>
          </Field>
        </FieldGroup>
      </CardContent>

      <CardFooter class="justify-end gap-2">
        <Button
          v-if="!status.connected"
          class="h-10"
          :disabled="formInvalid || plc.isBusy"
          @click="handleConnect"
        >
          <Spinner v-if="plc.pending.connect" data-icon="inline-start" />
          <PlugIcon v-else data-icon="inline-start" />
          连接 PLC
        </Button>
        <Button v-else variant="outline" class="h-10" :disabled="plc.isBusy" @click="handleDisconnect">
          <Spinner v-if="plc.pending.disconnect" data-icon="inline-start" />
          <UnplugIcon v-else data-icon="inline-start" />
          断开 PLC
        </Button>
      </CardFooter>
    </Card>

    <!-- 高压供电 -->
    <Card class="lg:col-span-7">
      <CardHeader class="border-b pb-3">
        <div class="flex items-center justify-between gap-2">
          <CardTitle>高压供电（{{ status.target_voltage }} V）</CardTitle>
          <Badge :variant="powerBadge.variant">{{ powerBadge.label }}</Badge>
        </div>
        <CardDescription>
          上电前确认安全回路闭合；下电时先关闭电机使能，再断开高压。
        </CardDescription>
      </CardHeader>

      <CardContent class="flex flex-1 flex-col gap-5 pt-5">
        <Alert v-if="status.power_state === 'fault' && status.fault_reason" variant="destructive">
          <AlertTriangleIcon />
          <AlertTitle>供电故障</AlertTitle>
          <AlertDescription>{{ status.fault_reason }}</AlertDescription>
        </Alert>

        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <section class="flex flex-col rounded-lg border">
            <h3 class="px-4 pt-3 text-sm font-medium text-foreground">PLC 反馈</h3>
            <dl class="flex flex-col gap-3 px-4 pt-3 pb-4">
              <div
                v-for="row in feedbackRows"
                :key="row.label"
                class="flex items-center justify-between gap-3 text-sm"
              >
                <dt class="text-muted-foreground">{{ row.label }}</dt>
                <dd><Badge :variant="row.variant">{{ row.value }}</Badge></dd>
              </div>
            </dl>
          </section>

          <section class="flex flex-col rounded-lg border">
            <h3 class="px-4 pt-3 text-sm font-medium text-foreground">电源与产品</h3>
            <dl class="flex flex-col gap-3 px-4 pt-3 pb-4">
              <div
                v-for="row in readingRows"
                :key="row.label"
                class="flex items-center justify-between gap-3 text-sm"
              >
                <dt class="shrink-0 text-muted-foreground">{{ row.label }}</dt>
                <dd class="min-w-0 text-right">
                  <Badge v-if="row.variant" :variant="row.variant">{{ row.value }}</Badge>
                  <span v-else class="block truncate font-mono text-foreground">{{ row.value }}</span>
                </dd>
              </div>
            </dl>
          </section>
        </div>

        <p v-if="status.last_message" class="text-sm text-muted-foreground">
          最近操作：{{ status.last_message }}
        </p>
      </CardContent>

      <CardFooter class="grid grid-cols-2 gap-3">
        <Button class="h-10" :disabled="!canPowerOn" @click="openConfirm('power-on')">
          <Spinner v-if="plc.pending['power-on']" data-icon="inline-start" />
          <PowerIcon v-else data-icon="inline-start" />
          {{ plc.pending['power-on'] ? '上电中（最长 30 s）…' : 'PLC 上电' }}
        </Button>
        <Button
          variant="outline"
          class="h-10"
          :disabled="!canPowerOff"
          @click="openConfirm('power-off')"
        >
          <Spinner v-if="plc.pending['power-off']" data-icon="inline-start" />
          <PowerOffIcon v-else data-icon="inline-start" />
          {{ plc.pending['power-off'] ? '下电中…' : '下电' }}
        </Button>
      </CardFooter>
    </Card>

    <!-- 联调用：上位机与 PLC 双方收发情况 -->
    <PlcTrafficMonitor class="lg:col-span-12" />

    <!-- 上电 / 下电二次确认 -->
    <Dialog v-model:open="confirmOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ confirmAction === 'power-on' ? 'PLC 上电' : 'PLC 下电' }}</DialogTitle>
          <DialogDescription v-if="confirmAction === 'power-on'">
            将通过 PLC 给台架接通 {{ status.target_voltage }} V 高压。请确认人员已离开高压区域、线束连接可靠。
          </DialogDescription>
          <DialogDescription v-else>
            将先关闭电机使能，再断开高压。电机仍在转动时，建议先在电驱桥控制台点“停机”，等电机停稳后再下电。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="confirmOpen = false">取消</Button>
          <Button
            :variant="confirmAction === 'power-on' ? 'default' : 'destructive'"
            @click="handleConfirm"
          >
            {{ confirmAction === 'power-on' ? '确认上电' : '确认下电' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
