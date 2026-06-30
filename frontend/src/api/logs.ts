import api from './index'

export interface LogLine {
  time: string
  level: string
  module: string
  message: string
  raw: string
}

export interface LogsResponse {
  lines: LogLine[]
  total: number
}

export const logsApi = {
  /** 获取最近日志 */
  getLogs(lines = 200, level = '', keyword = ''): Promise<LogsResponse> {
    const params: any = { lines }
    if (level) params.level = level
    if (keyword) params.keyword = keyword
    return api.get('/logs', { params })
  },
}
