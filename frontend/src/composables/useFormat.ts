/**
 * 格式化工具函数（供 Files.vue / Share.vue 等视图共用，保证行为一致）
 */

/**
 * 格式化文件大小。
 * 统一行为：0 字节或无效值返回 '—'，避免不同视图一个返回空串、一个返回占位符的差异。
 * @param bytes 字节数
 */
export function formatSize(bytes: number): string {
  if (!bytes || bytes === 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return `${size.toFixed(i > 0 ? 1 : 0)} ${units[i]}`
}

/**
 * 格式化时间。
 * 兼容两种入参：
 *   1) Unix 秒级时间戳（数字或纯数字字符串）→ 乘 1000 转 Date
 *   2) ISO 字符串或其它 Date 可解析字符串 → 直接构造 Date
 * 非法值返回 '—'。
 * @param ts 时间戳或时间字符串
 */
export function formatTime(ts: string | number): string {
  if (!ts) return '—'
  // 纯数字字符串视作 Unix 秒级时间戳
  const date = new Date(typeof ts === 'string' && /^\d+$/.test(ts) ? Number(ts) * 1000 : ts)
  if (isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
