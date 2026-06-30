# OneFive 前端重构计划 · Phase 7-9

> 本计划接续已完成的 Phase 0-6（设计系统 + Layout/Login/Files/Settings 重写）。
> 目标：完成剩余 4 个组件的液态玻璃/新拟态重构，并做最终验证。

---

## 一、当前状态分析

### 已完成（Phase 0-6）
- ✅ `styles/tokens.css` 双主题 CSS 变量
- ✅ `styles/glass.css` 液态玻璃工具类（`.glass-panel/.glass-card/.glass-solid/.glass-overlay/.glass-header`）
- ✅ `styles/neu.css` 新拟态工具类（`.neu-raised/.neu-inset/.neu-flat/.neu-circle`）
- ✅ `styles/base.css` 全局 reset + EP 覆盖
- ✅ `composables/useTheme.ts` + `components/ThemeToggle.vue` 暗亮切换
- ✅ `views/Layout.vue` 侧边栏 glass-panel + 顶栏 glass-header + logo.png
- ✅ `views/Login.vue` 玻璃登录卡
- ✅ `views/Files.vue` 重写完成（Grep 验证无硬编码）
- ✅ `views/Settings.vue` 重写完成（Grep 验证无硬编码）
- ✅ `router/index.ts` 删除 Home，`/` redirect → `/files`

### 待重写（Phase 7-8）
| 文件 | 行数 | 主要问题 |
|------|------|---------|
| `views/About.vue` | 133 | 内联 SVG logo、硬编码 #ffffff/#1d1d1f/#6e6e73/#f3f4f6/#4b5563 |
| `components/Toast.vue` | 87 | 硬编码 #1d1d1f/white/rgba(0,0,0,.2)/#34c759/#ff3b30/#007aff |
| `components/LogViewer.vue` | 545 | 独立暗色主题（#18181b 等），不跟随全局主题 |
| `components/RecognizeModal.vue` | 685 | 硬编码 #ffffff/#7c3aed/#6b7280/#f3f4f6/#1f2937/#111827 等 |

### 设计原则（沿用 Phase 5-6）
1. **零逻辑改动**：所有 `<script setup>` 不动，只改 `<template>` 和 `<style>`
2. **Utility 类优先**：能加 `.glass-card/.glass-solid/.glass-overlay/.neu-raised/.neu-inset/.neu-circle` 的就加，避免重复 CSS
3. **颜色全部 token 化**：禁止硬编码 `#xxxxxx` / `white` / `black` / `rgba(数字,...)`，统一使用 `var(--xxx)`
4. **语义色保持一致**：主色 `--accent`（蓝），紫色 `--purple`（仅用于发布组/Telegram 等语义场景），成功 `--success`，警告 `--warning`，危险 `--danger`

---

## 二、Phase 7：About.vue 重写

### Template 修改
| 原始 | 修改后 | 说明 |
|------|-------|------|
| `<svg ... class="app-logo">...</svg>` | `<img src="@/assets/logo.png" alt="OneFive" class="app-logo" />` | 替换内联 SVG 为项目图标 |
| `<div class="about-card">` | `<div class="about-card glass-card">` | 卡片玻璃化 |
| `<span class="tech-tag">...</span>`（8处） | `<span class="tech-tag neu-raised">...</span>` | 技术标签新拟态凸起 |

### Style 完全重写（替换 `<style scoped>` 到 `</style>`）

**删除硬编码**：`#ffffff`、`#e8e8ed`、`#1d1d1f`、`#6e6e73`、`#f8f9fa`、`#f3f4f6`、`#4b5563`

**关键样式**：
```css
.about-card {
  /* 删除 background/border/box-shadow（由 glass-card 提供） */
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.app-logo-area {
  padding: 24px 20px;
  border-bottom: 1px solid var(--border);
}

.app-logo {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-md);
  object-fit: cover;
}

.app-title h2 { color: var(--text-primary); }
.app-title p { color: var(--text-tertiary); }

.info-row {
  padding: 14px 20px;
  transition: background var(--transition-base);
}
.info-row:hover { background: var(--bg-hover); }

.info-label { color: var(--text-primary); }
.info-value { color: var(--text-secondary); }

.tech-tag {
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  /* neu-raised 提供 background/shadow/transition */
}
```

---

## 三、Phase 8.1：Toast.vue 重写

### Template 修改
| 原始 | 修改后 |
|------|-------|
| `<div ... class="toast" :class="type">` | `<div ... class="toast glass-solid" :class="type">` |

### Style 完全重写

**删除硬编码**：`#1d1d1f`、`white`、`rgba(0,0,0,0.2)`、`#34c759`、`#ff3b30`、`#007aff`

```css
.toast {
  /* 删除 background/color/box-shadow（由 glass-solid 提供） */
  color: var(--text-inverse);  /* 暗底亮字，保持高对比 */
  border-radius: var(--radius-md);
  padding: 12px 20px;
  /* glass-solid 自带 blur + border + shadow */
}

.toast.success svg { color: var(--success); }
.toast.error svg { color: var(--danger); }
.toast.info svg { color: var(--accent); }
```

> 说明：Toast 文字使用 `--text-inverse`（暗底亮字），符合"系统级提示"语义。

---

## 四、Phase 8.2：LogViewer.vue 重写

### 现状问题
当前 LogViewer 是**独立暗色主题**（`#18181b` 背景 + `#e4e4e7` 文字），不跟随全局 `data-theme`，导致：
- 切换到亮色主题时，日志面板仍是暗色
- 颜色与设计系统脱节，无法 token 化

### Template 修改
| 原始 | 修改后 |
|------|-------|
| `<div ... class="log-overlay" @click.self="close">` | `<div ... class="log-overlay glass-overlay" @click.self="close">` |
| `<div class="log-panel">` | `<div class="log-panel glass-solid">` |
| `<button class="log-btn" ...>`（3处） | `<button class="log-btn neu-circle" ...>` |
| `<select v-model="selectedLevel" class="filter-select">` | `<select v-model="selectedLevel" class="filter-select neu-inset">` |
| `<select v-model="selectedModule" class="filter-select">` | `<select v-model="selectedModule" class="filter-select neu-inset">` |
| `<div class="search-input">` | `<div class="search-input neu-inset">` |

### Style 完全重写

**删除硬编码清单**：
- `#18181b`、`#e4e4e7`、`#71717a`、`#a1a1aa`、`#52525b`、`#818cf8`
- `rgba(255, 255, 255, 0.06)`、`rgba(255, 255, 255, 0.04)`、`rgba(255, 255, 255, 0.08)`
- `rgba(139, 92, 246, 0.15)`、`#a78bfa`、`rgba(59, 130, 246, 0.15)`、`#60a5fa`
- `rgba(245, 158, 11, 0.15)`、`#fbbf24`、`rgba(239, 68, 68, 0.15)`、`#f87171`
- `rgba(255, 255, 255, 0.02)`、`rgba(255, 255, 255, 0.03)`
- `#d4d4d8`

**关键替换**：
```css
.log-overlay {
  /* 删除 background/backdrop-filter（由 glass-overlay 提供） */
  justify-content: flex-end;
  padding: 0;
}

.log-panel {
  /* 删除 background/box-shadow（由 glass-solid 提供） */
  width: 100%;
  max-width: 640px;
  display: flex;
  flex-direction: column;
  border-radius: 0;
}

.log-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.log-icon { color: var(--purple); }
.log-header h3 { color: var(--text-primary); }

.log-count {
  color: var(--text-tertiary);
  background: var(--bg-hover);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

/* log-btn 由 neu-circle 提供 background/shadow */
.log-btn { color: var(--text-tertiary); }
.log-btn:hover { background: var(--bg-hover); color: var(--text-secondary); }
.log-btn.active { color: var(--accent); }

.log-toolbar {
  border-bottom: 1px solid var(--border);
}

/* filter-select/search-input 由 neu-inset 提供 */
.filter-select {
  color: var(--text-secondary);
  /* neu-inset 提供 background/shadow/border */
}
.filter-select:focus { border-color: var(--accent); }
.filter-select option { background: var(--bg-solid); color: var(--text-primary); }

.search-input input {
  color: var(--text-primary);
}
.search-input input::placeholder { color: var(--text-tertiary); }
.search-input svg { color: var(--text-tertiary); }

.log-table { font-family: var(--font-mono); }

.log-table th {
  background: var(--bg-solid);  /* sticky 表头 */
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border);
}

.log-table td {
  border-bottom: 1px solid var(--border);
}

.log-row:hover td { background: var(--bg-hover); }

.col-time { color: var(--text-tertiary); }
.col-module { color: var(--purple); }
.col-msg { color: var(--text-primary); }

/* 级别标签 token 化 */
.level-tag.debug   { background: var(--purple-bg);  color: var(--purple); }
.level-tag.info     { background: var(--accent-bg); color: var(--accent); }
.level-tag.warning  { background: var(--warning-bg); color: var(--warning); }
.level-tag.error    { background: var(--danger-bg);  color: var(--danger); }

.loading-spinner {
  border: 2px solid var(--border);
  border-top-color: var(--accent);
}

.log-empty { color: var(--text-tertiary); }

/* 滚动条 */
.log-body::-webkit-scrollbar-thumb { background: var(--border-strong); }
.log-body::-webkit-scrollbar-thumb:hover { background: var(--text-tertiary); }
```

---

## 五、Phase 8.3：RecognizeModal.vue 重写

### Template 修改
| 原始 | 修改后 |
|------|-------|
| `<div ... class="modal-overlay" @click.self="close">` | `<div ... class="glass-overlay" @click.self="close">` |
| `<div class="result-modal">` | `<div class="result-modal glass-solid">` |
| `<button class="btn-close-hero" @click="close">` | `<button class="btn-close-hero neu-circle" @click="close">` |
| `<div v-if="result?.tmdb_poster" class="hero-poster">` | `<div v-if="result?.tmdb_poster" class="hero-poster neu-raised">` |
| `<div v-else class="hero-poster poster-placeholder">` | `<div v-else class="hero-poster poster-placeholder neu-raised">` |

### Style 完全重写

**删除硬编码清单**：
- `#ffffff`、`rgba(0, 0, 0, 0.5)`、`rgba(0, 0, 0, 0.2)`、`rgba(0, 0, 0, 0.3)`
- `linear-gradient(to top, #ffffff 0%, rgba(255, 255, 255, 0.6) 40%, rgba(0, 0, 0, 0.15) 100%)`
- `linear-gradient(135deg, #667eea 0%, #764ba2 100%)`
- `#e5e7eb`、`rgba(255, 255, 255, 0.2)`、`rgba(255, 255, 255, 0.5)`、`rgba(255, 255, 255, 0.15)`、`rgba(255, 255, 255, 0.1)`
- `#1f2937`、`#7c3aed`、`rgba(124, 58, 237, 0.1)`、`#6b7280`、`#9ca3af`、`#f59e0b`
- `#2563eb`、`rgba(37, 99, 235, 0.08)`、`#f3f4f6`、`#4b5563`
- `#0891b2`、`rgba(8, 145, 178, 0.08)`、`#b45309`、`rgba(180, 83, 9, 0.08)`
- `#f9fafb`、`#111827`、`#fff`、`#374151`、`rgba(255,255,255,0.3)`
- `#fef2f2`、`#dc2626`、`#f0fdf4`、`#16a34a`

**关键替换**：
```css
/* modal-overlay 由 glass-overlay 提供（删除 background/display/z-index） */
.result-modal {
  /* 删除 background/box-shadow（由 glass-solid 提供） */
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 520px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 顶部 hero */
.hero-backdrop img { object-fit: cover; }

/* 渐变遮罩：暗亮自适应，使用 token */
.backdrop-mask {
  background: linear-gradient(
    to top,
    var(--bg-solid) 0%,
    color-mix(in srgb, var(--bg-solid) 60%, transparent) 40%,
    rgba(0, 0, 0, 0.15) 100%
  );
}

/* 占位渐变：accent → purple */
.hero-placeholder {
  background: linear-gradient(135deg, var(--accent) 0%, var(--purple) 100%);
}

/* 关闭按钮：圆形凸起，悬浮于 hero 上 */
.btn-close-hero {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 32px;
  height: 32px;
  background: rgba(0, 0, 0, 0.3);  /* 保留半透明黑底，确保海报上可读 */
  color: var(--text-inverse);
  z-index: 2;
  /* neu-circle 提供阴影/transition */
}

/* 海报：neu-raised 提供凸起阴影 */
.hero-poster {
  width: 100px;
  height: 150px;
  border-radius: var(--radius-md);
  overflow: hidden;
  /* neu-raised 提供 background/shadow/transition */
}

.hero-poster img { object-fit: cover; }

.poster-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-hover);
}
.poster-placeholder svg { color: var(--text-tertiary); }

/* 骨架屏 */
.poster-skeleton,
.skeleton-line {
  background: var(--bg-hover);
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.hero-title { color: var(--text-primary); }

.meta-type {
  color: var(--purple);
  background: var(--purple-bg);
  padding: 2px 10px;
  border-radius: var(--radius-full);
}

.meta-year { color: var(--text-secondary); }
.meta-rating { color: var(--warning); }

/* 加载/空状态 */
.result-loading,
.result-empty { color: var(--text-tertiary); }

.loading-spinner {
  border: 3px solid var(--border);
  border-top-color: var(--accent);
}

/* 标签 */
.tag-category {
  color: var(--accent);
  background: var(--accent-bg);
}

.tag-id {
  color: var(--text-secondary);
  background: var(--bg-hover);
  font-family: var(--font-mono);
}

/* 分区标题 */
.section-title {
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* 技术标签 */
.tech-tag {
  background: var(--bg-hover);
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
}

.tech-tag.tag-source {
  color: var(--accent);
  background: var(--accent-bg);
}

.tech-tag.tag-edition {
  color: var(--warning);
  background: var(--warning-bg);
}

.tech-tag.tag-group {
  color: var(--purple);
  background: var(--purple-bg);
}

/* 目标路径 */
.path-box {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font-family: var(--font-mono);
  box-shadow: var(--neu-inset);
}

.path-dir { color: var(--text-tertiary); }
.path-file { color: var(--text-primary); font-weight: 500; }

/* 简介 */
.overview-text { color: var(--text-secondary); }

/* 执行整理按钮 */
.action-bar { border-top: 1px solid var(--border); }

.btn-organize {
  background: var(--accent);
  color: var(--text-inverse);
  border-radius: var(--radius-md);
}
.btn-organize:hover:not(:disabled) { background: var(--accent-hover); }

.btn-spinner {
  border: 2px solid var(--border);
  border-top-color: var(--text-inverse);
}

.exec-error {
  background: var(--danger-bg);
  color: var(--danger);
  border-radius: var(--radius-sm);
}

.exec-success {
  background: var(--success-bg);
  color: var(--success);
  border-radius: var(--radius-sm);
}
```

---

## 六、Phase 9：验证

### 6.1 启动验证
```bash
cd d:\OneFive\frontend
npm run dev
```
- 浏览器访问 `http://localhost:5173`
- 验证 `/` 自动重定向到 `/files`
- 验证 `/about` 页面 logo.png 正确显示
- 触发 Toast（如登录失败、保存设置）验证样式
- 点击顶栏日志按钮验证 LogViewer 弹出
- 在文件列表右键"识别"验证 RecognizeModal 弹出

### 6.2 构建检查
```bash
npm run build
```
- 确认 TypeScript 类型检查通过
- 确认 Vite 构建无报错

### 6.3 硬编码巡检
对每个重写文件执行 Grep：
```
pattern: #[0-9a-fA-F]{3,6}\b|:\s*white\b|:\s*black\b|rgba\(\s*\d
path: <对应文件>
```
预期全部返回 `No matches found`。

需巡检文件：
- `frontend/src/views/About.vue`
- `frontend/src/components/Toast.vue`
- `frontend/src/components/LogViewer.vue`
- `frontend/src/components/RecognizeModal.vue`

### 6.4 主题切换验证
- 点击 ThemeToggle 切换到暗色模式
- 检查所有页面（Files/Settings/About）暗色显示正常
- 检查 Toast/LogViewer/RecognizeModal 在暗色下文字可读
- 刷新页面后主题保持（localStorage 持久化）

---

## 七、Assumptions & Decisions

### 假设
1. 项目图标 `onefive.png` 已存在于 `frontend/src/assets/logo.png` 和 `frontend/public/favicon.png`（前期已完成）
2. 设计 token 与 utility 类（glass.css/neu.css）已定义完整，无需新增
3. Phase 5-6 已完成且通过验证（Settings.vue Grep 验证通过）

### 决策
| 决策点 | 选择 | 理由 |
|--------|------|------|
| About 内联 SVG logo | 替换为 `<img src="@/assets/logo.png" />` | 用户明确要求"项目图标利用上" |
| About tech-tag | 加 `neu-raised` | 体现新拟态风格，与 Settings 卡片呼应 |
| Toast 文字色 | `var(--text-inverse)` | Toast 是暗底（glass-solid）+ 亮字，保持高对比 |
| LogViewer 主题 | 取消独立暗色，跟随全局 | 与设计系统统一，避免主题割裂 |
| LogViewer level-tag 颜色 | debug→purple、info→accent、warning→warning、error→danger | 复用语义 token，避免新增 |
| RecognizeModal btn-close-hero | 保留半透明黑底 + neu-circle | 海报上需要暗底白字保证可读性 |
| RecognizeModal backdrop-mask | 用 `color-mix` + var(--bg-solid) | 兼容暗亮主题，无需 JS 判断 |
| RecognizeModal hero-placeholder | accent → purple 渐变 | 替换原 indigo→purple，用语义色 |
| RecognizeModal tech-tag 颜色 | source→accent、edition→warning、group→purple | 复用 Settings 中的语义映射 |

### 不做的事
- ❌ 不修改任何 `<script setup>` 逻辑
- ❌ 不新增 token 变量（现有 token 已够用）
- ❌ 不重构组件结构（保持 v-if/v-for 不变）
- ❌ 不调整 Props/Emits 接口

---

## 八、执行顺序

1. **Phase 7**: About.vue（最简单，133 行）
2. **Phase 8.1**: Toast.vue（87 行，快速完成）
3. **Phase 8.2**: LogViewer.vue（545 行，需完整重写 style）
4. **Phase 8.3**: RecognizeModal.vue（685 行，最复杂）
5. **Phase 9**: 验证（dev + build + grep + 主题切换）

每个 Phase 完成后立即 Grep 验证，确保零硬编码残留。
