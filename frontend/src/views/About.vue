<template>
  <div class="about">
    <!-- 关于卡片：液态玻璃容器 -->
    <div class="about-card glass-card">
      <div class="app-logo-area">
        <!-- 项目图标 -->
        <img src="@/assets/logo.png" alt="OneFive" class="app-logo" />
        <div class="app-title">
          <h2>OneFive</h2>
          <p>115 Cloud Manager</p>
        </div>
      </div>

      <div class="info-list">
        <div class="info-row">
          <span class="info-label">版本</span>
          <span class="info-value">{{ appVersion }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">技术栈</span>
          <div class="tech-tags">
            <!-- 技术标签：新拟态凸起 -->
            <span class="tech-tag neu-raised">Vue 3</span>
            <span class="tech-tag neu-raised">TypeScript</span>
            <span class="tech-tag neu-raised">Vite</span>
            <span class="tech-tag neu-raised">FastAPI</span>
            <span class="tech-tag neu-raised">Python</span>
            <span class="tech-tag neu-raised">p115client</span>
            <span class="tech-tag neu-raised">TMDB API</span>
            <span class="tech-tag neu-raised">SQLite</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const appVersion = __APP_VERSION__
</script>

<style scoped>
/* 关于页：容器布局 */
.about {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 关于卡片：由 glass-card 提供背景/模糊/边框/阴影 */
.about-card {
  border-radius: var(--radius-lg);
  overflow: hidden;
}

/* 顶部 logo 区域 */
.app-logo-area {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px 20px;
  border-bottom: 1px solid var(--border);
}

/* 项目图标 */
.app-logo {
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  object-fit: cover;
}

.app-title h2 {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.app-title p {
  font-size: 13px;
  color: var(--text-tertiary);
  font-weight: 400;
  margin-top: 2px;
}

/* 信息列表 */
.info-list {
  padding: 4px 0;
}

.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  transition: background var(--transition-base);
}

.info-row:hover {
  background: var(--bg-hover);
}

.info-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.info-value {
  font-size: 13px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

/* 技术标签容器 */
.tech-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}

/* 技术标签：由 neu-raised 提供背景/阴影/过渡 */
.tech-tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}
</style>
