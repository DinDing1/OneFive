import api, { type ApiResult } from './index'

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

  /** 生成分享 STRM 文件 */
  generate(): Promise<ApiResult<StrmGenerateResult>> {
    return api.post('/strm/generate')
  },

  /** 生成云盘 STRM 文件 */
  generateCloud(): Promise<ApiResult<StrmGenerateResult>> {
    return api.post('/strm/generate-cloud')
  }
}
