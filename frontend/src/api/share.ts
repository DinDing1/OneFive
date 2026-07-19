import api, { type ApiResult } from './index'
import { type RecognizeResult } from './organize'

/** 分享来源 */
export interface ShareSource {
  id: number
  share_code: string
  receive_code: string
  share_name: string
  share_url: string
  source_type: string
  file_count: number
  total_size: number
  status: string
  link_valid: number  // 1=有效 0=无效 默认1
  error_msg: string
  created_at: string
  updated_at: string
}

/** 分享文件（含目录） */
export interface ShareFile {
  id: number
  source_id: number
  share_code: string
  receive_code: string
  file_id: string
  parent_id: string
  name: string
  is_dir: number
  size: number
  sha1: string
  media_type: string
  title: string
  year: string
  tmdb_id: number
  category: string
  organized_dir: string
  organized_name: string
  organized: number
  created_at: string
  updated_at: string
  // 联表查询时附带的信息
  file_count?: number
  share_name?: string
  link_valid?: number
}

/** 分享文件列表响应（listFiles 专用：含 items + count） */
export interface ShareFileListResponse {
  items: ShareFile[]
  total: number
  count?: number
  limit?: number
  offset?: number
}

export const shareApi = {
  /** 识别文件（只识别不写入数据库，用于预览） */
  recognizeFile(sourceId: number, fileId: string): Promise<ApiResult<RecognizeResult>> {
    return api.post('/share/recognize', { source_id: sourceId, file_id: fileId })
  },

  /** 手动纠错识别 */
  manualRecognizeFile(sourceId: number, fileId: string, tmdbId: number, mediaType: 'movie' | 'tv'): Promise<ApiResult<RecognizeResult>> {
    return api.post('/share/recognize/manual', { source_id: sourceId, file_id: fileId, tmdb_id: tmdbId, media_type: mediaType })
  },

  /** 手动纠错整理 */
  manualOrganizeFile(sourceId: number, fileId: string, tmdbId: number, mediaType: 'movie' | 'tv'): Promise<ApiResult<any>> {
    return api.post('/share/organize/manual', { source_id: sourceId, file_id: fileId, tmdb_id: tmdbId, media_type: mediaType })
  },

  /** 添加分享链接 */
  addShare(shareUrl: string, receiveCode: string = ''): Promise<ApiResult<ShareSource>> {
    return api.post('/share/add', { share_url: shareUrl, receive_code: receiveCode })
  },

  /** 列出分享来源 */
  listShares(params: { limit?: number; offset?: number } = {}): Promise<ApiResult<{
    shares: ShareSource[]
    total: number
    limit?: number
    offset?: number
  }>> {
    const { limit, offset = 0 } = params
    return api.get('/share/list', {
      params: {
        ...(limit != null ? { limit } : {}),
        offset,
      },
    })
  },

  /** 检测单个分享链接有效性 */
  checkLinkValid(sourceId: number): Promise<ApiResult<any>> {
    return api.post(`/share/${sourceId}/check`)
  },

  /** 批量检测分享链接有效性（SSE 流式） */
  checkAllLinksStream(): EventSource {
    const baseURL = api.defaults.baseURL || '/app/onefive/api'
    return new EventSource(`${baseURL}/share/check-stream`)
  },

  /** 删除分享 */
  deleteShare(sourceId: number): Promise<ApiResult<any>> {
    return api.delete(`/share/${sourceId}`)
  },

  /** 批量删除分享 */
  deleteSharesBatch(sourceIds: number[]): Promise<ApiResult<any>> {
    return api.post('/share/delete-batch', { source_ids: sourceIds })
  },

  /** 获取文件属性（分享信息 + 文件信息 + 可选分类） */
  getFileProperties(sourceId: number, fileId: string): Promise<ApiResult<any>> {
    return api.get(`/share/${sourceId}/properties`, { params: { file_id: fileId } })
  },

  /** 更新分享属性（名称、分享码、提取码） */
  updateShareProperties(sourceId: number, data: { share_name?: string; share_code?: string; receive_code?: string }): Promise<ApiResult<any>> {
    return api.put(`/share/${sourceId}/properties`, data)
  },

  /** 更新文件分类 */
  updateFileCategory(sourceId: number, fileId: string, category: string): Promise<ApiResult<any>> {
    return api.put(`/share/${sourceId}/files/${fileId}/category`, { category })
  },

  /** 分页获取所有分享根目录文件（3 万+ 规模必须分页） */
  getAllFiles(params: {
    filter?: 'all' | 'organized' | 'unorganized' | 'valid' | 'invalid'
    limit?: number
    offset?: number
    includeCounts?: boolean
  } = {}): Promise<ApiResult<{
    files: ShareFile[]
    total: number
    limit: number
    offset: number
    filter?: string
    counts?: {
      all_count: number
      organized_count: number
      unorganized_count: number
      valid_count: number
      invalid_count: number
    }
  }>> {
    const {
      filter = 'all',
      limit = 50,
      offset = 0,
      includeCounts = true,
    } = params
    return api.get('/share/all-files', {
      params: {
        filter,
        limit,
        offset,
        include_counts: includeCounts,
      },
    })
  },

  /** 获取指定分享目录下的文件 */
  listFiles(sourceId: number, parentId: string = '0', limit: number = 100, offset: number = 0): Promise<ApiResult<ShareFileListResponse>> {
    return api.get(`/share/${sourceId}/files`, { params: { parent_id: parentId, limit, offset } })
  },

  /**
   * 服务端分页浏览整理视图虚拟目录
   * path: category/organized_dir 前缀，空=根
   */
  browseOrganized(params: {
    path?: string
    limit?: number
    offset?: number
  } = {}): Promise<ApiResult<{
    path: string
    entries: Array<{
      name: string
      path: string
      is_dir: number
      file_count?: number
      total_size?: number
      file?: ShareFile
    }>
    total: number
    dir_count: number
    file_count: number
    limit: number
    offset: number
  }>> {
    return api.get('/share/organized-browse', {
      params: {
        path: params.path ?? '',
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
      },
    })
  },

  /**
   * 分页搜索分享文件
   * scope: all | organized | original
   */
  searchFiles(
    keyword: string,
    options: { limit?: number; offset?: number; scope?: 'all' | 'organized' | 'original' } = {}
  ): Promise<ApiResult<{
    files: ShareFile[]
    total: number
    limit: number
    offset: number
    keyword: string
    scope: string
    engine?: string
  }>> {
    return api.get('/share/search', {
      params: {
        keyword,
        limit: options.limit ?? 50,
        offset: options.offset ?? 0,
        scope: options.scope ?? 'all',
      },
    })
  },

  /** 自底向上重算目录已整理标记（修复脏数据） */
  recomputeOrganized(sourceId?: number): Promise<ApiResult<{
    sources: number
    checked_dirs: number
    changed_dirs: number
  }>> {
    return api.post('/share/recompute-organized', null, {
      params: sourceId != null ? { source_id: sourceId } : {},
    })
  },

  /** 批量整理 */
  organizeBatch(sourceId: number, fileIds: string[]): Promise<ApiResult<any>> {
    return api.post('/share/organize-batch', { source_id: sourceId, file_ids: fileIds })
  },

  /**
   * 流式批量整理（SSE 实时进度）
   * 返回 EventSource 实例，监听 message 事件获取进度
   * 事件数据格式：
   *   {type: "progress", index, total, name, success, title, category, error}
   *   {type: "done", total, success, failed}
   *   {type: "error", message}
   */
  organizeStream(sourceId: number, fileIds: string[]): EventSource {
    const fileIdsParam = fileIds.join(',')
    // 从 axios 实例读取 baseURL，避免硬编码导致与 index.ts 配置不一致
    const baseURL = api.defaults.baseURL || '/app/onefive/api'
    const url = `${baseURL}/share/organize-stream?source_id=${sourceId}&file_ids=${encodeURIComponent(fileIdsParam)}`
    return new EventSource(url)
  },

}
