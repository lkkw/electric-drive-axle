<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { Badge, type BadgeVariants } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import FaultCodeDialog from "@/components/axle/FaultCodeDialog.vue";
import { useAxleStore } from "@/stores/useAxleStore";
import {
  FAULT_LEVEL_MAP,
  getMcuFaultInfo,
  TBOX_FAULT_LEVEL_MAP,
  WORK_MODE_MAP,
} from "@/types/axle";

type BadgeVariant = NonNullable<BadgeVariants["variant"]>;

interface MetricTile {
  label: string;
  value: string;
  unit: string;
}

interface StatusRow {
  label: string;
  value: string;
  /** 不提供时按普通数值展示，提供时以对应 Badge 变体展示 */
  variant?: BadgeVariant;
}

interface StatusGroup {
  title: string;
  canId: string;
  rows: StatusRow[];
}

const axleStore = useAxleStore();

/** 界面刷新节流周期 (ms)，降低高频 CAN 数据导致的 UI 渲染开销 */
const DISPLAY_REFRESH_INTERVAL_MS = 200;
/** 反馈新鲜度裕量：0x35B 周期 10 ms，0x35A / 0x35C 周期 100 ms */
const MCU_2_FRESH_MS = 500;
const MCU_1_FRESH_MS = 1000;
const MCU_TBOX_FRESH_MS = 1000;
const PLACEHOLDER = "--";

const mcu1 = ref({ ...axleStore.telemetry.mcu_1 });
const mcu2 = ref({ ...axleStore.telemetry.mcu_2 });
const tbox = ref({ ...axleStore.telemetry.mcu_tbox });
const activeFaultInfo = computed(() => getMcuFaultInfo(mcu1.value.mcu_flt_code));

const feedbackClock = ref(Date.now());
let displayRefreshTimer: ReturnType<typeof setInterval> | undefined;

function formatDecimal(val: number | null | undefined, precision = 1): string {
  const num = Number(val);
  return Number.isFinite(num) ? num.toFixed(precision) : (0).toFixed(precision);
}

function formatInteger(val: number | null | undefined): string {
  const num = Number(val);
  return Number.isFinite(num) ? Math.round(num).toString() : "0";
}

function refreshDisplayedTelemetry(): void {
  mcu1.value = { ...axleStore.telemetry.mcu_1 };
  mcu2.value = { ...axleStore.telemetry.mcu_2 };
  tbox.value = { ...axleStore.telemetry.mcu_tbox };
  feedbackClock.value = Date.now();
}

onMounted(() => {
  refreshDisplayedTelemetry();
  displayRefreshTimer = setInterval(
    refreshDisplayedTelemetry,
    DISPLAY_REFRESH_INTERVAL_MS,
  );
});

onBeforeUnmount(() => {
  if (displayRefreshTimer) {
    clearInterval(displayRefreshTimer);
  }
});

function isFresh(receivedAt: number | null, marginMs: number): boolean {
  return (
    axleStore.isConnected &&
    receivedAt !== null &&
    feedbackClock.value - receivedAt * 1000 <= marginMs
  );
}

const hasFreshMcu2 = computed(() =>
  isFresh(axleStore.telemetry.mcu_2_last_rx_timestamp, MCU_2_FRESH_MS),
);
const hasFreshMcu1 = computed(() =>
  isFresh(axleStore.telemetry.mcu_1_last_rx_timestamp, MCU_1_FRESH_MS),
);
const hasFreshTbox = computed(() =>
  isFresh(axleStore.telemetry.mcu_tbox_last_rx_timestamp, MCU_TBOX_FRESH_MS),
);

const lowVoltageStatusText = computed(() => {
  if (!hasFreshMcu2.value) return "低压未知";
  return mcu2.value.mcu_lv_sts === 1 ? "低压已上电" : "低压未上电";
});

const enableStatusText = computed(() => {
  if (!hasFreshMcu2.value) return "使能未知";
  return mcu2.value.mcu_en_sts === 1 ? "MCU 已使能" : "MCU 未使能";
});

const workModeStatusText = computed(() => {
  if (!hasFreshMcu2.value) return "模式未知";
  return mcu2.value.mcu_motor_work_mod === 0
    ? "无操作"
    : (WORK_MODE_MAP[mcu2.value.mcu_motor_work_mod] ?? "未知模式");
});

const hasOverTemperature = computed(
  () =>
    hasFreshMcu2.value &&
    (mcu2.value.mcu_motor_temp_extre_over === 1 ||
      mcu2.value.mcu_mcu_temp_extre_over === 1),
);

const isSystemNormal = computed(
  () =>
    hasFreshMcu1.value &&
    mcu1.value.mcu_flt_levl === 0 &&
    mcu1.value.mcu_tbox_flt_levl === 0 &&
    !hasOverTemperature.value,
);

const metricTiles = computed<MetricTile[]>(() => [
  { label: "实际转速", value: formatInteger(mcu2.value.mcu_act_motor_spd), unit: "RPM" },
  { label: "实际转矩", value: formatDecimal(mcu2.value.mcu_act_motor_tq), unit: "Nm" },
  { label: "最大可用转矩", value: formatDecimal(mcu2.value.mcu_motor_tor_max), unit: "Nm" },
  { label: "母线电压", value: formatDecimal(mcu1.value.mcu_dc_main_wire_volt), unit: "V" },
  { label: "母线电流", value: formatDecimal(mcu1.value.mcu_dc_main_wire_curr), unit: "A" },
  {
    label: "电机温度",
    value: hasFreshTbox.value ? formatInteger(tbox.value.mcu_motor_temp) : PLACEHOLDER,
    unit: "℃",
  },
]);

function overTemperatureRow(label: string, flag: number): StatusRow {
  if (!hasFreshMcu2.value) return { label, value: "未知", variant: "secondary" };
  return flag === 1
    ? { label, value: "过温报警", variant: "destructive" }
    : { label, value: "正常", variant: "success" };
}

const statusGroups = computed<StatusGroup[]>(() => {
  const faultCode = mcu1.value.mcu_flt_code;
  const faultLevel = mcu1.value.mcu_flt_levl;
  const tboxLevel = mcu1.value.mcu_tbox_flt_levl;

  return [
    {
      title: "温度监控",
      canId: "0x35B / 0x35C",
      rows: [
        {
          label: "控制器温度",
          value: hasFreshTbox.value
            ? `${formatInteger(tbox.value.mcu_ctller_temp)} ℃`
            : PLACEHOLDER,
        },
        overTemperatureRow("电机过温", mcu2.value.mcu_motor_temp_extre_over),
        overTemperatureRow("控制器过温", mcu2.value.mcu_mcu_temp_extre_over),
        hasFreshMcu1.value
          ? {
              label: "温度故障等级",
              value: TBOX_FAULT_LEVEL_MAP[tboxLevel] ?? `等级 ${tboxLevel}`,
              variant: tboxLevel === 0 ? "success" : "destructive",
            }
          : { label: "温度故障等级", value: "未知", variant: "secondary" },
      ],
    },
    {
      title: "故障诊断",
      canId: "0x35A",
      rows: hasFreshMcu1.value
        ? [
            {
              label: "故障代码",
              value:
                faultCode === 0
                  ? "无"
                  : `0x${faultCode.toString(16).toUpperCase()} · ${activeFaultInfo.value?.code ?? "未知"}`,
              variant: faultCode === 0 ? "success" : "destructive",
            },
            {
              label: "故障含义",
              value: faultCode === 0 ? "—" : (activeFaultInfo.value?.meaning ?? "故障表未收录"),
            },
            {
              label: "故障等级",
              value: FAULT_LEVEL_MAP[faultLevel]?.text ?? `等级 ${faultLevel}`,
              variant: faultLevel === 0 ? "success" : "destructive",
            },
            { label: "故障个数", value: formatInteger(mcu1.value.mcu_integ_ctr_flt_num) },
          ]
        : [
            { label: "故障代码", value: "未知", variant: "secondary" },
            { label: "故障含义", value: PLACEHOLDER },
            { label: "故障等级", value: "未知", variant: "secondary" },
            { label: "故障个数", value: PLACEHOLDER },
          ],
    },
  ];
});
</script>

<template>
  <Card class="h-full flex flex-col">
    <!-- 顶部状态栏 -->
    <CardHeader class="border-b pb-3">
      <!-- 第一行：标题 + 故障报警与安全指示 -->
      <div class="flex flex-wrap items-center justify-between gap-2">
        <CardTitle>MCU 实时反馈</CardTitle>
        <div class="flex flex-wrap items-center gap-2">
          <Badge v-if="isSystemNormal" variant="success">系统正常</Badge>
          <Badge v-else-if="hasFreshMcu1 && mcu1.mcu_flt_levl !== 0" variant="destructive">
            {{ FAULT_LEVEL_MAP[mcu1.mcu_flt_levl]?.text ?? '故障报警' }}
          </Badge>
          <Badge v-if="hasFreshMcu1 && mcu1.mcu_tbox_flt_levl !== 0" variant="destructive">
            {{ TBOX_FAULT_LEVEL_MAP[mcu1.mcu_tbox_flt_levl] ?? '温度报警' }}
          </Badge>
          <Badge v-if="hasOverTemperature" variant="destructive">过温故障</Badge>
          <FaultCodeDialog :current-flt-code="mcu1.mcu_flt_code" />
        </div>
      </div>

      <!-- 第二行：0x35B 上电、使能与模式反馈 -->
      <div class="flex flex-wrap items-center gap-2">
        <Badge :variant="hasFreshMcu2 && mcu2.mcu_lv_sts === 1 ? 'success' : 'secondary'">
          {{ lowVoltageStatusText }}
        </Badge>
        <Badge :variant="hasFreshMcu2 && mcu2.mcu_en_sts === 1 ? 'success' : 'secondary'">
          {{ enableStatusText }}
        </Badge>
        <Badge :variant="hasFreshMcu2 && mcu2.mcu_motor_work_mod !== 0 ? 'info' : 'secondary'">
          {{ workModeStatusText }}
        </Badge>
      </div>
    </CardHeader>

    <CardContent class="@container flex flex-1 flex-col gap-5 p-4 sm:p-5">
      <!-- 动力、电气与温度核心数值 -->
      <div class="grid grid-cols-2 gap-3 @sm:grid-cols-3">
        <div
          v-for="tile in metricTiles"
          :key="tile.label"
          class="flex flex-col gap-1 rounded-lg border bg-muted/30 p-3"
        >
          <span class="text-xs text-muted-foreground">{{ tile.label }}</span>
          <div class="flex items-baseline justify-between gap-2">
            <span class="truncate font-mono text-xl font-semibold tabular-nums text-foreground">
              {{ tile.value }}
            </span>
            <span class="shrink-0 text-xs text-muted-foreground">{{ tile.unit }}</span>
          </div>
        </div>
      </div>

      <!-- 运行监控与状态诊断：两组宽松键值列表 -->
      <div class="grid flex-1 grid-cols-1 gap-4 @md:grid-cols-2">
        <section
          v-for="group in statusGroups"
          :key="group.title"
          class="flex flex-col rounded-lg border"
        >
          <div class="flex items-center justify-between px-4 pt-3">
            <h3 class="text-sm font-medium text-foreground">{{ group.title }}</h3>
            <span class="font-mono text-xs text-muted-foreground">{{ group.canId }}</span>
          </div>
          <dl class="flex flex-col gap-3 px-4 pt-3 pb-4">
            <div
              v-for="row in group.rows"
              :key="row.label"
              class="flex items-center justify-between gap-3 text-sm"
            >
              <dt class="shrink-0 text-muted-foreground">{{ row.label }}</dt>
              <dd class="min-w-0 text-right">
                <Badge v-if="row.variant" :variant="row.variant">{{ row.value }}</Badge>
                <span v-else class="block truncate font-mono text-foreground" :title="row.value">
                  {{ row.value }}
                </span>
              </dd>
            </div>
          </dl>
        </section>
      </div>
    </CardContent>
  </Card>
</template>
