<template>
  <router-view />
  <Toast ref="toastRef" />
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Toast from '@/components/Toast.vue'
import { setToastRef } from '@/composables/useToast'
import { useTheme } from '@/composables/useTheme'

const toastRef = ref(null)

// 初始化主题（明/暗，跟随系统或 localStorage）
useTheme()

onMounted(() => {
  if (toastRef.value) {
    setToastRef(toastRef.value)
  }
})
</script>
