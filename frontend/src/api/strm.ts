import api from './index'

/** STRM 配置 */
export interface StrmSettings {
  direct_link_base_url: string
  output_path: string
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
  getSettings(): Promise<any> {
    return api.get('/strm/settings')
  },

  /** 保存 STRM 配置 */
  saveSettings(settings: StrmSettings): Promise<any> {
    return api.post('/strm/settings', settings)
  },

  /** 获取飞牛授权目录列表 */
  getAccessiblePaths(): Promise<any> {
    return api.get('/strm/accessible-paths')
  },

  /** 生成 STRM 文件 */
  generate(): Promise<any> {
    return api.post('/strm/generate')
  }
}
