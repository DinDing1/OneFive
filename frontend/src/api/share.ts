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
}

/** 分享文件列表响应（listFiles 专用：含 items + count） */
export interface ShareFileListResponse {
  items: ShareFile[]
  count: number
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
  listShares(): Promise<ApiResult<{ shares: ShareSource[] }>> {
    return api.get('/share/list')
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

  /** 获取所有分享的根目录文件 */
  getAllFiles(organizedOnly: boolean = false, unorganizedOnly: boolean = false): Promise<ApiResult<{ files: ShareFile[] }>> {
    return api.get('/share/all-files', { params: { organized_only: organizedOnly, unorganized_only: unorganizedOnly } })
  },

  /** 获取指定分享目录下的文件 */
  listFiles(sourceId: number, parentId: string = '0', limit: number = 100, offset: number = 0): Promise<ApiResult<ShareFileListResponse>> {
    return api.get(`/share/${sourceId}/files`, { params: { parent_id: parentId, limit, offset } })
  },

  /** 获取所有分享的已整理文件（构建虚拟目录树用） */
  getAllOrganized(): Promise<ApiResult<any>> {
    return api.get('/share/all-organized')
  },

  /** 搜索分享文件 */
  searchFiles(keyword: string): Promise<ApiResult<{ files: ShareFile[] }>> {
    return api.get('/share/search', { params: { keyword } })
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
