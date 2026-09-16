<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  FileTextIcon,
  SearchIcon,
  XIcon,
} from '@lucide/vue'

import { cn } from '@/lib/utils'
import { Alert, AlertDescription } from '@/components/ui/alert'
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
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { MCU_FAULT_CODES } from '@/types/axle'

/**
 * 组件 Props
 * - currentFltCode: 当前总线反馈的 MCU_FltCode 原始数值 (0x00 ~ 0xFA)，若存在则自动高亮匹配项
 * - open: 支持外部受控打开
 */
const props = withDefaults(
  defineProps<{
    currentFltCode?: number
    open?: boolean
  }>(),
  {
    currentFltCode: 0,
    open: undefined,
  },
)

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
}>()

const internalOpen = ref(false)

const isDialogOpen = computed({
  get: () => (props.open !== undefined ? props.open : internalOpen.value),
  set: (val: boolean) => {
    internalOpen.value = val
    emit('update:open', val)
  },
})

// 搜索筛选关键词
const searchKeyword = ref('')

// 根据故障码或含义模糊检索 (支持 DisplayCode、中文含义、十进制原始码、十六进制如 0x40 或 40、0x07 或 07)
const filteredFaultCodes = computed(() => {
  const query = searchKeyword.value.trim().toLowerCase()
  if (!query) {
    return MCU_FAULT_CODES
  }
  return MCU_FAULT_CODES.filter((item) => {
    const codeMatch = item.code.toLowerCase().includes(query)
    const meaningMatch = item.meaning.toLowerCase().includes(query)
    const levelMatch = item.level.toLowerCase().includes(query)
    const rawStr = item.raw_code.toString()
    const rawMatch = rawStr.includes(query)

    const hexRaw = item.raw_code.toString(16).toLowerCase()
    const hexPadded = hexRaw.padStart(2, '0')
    const hexMatch =
      hexRaw.includes(query) ||
      hexPadded.includes(query) ||
      `0x${hexRaw}`.includes(query) ||
      `0x${hexPadded}`.includes(query)

    return codeMatch || meaningMatch || levelMatch || rawMatch || hexMatch
  })
})

// 当前是否有活动故障
const hasActiveFault = computed(() => props.currentFltCode > 0)
const activeFaultItem = computed(() =>
  MCU_FAULT_CODES.find((item) => item.raw_code === props.currentFltCode),
)

</script>

<template>
  <Dialog v-model:open="isDialogOpen">
    <!-- 触发按钮插槽：若外部未提供自定义触发插槽，则渲染默认按钮 -->
    <DialogTrigger as-child>
      <slot name="trigger">
        <Button variant="outline" size="sm">
          <FileTextIcon data-icon="inline-start" />
          <span>故障码表</span>
        </Button>
      </slot>
    </DialogTrigger>

    <DialogContent class="flex h-[85vh] max-h-[48rem] flex-col gap-4 overflow-hidden p-5 sm:max-w-2xl">
      <!-- 对话框头部：依据 shadcn-vue 规范必须具备 DialogTitle 与 DialogDescription -->
      <DialogHeader class="gap-1.5">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-2">
            <div class="p-2 rounded-lg bg-primary/10 text-primary">
              <FileTextIcon />
            </div>
            <div>
              <DialogTitle class="text-lg font-bold">
                MCU 控制器故障代码表
              </DialogTitle>
              <DialogDescription class="sr-only">
                MCU 控制器故障代码查询
              </DialogDescription>
            </div>
          </div>
          <Badge variant="secondary" class="font-mono text-xs shrink-0">
            共 {{ MCU_FAULT_CODES.length }} 项
          </Badge>
        </div>
      </DialogHeader>

      <!-- 当前活动故障指示条 (基于 shadcn-vue Alert 组件) -->
      <Alert v-if="hasActiveFault" variant="destructive" class="py-2.5">
        <AlertTriangleIcon />
        <div class="flex items-center justify-between w-full">
          <AlertDescription class="text-xs">
            当前上报故障:
            <span class="font-mono font-bold">
              0x{{ currentFltCode.toString(16).toUpperCase().padStart(2, '0') }}
              ({{ activeFaultItem?.code ?? `Code_${currentFltCode}` }})
            </span>
            <span v-if="activeFaultItem"> - {{ activeFaultItem.meaning }}</span>
          </AlertDescription>
          <Badge variant="destructive" class="text-[11px] shrink-0 ml-2">
            {{ activeFaultItem?.level ?? '未知等级' }}
          </Badge>
        </div>
      </Alert>

      <!-- 搜索过滤栏 -->
      <div class="relative w-full">
        <SearchIcon class="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        <Input
          v-model="searchKeyword"
          placeholder="搜索故障码 (如 MCU_64、64、0x40) 或故障含义..."
          class="pl-9 pr-8 h-9 text-xs"
        />
        <Button
          v-if="searchKeyword"
          variant="ghost"
          size="icon-sm"
          class="absolute right-1 top-1/2 -translate-y-1/2"
          @click="searchKeyword = ''"
        >
          <XIcon />
          <span class="sr-only">清空检索</span>
        </Button>
      </div>

      <!-- DEF 三列故障码表格滚动视图 -->
      <ScrollArea
        type="always"
        class="min-h-0 flex-1 overflow-hidden rounded-lg border border-border"
      >
        <Table>
          <TableHeader class="sticky top-0 bg-muted/80 backdrop-blur-xs z-10">
            <TableRow>
              <!-- 列 E: 故障码 (DisplayCode) -->
              <TableHead class="w-[140px] font-semibold text-foreground">
                故障码 (DisplayCode)
              </TableHead>
              <!-- 列 D: 含义 (DTC Meaning) -->
              <TableHead class="font-semibold text-foreground">
                含义 (DTC Meaning)
              </TableHead>
              <!-- 列 F: 故障级别 (FaultLevel) -->
              <TableHead class="w-[150px] text-right font-semibold text-foreground">
                故障级别 (FaultLevel)
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <template v-if="filteredFaultCodes.length > 0">
              <TableRow
                v-for="item in filteredFaultCodes"
                :key="item.code"
                :class="
                  cn(
                    'transition-colors',
                    item.raw_code === currentFltCode
                      ? 'bg-destructive/15 hover:bg-destructive/20 font-semibold'
                      : 'hover:bg-muted/50',
                  )
                "
              >
                <!-- 列 E: 故障码 (DisplayCode) -->
                <TableCell class="font-mono py-2.5">
                  <div class="flex items-center gap-1.5">
                    <span
                      v-if="item.raw_code === currentFltCode"
                      class="size-1.5 rounded-full bg-destructive animate-ping"
                    />
                    <Badge
                      variant="outline"
                      class="font-mono text-xs text-foreground px-2 py-0.5"
                    >
                      {{ item.code }}
                    </Badge>
                  </div>
                </TableCell>

                <!-- 列 D: DTC 含义 -->
                <TableCell class="py-2.5 text-xs text-foreground font-medium">
                  {{ item.meaning }}
                </TableCell>

                <!-- 列 F: 故障等级 (FaultLevel) -->
                <TableCell class="py-2.5 text-right">
                  <Badge
                    variant="outline"
                    class="text-[11px] font-normal text-foreground"
                  >
                    {{ item.level }}
                  </Badge>
                </TableCell>
              </TableRow>
            </template>
            <TableRow v-else>
              <TableCell colspan="3" class="h-32 text-center text-muted-foreground text-xs">
                未匹配到符合条件的故障码
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </ScrollArea>

      <Separator />

      <!-- 对话框底部 -->
      <DialogFooter class="flex flex-row items-center justify-between sm:justify-between pt-1">
        <div class="text-[11px] text-muted-foreground flex items-center gap-1.5">
          <CheckCircle2Icon class="text-success" />
          <span>显示 {{ filteredFaultCodes.length }} / {{ MCU_FAULT_CODES.length }} 条记录</span>
        </div>
        <DialogClose as-child>
          <Button variant="outline" size="sm">
            关闭
          </Button>
        </DialogClose>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
