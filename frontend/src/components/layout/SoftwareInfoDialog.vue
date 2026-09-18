<script setup lang="ts">
import {
  CheckCircle2,
  Cpu,
  Phone,
  Radio,
  Users,
  Zap,
} from '@lucide/vue'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Separator } from '@/components/ui/separator'

/**
 * 软件信息弹窗组件 (SoftwareInfoDialog)
 *
 * 使用 shadcn/vue Dialog 原语构建，展示开发团队及测控上位机的软件规格、
 * 硬件驱动、通讯协议与技术支持信息。
 */
const open = defineModel<boolean>('open', { default: false })

/** 系统核心参数定义（便于维护与扩展） */
interface SystemSpec {
  label: string
  value: string
  icon: typeof Users
  badge?: string
}

const specs: readonly SystemSpec[] = [
  {
    label: '开发团队',
    value: '电驱系统研究所',
    icon: Users,
  },
  {
    label: '系统定位',
    value: '电驱桥台架测控与诊断上位机',
    icon: Zap,
  },
  {
    label: '总线协议',
    value: '11898 标准 CAN 协议',
    icon: Radio,
  },
  {
    label: '硬件驱动',
    value: 'ZLG CAN 适配器 (USBCAN / CANFD)',
    icon: Cpu,
  },
  {
    label: '技术支持',
    value: '17873554355',
    icon: Phone,
  },
]
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-[540px] gap-5 p-6">
      <!-- 弹窗标题与软件标识 -->
      <DialogHeader class="gap-2 text-left">
        <div class="flex items-center gap-3">
          <div class="flex aspect-square size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-xs">
            <Zap class="size-5" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <DialogTitle class="text-base font-bold sm:text-lg">
                株齿 2.5T 电驱桥下线测试上位机
              </DialogTitle>
              <Badge variant="secondary" class="font-mono text-[11px] px-1.5 py-0">
                v1.0.0
              </Badge>
            </div>
            <DialogDescription class="text-xs text-muted-foreground mt-0.5">
              株齿 2.5T 电驱桥 EOL 下线测试、通讯诊断与台架标定平台
            </DialogDescription>
          </div>
        </div>
      </DialogHeader>

      <Separator />

      <!-- 软件详细规格清单 -->
      <div class="grid gap-2.5">
        <div
          v-for="spec in specs"
          :key="spec.label"
          class="flex items-center justify-between rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-xs transition-colors hover:bg-muted/70"
        >
          <div class="flex items-center gap-2 text-muted-foreground">
            <component :is="spec.icon" class="size-3.5 shrink-0 text-primary" />
            <span class="font-medium">{{ spec.label }}</span>
          </div>

          <div class="flex items-center gap-1.5 text-right font-medium text-foreground">
            <span class="truncate max-w-[280px]">{{ spec.value }}</span>
            <Badge
              v-if="spec.badge"
              variant="outline"
              class="text-[10px] px-1 py-0 font-mono text-primary border-primary/30"
            >
              {{ spec.badge }}
            </Badge>
          </div>
        </div>
      </div>

      <!-- 系统健康状态条 -->
      <div class="flex items-center justify-between rounded-lg border border-success/20 bg-success/5 px-3 py-2 text-xs">
        <div class="flex items-center gap-2">
          <span class="relative flex size-2 shrink-0">
            <span class="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-75" />
            <span class="relative inline-flex size-2 rounded-full bg-success" />
          </span>
          <span class="font-medium text-success">系统服务与接口状态</span>
        </div>
        <div class="flex items-center gap-1 text-[11px] text-success">
          <CheckCircle2 class="size-3.5" />
          <span>服务正常 · SSE 数据流已就绪</span>
        </div>
      </div>

      <!-- 底部版权与操作按键 -->
      <DialogFooter class="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 pt-1">
        <div class="text-[11px] text-muted-foreground text-center sm:text-left font-normal">
          © 2026 电驱系统研究所 · 保留所有权利
        </div>
        <DialogClose as-child>
          <Button variant="default" size="sm" class="px-5">
            确定
          </Button>
        </DialogClose>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
