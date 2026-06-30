<template>
  <div class="login-container">
    <!-- 背景光斑装饰 -->
    <div class="bg-orb orb-1"></div>
    <div class="bg-orb orb-2"></div>
    <div class="bg-orb orb-3"></div>

    <!-- 主题切换按钮（右上角） -->
    <div class="theme-corner">
      <ThemeToggle />
    </div>

    <!-- 登录卡片（液态玻璃） -->
    <div class="login-card glass-panel">
      <div class="login-content">
        <!-- 二维码区域 -->
        <div class="qr-section">
          <div v-if="loading" class="qr-loading neu-inset">
            <div class="loading-spinner"></div>
            <p>获取二维码中...</p>
          </div>
          <div v-else-if="qrCodeUrl" class="qr-wrapper neu-inset">
            <img :src="qrCodeUrl" alt="扫码登录" class="qr-code" />
          </div>
          <div v-else class="qr-error neu-inset">
            <p>获取二维码失败</p>
            <button class="btn-link" @click="loadQRCode">重试</button>
          </div>
          <p class="device-info">当前登录设备：{{ devices[selectedDevice] || '网页端' }}</p>
          <p v-if="scanStatus === 'scanned'" class="scan-success">已扫码，正在确认...</p>
          <div class="qr-actions">
            <button class="btn-link" @click="loadQRCode">刷新</button>
            <span class="qr-divider">|</span>
            <button class="btn-link" @click="showCookieInput = true">手动输入</button>
          </div>
        </div>
      </div>

      <!-- 底部 -->
      <div class="login-footer">
        <button class="link-btn" @click="showDeviceSettings = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          切换设备
        </button>
      </div>
    </div>

    <!-- 设备设置弹窗 -->
    <div v-if="showDeviceSettings" class="modal-overlay" @click.self="showDeviceSettings = false">
      <div class="modal-card glass-solid">
        <div class="modal-header">
          <h3>选择登录设备</h3>
          <button class="btn-close neu-circle" @click="showDeviceSettings = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="device-grid">
            <button
              v-for="(name, key) in devices"
              :key="key"
              class="device-item neu-raised"
              :class="{ active: selectedDevice === key }"
              @click="selectDevice(key)"
            >
              {{ name }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Cookies 输入弹窗 -->
    <div v-if="showCookieInput" class="modal-overlay" @click.self="showCookieInput = false">
      <div class="modal-card glass-solid">
        <div class="modal-header">
          <h3>手动输入 Cookies</h3>
          <button class="btn-close neu-circle" @click="showCookieInput = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <textarea
            v-model="cookiesInput"
            class="cookie-input neu-inset"
            placeholder="请输入 115 网盘的 Cookies 字符串&#10;&#10;格式: UID=xxx; CID=xxx; SEID=xxx; KID=xxx"
            rows="6"
          />
        </div>
        <div class="modal-footer">
          <button class="btn-secondary neu-flat" @click="showCookieInput = false">取消</button>
          <button class="btn-primary" @click="loginWithCookies" :disabled="loading">
            {{ loading ? '登录中...' : '登录' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { showToast } from '@/composables/useToast'
import ThemeToggle from '@/components/ThemeToggle.vue'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const devices = ref<Record<string, string>>({})
const selectedDevice = ref('web')
const qrCodeUrl = ref('')
const sessionId = ref('')
const showDeviceSettings = ref(false)
const showCookieInput = ref(false)
const cookiesInput = ref('')
const scanStatus = ref('')

let checkTimer: number | null = null

onMounted(async () => {
  await authStore.checkLoginStatus()
  if (authStore.isLoggedIn) {
    router.push('/')
    return
  }

  try {
    const res = await authApi.getDevices()
    if (res.code === 0 && res.data) {
      devices.value = res.data.devices
    }
  } catch {
    devices.value = {
      web: '网页端',
      ios: '苹果端',
      android: '安卓端',
      '115ipad': '苹果平板端',
      tv: '安卓电视端',
      wechatmini: '微信小程序端',
      harmony: '鸿蒙端',
    }
  }

  loadQRCode()
})

async function loadQRCode() {
  loading.value = true
  stopCheckLoginStatus()
  sessionId.value = ''
  qrCodeUrl.value = ''
  scanStatus.value = ''

  try {
    const res = await authApi.getQRCode(selectedDevice.value)
    if (res.code === 0 && res.data) {
      qrCodeUrl.value = res.data.qr_code_url
      sessionId.value = res.data.session_id
      startCheckLoginStatus()
    }
  } catch (error: any) {
    console.error('获取二维码失败:', error)
  } finally {
    loading.value = false
  }
}

function selectDevice(device: string) {
  selectedDevice.value = device
  showDeviceSettings.value = false
  loadQRCode()
}

function startCheckLoginStatus() {
  checkTimer = window.setInterval(async () => {
    if (!sessionId.value) return
    try {
      const res = await authApi.checkQRCodeStatus(sessionId.value)

      if (res.status === 'confirmed') {
        stopCheckLoginStatus()
        await authStore.checkLoginStatus()
        router.push('/')
      } else if (res.status === 'invalid' || res.status === 'expired') {
        stopCheckLoginStatus()
        await authStore.checkLoginStatus()
        if (authStore.isLoggedIn) {
          router.push('/')
        } else {
          loadQRCode()
        }
      } else if (res.status === 'scanned') {
        scanStatus.value = 'scanned'
      } else if (res.status === 'error') {
        console.warn('检查登录状态失败:', res.message)
        await authStore.checkLoginStatus()
        if (authStore.isLoggedIn) {
          router.push('/')
        }
      }
    } catch (error) {
      console.warn('检查登录状态网络错误:', error)
    }
  }, 1000)
}

function stopCheckLoginStatus() {
  if (checkTimer) {
    clearInterval(checkTimer)
    checkTimer = null
  }
}

async function loginWithCookies() {
  if (!cookiesInput.value.trim()) {
    showToast('请输入 Cookies', 'error')
    return
  }
  loading.value = true
  try {
    await authApi.loginWithCookies(cookiesInput.value.trim())
    await authStore.checkLoginStatus()
    showCookieInput.value = false
    router.push('/')
  } catch (error: any) {
    showToast(error.message || '登录失败', 'error')
  } finally {
    loading.value = false
  }
}

onUnmounted(() => {
  stopCheckLoginStatus()
})
</script>

<style scoped>
.login-container {
  position: relative;
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: var(--bg-base);
  padding: 20px;
  overflow: hidden;
}

/* ==================== 背景光斑装饰 ==================== */
.bg-orb {
  position: absolute;
  border-radius: var(--radius-full);
  filter: blur(80px);
  opacity: 0.4;
  pointer-events: none;
  z-index: 0;
}

.orb-1 {
  width: 360px;
  height: 360px;
  background: var(--accent);
  top: -120px;
  left: -80px;
  animation: orb-float-1 12s ease-in-out infinite;
}

.orb-2 {
  width: 280px;
  height: 280px;
  background: var(--purple);
  bottom: -80px;
  right: -60px;
  animation: orb-float-2 14s ease-in-out infinite;
}

.orb-3 {
  width: 200px;
  height: 200px;
  background: var(--success);
  top: 50%;
  right: 20%;
  animation: orb-float-3 10s ease-in-out infinite;
}

@keyframes orb-float-1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(40px, 60px) scale(1.1); }
}

@keyframes orb-float-2 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(-50px, -40px) scale(0.9); }
}

@keyframes orb-float-3 {
  0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.3; }
  50% { transform: translate(-30px, 30px) scale(1.2); opacity: 0.5; }
}

:root[data-theme='dark'] .bg-orb {
  opacity: 0.25;
}

/* ==================== 主题切换按钮 ==================== */
.theme-corner {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 10;
}

/* ==================== 登录卡片 ==================== */
.login-card {
  position: relative;
  z-index: 1;
  padding: 40px 36px 28px;
  width: 100%;
  max-width: 380px;
  border-radius: var(--radius-xl);
}

.login-content {
  margin-bottom: 20px;
}

/* ==================== 二维码区 ==================== */
.qr-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.qr-wrapper {
  width: 200px;
  height: 200px;
  border-radius: var(--radius-md);
  padding: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.qr-code {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: var(--radius-sm);
}

.qr-loading,
.qr-error {
  width: 200px;
  height: 200px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border-radius: var(--radius-md);
  color: var(--text-tertiary);
}

.qr-loading p,
.qr-error p {
  font-size: 13px;
  color: var(--text-secondary);
}

.loading-spinner {
  width: 28px;
  height: 28px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: var(--radius-full);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.device-info {
  font-size: 13px;
  color: var(--text-secondary);
}

.scan-success {
  font-size: 13px;
  color: var(--success);
  font-weight: 500;
}

.qr-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.btn-link {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 13px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.btn-link:hover {
  background: var(--accent-bg);
}

.qr-divider {
  color: var(--text-tertiary);
  font-size: 12px;
}

.login-footer {
  text-align: center;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.link-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  transition: all var(--transition-base);
}

.link-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.link-btn svg {
  width: 16px;
  height: 16px;
}

/* ==================== 弹窗 ==================== */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, black 30%, transparent);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  z-index: 1000;
}

:root[data-theme='dark'] .modal-overlay {
  background: color-mix(in srgb, black 50%, transparent);
}

.modal-card {
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 380px;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.modal-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-close {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
}

.btn-close:hover {
  color: var(--text-primary);
}

.btn-close svg {
  width: 16px;
  height: 16px;
}

.modal-body {
  padding: 16px 20px;
}

.device-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.device-item {
  padding: 10px 8px;
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  text-align: center;
  transition: all var(--transition-base);
}

.device-item:hover {
  transform: translateY(-1px);
}

.device-item.active {
  background: var(--accent);
  color: var(--text-inverse);
  box-shadow: var(--neu-inset), 0 4px 12px var(--accent-bg);
}

.cookie-input {
  width: 100%;
  padding: 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-family: var(--font-mono);
  color: var(--text-primary);
  resize: vertical;
  outline: none;
}

.cookie-input::placeholder {
  color: var(--text-tertiary);
}

.modal-footer {
  display: flex;
  gap: 12px;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  justify-content: flex-end;
}

.btn-primary {
  height: 36px;
  padding: 0 20px;
  background: var(--accent);
  color: var(--text-inverse);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-base);
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  height: 36px;
  padding: 0 20px;
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
  border-radius: var(--radius-sm);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

/* ==================== 响应式 ==================== */
@media (max-width: 480px) {
  .login-container {
    padding: 16px;
    align-items: flex-start;
    padding-top: 80px;
  }

  .login-card {
    padding: 32px 24px 24px;
    border-radius: var(--radius-lg);
  }

  .device-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
