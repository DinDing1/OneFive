import api from './index'

export interface RecognizeRequest {
  file_id: string
  file_name: string
  is_dir: boolean
  folder_files?: string[]
}

export interface ManualRecognizeRequest extends RecognizeRequest {
  tmdb_id: number
  media_type: 'movie' | 'tv'
}

export interface RecognizeResult {
  file_id: string
  filename: string
  is_dir: boolean
  media_type: string
  title: string
  year: string | null
  season: number | null
  episode: number | null
  tmdb_id: number | null
  category: string
  tech_info: {
    videoFormat: string
    videoCodec: string
    audioCodec: string
    webSource: string
    edition: string
    releaseGroup: string
    fileExt: string
  }
  target_path: {
    dir: string
    filename: string
  } | null
  tmdb_poster: string | null
  tmdb_backdrop: string | null
  tmdb_overview: string
  tmdb_rating: number
}

export interface ExecuteRequest {
  file_id: string
  file_name: string
  is_dir: boolean
  target_path: { dir: string; filename: string }
  organize_mode: string
  category?: string
  target_title?: string
  tmdb_id?: number
  media_type?: string
  year?: string
  season?: number
  episode?: number
  tmdb_poster?: string
  tmdb_backdrop?: string
  tmdb_rating?: number
  tech_info?: Record<string, string>
}

export const organizeApi = {
  /** 识别文件 */
  recognize(req: RecognizeRequest): Promise<any> {
    return api.post('/organize/recognize', req)
  },

  /** 手动纠错识别 */
  manualRecognize(req: ManualRecognizeRequest): Promise<any> {
    return api.post('/organize/recognize/manual', req)
  },

  /** 获取整理配置 */
  getSettings(): Promise<any> {
    return api.get('/organize/settings')
  },

  /** 更新整理配置 */
  updateSettings(settings: Record<string, string>): Promise<any> {
    return api.put('/organize/settings', settings)
  },

  /** 恢复默认重命名模板 */
  resetTemplates(): Promise<any> {
    return api.post('/organize/settings/reset-templates')
  },

  /** 恢复默认分类策略 */
  resetRules(): Promise<any> {
    return api.post('/organize/settings/reset-rules')
  },

  /** 执行整理 */
  execute(req: ExecuteRequest): Promise<any> {
    return api.post('/organize/execute', req)
  },
}
