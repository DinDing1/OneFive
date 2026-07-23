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

export const shareWashApi = {
  analyze(mediaType: 'all' | 'movie' | 'tv' = 'all'): Promise<ApiResult<WashAnalyzeResult>> {
    return api.post('/share-wash/analyze', { media_type: mediaType })
  },
  deleteSources(sourceIds: number[]): Promise<ApiResult<{ total: number; success: number; failed: number; source_ids: number[] }>> {
    return api.post('/share-wash/delete', { source_ids: sourceIds })
  }
}
