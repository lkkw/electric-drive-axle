<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { AlertTriangleIcon } from "@lucide/vue";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import AxleTelemetryChart from "@/components/axle/AxleTelemetryChart.vue";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import FaultCodeDialog from "@/components/axle/FaultCodeDialog.vue";
import { useAxleStore } from "@/stores/useAxleStore";
import {
  FAULT_LEVEL_MAP,
  getMcuFaultInfo,
  TBOX_FAULT_LEVEL_MAP,
} from "@/types/axle";

interface MetricTile {
  label: string;
  value: string;
  unit: string;
  /** 异常标注（如“过温”），正常时不显示 */
  tag?: string;
  /** 异常时整格以红色强调 */
  danger?: boolean;
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

/** 过温标志（0x35B）：对应温度格变红并标注“过温” */
const motorOverTemp = computed(
  () => hasFreshMcu2.value && mcu2.value.mcu_motor_temp_extre_over === 1,
);
const controllerOverTemp = computed(
  () => hasFreshMcu2.value && mcu2.value.mcu_mcu_temp_extre_over === 1,
);
const hasOverTemperature = computed(() => motorOverTemp.value || controllerOverTemp.value);

const isSystemNormal = computed(
  () =>
    hasFreshMcu1.value &&
    mcu1.value.mcu_flt_levl === 0 &&
    mcu1.value.mcu_tbox_flt_levl === 0 &&
    !hasOverTemperature.value,
);

/** 当前 MCU 故障（0x35A）；未收到新鲜反馈时视为未知，不显示故障条 */
const hasActiveFault = computed(() => hasFreshMcu1.value && mcu1.value.mcu_flt_code !== 0);
const faultCodeLabel = computed(() => {
  const code = mcu1.value.mcu_flt_code;
  return activeFaultInfo.value?.code ?? `0x${code.toString(16).toUpperCase()}`;
});

/** 故障码表：标题栏按钮与“故障状态”格都可以打开 */
const faultDialogOpen = ref(false);

function temperatureTile(label: string, value: number, overTemp: boolean): MetricTile {
  return {
    label,
    value: hasFreshTbox.value ? formatInteger(value) : PLACEHOLDER,
    unit: "℃",
    tag: overTemp ? "过温" : undefined,
    danger: overTemp,
  };
}

/** 4×2 数值格的前 7 格：动力、电气、温度；第 8 格“故障状态”在模板中单独渲染 */
const metricTiles = computed<MetricTile[]>(() => [
  { label: "实际转速", value: formatInteger(mcu2.value.mcu_act_motor_spd), unit: "RPM" },
  { label: "实际转矩", value: formatDecimal(mcu2.value.mcu_act_motor_tq), unit: "Nm" },
  { label: "最大可用转矩", value: formatDecimal(mcu2.value.mcu_motor_tor_max), unit: "Nm" },
  { label: "母线电压", value: formatDecimal(mcu1.value.mcu_dc_main_wire_volt), unit: "V" },
  { label: "母线电流", value: formatDecimal(mcu1.value.mcu_dc_main_wire_curr), unit: "A" },
  temperatureTile("电机温度", tbox.value.mcu_motor_temp, motorOverTemp.value),
  temperatureTile("控制器温度", tbox.value.mcu_ctller_temp, controllerOverTemp.value),
]);
</script>

<template>
  <Card class="h-full flex flex-col">
    <!-- 顶部状态栏 -->
    <CardHeader class="border-b pb-3">
      <!-- 标题 + 故障报警与安全指示 -->
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
          <FaultCodeDialog v-model:open="faultDialogOpen" :current-flt-code="mcu1.mcu_flt_code" />
        </div>
      </div>
    </CardHeader>

    <CardContent class="@container flex flex-1 flex-col gap-4 px-4 pb-4 sm:px-5 sm:pb-5">
      <!-- 4×2 数值格：动力、电气、温度与故障状态 -->
      <div class="grid grid-cols-2 gap-3 @md:grid-cols-4">
        <div
          v-for="tile in metricTiles"
          :key="tile.label"
          :class="cn(
            'flex flex-col gap-1 rounded-lg border bg-muted/30 p-3',
            tile.danger && 'border-destructive/50 bg-destructive/5',
          )"
        >
          <div class="flex items-center justify-between gap-1">
            <span class="truncate text-xs text-muted-foreground">{{ tile.label }}</span>
            <Badge v-if="tile.tag" variant="destructive">{{ tile.tag }}</Badge>
          </div>
          <div class="flex items-baseline justify-between gap-2">
            <span
              :class="cn(
                'truncate font-mono text-xl font-semibold tabular-nums text-foreground',
                tile.danger && 'text-destructive',
              )"
            >
              {{ tile.value }}
            </span>
            <span class="shrink-0 text-xs text-muted-foreground">{{ tile.unit }}</span>
          </div>
        </div>

        <!-- 第 8 格：故障状态，点击打开故障码表 -->
        <button
          type="button"
          :class="cn(
            'flex flex-col gap-1 rounded-lg border bg-muted/30 p-3 text-left transition-colors hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
            hasActiveFault && 'border-destructive/50 bg-destructive/5 hover:bg-destructive/10',
          )"
          title="查看故障码表"
          @click="faultDialogOpen = true"
        >
          <span class="text-xs text-muted-foreground">故障状态</span>
          <span
            :class="cn(
              'truncate font-mono text-xl font-semibold',
              !hasFreshMcu1 && 'text-muted-foreground',
              hasFreshMcu1 && !hasActiveFault && 'text-success',
              hasActiveFault && 'text-destructive',
            )"
          >
            {{ !hasFreshMcu1 ? PLACEHOLDER : hasActiveFault ? faultCodeLabel : "无故障" }}
          </span>
        </button>
      </div>

      <!-- 故障条：只在有故障时出现 -->
      <Alert v-if="hasActiveFault" variant="destructive">
        <AlertTriangleIcon />
        <AlertTitle>{{ faultCodeLabel }} · {{ activeFaultInfo?.meaning ?? "故障表未收录" }}</AlertTitle>
        <AlertDescription>
          故障等级 {{ FAULT_LEVEL_MAP[mcu1.mcu_flt_levl]?.text ?? `等级 ${mcu1.mcu_flt_levl}` }}
          · 共 {{ formatInteger(mcu1.mcu_integ_ctr_flt_num) }} 个故障
          · 原始码 0x{{ mcu1.mcu_flt_code.toString(16).toUpperCase() }}
        </AlertDescription>
      </Alert>

      <!-- 转速与转矩曲线：占满卡片剩余高度，与左侧控制区等高 -->
      <AxleTelemetryChart />
    </CardContent>
  </Card>
</template>
