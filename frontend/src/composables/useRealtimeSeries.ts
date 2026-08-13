import { shallowRef, type ShallowRef } from 'vue'

import type { RealtimeLinePoint } from '@/types/chart'

interface RealtimeSeriesOptions {
  maxPoints?: number
  refreshIntervalMs?: number
}

interface RealtimeSeriesController {
  points: ShallowRef<readonly RealtimeLinePoint[]>
  append: (point: RealtimeLinePoint) => void
  clear: () => void
  flush: () => void
  dispose: () => void
}

class FixedSizeBuffer<T> {
  readonly #values: Array<T | undefined>
  readonly capacity: number
  #head = 0
  #size = 0

  constructor(capacity: number) {
    if (!Number.isInteger(capacity) || capacity <= 0) {
      throw new RangeError('Buffer capacity must be a positive integer')
    }
    this.capacity = capacity
    this.#values = new Array<T | undefined>(capacity)
  }

  push(value: T): void {
    if (this.#size < this.capacity) {
      const index = (this.#head + this.#size) % this.capacity
      this.#values[index] = value
      this.#size += 1
      return
    }

    this.#values[this.#head] = value
    this.#head = (this.#head + 1) % this.capacity
  }

  clear(): void {
    this.#values.fill(undefined)
    this.#head = 0
    this.#size = 0
  }

  toArray(): T[] {
    return Array.from({ length: this.#size }, (_, offset) => {
      const value = this.#values[(this.#head + offset) % this.capacity]
      // Every index below #size has been assigned by push().
      return value as T
    })
  }
}

export function useRealtimeSeries(
  options: RealtimeSeriesOptions = {},
): RealtimeSeriesController {
  const maxPoints = options.maxPoints ?? 1_000
  const refreshIntervalMs = options.refreshIntervalMs ?? 100

  if (!Number.isFinite(refreshIntervalMs) || refreshIntervalMs < 0) {
    throw new RangeError('Refresh interval must be a non-negative finite number')
  }

  const buffer = new FixedSizeBuffer<RealtimeLinePoint>(maxPoints)
  const points = shallowRef<readonly RealtimeLinePoint[]>([])
  let refreshTimer: ReturnType<typeof setTimeout> | null = null
  let disposed = false
  let dirty = false

  function flush(): void {
    if (refreshTimer !== null) {
      clearTimeout(refreshTimer)
      refreshTimer = null
    }
    if (!dirty || disposed) {
      return
    }

    points.value = buffer.toArray()
    dirty = false
  }

  function scheduleFlush(): void {
    if (refreshTimer !== null || disposed) {
      return
    }
    refreshTimer = setTimeout(flush, refreshIntervalMs)
  }

  function append(point: RealtimeLinePoint): void {
    if (disposed) {
      return
    }
    if (!Number.isFinite(point.timestamp)) {
      throw new TypeError('Point timestamp must be finite')
    }
    if (point.value !== null && !Number.isFinite(point.value)) {
      throw new TypeError('Point value must be finite or null')
    }

    buffer.push(point)
    dirty = true
    scheduleFlush()
  }

  function clear(): void {
    if (refreshTimer !== null) {
      clearTimeout(refreshTimer)
      refreshTimer = null
    }
    buffer.clear()
    dirty = false
    points.value = []
  }

  function dispose(): void {
    clear()
    disposed = true
  }

  return { points, append, clear, flush, dispose }
}
