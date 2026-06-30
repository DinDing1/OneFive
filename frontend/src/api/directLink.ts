import api from './index'

/** 直链服务设置 */
export interface DirectLinkSettings {
  enabled: boolean
  port: number
  running: boolean
}

export const directLinkApi = {
  /** 获取直链设置 */
  getSettings(): Promise<any> {
    return api.get('/direct-link/settings')
  },

  /** 保存直链设置 */
  saveSettings(settings: { enabled: boolean; port: number }): Promise<any> {
    return api.post('/direct-link/settings', settings)
  },

  /** 启动直链服务 */
  start(): Promise<any> {
    return api.post('/direct-link/start')
  },

  /** 停止直链服务 */
  stop(): Promise<any> {
    return api.post('/direct-link/stop')
  },

  /** 查询服务状态 */
  getStatus(): Promise<any> {
    return api.get('/direct-link/status')
  }
}
