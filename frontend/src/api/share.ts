import api from './index'

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

export const shareApi = {
  /** 识别文件（只识别不写入数据库，用于预览） */
  recognizeFile(sourceId: number, fileId: string): Promise<any> {
    return api.post('/share/recognize', { source_id: sourceId, file_id: fileId })
  },

  /** 手动纠错识别 */
  manualRecognizeFile(sourceId: number, fileId: string, tmdbId: number, mediaType: 'movie' | 'tv'): Promise<any> {
    return api.post('/share/recognize/manual', { source_id: sourceId, file_id: fileId, tmdb_id: tmdbId, media_type: mediaType })
  },

  /** 手动纠错整理 */
  manualOrganizeFile(sourceId: number, fileId: string, tmdbId: number, mediaType: 'movie' | 'tv'): Promise<any> {
    return api.post('/share/organize/manual', { source_id: sourceId, file_id: fileId, tmdb_id: tmdbId, media_type: mediaType })
  },

  /** 添加分享链接 */
  addShare(shareUrl: string, receiveCode: string = ''): Promise<any> {
    return api.post('/share/add', { share_url: shareUrl, receive_code: receiveCode })
  },

  /** 列出分享来源 */
  listShares(): Promise<any> {
    return api.get('/share/list')
  },

  /** 删除分享 */
  deleteShare(sourceId: number): Promise<any> {
    return api.delete(`/share/${sourceId}`)
  },

  /** 获取所有分享的根目录文件 */
  getAllFiles(organizedOnly: boolean = false, unorganizedOnly: boolean = false): Promise<any> {
    return api.get('/share/all-files', { params: { organized_only: organizedOnly, unorganized_only: unorganizedOnly } })
  },

  /** 获取指定分享目录下的文件 */
  listFiles(sourceId: number, parentId: string = '0', limit: number = 100, offset: number = 0): Promise<any> {
    return api.get(`/share/${sourceId}/files`, { params: { parent_id: parentId, limit, offset } })
  },

  /** 获取所有分享的已整理文件（构建虚拟目录树用） */
  getAllOrganized(): Promise<any> {
    return api.get('/share/all-organized')
  },

  /** 搜索分享文件 */
  searchFiles(keyword: string): Promise<any> {
    return api.get('/share/search', { params: { keyword } })
  },

  /** 批量整理 */
  organizeBatch(sourceId: number, fileIds: string[]): Promise<any> {
    return api.post('/share/organize-batch', { source_id: sourceId, file_ids: fileIds })
  },

}
