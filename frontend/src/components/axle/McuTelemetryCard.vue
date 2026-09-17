<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import FaultCodeDialog from "@/components/axle/FaultCodeDialog.vue";
import { useAxleStore } from "@/stores/useAxleStore";
import {
  FAULT_LEVEL_MAP,
  getMcuFaultInfo,
  TBOX_FAULT_LEVEL_MAP,
  WORK_MODE_MAP,
} from "@/types/axle";

const axleStore = useAxleStore();

/** 界面刷新节流周期 (ms)，降低高频 CAN 数据导致的 UI 渲染开销 */
const DISPLAY_REFRESH_INTERVAL_MS = 200;

const displayedMcu1 = ref({ ...axleStore.telemetry.mcu_1 });
const displayedMcu2 = ref({ ...axleStore.telemetry.mcu_2 });

const mcu1 = computed(() => displayedMcu1.value);
const mcu2 = computed(() => displayedMcu2.value);
const activeFaultInfo = computed(() => getMcuFaultInfo(mcu1.value.mcu_flt_code));

const feedbackClock = ref(Date.now());
let feedbackClockTimer: ReturnType<typeof setInterval> | undefined;
let displayRefreshTimer: ReturnType<typeof setInterval> | undefined;

function refreshDisplayedTelemetry(): void {
  displayedMcu1.value = { ...axleStore.telemetry.mcu_1 };
  displayedMcu2.value = { ...axleStore.telemetry.mcu_2 };
}

onMounted(() => {
  refreshDisplayedTelemetry();
  displayRefreshTimer = setInterval(
    refreshDisplayedTelemetry,
    DISPLAY_REFRESH_INTERVAL_MS,
  );

  feedbackClockTimer = setInterval(() => {
    feedbackClock.value = Date.now();
  }, 250);
});

onBeforeUnmount(() => {
  if (displayRefreshTimer) {
    clearInterval(displayRefreshTimer);
  }
  if (feedbackClockTimer) {
    clearInterval(feedbackClockTimer);
  }
});

// 0x35B 期望以 10 ms 周期返回，留出 500 ms 裕量判别通信状态
const hasFreshMcu2Feedback = computed(() => {
  const receivedAt = axleStore.telemetry.mcu_2_last_rx_timestamp;
  return (
    axleStore.isConnected &&
    receivedAt !== null &&
    feedbackClock.value - receivedAt * 1000 <= 500
  );
});

// 0x35A 期望以 100 ms 周期返回，留出 1000 ms 裕量判别通信状态
const hasFreshMcu1Feedback = computed(() => {
  const receivedAt = axleStore.telemetry.mcu_1_last_rx_timestamp;
  return (
    axleStore.isConnected &&
    receivedAt !== null &&
    feedbackClock.value - receivedAt * 1000 <= 1000
  );
});

const lowVoltageStatusText = computed(() => {
  if (!hasFreshMcu2Feedback.value) return "低压未知";
  return mcu2.value.mcu_lv_sts === 1 ? "低压已上电" : "低压未上电";
});

const enableStatusText = computed(() => {
  if (!hasFreshMcu2Feedback.value) return "使能未知";
  return mcu2.value.mcu_en_sts === 1 ? "MCU 已使能" : "MCU 未使能";
});

const workModeStatusText = computed(() => {
  if (!hasFreshMcu2Feedback.value) return "模式未知";
  return mcu2.value.mcu_motor_work_mod === 0
    ? "无操作"
    : (WORK_MODE_MAP[mcu2.value.mcu_motor_work_mod] ?? "未知模式");
});

const isSystemNormal = computed(() => {
  return (
    hasFreshMcu1Feedback.value &&
    mcu1.value.mcu_flt_levl === 0 &&
    mcu1.value.mcu_tbox_flt_levl === 0 &&
    mcu2.value.mcu_motor_temp_extre_over === 0 &&
    mcu2.value.mcu_mcu_temp_extre_over === 0
  );
});
</script>

<template>
  <Card class="border-border shadow-xs h-full flex flex-col">
    <!-- 顶部状态栏 -->
    <CardHeader class="p-3 border-b bg-muted/20">
      <div class="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
        <div class="flex flex-wrap items-center gap-1.5">
          <CardTitle class="text-sm font-bold mr-1">
            MCU 实时反馈
          </CardTitle>

          <!-- 0x35B 核心硬件与控制状态 -->
          <Badge
            :variant="hasFreshMcu2Feedback && mcu2.mcu_lv_sts === 1 ? 'success' : 'secondary'"
            class="text-xs px-1.5 py-0"
          >
            {{ lowVoltageStatusText }}
          </Badge>

          <Badge
            :variant="hasFreshMcu2Feedback && mcu2.mcu_en_sts === 1 ? 'success' : 'secondary'"
            class="text-xs px-1.5 py-0"
          >
            {{ enableStatusText }}
          </Badge>

          <Badge
            :variant="hasFreshMcu2Feedback && mcu2.mcu_motor_work_mod !== 0 ? 'outline' : 'secondary'"
            class="text-xs px-1.5 py-0"
            :class="hasFreshMcu2Feedback && mcu2.mcu_motor_work_mod !== 0 ? 'border-primary/50 text-primary font-medium' : ''"
          >
            {{ workModeStatusText }}
          </Badge>

          <Badge
            v-if="hasFreshMcu2Feedback && mcu2.mcm_slope_sts === 1"
            variant="outline"
            class="border-warning/60 bg-warning/5 text-warning font-semibold text-xs px-1.5 py-0"
          >
            驻坡中
          </Badge>
        </div>

        <!-- 故障报警与安全指示 -->
        <div class="flex flex-wrap items-center gap-1.5">
          <Badge
            v-if="isSystemNormal"
            variant="outline"
            class="border-success/60 bg-success/5 text-success font-semibold text-xs px-1.5 py-0"
          >
            系统正常
          </Badge>
          <Badge
            v-else-if="hasFreshMcu1Feedback && mcu1.mcu_flt_levl !== 0"
            variant="destructive"
            class="animate-pulse font-bold text-xs px-1.5 py-0"
          >
            {{ FAULT_LEVEL_MAP[mcu1.mcu_flt_levl]?.text ?? '故障报警' }}
          </Badge>

          <Badge
            v-if="hasFreshMcu1Feedback && mcu1.mcu_tbox_flt_levl !== 0"
            variant="destructive"
            class="animate-pulse font-bold text-xs px-1.5 py-0"
          >
            {{ TBOX_FAULT_LEVEL_MAP[mcu1.mcu_tbox_flt_levl] ?? '温度报警' }}
          </Badge>

          <Badge
            v-if="hasFreshMcu2Feedback && (mcu2.mcu_motor_temp_extre_over === 1 || mcu2.mcu_mcu_temp_extre_over === 1)"
            variant="destructive"
            class="animate-pulse font-bold text-xs px-1.5 py-0"
          >
            过温故障
          </Badge>

          <FaultCodeDialog :current-flt-code="mcu1.mcu_flt_code" />
        </div>
      </div>
    </CardHeader>

    <CardContent class="p-3 sm:p-4 flex-1 flex flex-col justify-between gap-3">
      <!-- 动力与电气核心数值网格 (3列 x 2行，严格对齐 CAN 报文信号) -->
      <div class="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
        <!-- 实际转速 (0x35B) -->
        <div class="p-2.5 bg-muted/25 rounded-lg border border-border/60 flex flex-col justify-center">
          <div class="text-xs text-muted-foreground font-semibold">实际转速</div>
          <div class="text-xl font-mono font-bold text-info">
            {{ mcu2.mcu_act_motor_spd }}
            <span class="text-xs font-normal text-muted-foreground font-sans">RPM</span>
          </div>
        </div>

        <!-- 实际转矩 (0x35B) -->
        <div class="p-2.5 bg-muted/25 rounded-lg border border-border/60 flex flex-col justify-center">
          <div class="text-xs text-muted-foreground font-semibold">实际转矩</div>
          <div class="text-xl font-mono font-bold text-warning">
            {{ mcu2.mcu_act_motor_tq }}
            <span class="text-xs font-normal text-muted-foreground font-sans">Nm</span>
          </div>
        </div>

        <!-- 最大可用转矩 (0x35B) -->
        <div class="p-2.5 bg-muted/25 rounded-lg border border-border/60 flex flex-col justify-center">
          <div class="text-xs text-muted-foreground font-semibold">最大可用转矩</div>
          <div class="text-xl font-mono font-bold text-foreground">
            {{ mcu2.mcu_motor_tor_max }}
            <span class="text-xs font-normal text-muted-foreground font-sans">Nm</span>
          </div>
        </div>

        <!-- 母线电压 (0x35A) -->
        <div class="p-2.5 bg-muted/25 rounded-lg border border-border/60 flex flex-col justify-center">
          <div class="text-xs text-muted-foreground font-semibold">母线电压</div>
          <div class="text-xl font-mono font-bold text-primary">
            {{ mcu1.mcu_dc_main_wire_volt }}
            <span class="text-xs font-normal text-muted-foreground font-sans">V</span>
          </div>
        </div>

        <!-- 母线电流 (0x35A) -->
        <div class="p-2.5 bg-muted/25 rounded-lg border border-border/60 flex flex-col justify-center">
          <div class="text-xs text-muted-foreground font-semibold">母线电流</div>
          <div class="text-xl font-mono font-bold text-info">
            {{ mcu1.mcu_dc_main_wire_curr }}
            <span class="text-xs font-normal text-muted-foreground font-sans">A</span>
          </div>
        </div>

        <!-- 主动放电状态 (0x35B) -->
        <div class="p-2.5 bg-muted/25 rounded-lg border border-border/60 flex flex-col justify-center">
          <div class="text-xs text-muted-foreground font-semibold">主动放电</div>
          <div
            class="text-base font-bold truncate"
            :class="cn(
              mcu2.mcu_active_dischrg_sts === 0 ? 'text-warning' :
              mcu2.mcu_active_dischrg_sts === 1 ? 'text-success' :
              mcu2.mcu_active_dischrg_sts === 2 ? 'text-destructive' : 'text-muted-foreground'
            )"
          >
            {{
              mcu2.mcu_active_dischrg_sts === 0 ? "放电中" :
              mcu2.mcu_active_dischrg_sts === 1 ? "放电完成" :
              mcu2.mcu_active_dischrg_sts === 2 ? "放电失败" : "未触发"
            }}
          </div>
        </div>
      </div>

      <!-- 控制状态、温度安全与故障诊断 (3列等宽对齐排布) -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
        <!-- 控制与运行状态 (0x35B) -->
        <div class="p-2.5 rounded-lg border border-border/60 bg-muted/25 flex flex-col justify-between gap-1.5">
          <div class="font-semibold text-muted-foreground">控制状态</div>
          <div class="space-y-1">
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">工作模式:</span>
              <span class="font-medium text-foreground">{{ workModeStatusText }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">MCU使能:</span>
              <span :class="mcu2.mcu_en_sts === 1 ? 'text-success font-semibold' : 'text-muted-foreground'">
                {{ mcu2.mcu_en_sts === 1 ? '已使能' : '未使能' }}
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">低压状态:</span>
              <span :class="mcu2.mcu_lv_sts === 1 ? 'text-success font-semibold' : 'text-muted-foreground'">
                {{ mcu2.mcu_lv_sts === 1 ? '正常' : '无效' }}
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">通信心跳:</span>
              <span class="font-mono text-foreground font-semibold">#{{ mcu2.mcu_life_2 }}</span>
            </div>
          </div>
        </div>

        <!-- 温度安全保护 (0x35A/B) -->
        <div class="p-2.5 rounded-lg border border-border/60 bg-muted/25 flex flex-col justify-between gap-1.5">
          <div class="font-semibold text-muted-foreground">温度安全</div>
          <div class="space-y-1">
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">电机过温:</span>
              <span :class="mcu2.mcu_motor_temp_extre_over === 1 ? 'text-destructive font-bold' : 'text-success'">
                {{ mcu2.mcu_motor_temp_extre_over === 1 ? '过温报警' : '正常' }}
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">控制器过温:</span>
              <span :class="mcu2.mcu_mcu_temp_extre_over === 1 ? 'text-destructive font-bold' : 'text-success'">
                {{ mcu2.mcu_mcu_temp_extre_over === 1 ? '过温报警' : '正常' }}
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">温度故障级:</span>
              <span :class="mcu1.mcu_tbox_flt_levl === 0 ? 'text-success' : 'text-destructive font-semibold'">
                {{ TBOX_FAULT_LEVEL_MAP[mcu1.mcu_tbox_flt_levl] ?? '正常' }}
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">驻坡状态:</span>
              <span :class="mcu2.mcm_slope_sts === 1 ? 'text-warning font-semibold' : 'text-foreground'">
                {{ mcu2.mcm_slope_sts === 1 ? '驻坡中' : '未驻坡' }}
              </span>
            </div>
          </div>
        </div>

        <!-- MCU 故障诊断 (0x35A) -->
        <div class="p-2.5 rounded-lg border border-border/60 bg-muted/25 flex flex-col justify-between gap-1.5">
          <div class="font-semibold text-muted-foreground">故障诊断</div>
          <div class="space-y-1">
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">故障代码:</span>
              <span class="font-mono font-bold" :class="mcu1.mcu_flt_code === 0 ? 'text-success' : 'text-destructive'">
                {{ mcu1.mcu_flt_code === 0 ? "0x00 (正常)" : `0x${mcu1.mcu_flt_code.toString(16).toUpperCase()} (${activeFaultInfo?.code ?? '未知'})` }}
              </span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">故障等级:</span>
              <span class="font-medium text-foreground">{{ FAULT_LEVEL_MAP[mcu1.mcu_flt_levl]?.text ?? '无故障' }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">记录条数:</span>
              <span class="font-mono">{{ mcu1.mcu_integ_ctr_flt_num }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-muted-foreground">通信心跳:</span>
              <span class="font-mono text-foreground font-semibold">#{{ mcu1.mcu_life_1 }}</span>
            </div>
          </div>
        </div>
      </div>
    </CardContent>
  </Card>
</template>
