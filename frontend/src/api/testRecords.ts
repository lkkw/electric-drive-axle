import type {
  TestRecord,
  TestRecordExportResponse,
  TestRecordFilters,
  TestRecordJudgeResponse,
  TestResult,
  TestSessionStats,
} from '@/types/testRecords'
import { alova } from '@/utils/alova'

/** 当前这台电驱桥的试车统计 */
export const getTestSession = () =>
  alova.Get<TestSessionStats>('/test-records/session', { cacheFor: 0 })

/** 试车判定：写入 PLC Result、保存记录、清零统计 */
export const judgeTest = (result: TestResult, remark = '') =>
  alova.Post<TestRecordJudgeResponse>('/test-records/judge', { result, remark })

/** 查询试车记录（最新在前） */
export const getTestRecords = (filters: TestRecordFilters, limit = 2000) =>
  alova.Get<TestRecord[]>('/test-records', { params: { ...filters, limit }, cacheFor: 0 })

/** 按筛选条件导出 CSV，并在资源管理器中打开所在文件夹 */
export const exportTestRecords = (filters: TestRecordFilters) =>
  alova.Post<TestRecordExportResponse>('/test-records/export', {}, {
    params: { ...filters, open_folder: true },
  })
