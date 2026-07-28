import api, { type ApiResult } from './index'
import { openEventSource } from './sse'

/** STRM 配置 */
export interface StrmSettings {
  direct_link_base_url: string
  output_path: string
  cloud_output_path: string
  video_extensions: string
}

/** STRM 生成结果 */
export interface StrmGenerateResult {
  total: number
  created: number
  skipped: number
  failed: number
  errors: Array<{ file_id: string; name: string; error: string }>
  truncated?: boolean
}

/**
 * 分享/云盘 STRM 生成：正式环境走飞牛统一网关，长任务用 SSE（与洗版/检测一致），
 * 不依赖 axios 默认 30s 超时。
 */
function openStrmGenerateStream(path: string): EventSource {
  return openEventSource(path)
}

export const strmApi = {
  /** 获取 STRM 配置 */
  getSettings(): Promise<ApiResult<StrmSettings>> {
    return api.get('/strm/settings')
  },

  /** 保存 STRM 配置 */
  saveSettings(settings: StrmSettings): Promise<ApiResult<any>> {
    return api.post('/strm/settings', settings)
  },

  /** 获取飞牛授权目录列表 */
  getAccessiblePaths(): Promise<ApiResult<any>> {
    return api.get('/strm/accessible-paths')
  },

  /** 列出授权目录下的子目录（一层） */
  getAccessibleChildren(path: string): Promise<ApiResult<any>> {
    return api.get('/strm/accessible-paths/children', { params: { path } })
  },

  /** @deprecated 优先使用 generateStream，保留同步接口作兼容 */
  generate(): Promise<ApiResult<StrmGenerateResult>> {
    return api.post('/strm/generate')
  },

  /** @deprecated 优先使用 generateCloudStream，保留同步接口作兼容 */
  generateCloud(): Promise<ApiResult<StrmGenerateResult>> {
    return api.post('/strm/generate-cloud')
  },

  /** 流式生成分享 STRM（SSE） */
  generateStream(): EventSource {
    return openStrmGenerateStream('/strm/generate-stream')
  },

  /** 流式生成云盘 STRM（SSE） */
  generateCloudStream(): EventSource {
    return openStrmGenerateStream('/strm/generate-cloud-stream')
  }
}
