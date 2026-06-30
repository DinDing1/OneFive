import api from './index'

export const notificationApi = {
  /** 获取所有通知渠道状态 */
  getChannels(): Promise<any> {
    return api.get('/notification/channels')
  },

  /** 获取渠道配置 */
  getSettings(channel: string): Promise<any> {
    return api.get(`/notification/settings/${channel}`)
  },

  /** 更新渠道配置 */
  updateSettings(channel: string, settings: Record<string, any>): Promise<any> {
    return api.put('/notification/settings', { channel, settings })
  },

  /** 连接渠道 */
  connect(channel: string): Promise<any> {
    return api.post('/notification/connect', { channel })
  },

  /** 发送测试消息 */
  test(channel: string, message?: string): Promise<any> {
    return api.post('/notification/test', { channel, message })
  },

  /** Telegram：发送验证码 */
  sendCode(phone: string, apiId: string, apiHash: string): Promise<any> {
    return api.post('/notification/telegram/send-code', { phone, api_id: apiId, api_hash: apiHash })
  },

  /** Telegram：验证码登录 */
  signIn(phone: string, code: string, password?: string): Promise<any> {
    return api.post('/notification/telegram/sign-in', { phone, code, password: password || '' })
  },

  /** Telegram：检查登录状态 */
  checkLogin(): Promise<any> {
    return api.post('/notification/telegram/check-login')
  },
}
