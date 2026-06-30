import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi, type VipType } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const isLoggedIn = ref(false)
  const userId = ref<string | null>(null)
  const userName = ref<string | null>(null)
  const vipType = ref<VipType>('none')
  const face = ref('')

  async function checkLoginStatus() {
    try {
      const status = await authApi.getLoginStatus()
      isLoggedIn.value = status.is_logged_in
      userId.value = status.user_id
      userName.value = status.user_name
      vipType.value = status.vip_type || 'none'
      face.value = status.face || ''
    } catch (error) {
      isLoggedIn.value = false
      userId.value = null
      userName.value = null
      vipType.value = 'none'
      face.value = ''
    }
  }

  async function logout() {
    try {
      await authApi.logout()
    } finally {
      isLoggedIn.value = false
      userId.value = null
      userName.value = null
      vipType.value = 'none'
      face.value = ''
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