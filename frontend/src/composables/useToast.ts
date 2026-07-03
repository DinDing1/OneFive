import { ref } from 'vue'

/**
 * Toast 实例接口（与 Toast.vue 的 defineExpose({ show }) 对齐）。
 * 用具体接口替代 any，让 setToastRef / showToast 获得类型校验。
 */
export interface ToastInstance {
  show(msg: string, type?: 'success' | 'error' | 'info', duration?: number): void
}

const toastRef = ref<ToastInstance | null>(null)

/** 由 App.vue 在挂载时注入 Toast 组件实例 */
export function setToastRef(instance: ToastInstance | null) {
  toastRef.value = instance
}

/** 全局 Toast 提示 */
export function showToast(message: string, type: 'success' | 'error' | 'info' = 'info', duration = 3000) {
  if (toastRef.value) {
    toastRef.value.show(message, type, duration)
  }
}
