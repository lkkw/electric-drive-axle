import { createAlova } from 'alova'
import adapterFetch from 'alova/fetch'
import VueHook from 'alova/vue'

interface ApiErrorBody {
  detail?: string | Array<{ msg?: string }>
  message?: string
}

function getErrorMessage(body: ApiErrorBody, status: number): string {
  if (typeof body.detail === 'string') {
    return body.detail
  }

  if (Array.isArray(body.detail)) {
    const messages = body.detail.map((item) => item.msg).filter(Boolean)
    if (messages.length > 0) {
      return messages.join('；')
    }
  }

  return body.message ?? `请求失败（HTTP ${status}）`
}

/** REST 与 SSE 共用同一个 API 前缀。开发时由 Vite 代理 `/api`。 */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '')

export const alova = createAlova({
  baseURL: API_BASE_URL,
  statesHook: VueHook,
  requestAdapter: adapterFetch(),

  beforeRequest(method) {
    method.config.headers.Accept = 'application/json'
    method.config.headers['X-Client-Name'] = 'electric-drive-axle'

    // 示例：登录后把令牌写到 localStorage，所有 REST 请求会自动携带它。
    const token = localStorage.getItem('access_token')
    if (token) {
      method.config.headers.Authorization = `Bearer ${token}`
    }
  },

  responded: {
    async onSuccess(response) {
      // Fetch 收到 4xx/5xx 时不会自动 reject，必须在这里显式检查。
      if (!response.ok) {
        let message = `请求失败（HTTP ${response.status}）`

        try {
          const body = (await response.json()) as ApiErrorBody
          message = getErrorMessage(body, response.status)
        } catch {
          // 错误响应不一定是 JSON；保留上面的 HTTP 状态信息即可。
        }

        throw new Error(message)
      }

      if (response.status === 204) {
        return undefined
      }

      return response.json()
    },
    onError(error) {
      // 继续抛出，调用层才能正确进入 catch 并更新错误状态。
      throw error
    },
  },
})
