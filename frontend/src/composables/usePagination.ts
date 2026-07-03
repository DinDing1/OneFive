import { computed, type Ref } from 'vue'

/**
 * 计算可见页码列表
 * 总页数 ≤7 全显示，否则首尾+省略号（-1 表示省略号）
 */
export function useVisiblePages(totalPages: Ref<number>, currentPage: Ref<number>): Ref<number[]> {
  return computed(() => {
    const total = totalPages.value
    const current = currentPage.value
    if (total <= 0) return []
    if (total <= 7) {
      return Array.from({ length: total }, (_, i) => i + 1)
    }
    if (current <= 4) {
      return [1, 2, 3, 4, 5, -1, total]
    }
    if (current >= total - 3) {
      return [1, -1, total - 4, total - 3, total - 2, total - 1, total]
    }
    return [1, -1, current - 1, current, current + 1, -1, total]
  })
}
