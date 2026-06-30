<template>
  <div class="layout">
    <!-- 移动端顶栏 -->
    <header class="mobile-header glass-header">
      <button class="menu-btn" @click="showSidebar = true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
      <h1 class="mobile-title">{{ currentTitle }}</h1>
      <div class="mobile-right">
        <ThemeToggle />
        <div class="mobile-avatar" @click="showUserMenu = !showUserMenu">
          <img v-if="authStore.face" :src="authStore.face" alt="avatar" />
          <span v-else>{{ userInitial }}</span>
        </div>
      </div>
    </header>

    <!-- 侧边栏遮罩 -->
    <div v-if="showSidebar" class="sidebar-overlay" @click="showSidebar = false" />

    <!-- 侧边栏 -->
    <aside class="sidebar glass-panel" :class="{ 'sidebar-open': showSidebar }">
      <div class="sidebar-header">
        <img src="@/assets/logo.png" alt="OneFive" class="sidebar-logo" />
        <div class="sidebar-brand">
          <h2>OneFive</h2>
          <span class="sidebar-version">v{{ appVersion }}</span>
        </div>
      </div>

      <nav class="sidebar-nav">
        <router-link to="/files" class="nav-item" @click="showSidebar = false">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
          <span>文件管理</span>
        </router-link>
        <router-link to="/share" class="nav-item" @click="showSidebar = false">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
          </svg>
          <span>分享管理</span>
        </router-link>
        <router-link to="/settings" class="nav-item" @click="showSidebar = false">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          <span>设置</span>
        </router-link>
        <router-link to="/about" class="nav-item" @click="showSidebar = false">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z" />
            <path d="M12 16v-4" />
            <path d="M12 8h.01" />
          </svg>
          <span>关于</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="user-card" @click="showUserMenu = !showUserMenu">
          <div class="user-avatar">
            <img v-if="authStore.face" :src="authStore.face" alt="avatar" />
            <span v-else>{{ userInitial }}</span>
          </div>
          <div class="user-info">
            <p class="user-name">
              {{ authStore.userName || authStore.userId || '用户' }}
              <span v-if="authStore.vipType === 'vip'" class="vip-badge vip-normal">VIP</span>
              <span v-else-if="authStore.vipType === 'forever'" class="vip-badge vip-forever">&#x1F451; 终身VIP</span>
            </p>
            <p class="user-status">已登录</p>
          </div>
          <svg class="user-chevron" :class="{ 'chevron-up': showUserMenu }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>

        <div v-if="showUserMenu" class="user-menu">
          <button class="menu-item" @click="handleLogout">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            <span>退出登录</span>
          </button>
        </div>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
      <div class="content-header glass-header">
        <h1>{{ currentTitle }}</h1>
        <div class="header-actions">
          <ThemeToggle />
          <button class="header-log-btn neu-circle" @click="showLogs = true" title="日志">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
          </button>
        </div>
      </div>
      <div class="content-body">
        <router-view />
      </div>
    </main>

    <!-- 退出登录确认弹窗 -->
    <div v-if="showLogoutConfirm" class="modal-overlay" @click.self="showLogoutConfirm = false">
      <div class="confirm-modal glass-solid">
        <div class="confirm-body">
          <div class="confirm-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </div>
          <h3>退出登录</h3>
          <p>确定要退出当前账号吗？</p>
        </div>
        <div class="confirm-actions">
          <button class="confirm-btn cancel" @click="showLogoutConfirm = false">取消</button>
          <button class="confirm-btn ok" @click="doLogout">确定</button>
        </div>
      </div>
    </div>

    <!-- 日志查看器 -->
    <LogViewer :visible="showLogs" @close="showLogs = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import LogViewer from '@/components/LogViewer.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'

// 从 vite.config.ts 注入的版本号
declare const __APP_VERSION__: string
const appVersion = __APP_VERSION__

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const showSidebar = ref(false)
const showUserMenu = ref(false)
const showLogoutConfirm = ref(false)
const showLogs = ref(false)

const currentTitle = computed(() => {
  const titles: Record<string, string> = {
    'Files': '文件管理',
    'Share': '分享管理',
    'Settings': '设置',
    'About': '关于'
  }
  return titles[route.name as string] || 'OneFive'
})

const userInitial = computed(() => {
  const name = authStore.userName || authStore.userId
  return name ? name.charAt(0).toUpperCase() : 'U'
})

async function handleLogout() {
  showUserMenu.value = false
  showLogoutConfirm.value = true
}

async function doLogout() {
  showLogoutConfirm.value = false
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  background: var(--bg-base);
  font-family: var(--font-sans);
}

.mobile-header {
  display: none;
}

/* ==================== 侧边栏（液态玻璃） ==================== */
.sidebar {
  width: 260px;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px;
  border-bottom: 1px solid var(--border);
}

.sidebar-logo {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border-radius: var(--radius-sm);
  object-fit: cover;
}

/* 标题行：名称 + 版本号 */
.sidebar-brand h2 {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 版本号样式（标题右侧） */
.sidebar-version {
  display: inline-block;
  font-size: 10px;
  color: var(--text-tertiary);
  background: var(--bg-hover);
  padding: 2px 6px;
  border-radius: var(--radius-full);
  font-weight: 500;
}

/* ==================== 导航（新拟态） ==================== */
.sidebar-nav {
  flex: 1;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  color: var(--text-secondary);
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  transition: all var(--transition-base);
  border: 1px solid transparent;
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

/* 选中态：macOS 风格 —— 半透明背景 + 左侧指示条 */
.nav-item.router-link-active {
  background: var(--bg-selected);
  color: var(--accent);
  border-left: 3px solid var(--accent);
  padding-left: calc(14px - 3px);  /* 左边条占位，避免布局跳动 */
}

.nav-item.router-link-active:hover {
  background: var(--bg-selected);
}

.nav-item svg {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
}

/* ==================== 用户区域 ==================== */
.sidebar-footer {
  padding: 12px;
  border-top: 1px solid var(--border);
}

.user-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.user-card:hover {
  background: var(--bg-hover);
}

.user-avatar {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, var(--accent), var(--purple));
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-inverse);
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.user-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.user-info {
  flex: 1;
  min-width: 0;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 6px;
}

.vip-badge {
  display: inline-block;
  font-size: 9px;
  font-weight: 700;
  color: var(--text-inverse);
  padding: 1px 5px;
  border-radius: 4px;
  letter-spacing: 0.5px;
  line-height: 1.4;
  flex-shrink: 0;
}

.vip-normal {
  background: linear-gradient(135deg, var(--warning), var(--danger));
}

.vip-forever {
  background: linear-gradient(135deg, var(--folder), var(--warning));
  box-shadow: 0 0 8px var(--warning-bg);
}

.user-status {
  font-size: 11px;
  color: var(--success);
  margin-top: 1px;
}

.user-chevron {
  width: 14px;
  height: 14px;
  color: var(--text-tertiary);
  transition: transform var(--transition-base);
  flex-shrink: 0;
}

.chevron-up {
  transform: rotate(180deg);
}

.user-menu {
  margin-top: 6px;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 14px;
  background: none;
  border: none;
  color: var(--danger);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.menu-item:hover {
  background: var(--danger-bg);
}

.menu-item svg {
  width: 16px;
  height: 16px;
}

/* ==================== 主内容区 ==================== */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.content-header {
  padding: 18px 24px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.content-header h1 {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-log-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.header-log-btn:hover {
  color: var(--accent);
}

.header-log-btn svg {
  width: 20px;
  height: 20px;
}

.content-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

/* ==================== 退出确认弹窗 ==================== */
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

.confirm-modal {
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 320px;
  overflow: hidden;
}

.confirm-body {
  padding: 28px 24px 20px;
  text-align: center;
}

.confirm-icon {
  width: 48px;
  height: 48px;
  margin: 0 auto 16px;
  background: var(--danger-bg);
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
}

.confirm-icon svg {
  width: 24px;
  height: 24px;
  color: var(--danger);
}

.confirm-body h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.confirm-body p {
  font-size: 13px;
  color: var(--text-secondary);
}

.confirm-actions {
  display: flex;
  border-top: 1px solid var(--border);
}

.confirm-btn {
  flex: 1;
  height: 44px;
  background: none;
  border: none;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.confirm-btn.cancel {
  color: var(--text-secondary);
  border-right: 1px solid var(--border);
}

.confirm-btn.cancel:hover {
  background: var(--bg-hover);
}

.confirm-btn.ok {
  color: var(--danger);
}

.confirm-btn.ok:hover {
  background: var(--danger-bg);
}

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
  .mobile-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 100;
  }

  .menu-btn {
    width: 36px;
    height: 36px;
    background: var(--bg-base);
    border: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    border-radius: var(--radius-sm);
    color: var(--text-primary);
  }

  .menu-btn:hover {
    background: var(--bg-hover);
  }

  .menu-btn svg {
    width: 22px;
    height: 22px;
  }

  .mobile-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .mobile-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .mobile-avatar {
    width: 32px;
    height: 32px;
    background: linear-gradient(135deg, var(--accent), var(--purple));
    border-radius: var(--radius-full);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-inverse);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    overflow: hidden;
  }

  .mobile-avatar img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .sidebar-overlay {
    position: fixed;
    inset: 0;
    background: color-mix(in srgb, black 40%, transparent);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    z-index: 200;
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 300;
    transform: translateX(-100%);
    box-shadow: var(--shadow-lg);
  }

  .sidebar-open {
    transform: translateX(0);
  }

  .main-content {
    padding-top: 56px;
  }

  .content-header {
    display: none;
  }

  .content-body {
    padding: 16px;
  }
}
</style>
