import axios from 'axios'

/**
 * 统一 API 响应结构。
 * 响应拦截器已将 axios response.data（即该结构）直接返回，
 * 因此各 API 方法的返回类型用 Promise<ApiResult<T>> 描述更精确。
 */
export interface ApiResult<T = any> {
  code: number
  message: string
  data: T
}

/** 全局请求超时时间（毫秒），长耗时接口（如整理）改用 SSE 流式响应绕过此限制 */
const API_TIMEOUT = 30000

const api = axios.create({
  baseURL: '/app/onefive/api',
  timeout: API_TIMEOUT,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 响应拦截器
api.interceptors.response.use(
  response => response.data,
  error => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export default api
