import api, { type ApiResult } from './index'

/** 直链服务设置 */
export interface DirectLinkSettings {
  enabled: boolean
  port: number
  allow_lan: boolean
  running: boolean
}

export const directLinkApi = {
  /** 获取直链设置 */
  getSettings(): Promise<ApiResult<DirectLinkSettings>> {
    return api.get('/direct-link/settings')
  },

  /** 保存直链设置 */
  saveSettings(settings: { enabled: boolean; port: number; allow_lan?: boolean }): Promise<ApiResult<any>> {
    return api.post('/direct-link/settings', settings)
  },

  /** 启动直链服务 */
  start(): Promise<ApiResult<any>> {
    return api.post('/direct-link/start')
  },

  /** 停止直链服务 */
  stop(): Promise<ApiResult<any>> {
    return api.post('/direct-link/stop')
  },

  /** 查询服务状态 */
  getStatus(): Promise<ApiResult<DirectLinkSettings>> {
    return api.get('/direct-link/status')
  }
}
