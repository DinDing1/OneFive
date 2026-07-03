import api, { type ApiResult } from './index'

/** 文件/目录项 */
export interface FileItem {
  file_id: string
  name: string
  is_dir: boolean
  size: number
  file_type: number
  pick_code: string
  parent_id: string
  created_at: string
  updated_at: string
}

/** 文件列表响应 */
export interface FileListResponse {
  items: FileItem[]
  count: number
  offset: number
  limit: number
  parent_id: string
}

/** Open API 设置 */
export interface OpenApiSettings {
  enabled: boolean
  app_id: string
  token_valid: boolean
}

export const filesApi = {
  /** 列出目录内容 */
  listFiles(cid: string = '0', limit = 100, offset = 0, order = 'file_name', asc = 1): Promise<ApiResult<FileListResponse>> {
    return api.get('/files/list', { params: { cid, limit, offset, order, asc } })
  },

  /** 获取文件/目录详情 */
  getFileInfo(fileId: string): Promise<ApiResult<FileItem>> {
    return api.get(`/files/info/${fileId}`)
  },

  /** 创建目录 */
  createFolder(name: string, pid: string = '0'): Promise<ApiResult<any>> {
    return api.post('/files/mkdir', { name, pid: Number(pid) })
  },

  /** 搜索文件 */
  searchFiles(keyword: string, cid: string = '0'): Promise<ApiResult<FileListResponse>> {
    return api.get('/files/search', { params: { keyword, cid } })
  },

  /** 批量移动文件 */
  moveFiles(fileIds: string[], toCid: string): Promise<ApiResult<any>> {
    return api.post('/files/move', { file_ids: fileIds, to_cid: toCid })
  },

  /** 批量复制文件 */
  copyFiles(fileIds: string[], toCid: string): Promise<ApiResult<any>> {
    return api.post('/files/copy', { file_ids: fileIds, to_cid: toCid })
  },

  /** 批量删除文件 */
  deleteFiles(fileIds: string[]): Promise<ApiResult<any>> {
    return api.post('/files/delete', { file_ids: fileIds })
  },

  /** 重命名文件 */
  renameFile(fileId: string, newName: string): Promise<ApiResult<any>> {
    return api.post('/files/rename', { file_id: fileId, new_name: newName })
  },

  /** 获取 Open API 设置 */
  getOpenApiSettings(): Promise<ApiResult<OpenApiSettings>> {
    return api.get('/config/open-api')
  },

  /** 更新 Open API 设置 */
  updateOpenApiSettings(enabled: boolean, appId: string): Promise<ApiResult<any>> {
    return api.post('/config/open-api', { enabled, app_id: appId })
  },
}
