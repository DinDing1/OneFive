import api, { type ApiResult } from './index'

export interface WashSourceItem {
  source_id: number
  share_code: string
  receive_code: string
  share_name: string
  share_url: string
  link_valid: number
  file_count: number
  total_size: number
  updated_at: string
  created_at: string
  media_type: string
  tmdb_id: number
  title: string
  year: string
  season?: number | null
  group_key: string
  episode_count: number
  quality_score: number
  completeness_bonus?: number
  completeness_ratio?: number
  score: number
  quality_level?: string
  tags: string[]
  release_group?: string
  multi_title: boolean
  organized_video_count: number
  sample_names: string[]
  keep: boolean
  selected: boolean
}

export interface WashGroup {
  key: string
  media_type: string
  tmdb_id: number
  title: string
  year: string
  season?: number | null
  count: number
  items: WashSourceItem[]
}

export interface WashAnalyzeResult {
  summary: {
    organized_videos: number
    sources_scanned: number
    groups: number
    deletable_sources: number
    keep_sources: number
  }
  groups: WashGroup[]
}

/**
 * 分享洗版分析：正式环境走飞牛统一网关，长任务用 SSE（与整理/检测一致），
 * 不依赖 axios 默认 30s 超时。
 */
export function analyzeShareWashStream(mediaType: 'all' | 'movie' | 'tv' = 'all'): EventSource {
  const baseURL = api.defaults.baseURL || '/app/onefive/api'
  const url = `${baseURL}/share-wash/analyze-stream?media_type=${encodeURIComponent(mediaType)}`
  return new EventSource(url)
}

export const shareWashApi = {
  /** @deprecated 优先使用 analyzeStream，保留同步接口作兼容 */
  analyze(mediaType: 'all' | 'movie' | 'tv' = 'all'): Promise<ApiResult<WashAnalyzeResult>> {
    return api.post('/share-wash/analyze', { media_type: mediaType }, { timeout: 300000 })
  },
  analyzeStream(mediaType: 'all' | 'movie' | 'tv' = 'all'): EventSource {
    return analyzeShareWashStream(mediaType)
  },
  deleteSources(sourceIds: number[]): Promise<ApiResult<{ total: number; success: number; failed: number; source_ids: number[] }>> {
    return api.post('/share-wash/delete', { source_ids: sourceIds }, { timeout: 120000 })
  }
}
