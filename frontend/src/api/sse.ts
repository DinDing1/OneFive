/**
 * SSE 工具：统一 EventSource 基址与「POST 建任务 → GET 拉流」两段式长任务。
 * 正式环境走飞牛统一网关，长任务必须 SSE + 服务端心跳，勿依赖 axios timeout。
 */
import api from './index'

export function apiBaseURL(): string {
  return api.defaults.baseURL || '/app/onefive/api'
}

export function openEventSource(pathWithQuery: string): EventSource {
  const base = apiBaseURL()
  const path = pathWithQuery.startsWith('/') ? pathWithQuery : `/${pathWithQuery}`
  return new EventSource(`${base}${path}`)
}

export type SseHandlers = {
  onStart?: (data: any) => void
  onProgress?: (data: any) => void
  onDone?: (data: any) => void
  onError?: (message: string, data?: any) => void
  /** 连接中断（且业务未正常结束） */
  onConnectionError?: (message: string) => void
}

/**
 * 监听 SSE，自动解析 JSON；返回 close 函数。
 * 忽略注释心跳（浏览器不会把 `: heartbeat` 交给 onmessage）。
 */
export function listenSse(es: EventSource, handlers: SseHandlers): () => void {
  let finished = false

  const close = () => {
    try { es.close() } catch { /* ignore */ }
  }

  es.onmessage = (event) => {
    let data: any
    try {
      data = JSON.parse(event.data)
    } catch {
      return
    }
    const t = data?.type
    if (t === 'start') {
      handlers.onStart?.(data)
      return
    }
    if (t === 'progress') {
      handlers.onProgress?.(data)
      return
    }
    if (t === 'done') {
      finished = true
      handlers.onDone?.(data)
      close()
      return
    }
    if (t === 'error') {
      finished = true
      handlers.onError?.(data?.message || '任务失败', data)
      close()
    }
  }

  es.onerror = () => {
    if (finished) {
      close()
      return
    }
    if (es.readyState === EventSource.CLOSED) {
      finished = true
      handlers.onConnectionError?.('连接中断（网关或网络），请重试')
      close()
    }
  }

  return close
}
