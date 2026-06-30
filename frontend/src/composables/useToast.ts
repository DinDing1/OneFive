import { ref } from 'vue'

const toastRef = ref<any>(null)

export function setToastRef(ref: any) {
  toastRef.value = ref
}

export function showToast(message: string, type: 'success' | 'error' | 'info' = 'info', duration = 3000) {
  if (toastRef.value) {
    toastRef.value.show(message, type, duration)
  }
}
