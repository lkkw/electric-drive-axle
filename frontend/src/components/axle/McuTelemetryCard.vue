<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangleIcon } from '@lucide/vue'

import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { useAxleStore } from '@/stores/useAxleStore'
import {
  FAULT_LEVEL_MAP,
  MOTOR_STATE_MAP,
  WORK_MODE_MAP,
} from '@/types/axle'

const axleStore = useAxleStore()

const mcu1 = computed(() => axleStore.telemetry.mcu_1)
const mcu2 = computed(() => axleStore.telemetry.mcu_2)
const tbox = computed(() => axleStore.telemetry.mcu_tbox)

// 直流母线输入功率: P (kW) = U (V) * I (A) / 1000
const dcPowerKw = computed(() => {
  const p = (mcu1.value.mcu_dc_main_wire_volt * mcu1.value.mcu_dc_main_wire_curr) / 1000
  return p.toFixed(2)
})

// 电机输出机械功率: P_mech (kW) = T (Nm) * n (rpm) / 9549
const mechPowerKw = computed(() => {
  const p = (mcu2.value.mcu_act_motor_tq * mcu2.value.mcu_act_motor_spd) / 9549
  return p.toFixed(2)
})
</script>

<template>
  <Card class="border-border shadow-xs h-full flex flex-col">
    <CardHeader class="pb-3 border-b bg-muted/20">
      <div class="flex items-center justify-between">
        <div>
          <CardTitle class="text-base font-semibold flex items-center gap-2">
            MCU 实时反馈
            <Badge
              v-if="mcu2.mcu_en_sts === 1"
              variant="success"
              class="font-mono text-xs px-1.5 py-0"
            >
              驱动使能
            </Badge>
            <Badge v-else variant="secondary" class="font-mono text-xs px-1.5 py-0">
              未使能
            </Badge>
          </CardTitle>
        </div>

        <div class="flex items-center gap-2">
          <Badge
            v-if="mcu1.mcu_flt_levl === 0"
            variant="outline"
            class="border-success/60 bg-success/5 text-success font-semibold text-xs"
          >
            系统正常
          </Badge>
          <Badge
            v-else
            variant="destructive"
            class="animate-pulse font-bold text-xs"
          >
            <AlertTriangleIcon data-icon="inline-start" />
            {{ FAULT_LEVEL_MAP[mcu1.mcu_flt_levl]?.text ?? '故障报警' }}
          </Badge>
        </div>
      </div>
    </CardHeader>

    <CardContent class="p-4 sm:p-5 flex-1 flex flex-col justify-between gap-4">
      <!-- 动力与电气核心指标 (4列) -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <!-- 电机转速 -->
        <div class="p-3.5 bg-muted/25 rounded-xl border border-border/60 flex flex-col justify-between gap-1">
          <div class="text-xs text-muted-foreground font-semibold">
            <span>实际转速</span>
          </div>
          <div class="text-2xl font-mono font-bold text-info">
            {{ mcu2.mcu_act_motor_spd }}
            <span class="text-xs font-normal text-muted-foreground font-sans">RPM</span>
          </div>
          <div class="text-[11px] text-muted-foreground">
            机械功率: <span class="font-mono font-semibold text-foreground">{{ mechPowerKw }}</span> kW
          </div>
        </div>

        <!-- 电机实际转矩 -->
        <div class="p-3.5 bg-muted/25 rounded-xl border border-border/60 flex flex-col justify-between gap-1">
          <div class="text-xs text-muted-foreground font-semibold">
            <span>实际转矩</span>
          </div>
          <div class="text-2xl font-mono font-bold text-warning">
            {{ mcu2.mcu_act_motor_tq }}
            <span class="text-xs font-normal text-muted-foreground font-sans">Nm</span>
          </div>
          <div class="text-[11px] text-muted-foreground">
            能力上限: <span class="font-mono font-semibold text-foreground">{{ mcu2.mcu_motor_tor_max }}</span> Nm
          </div>
        </div>

        <!-- 母线电压 -->
        <div class="p-3.5 bg-muted/25 rounded-xl border border-border/60 flex flex-col justify-between gap-1">
          <div class="text-xs text-muted-foreground font-semibold">
            <span>母线电压</span>
          </div>
          <div class="text-2xl font-mono font-bold text-primary">
            {{ mcu1.mcu_dc_main_wire_volt }}
            <span class="text-xs font-normal text-muted-foreground font-sans">V</span>
          </div>
          <div class="text-[11px] text-muted-foreground">
            回路状态: <span class="font-mono font-semibold text-foreground">{{ mcu1.mcu_dc_main_wire_volt > 60 ? '高压供电' : '安全低压' }}</span>
          </div>
        </div>

        <!-- 母线电流与效率 -->
        <div class="p-3.5 bg-muted/25 rounded-xl border border-border/60 flex flex-col justify-between gap-1">
          <div class="text-xs text-muted-foreground font-semibold">
            <span>母线电流</span>
          </div>
          <div class="text-2xl font-mono font-bold text-info">
            {{ mcu1.mcu_dc_main_wire_curr }}
            <span class="text-xs font-normal text-muted-foreground font-sans">A</span>
          </div>
          <div class="text-[11px] text-muted-foreground">
            瞬时输入: <span class="font-mono font-semibold text-foreground">{{ dcPowerKw }}</span> kW
          </div>
        </div>
      </div>

      <!-- 温度监控与电机运行状态 (3列) -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <!-- 驱动电机温度 -->
        <div class="p-3.5 rounded-xl border border-border/60 bg-muted/25 flex flex-col justify-between gap-1.5">
          <div class="flex items-center justify-between text-xs font-semibold text-muted-foreground">
            <span>驱动电机温度</span>
            <Badge
              v-if="mcu2.mcu_motor_temp_extre_over === 1"
              variant="destructive"
              class="text-[10px] px-1.5 py-0 animate-pulse"
            >
              过温报警
            </Badge>
          </div>
          <div class="text-2xl font-bold font-mono text-foreground">
            {{ tbox.mcu_motor_temp }}
            <span class="text-xs font-normal text-muted-foreground font-sans">℃</span>
          </div>
          <div class="text-[11px] text-muted-foreground">
            极限保护阈值: <span class="font-mono font-semibold text-foreground">150</span> ℃
          </div>
        </div>

        <!-- MCU 控制器温度 -->
        <div class="p-3.5 rounded-xl border border-border/60 bg-muted/25 flex flex-col justify-between gap-1.5">
          <div class="flex items-center justify-between text-xs font-semibold text-muted-foreground">
            <span>MCU 控制器温度</span>
            <Badge
              v-if="mcu2.mcu_mcu_temp_extre_over === 1"
              variant="destructive"
              class="text-[10px] px-1.5 py-0 animate-pulse"
            >
              过温报警
            </Badge>
          </div>
          <div class="text-2xl font-bold font-mono text-foreground">
            {{ tbox.mcu_ctller_temp }}
            <span class="text-xs font-normal text-muted-foreground font-sans">℃</span>
          </div>
          <div class="text-[11px] text-muted-foreground">
            极限保护阈值: <span class="font-mono font-semibold text-foreground">85</span> ℃
          </div>
        </div>

        <!-- 电机运行状态与低压供电 -->
        <div class="p-3.5 rounded-xl border border-border/60 bg-muted/25 flex flex-col justify-between gap-1.5">
          <div class="flex items-center justify-between text-xs font-semibold text-muted-foreground">
            <span>运行状态</span>
            <Badge
              v-if="mcu2.mcu_lv_sts !== 1"
              variant="secondary"
              class="text-[10px] px-1.5 py-0 text-muted-foreground"
            >
              未上电
            </Badge>
          </div>
          <div class="h-8 flex items-center gap-2">
            <span
              class="size-2.5 shrink-0 rounded-full transition-colors"
              :class="cn({
                'bg-success shadow-xs shadow-success/50 animate-pulse': tbox.st_mtr === 1,
                'bg-info shadow-xs shadow-info/50 animate-pulse': tbox.st_mtr === 2,
                'bg-muted-foreground/50': tbox.st_mtr === 3,
                'bg-info/70': tbox.st_mtr === 4,
                'bg-destructive shadow-xs shadow-destructive/50': tbox.st_mtr === 255,
              })"
            />
            <span class="text-base font-semibold text-foreground truncate">
              {{ MOTOR_STATE_MAP[tbox.st_mtr] ?? '未知' }}
            </span>
          </div>
          <div class="text-[11px] text-muted-foreground">
            低压供电: <span class="font-mono font-semibold text-foreground">{{ mcu2.mcu_lv_sts === 1 ? 'OK' : 'OFF' }}</span>
          </div>
        </div>
      </div>

      <!-- 控制反馈与故障诊断 (3列) -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
        <div class="p-3.5 rounded-xl border border-border/60 bg-muted/25 flex flex-col justify-between gap-1">
          <div class="text-muted-foreground font-medium">工作模式反馈</div>
          <div class="font-bold text-sm text-foreground">
            {{ WORK_MODE_MAP[mcu2.mcu_motor_work_mod] ?? '无操作' }}
          </div>
          <div class="text-[11px] text-muted-foreground">当前运行模式</div>
        </div>

        <div class="p-3.5 rounded-xl border border-border/60 bg-muted/25 flex flex-col justify-between gap-1">
          <div class="text-muted-foreground font-medium">主动放电反馈</div>
          <div
            class="font-bold text-sm"
            :class="cn(mcu2.mcu_active_dischrg_sts === 0 ? 'text-warning' : 'text-foreground')"
          >
            {{ mcu2.mcu_active_dischrg_sts === 0 ? '放电中' : mcu2.mcu_active_dischrg_sts === 1 ? '放电完成' : mcu2.mcu_active_dischrg_sts === 2 ? '放电失败' : '未触发' }}
          </div>
          <div class="text-[11px] text-muted-foreground">高压回路状态</div>
        </div>

        <div class="p-3.5 rounded-xl border border-border/60 bg-muted/25 flex flex-col justify-between gap-1">
          <div class="text-muted-foreground font-medium">MCU 故障诊断</div>
          <div
            class="font-bold text-sm font-mono"
            :class="cn(mcu1.mcu_flt_code === 0 ? 'text-success' : 'text-destructive')"
          >
            {{ mcu1.mcu_flt_code === 0 ? '0x00 (正常)' : `0x${mcu1.mcu_flt_code.toString(16).toUpperCase()}` }}
          </div>
          <div class="text-[11px] text-muted-foreground">
            {{ mcu1.mcu_integ_ctr_flt_num === 0 ? '无故障记录' : `记录数: ${mcu1.mcu_integ_ctr_flt_num}` }}
          </div>
        </div>
      </div>
    </CardContent>
  </Card>
</template>
