import api, { type ApiResult } from './index'

export interface TaskSchedulePreset {
  frequency: 'minutely' | 'daily' | 'weekly' | 'hourly' | 'custom'
  hour?: number
  minute?: number
  interval?: number
  weekday?: number
  cron?: string
}

export interface TaskLastResult {
  success?: boolean
  message?: string
  trigger?: string
  started_at?: string
  finished_at?: string
  scanned?: number
  processed?: number
  success_count?: number
  failed?: number
  skipped?: number
  errors?: Array<{ name?: string; reason?: string; error?: string }>
  [key: string]: any
}

export interface TaskItem {
  id: string
  name: string
  description: string
  icon?: string
  category?: string
  category_label?: string
  enabled: boolean
  cron: string
  cron_label: string
  schedule_preset: TaskSchedulePreset
  next_run_time?: string
  last_run_time?: string
  last_result?: TaskLastResult | null
  running: boolean
  last_error?: string
  scheduler_ready?: boolean
}

export interface TaskUpdatePayload {
  enabled?: boolean
  cron?: string
  frequency?: 'minutely' | 'daily' | 'weekly' | 'hourly'
  hour?: number
  minute?: number
  interval?: number
  weekday?: number
}

export const tasksApi = {
  list(): Promise<ApiResult<{ tasks: TaskItem[] }>> {
    return api.get('/tasks') as any
  },
  get(taskId: string): Promise<ApiResult<TaskItem>> {
    return api.get(`/tasks/${encodeURIComponent(taskId)}`) as any
  },
  update(taskId: string, payload: TaskUpdatePayload): Promise<ApiResult<TaskItem>> {
    return api.put(`/tasks/${encodeURIComponent(taskId)}`, payload) as any
  },
  run(taskId: string): Promise<ApiResult<any>> {
    return api.post(`/tasks/${encodeURIComponent(taskId)}/run`) as any
  },
}
