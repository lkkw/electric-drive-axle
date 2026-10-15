<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { DownloadIcon, SearchIcon } from '@lucide/vue'
import { toast } from 'vue-sonner'

import { exportTestRecords, getTestRecords } from '@/api/testRecords'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import {
  Table,
  TableBody,
  TableCell,
  TableEmpty,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { TestRecord, TestRecordFilters, TestResult } from '@/types/testRecords'
import {
  formatDuration,
  formatLocalTime,
  formatValue,
  localDateText,
  summarizeRecords,
} from './testRecordUtils'

const ALL = 'all'
const COLUMN_COUNT = 12
const DEFAULT_RANGE_DAYS = 7

const weekAgo = new Date()
weekAgo.setDate(weekAgo.getDate() - (DEFAULT_RANGE_DAYS - 1))

const filters = reactive({
  dateFrom: localDateText(weekAgo),
  dateTo: localDateText(),
  sn: '',
  result: ALL,
})

const records = ref<TestRecord[]>([])
const loading = ref(false)
const exporting = ref(false)
const errorText = ref('')

const summary = computed(() => summarizeRecords(records.value))

function currentFilters(): TestRecordFilters {
  return {
    date_from: filters.dateFrom || undefined,
    date_to: filters.dateTo || undefined,
    sn: filters.sn.trim() || undefined,
    result: filters.result === ALL ? undefined : (Number(filters.result) as TestResult),
  }
}

async function loadRecords() {
  loading.value = true
  errorText.value = ''
  try {
    records.value = await getTestRecords(currentFilters())
  } catch (error) {
    errorText.value = `试车记录读取失败：${error instanceof Error ? error.message : String(error)}`
  } finally {
    loading.value = false
  }
}

async function handleExport() {
  exporting.value = true
  try {
    const response = await exportTestRecords(currentFilters())
    toast.success(`已导出 ${response.count} 条试车记录`, { description: response.path })
  } catch (error) {
    toast.error('导出失败', {
      description: error instanceof Error ? error.message : '请稍后重试',
    })
  } finally {
    exporting.value = false
  }
}

onMounted(loadRecords)
</script>

<template>
  <Card class="w-full">
    <CardHeader class="border-b pb-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <CardTitle>试车记录</CardTitle>
        <div class="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant="outline">共 {{ summary.total }} 台</Badge>
          <Badge variant="success">合格 {{ summary.passed }}</Badge>
          <Badge variant="destructive">NG {{ summary.failed }}</Badge>
          <Badge variant="outline">合格率 {{ summary.passRate }}</Badge>
        </div>
      </div>
      <CardDescription>
        每次在下线测试页判定合格 / NG 时保存一条，记录保存在本机。导出的 CSV 可直接用 Excel 打开。
      </CardDescription>
    </CardHeader>

    <CardContent class="flex flex-col gap-4 pt-1">
      <form class="flex flex-wrap items-end gap-3" @submit.prevent="loadRecords">
        <Field class="w-40">
          <FieldLabel for="records-date-from">起始日期</FieldLabel>
          <Input id="records-date-from" v-model="filters.dateFrom" type="date" />
        </Field>
        <Field class="w-40">
          <FieldLabel for="records-date-to">结束日期</FieldLabel>
          <Input id="records-date-to" v-model="filters.dateTo" type="date" />
        </Field>
        <Field class="w-48">
          <FieldLabel for="records-sn">序列号</FieldLabel>
          <Input id="records-sn" v-model="filters.sn" placeholder="包含即可" class="font-mono" />
        </Field>
        <Field class="w-32">
          <FieldLabel for="records-result">结论</FieldLabel>
          <Select v-model="filters.result">
            <SelectTrigger id="records-result" class="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent position="popper" side="bottom" align="start">
              <SelectGroup>
                <SelectItem :value="ALL">全部</SelectItem>
                <SelectItem value="1">合格</SelectItem>
                <SelectItem value="2">NG</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
        <div class="flex gap-2">
          <Button type="submit" :disabled="loading">
            <Spinner v-if="loading" data-icon="inline-start" />
            <SearchIcon v-else data-icon="inline-start" />
            查询
          </Button>
          <Button type="button" variant="outline" :disabled="exporting" @click="handleExport">
            <Spinner v-if="exporting" data-icon="inline-start" />
            <DownloadIcon v-else data-icon="inline-start" />
            导出 CSV
          </Button>
        </div>
      </form>

      <Alert v-if="errorText" variant="destructive">
        <AlertDescription>{{ errorText }}</AlertDescription>
      </Alert>

      <div class="overflow-x-auto rounded-lg border">
        <Table class="min-w-[1100px]">
          <TableHeader>
            <TableRow>
              <TableHead>判定时间</TableHead>
              <TableHead>序列号</TableHead>
              <TableHead>结论</TableHead>
              <TableHead class="text-right">试车时长</TableHead>
              <TableHead class="text-right">最高转速</TableHead>
              <TableHead class="text-right">最大转矩</TableHead>
              <TableHead class="text-right">电机温度</TableHead>
              <TableHead class="text-right">控制器温度</TableHead>
              <TableHead class="text-right">母线电流</TableHead>
              <TableHead>故障码</TableHead>
              <TableHead>PLC</TableHead>
              <TableHead>备注</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="record in records" :key="record.id">
              <TableCell class="whitespace-nowrap font-mono text-xs">
                {{ formatLocalTime(record.timestamp) }}
              </TableCell>
              <TableCell class="font-mono">{{ record.sn || '--' }}</TableCell>
              <TableCell>
                <Badge :variant="record.result === 1 ? 'success' : 'destructive'">
                  {{ record.result === 1 ? '合格' : 'NG' }}
                </Badge>
              </TableCell>
              <TableCell class="text-right">{{ formatDuration(record.duration_s) }}</TableCell>
              <TableCell class="text-right font-mono">
                {{ formatValue(record.max_speed_rpm, 'RPM') }}
              </TableCell>
              <TableCell class="text-right font-mono">
                {{ formatValue(record.max_torque_nm, 'Nm', 1) }}
              </TableCell>
              <TableCell class="text-right font-mono">
                {{ formatValue(record.max_motor_temp_c, '℃') }}
              </TableCell>
              <TableCell class="text-right font-mono">
                {{ formatValue(record.max_controller_temp_c, '℃') }}
              </TableCell>
              <TableCell class="text-right font-mono">
                {{ formatValue(record.max_bus_current_a, 'A', 1) }}
              </TableCell>
              <TableCell class="font-mono text-xs">
                {{ record.fault_codes || '--' }}
                <span v-if="record.safety_trips" class="block text-muted-foreground">
                  安全停机 {{ record.safety_trips }} 次
                </span>
              </TableCell>
              <TableCell>
                <Badge :variant="record.plc_result_written ? 'outline' : 'warning'">
                  {{ record.plc_result_written ? '已写入' : '未写入' }}
                </Badge>
              </TableCell>
              <TableCell class="max-w-56 truncate" :title="record.remark">
                {{ record.remark || '--' }}
              </TableCell>
            </TableRow>
            <TableEmpty v-if="!records.length && !loading" :colspan="COLUMN_COUNT">
              所选范围内没有试车记录
            </TableEmpty>
          </TableBody>
        </Table>
      </div>
    </CardContent>
  </Card>
</template>
