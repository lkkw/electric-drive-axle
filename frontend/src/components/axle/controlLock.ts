import type { BadgeVariants } from '@/components/ui/badge'
import type { CycleTestStatus } from '@/types/axle'

export interface CycleControlLock {
  /** 手动控制是否锁定（页签不可切换、所有手动指令禁用） */
  locked: boolean
  /** 循环测试页签上的状态标记；未锁定时为 null */
  label: '运行中' | '已暂停' | '判定中' | null
  variant: NonNullable<BadgeVariants['variant']>
}

/**
 * 循环测试对手动控制的占用状态。
 *
 * 运行、暂停时循环测试持有控制权；循环结束后的自动判定期间（等待停转 → 判定 → 自动下电）
 * 后端同样拒绝手动指令，前端一并锁定，避免操作员在下电前重新使能电机。
 */
export function cycleControlLock(
  cycle: Pick<CycleTestStatus, 'status' | 'auto_judge'>,
): CycleControlLock {
  if (cycle.status === 'running') return { locked: true, label: '运行中', variant: 'success' }
  if (cycle.status === 'paused') return { locked: true, label: '已暂停', variant: 'warning' }
  if (cycle.auto_judge === 'pending') return { locked: true, label: '判定中', variant: 'info' }
  return { locked: false, label: null, variant: 'secondary' }
}
