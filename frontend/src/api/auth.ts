import api from './index'

export type VipType = 'none' | 'vip' | 'forever'

export interface LoginStatus {
  is_logged_in: boolean
  user_id: string | null
  user_name: string | null
  vip: number
  vip_type: VipType
  face: string
  message: string
}

export interface QRCodeResponse {
  code: number
  message: string
  data: {
    session_id: string
    qr_code_url: string
    device: string
    device_name: string
    tip: string
  }
}

export interface LoginCheckResponse {
  status: string
  cookies: string | null
  user_name: string | null
  message: string
}

export interface DevicesResponse {
  code: number
  message: string
  data: {
    devices: Record<string, string>
  }
}

export const authApi = {
  // 获取登录状态
  getLoginStatus(): Promise<LoginStatus> {
    return api.get('/auth/status')
  },

  // 获取可用设备列表
  getDevices(): Promise<DevicesResponse> {
    return api.get('/auth/devices')
  },

  // 获取扫码登录二维码
  getQRCode(device: string = 'web'): Promise<QRCodeResponse> {
    return api.post('/auth/qrcode', { device })
  },

  // 检查扫码登录状态
  checkQRCodeStatus(sessionId: string): Promise<LoginCheckResponse> {
    return api.get(`/auth/qrcode/check/${sessionId}`)
  },

  // 手动设置 cookies 登录
  loginWithCookies(cookies: string): Promise<any> {
    return api.post('/auth/login/cookies', { cookies })
  },

  // 登出
  logout(): Promise<any> {
    return api.post('/auth/logout')
  }
}