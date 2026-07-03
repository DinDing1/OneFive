import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi, type VipType } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const isLoggedIn = ref(false)
  const userId = ref<string | null>(null)
  const userName = ref<string | null>(null)
  const vipType = ref<VipType>('none')
  const face = ref('')

  /** 重置登录态为未登录的默认值（登录态校验失败 / 登出时复用） */
  function resetState() {
    isLoggedIn.value = false
    userId.value = null
    userName.value = null
    vipType.value = 'none'
    face.value = ''
  }

  async function checkLoginStatus() {
    try {
      const status = await authApi.getLoginStatus()
      isLoggedIn.value = status.is_logged_in
      userId.value = status.user_id
      userName.value = status.user_name
      vipType.value = status.vip_type || 'none'
      face.value = status.face || ''
    } catch (error) {
      resetState()
    }
  }

  async function logout() {
    try {
      await authApi.logout()
    } finally {
      resetState()
    }
  }

  return {
    isLoggedIn,
    userId,
    userName,
    vipType,
    face,
    checkLoginStatus,
    logout
  }
})