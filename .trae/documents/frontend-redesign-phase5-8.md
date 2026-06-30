# OneFive 前端重构计划 - Phase 5~8

> 本文档承接 `frontend-redesign.md`（Phase 0~4 已完成），聚焦剩余页面与组件的视觉重构。
> 设计系统（tokens.css / base.css / glass.css / neu.css）、主题切换（useTheme.ts / ThemeToggle.vue）、Layout/Login 重构均已落地，本阶段只做"应用层"迁移。

---

## 一、当前状态分析

### 已完成（Phase 0~4）
- `styles/tokens.css`：明暗双主题 CSS 变量（含 `--purple` 紫色 token）
- `styles/base.css`：全局 reset + 滚动条 + Element Plus 覆盖
- `styles/glass.css`：`.glass-panel / .glass-card / .glass-solid / .glass-overlay / .glass-header`
- `styles/neu.css`：`.neu-raised / .neu-inset / .neu-flat / .neu-circle`
- `composables/useTheme.ts` + `components/ThemeToggle.vue`：明暗切换 + localStorage 持久化
- `Layout.vue`：侧边栏玻璃化 + 导航新拟态 + 顶栏毛玻璃 + logo 替换
- `Login.vue`：玻璃登录卡 + 浮动光斑 + 设备选择新拟态
- `router/index.ts`：删除 Home，`/` → `/files`
- `main.ts`：引入 4 个样式文件
- `assets/logo.png` + `public/favicon.png`：项目图标就位

### 待重写（本计划范围）
| 文件 | 行数 | 核心问题 |
|---|---|---|
| `views/Files.vue` | 1682 | 局部变量 `--bg-card/--border/--folder-color` 与全局 token 冲突；工具栏/弹窗未玻璃化；按钮未新拟态 |
| `views/Settings.vue` | 986 | 几乎全硬编码（`#fff/#e5e7eb/#111827/#a855f7/#f3f4f6` 等）；紫色主题未走 `--purple`；卡片未玻璃化 |
| `views/About.vue` | 133 | 内联 SVG logo；硬编码颜色；未玻璃化 |
| `components/Toast.vue` | 87 | 硬编码 `#1d1d1f/#34c759/#ff3b30/#007aff`；未玻璃化 |
| `components/LogViewer.vue` | 545 | 独立暗色主题 `#18181b` 不跟随全局主题；硬编码大量颜色 |
| `components/RecognizeModal.vue` | 685 | 硬编码颜色 + 紫色 `#7c3aed`；遮罩未玻璃化；海报框未新拟态 |

---

## 二、设计原则（贯穿所有文件）

1. **颜色全 token 化**：所有 `#xxx` / `rgb()` 替换为 `var(--xxx)`，禁止硬编码
2. **容器层走液态玻璃**：卡片、弹窗、抽屉 → `.glass-panel / .glass-card / .glass-solid`
3. **交互层走新拟态**：按钮、输入框、开关、分页器 → `.neu-raised / .neu-inset / .neu-flat / .neu-circle`
4. **遮罩统一**：弹窗遮罩用 `.glass-overlay`（base.css 已定义）
5. **紫色保留语义**：通知/Telegram 相关紫色 → `var(--purple)` + `var(--purple-bg)`
6. **逻辑零改动**：只动 `<template>` 结构（增加 class）和 `<style>`，`<script>` 一字不改
7. **响应式保留**：原有 `@media (max-width: 768px)` 保留并 token 化

---

## 三、实施计划

### Phase 5：Files.vue 重写

**目标**：文件管理页全部 token 化 + 液态玻璃容器 + 新拟态交互元素

**改动清单**：
1. **删除局部变量定义**（`:root` 内的 `--bg-card/--border/--folder-color/--text-primary` 等），全部改用全局 token
2. **面包屑栏 `.breadcrumb-bar`**：改用 `.glass-card` + `padding: 12px 16px` + `border-radius: var(--radius-md)`
3. **返回按钮 `.btn-back`**：改用 `.neu-circle` + 36×36
4. **工具栏 `.toolbar`**：改用 `.glass-card`，`.toolbar-btn` 改用 `.neu-flat` + 主色填充态
5. **搜索框 `.search-box`**：改用 `.neu-inset` + 圆角 `var(--radius-full)`，icon 颜色 `var(--text-tertiary)`
6. **文件列表容器 `.file-list-container`**：改用 `.glass-card` + `border-radius: var(--radius-lg)`
7. **表头 `.table-header`**：`background: var(--bg-hover)` + `backdrop-filter: blur(8px)` + `position: sticky; top: 0`
8. **文件行 `.table-row`**：
   - hover：`var(--bg-hover)`
   - selected：`var(--bg-selected)` + 左侧 3px `var(--accent)` 边条
9. **复选框 `.checkbox-custom`**：选中态用 `var(--accent)` 填充 + 白色对勾；未选中用 `.neu-inset` 凹陷感
10. **更多按钮 `.btn-more`**：改用 `.neu-circle` 28×28
11. **右键菜单 `.context-menu`**：改用 `.glass-solid` + `border-radius: var(--radius-md)` + `padding: 4px`
12. **菜单项 `.menu-option`**：hover `var(--bg-hover)`，danger 用 `var(--danger)` + `var(--danger-bg)`
13. **弹窗 `.modal-overlay`**：改用 `.glass-overlay`（删除局部定义）
14. **弹窗卡片 `.modal-card`**：改用 `.glass-solid` + `border-radius: var(--radius-lg)`
15. **输入框 `.input-field`**：改用 `.neu-inset` + focus `var(--accent)` 光环
16. **按钮组**：`.btn-secondary` → `.neu-flat`；`.btn-primary` → `background: var(--accent)`；`.btn-danger` → `background: var(--danger)`
17. **目录选择器 `.picker-item`**：hover `var(--bg-hover)` + 圆角 `var(--radius-sm)`
18. **分页器 `.page-btn`**：未选中 `.neu-flat`；active `background: var(--accent)` + 白字
19. **loading spinner**：边框用 `var(--border)` + 顶部 `var(--accent)`
20. **空状态图标**：颜色 `var(--text-tertiary)`

**验证**：
- 列表正常加载、翻页、排序
- 多选/全选/取消选择
- 右键菜单移动/复制/识别/重命名/删除
- 新建文件夹、重命名、删除确认弹窗
- 目录选择器弹窗（双击进入子目录、确认移动/复制）
- 明暗主题切换无残留硬编码

---

### Phase 6：Settings.vue 重写

**目标**：4 个折叠卡片玻璃化 + 所有硬编码紫色走 `--purple` + 输入框/开关新拟态

**改动清单**：
1. **卡片 `.card`**：改用 `.glass-card` + `border-radius: var(--radius-lg)`，删除 `:hover` 阴影（玻璃卡片不需要）
2. **卡片头 `.card-head`**：保留 hover `var(--bg-hover)`
3. **卡片图标 `.card-icon`**：4 个语义色背景全部 token 化
   - `.tmdb-icon`：`var(--accent-bg)` + `var(--accent)`
   - `.api-icon`：`var(--success-bg)` + `var(--success)`
   - `.media-icon`：`var(--purple-bg)` + `var(--purple)`
   - `.notify-icon`：`var(--warning-bg)` + `var(--warning)`
4. **卡片标题**：`var(--text-primary)` / `var(--text-tertiary)`
5. **折叠箭头 `.chevron`**：`var(--text-tertiary)`
6. **卡片体 `.card-body`**：`border-top: 1px solid var(--border)`
7. **输入框/选择框 `.field input/select`**：改用 `.neu-inset` + focus `var(--accent)` 光环（不再用紫色）
8. **Toggle 开关 `.slider`**：
   - 未选中：`background: var(--border-strong)`
   - 选中：`background: var(--accent)`（从紫色 `#a855f7` 改为主色，与系统 Toggle 一致）
   - 圆点：`background: var(--bg-solid)` + 阴影
9. **子卡片 `.sub-card`**：`border: 1px solid var(--border)` + `var(--bg-elevated)` 半透明
10. **子卡片图标**：`.tg-icon` → `var(--accent)`；`.wx-icon` → `var(--success)`
11. **模式行 `.mode-row`**：`border-bottom: 1px solid var(--border)`
12. **模式状态 `.mode-status`**：`var(--success-bg)` + `var(--success)`
13. **路径字段 `.path-text`**：改用 `.neu-inset` + 等宽字体
14. **路径按钮 `.btn-ghost`**：改用 `.neu-circle` 36×36
15. **胶囊开关 `.pill-switch`**：`background: var(--bg-input)` + `.neu-inset`
    - `.pill-indicator`：`background: var(--bg-solid)` + `var(--shadow-sm)`
    - `.pill-label.active`：`var(--text-primary)`
16. **保存按钮 `.btn-save`**：`background: var(--accent)` + hover `var(--accent-hover)`
17. **小按钮 `.btn-ghost-sm`**：改用 `.neu-flat`
18. **徽章 `.badge-ok/.badge-warn`**：用 `var(--success-bg)/var(--success)` 和 `var(--warning-bg)/var(--warning)`
19. **标签 `.tag`**：`background: var(--bg-input)` + `var(--text-secondary)`
20. **自定义标签 `.tag-custom`**：`var(--purple-bg)` + `var(--purple)`
21. **标签输入框 `.tag-input-box`**：改用 `.neu-inset`
22. **规则行 `.rule-cat/.rule-cond`**：改用 `.neu-inset` + focus `var(--accent)`
23. **类型标签 `.type-movie`**：`var(--accent-bg)` + `var(--accent)`；`.type-tv`：`var(--purple-bg)` + `var(--purple)`
24. **虚线按钮 `.btn-dashed`**：`border: 1px dashed var(--border-strong)` + hover `var(--purple)`
25. **重置按钮 `.btn-icon-reset`**：hover `var(--text-secondary)` + `var(--bg-hover)`
26. **删除小图标 `.btn-icon-sm.danger:hover`**：`var(--danger-bg)` + `var(--danger)`
27. **手机号输入行 `.phone-row`**：保留布局，输入框 `.neu-inset`
28. **登录状态 `.status-ok/.status-warn`**：`var(--success)/var(--warning)`

**验证**：
- 4 个卡片折叠/展开
- OpenAPI 启用/选择应用
- TMDB 保存
- 整理方式切换、路径选择弹窗、模板输入、规则增删、发布组标签增删
- 通知卡片：Bot/User 模式开关、发送验证码、登录、测试、保存
- 明暗主题切换

---

### Phase 7：About.vue 重写

**目标**：使用项目 logo + 液态玻璃卡片 + 技术栈标签新拟态

**改动清单**：
1. **删除内联 SVG logo**，替换为 `<img src="@/assets/logo.png" />` 64×64 + 圆角 `var(--radius-md)`
2. **卡片 `.about-card`**：改用 `.glass-card` + `border-radius: var(--radius-lg)`
3. **Logo 区 `.app-logo-area`**：`border-bottom: 1px solid var(--border)`
4. **标题**：`var(--text-primary)` / `var(--text-secondary)`
5. **信息行 `.info-row`**：hover `var(--bg-hover)`
6. **技术栈标签 `.tech-tag`**：改用 `.neu-raised` + 8px 圆角 + `var(--text-secondary)`
7. **版本号**：`var(--text-secondary)` + 等宽字体

**验证**：logo 显示正确，明暗主题切换

---

### Phase 8：组件层重写

#### 8.1 Toast.vue
1. **容器 `.toast`**：改用 `.glass-solid` + `border-radius: var(--radius-full)` + `var(--shadow-lg)`
2. **文字颜色**：`var(--text-primary)`（从白色改为跟随主题，因背景已玻璃化）
3. **图标颜色**：
   - success → `var(--success)`
   - error → `var(--danger)`
   - info → `var(--accent)`
4. **进入动画**：保留 `translateY` 过渡

#### 8.2 LogViewer.vue
**核心改动**：移除独立暗色主题，完全跟随全局主题
1. **遮罩 `.log-overlay`**：改用 `.glass-overlay`（但 `justify-content: flex-end` 保留右侧抽屉）
2. **面板 `.log-panel`**：改用 `.glass-solid` + `border-left: 1px solid var(--border)`
3. **头部 `.log-header`**：`border-bottom: 1px solid var(--border)`
4. **日志图标**：`var(--purple)`
5. **标题**：`var(--text-primary)`
6. **计数徽章**：`var(--bg-input)` + `var(--text-tertiary)`
7. **按钮 `.log-btn`**：未激活 `var(--text-tertiary)`；激活 `var(--accent)`；hover `var(--bg-hover)`
8. **筛选栏 `.log-toolbar`**：`border-bottom: 1px solid var(--border)`
9. **筛选下拉 `.filter-select`**：改用 `.neu-inset` + 12px
10. **搜索输入 `.search-input`**：改用 `.neu-inset`
11. **日志表格**：
    - 表头 `th`：`background: var(--bg-solid)` + `color: var(--text-tertiary)`
    - 行 `td`：`border-bottom: 1px solid var(--border)`
    - hover：`var(--bg-hover)`
    - 时间列：`var(--text-tertiary)`
    - 模块列：`var(--purple)`
    - 消息列：`var(--text-primary)`
12. **级别标签**：
    - debug → `var(--purple-bg)` + `var(--purple)`
    - info → `var(--accent-bg)` + `var(--accent)`
    - warning → `var(--warning-bg)` + `var(--warning)`
    - error → `var(--danger-bg)` + `var(--danger)`
13. **loading spinner**：边框 `var(--border)` + 顶部 `var(--purple)`
14. **滚动条**：跟随全局（已在 base.css 定义，删除局部覆盖）
15. **`option` 元素**：`background: var(--bg-solid)` + `color: var(--text-primary)`

#### 8.3 RecognizeModal.vue
1. **遮罩 `.modal-overlay`**：改用 `.glass-overlay`
2. **弹窗 `.result-modal`**：改用 `.glass-solid` + `border-radius: var(--radius-lg)`
3. **Hero 区背景遮罩 `.backdrop-mask`**：
   - 亮色：`linear-gradient(to top, var(--bg-solid) 0%, rgba(255,255,255,0.6) 40%, rgba(0,0,0,0.15) 100%)`
   - 暗色：`linear-gradient(to top, var(--bg-solid) 0%, rgba(44,44,46,0.6) 40%, rgba(0,0,0,0.3) 100%)`
4. **占位渐变 `.hero-placeholder`**：`linear-gradient(135deg, var(--accent), var(--purple))`
5. **关闭按钮 `.btn-close-hero`**：保留半透明黑底，hover 加深
6. **海报 `.hero-poster`**：改用 `.neu-raised` 风格 + 圆角 `var(--radius-md)`
7. **海报占位 `.poster-placeholder`**：`var(--bg-input)` + 图标 `var(--text-tertiary)`
8. **骨架屏**：`var(--bg-hover)` + 脉冲动画
9. **标题 `.hero-title`**：`var(--text-primary)`
10. **类型标签 `.meta-type`**：`var(--purple-bg)` + `var(--purple)`
11. **年份 `.meta-year`**：`var(--text-secondary)`
12. **评分 `.meta-rating`**：`var(--warning)`
13. **loading spinner**：边框 `var(--border)` + 顶部 `var(--purple)`
14. **标签行 `.tag-category`**：`var(--accent-bg)` + `var(--accent)`；`.tag-id`：`var(--bg-input)` + `var(--text-secondary)` + 等宽
15. **分区标题 `.section-title`**：`var(--text-tertiary)`
16. **技术标签**：
    - 默认：`var(--bg-input)` + `var(--text-secondary)`
    - `.tag-source`：`var(--accent-bg)` + `var(--accent)`（青色无 token，借用 accent）
    - `.tag-edition`：`var(--warning-bg)` + `var(--warning)`
    - `.tag-group`：`var(--purple-bg)` + `var(--purple)`
17. **目标路径 `.path-box`**：改用 `.neu-inset` + 等宽字体；`.path-dir` `var(--text-tertiary)`；`.path-file` `var(--text-primary)`
18. **简介 `.overview-text`**：`var(--text-secondary)`
19. **整理按钮 `.btn-organize`**：`background: var(--accent)` + hover `var(--accent-hover)`
20. **执行错误 `.exec-error`**：`var(--danger-bg)` + `var(--danger)`
21. **执行成功 `.exec-success`**：`var(--success-bg)` + `var(--success)`
22. **空状态**：`var(--text-tertiary)`

---

## 四、Assumptions & Decisions

### Assumptions
1. 所有 `<script>` 逻辑保持不变，只改 `<template>` 与 `<style>`
2. 原有 DOM 结构与 class 名尽量保留（避免大改 template，降低风险）
3. Element Plus 仍全量引入，但本阶段不主动使用 Element 组件（保持原生实现）
4. 已完成的设计系统文件（tokens/glass/neu/base）不再修改

### Decisions
1. **Toggle 主色统一为 `var(--accent)`**：Settings.vue 原紫色 `#a855f7` 切换为主色 `--accent`，与 Layout/Login/ThemeToggle 视觉一致；紫色保留给 Telegram/发布组等语义场景
2. **LogViewer 取消独立暗色主题**：原 `#18181b` 黑底改为跟随 `data-theme`，亮色用 `var(--bg-solid)`，暗色自动用 `#2c2c2e`
3. **弹窗遮罩统一用 `.glass-overlay`**：删除各组件内重复定义的 `.modal-overlay`
4. **海报框走新拟态凸起**：`.neu-raised` 替代硬编码阴影
5. **图标按钮统一 `.neu-circle`**：返回按钮、关闭按钮、更多按钮、日志按钮风格一致
6. **保留所有响应式断点**：`@media (max-width: 768px)` 保留，仅 token 化颜色

---

## 五、验证步骤

### 5.1 开发环境验证
```bash
cd d:\OneFive\frontend
npm run dev
```
- 浏览器访问 `http://localhost:5173`
- 登录后默认进入 `/files`
- 切换明暗主题（顶栏右上角太阳/月亮按钮）

### 5.2 功能回归 Checklist
**Files 页**：
- [ ] 列表加载、翻页、排序
- [ ] 多选、全选、取消选择
- [ ] 右键菜单（移动/复制/识别/重命名/删除）
- [ ] 新建文件夹、重命名、删除确认弹窗
- [ ] 目录选择器（双击进入子目录、确认）
- [ ] 搜索框输入与清空

**Settings 页**：
- [ ] 4 个卡片折叠/展开
- [ ] OpenAPI 启用 + 选择应用
- [ ] TMDB 保存
- [ ] 整理方式切换、路径选择、模板输入
- [ ] 规则增删、发布组标签增删
- [ ] 通知卡片：Bot/User 开关、发送验证码、登录、测试、保存

**About 页**：
- [ ] logo 显示
- [ ] 技术栈标签新拟态凸起

**组件**：
- [ ] Toast 三种类型（success/error/info）显示
- [ ] LogViewer 抽屉打开、筛选、搜索、自动滚动
- [ ] RecognizeModal 弹窗、海报、技术信息、执行整理

### 5.3 主题验证 Checklist
- [ ] 亮色模式：所有卡片半透明 + blur 效果可见
- [ ] 暗色模式：所有卡片背景 `#2c2c2e` + 文字高对比
- [ ] 切换主题：localStorage 持久化（刷新后保留）
- [ ] 跟随系统：清除 localStorage 后，根据 `prefers-color-scheme` 自动选择

### 5.4 构建检查
```bash
cd d:\OneFive\frontend
npm run build
```
- 无 TypeScript 错误
- 无 Vue 模板编译错误
- 产物体积无明显膨胀（应持平或略降，因删除局部变量）

### 5.5 视觉巡检
- [ ] 无任何硬编码 `#xxx` 残留（Grep 验证）
- [ ] 所有交互元素 hover/active 态有反馈
- [ ] 所有弹窗遮罩一致（blur + 半透明）
- [ ] 所有图标按钮圆形 + 新拟态
- [ ] 所有输入框凹陷 + focus 主色光环

---

## 六、执行顺序

1. **Phase 5**：Files.vue（最复杂，先做）
2. **Phase 6**：Settings.vue（次复杂）
3. **Phase 7**：About.vue（最简单，快速完成）
4. **Phase 8**：Toast → LogViewer → RecognizeModal（组件层）
5. **验证**：dev 启动 + 功能回归 + 主题巡检 + build

每个 Phase 完成后立即标记 Todo 完成，不做批量合并。
