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
 *
 * 飞牛网关可能中途断开长连接，浏览器 EventSource 会自动重连：
 * - CONNECTING：重连中，不报错
 * - 已收到业务事件后短暂 CLOSED：宽限等待重连，避免误报失败
 * - 从未收到事件且最终 CLOSED：提示连接中断
 */
export function listenSse(es: EventSource, handlers: SseHandlers): () => void {
  let finished = false
  let sawEvent = false
  let softErrorTimer: number | null = null

  const clearSoftTimer = () => {
    if (softErrorTimer != null) {
      window.clearTimeout(softErrorTimer)
      softErrorTimer = null
    }
  }

  const close = () => {
    clearSoftTimer()
    try { es.close() } catch { /* ignore */ }
  }

  es.onmessage = (event) => {
    let data: any
    try {
      data = JSON.parse(event.data)
    } catch {
      return
    }
    sawEvent = true
    clearSoftTimer()

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
    // 浏览器自动重连中，忽略
    if (es.readyState === EventSource.CONNECTING) {
      return
    }
    if (es.readyState === EventSource.CLOSED) {
      // 已有业务事件：通常是网关断开，给重连留宽限；宽限后仍无后续事件再报中断
      // 注意：后端 claim 模型下重连可继续收进度，不要立刻 onConnectionError
      if (softErrorTimer == null) {
        softErrorTimer = window.setTimeout(() => {
          if (finished) return
          // 宽限后若仍未结束：提示可能后台仍在跑
          finished = true
          const msg = sawEvent
            ? '进度连接中断（后台任务可能仍在执行，请稍后刷新查看）'
            : '连接中断（网关或网络），请重试'
          handlers.onConnectionError?.(msg)
          close()
        }, sawEvent ? 12000 : 8000)
      }
    }
  }

  return close
}