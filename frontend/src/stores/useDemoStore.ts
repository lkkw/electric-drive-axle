import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { getDemo, type DemoResponse } from '@/api/demo'

export const useDemoStore = defineStore('demo', () => {
  const demo = ref<DemoResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const hasData = computed(() => demo.value !== null)

  async function fetchDemo(): Promise<DemoResponse | null> {
    loading.value = true
    error.value = null

    try {
      // Alova Method 是 PromiseLike；send() 明确表达“立即发送请求”。
      const response = await getDemo().send()
      demo.value = response
      return response
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '无法读取 REST 演示数据'
      return null
    } finally {
      loading.value = false
    }
  }

  function clearDemo(): void {
    demo.value = null
    error.value = null
  }

  return {
    demo,
    loading,
    error,
    hasData,
    fetchDemo,
    clearDemo,
  }
})
