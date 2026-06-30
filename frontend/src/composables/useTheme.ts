/**
 * 主题切换 composable
 *
 * 通过 <html data-theme="light|dark"> 切换主题
 * 持久化到 localStorage，首次访问跟随系统偏好
 */
import { ref, onMounted } from 'vue'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'onefive-theme'

// 全局共享状态（单例）
const theme = ref<Theme>('light')

function getStoredTheme(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // localStorage 不可用（如 SSR），忽略
  }
  // 跟随系统
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'light'
}

function applyTheme(t: Theme) {
  document.documentElement.setAttribute('data-theme', t)
  try {
    localStorage.setItem(STORAGE_KEY, t)
  } catch {
    // 忽略写入错误
  }
}

let initialized = false

export function useTheme() {
  onMounted(() => {
    if (!initialized) {
      theme.value = getStoredTheme()
      applyTheme(theme.value)
      initialized = true

      // 监听系统主题变化（仅当用户未主动设置过时）
      if (window.matchMedia) {
        const mql = window.matchMedia('(prefers-color-scheme: dark)')
        mql.addEventListener('change', (e) => {
          // 仅在用户没有显式保存过主题时跟随系统
          if (!localStorage.getItem(STORAGE_KEY)) {
            theme.value = e.matches ? 'dark' : 'light'
            applyTheme(theme.value)
          }
        })
      }
    }
  })

  function toggle() {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
    applyTheme(theme.value)
  }

  function setTheme(t: Theme) {
    theme.value = t
    applyTheme(t)
  }

  return {
    theme,
    toggle,
    setTheme,
  }
}
