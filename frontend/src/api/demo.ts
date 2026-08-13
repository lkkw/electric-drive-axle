import { alova } from '@/utils/alova'

export interface DemoResponse {
  message: string
  server_time: string
  request_id: string
}

export interface DemoEchoRequest {
  name: string
  message: string
}

export interface DemoEchoResponse {
  reply: string
  received_at: string
}

/** 实时状态类 GET 禁用缓存，确保每次都访问后端。 */
export const getDemo = () => alova.Get<DemoResponse>('/demo', { cacheFor: 0 })

export const echoDemo = (payload: DemoEchoRequest) =>
  alova.Post<DemoEchoResponse>('/demo/echo', payload)
