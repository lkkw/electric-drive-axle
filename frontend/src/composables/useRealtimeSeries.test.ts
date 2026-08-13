import { afterEach, describe, expect, it, vi } from 'vitest'

import { useRealtimeSeries } from '@/composables/useRealtimeSeries'

afterEach(() => {
  vi.useRealTimers()
})

describe('useRealtimeSeries', () => {
  it('batches incoming points into one published snapshot', () => {
    vi.useFakeTimers()
    const series = useRealtimeSeries({ maxPoints: 5, refreshIntervalMs: 100 })

    series.append({ timestamp: 1, value: 10 })
    series.append({ timestamp: 2, value: 20 })

    expect(series.points.value).toEqual([])
    vi.advanceTimersByTime(99)
    expect(series.points.value).toEqual([])
    vi.advanceTimersByTime(1)
    expect(series.points.value).toEqual([
      { timestamp: 1, value: 10 },
      { timestamp: 2, value: 20 },
    ])
  })

  it('keeps only the newest values when the fixed buffer is full', () => {
    vi.useFakeTimers()
    const series = useRealtimeSeries({ maxPoints: 3, refreshIntervalMs: 100 })

    for (let value = 1; value <= 5; value += 1) {
      series.append({ timestamp: value, value })
    }
    vi.runOnlyPendingTimers()

    expect(series.points.value).toEqual([
      { timestamp: 3, value: 3 },
      { timestamp: 4, value: 4 },
      { timestamp: 5, value: 5 },
    ])
  })

  it('clears pending work and ignores points after disposal', () => {
    vi.useFakeTimers()
    const series = useRealtimeSeries({ refreshIntervalMs: 100 })

    series.append({ timestamp: 1, value: 1 })
    series.dispose()
    series.append({ timestamp: 2, value: 2 })
    vi.runAllTimers()

    expect(series.points.value).toEqual([])
    expect(vi.getTimerCount()).toBe(0)
  })

  it('preserves null values as explicit gaps between stream sessions', () => {
    const series = useRealtimeSeries({ refreshIntervalMs: 0 })

    series.append({ timestamp: 1, value: 1 })
    series.append({ timestamp: 2, value: null })
    series.append({ timestamp: 3, value: 1 })
    series.flush()

    expect(series.points.value[1]).toEqual({ timestamp: 2, value: null })
  })
})
