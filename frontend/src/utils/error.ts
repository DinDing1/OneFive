import { showToast } from '@/composables/useToast'

/**
 * 统一处理 API 错误，显示 toast 提示
 * 优先取后端返回的 message，其次取异常本身的 message，最后用 fallback
 */
export function handleApiError(e: any, fallback = '操作失败') {
  const msg = e?.response?.data?.message || e?.message || fallback
  showToast(msg, 'error')
}
