<template>
  <div v-if="visible" class="glass-overlay" @click.self="close">
    <div class="result-modal glass-solid">
      <!-- 顶部背景区域 -->
      <div class="hero-area">
        <!-- 背景图 -->
        <div v-if="result?.tmdb_backdrop" class="hero-backdrop">
          <img :src="result.tmdb_backdrop" alt="" />
          <div class="backdrop-mask"></div>
        </div>
        <div v-else class="hero-backdrop hero-placeholder"></div>

        <!-- 关闭按钮 -->
        <button class="btn-close-hero neu-circle" @click="close">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <!-- 加载中：骨架屏 -->
        <div v-if="loading" class="hero-content">
          <div class="hero-poster poster-skeleton"></div>
          <div class="hero-info">
            <div class="skeleton-line skeleton-title"></div>
            <div class="skeleton-line skeleton-meta"></div>
          </div>
        </div>

        <!-- 海报 + 标题区 -->
        <div v-else class="hero-content">
          <div v-if="result?.tmdb_poster" class="hero-poster neu-raised">
            <img :src="result.tmdb_poster" alt="poster" />
          </div>
          <div v-else class="hero-poster poster-placeholder neu-raised">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
              <line x1="8" y1="21" x2="16" y2="21" />
              <line x1="12" y1="17" x2="12" y2="21" />
            </svg>
          </div>
          <div class="hero-info">
            <h2 class="hero-title">{{ result?.title || item?.name || '未知' }}</h2>
            <div class="hero-meta">
              <span v-if="result" class="meta-type">{{ result.media_type === 'movie' ? '电影' : '电视剧' }}</span>
              <span v-if="result?.year" class="meta-year">{{ result.year }}</span>
              <span v-if="Number(result?.tmdb_rating) > 0" class="meta-rating">
                <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14">
                  <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                </svg>
                {{ Number(result.tmdb_rating).toFixed(1) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 加载中 -->
      <div v-if="loading" class="result-loading">
        <div class="loading-spinner"></div>
        <p>正在识别...</p>
      </div>

      <!-- 有结果 -->
      <div v-else-if="result" class="result-body">
        <!-- 标签行：分类 + TMDB ID -->
        <div class="tag-row">
          <span v-if="result.category" class="tag tag-category">{{ result.category }}</span>
          <span v-if="result.tmdb_id" class="tag tag-id">TMDB {{ result.tmdb_id }}</span>
          <span v-else class="tag tag-warn">未命中 TMDB，可手动纠错</span>
        </div>

        <!-- 手动纠错 -->
        <div class="manual-box">
          <div class="section-title">手动纠错</div>
          <div class="manual-row">
            <select v-model="manualMediaType" class="manual-select">
              <option value="movie">电影</option>
              <option value="tv">电视剧</option>
            </select>
            <input v-model="manualTmdbId" class="manual-input" placeholder="输入 TMDB ID" @keyup.enter="manualRecognize" />
            <button class="manual-btn" :disabled="manualLoading" @click="manualRecognize">
              {{ manualLoading ? '识别中...' : '重新识别' }}
            </button>
          </div>
          <div v-if="manualError" class="manual-error">{{ manualError }}</div>
        </div>

        <!-- 技术信息 -->
        <div v-if="hasTechInfo" class="section">
          <div class="section-title">技术信息</div>
          <div class="tech-tags">
            <span v-if="result.tech_info.videoFormat" class="tech-tag">{{ result.tech_info.videoFormat }}</span>
            <span v-if="result.tech_info.edition" class="tech-tag tag-edition">{{ result.tech_info.edition }}</span>
            <span v-if="result.tech_info.videoCodec" class="tech-tag">{{ result.tech_info.videoCodec }}</span>
            <span v-if="result.tech_info.audioCodec" class="tech-tag">{{ result.tech_info.audioCodec }}</span>
            <span v-if="result.tech_info.webSource" class="tech-tag tag-source">{{ result.tech_info.webSource }}</span>
            <span v-if="result.tech_info.releaseGroup" class="tech-tag tag-group">{{ result.tech_info.releaseGroup }}</span>
          </div>
        </div>

        <!-- 目标路径 -->
        <div v-if="result.target_path" class="section">
          <div class="section-title">目标路径</div>
          <div class="path-box">
            <span class="path-dir">{{ result.target_path.dir }}/</span><span class="path-file">{{ result.target_path.filename }}</span>
          </div>
        </div>

        <!-- 简介 -->
        <div v-if="result.tmdb_overview" class="section">
          <div class="section-title">简介</div>
          <p class="overview-text">{{ result.tmdb_overview }}</p>
        </div>

        <!-- 执行整理 -->
        <div v-if="result.target_path" class="action-bar">
          <div v-if="execError" class="exec-error">{{ execError }}</div>
          <div v-if="execSuccess" class="exec-success">{{ execSuccess }}</div>
          <button
            class="btn-organize"
            :disabled="executing || !!execSuccess"
            @click="doOrganize"
          >
            <svg v-if="!executing" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg>
            <div v-else class="btn-spinner"></div>
            {{ executing ? '整理中...' : '执行整理' }}
          </button>
        </div>
      </div>

      <!-- 无结果 -->
      <div v-else class="result-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
          <line x1="8" y1="11" x2="14" y2="11" />
        </svg>
        <p>未识别到媒体信息</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { organizeApi, type RecognizeResult } from '@/api/organize'
import { filesApi, type FileItem } from '@/api/files'

const props = defineProps<{
  visible: boolean
  item: FileItem | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const loading = ref(false)
const result = ref<RecognizeResult | null>(null)
const executing = ref(false)
const execError = ref('')
const execSuccess = ref('')
const manualTmdbId = ref('')
const manualMediaType = ref<'movie' | 'tv'>('movie')
const manualLoading = ref(false)
const manualError = ref('')

// 请求版本号：每次发起新识别或关闭弹窗时自增，
// await 后比对版本可判断本次请求是否仍为"当前请求"，避免旧请求覆盖新状态
let currentRequestId = 0

const hasTechInfo = computed(() => {
  if (!result.value?.tech_info) return false
  const t = result.value.tech_info
  return t.videoFormat || t.edition || t.videoCodec || t.audioCodec || t.webSource || t.releaseGroup
})

// 打开时自动识别
watch(() => props.visible, (val) => {
  if (val && props.item) {
    recognizeFile(props.item)
  } else {
    // 关闭时自增版本号，使进行中的识别请求作废，避免其 await 完成后覆盖新状态
    currentRequestId++
    result.value = null
    execError.value = ''
    execSuccess.value = ''
    manualTmdbId.value = ''
    manualMediaType.value = 'movie'
    manualError.value = ''
    manualLoading.value = false
    executing.value = false
  }
})

function close() {
  emit('close')
}

/**
 * 自动识别入口（打开弹窗时触发）
 * - 文件夹模式：根据内容推断 mediaType 后调用 TMDB 搜索
 * - 文件模式：直接调用 TMDB 搜索
 * - 含请求版本号校验，避免旧版本响应覆盖新版本结果
 */
async function recognizeFile(item: FileItem) {
  // 自增版本号并捕获，作为本次请求的"当前性"凭证
  const reqId = ++currentRequestId
  loading.value = true
  result.value = null
  try {
    let folderFiles: string[] | undefined

    // 文件夹模式：先获取内部文件列表
    if (item.is_dir) {
      try {
        const listRes = await filesApi.listFiles(item.file_id, 200)
        // 若期间已发起新请求或关闭弹窗，则丢弃本次结果
        if (reqId !== currentRequestId) return
        if (listRes.code === 0 && listRes.data?.items) {
          folderFiles = listRes.data.items.map((f: FileItem) => f.name)
        }
      } catch (e) {
        console.warn('获取文件夹内容失败:', e)
      }
    }

    const res = await organizeApi.recognize({
      file_id: item.file_id,
      file_name: item.name,
      is_dir: item.is_dir,
      folder_files: folderFiles,
    })
    // await 完成后再次校验版本，避免旧请求覆盖新状态
    if (reqId !== currentRequestId) return
    if (res.code === 0 && res.data) {
      result.value = res.data
      manualTmdbId.value = res.data.tmdb_id ? String(res.data.tmdb_id) : ''
      manualMediaType.value = res.data.media_type === 'tv' ? 'tv' : 'movie'
    } else {
      result.value = null
    }
  } catch (e) {
    console.error('识别失败:', e)
    if (reqId !== currentRequestId) return
    result.value = null
  } finally {
    // 仅当本次仍为当前请求时才复位 loading
    if (reqId === currentRequestId) {
      loading.value = false
    }
  }
}

/**
 * 手动识别入口（用户输入 TMDB ID 后触发）
 * 与 recognizeFile 的区别：跳过 TMDB 搜索，直接用用户指定的 ID 查询详情
 */
async function manualRecognize() {
  if (!props.item) return
  const tmdbId = Number(manualTmdbId.value)
  if (!Number.isInteger(tmdbId) || tmdbId <= 0) {
    manualError.value = '请输入正确的 TMDB ID'
    return
  }

  // 自增版本号并捕获，用于 await 后校验请求当前性
  const reqId = ++currentRequestId
  manualLoading.value = true
  manualError.value = ''
  execError.value = ''
  execSuccess.value = ''
  try {
    let folderFiles: string[] | undefined
    if (props.item.is_dir) {
      // 与 recognizeFile 保持一致：listFiles 失败不应中断主流程
      try {
        const listRes = await filesApi.listFiles(props.item.file_id, 200)
        if (reqId !== currentRequestId) return
        if (listRes.code === 0 && listRes.data?.items) {
          folderFiles = listRes.data.items.map((f: FileItem) => f.name)
        }
      } catch (e) {
        console.warn('获取文件夹内容失败:', e)
      }
    }

    const res = await organizeApi.manualRecognize({
      file_id: props.item.file_id,
      file_name: props.item.name,
      is_dir: props.item.is_dir,
      folder_files: folderFiles,
      tmdb_id: tmdbId,
      media_type: manualMediaType.value,
    })
    // await 完成后校验版本，避免旧请求覆盖新状态
    if (reqId !== currentRequestId) return
    if (res.code === 0 && res.data) {
      result.value = res.data
      manualTmdbId.value = String(res.data.tmdb_id || tmdbId)
      manualMediaType.value = res.data.media_type === 'tv' ? 'tv' : 'movie'
    } else {
      manualError.value = res.message || '手动识别失败'
    }
  } catch (e: any) {
    if (reqId !== currentRequestId) return
    manualError.value = e.message || '手动识别失败'
  } finally {
    // 仅当本次仍为当前请求时才复位 manualLoading
    if (reqId === currentRequestId) {
      manualLoading.value = false
    }
  }
}

/**
 * 执行整理入口
 * 依赖 result.target_path，调用后端整理接口将文件移动到目标路径
 */
async function doOrganize() {
  if (!props.item || !result.value?.target_path) return

  executing.value = true
  execError.value = ''
  execSuccess.value = ''

  try {
    // 从设置读取整理模式
    let organizeMode = 'move'
    try {
      const settingsRes = await organizeApi.getSettings()
      if (settingsRes.code === 0 && settingsRes.data?.organize_mode) {
        organizeMode = settingsRes.data.organize_mode
      }
    } catch (e) { /* 使用默认 move */ }

    const res = await organizeApi.execute({
      file_id: props.item.file_id,
      file_name: props.item.name,
      is_dir: props.item.is_dir,
      target_path: result.value.target_path,
      organize_mode: organizeMode,
      category: result.value.category || '',
      target_title: result.value.title || '',
      tmdb_id: result.value.tmdb_id || 0,
      media_type: result.value.media_type || '',
      year: result.value.year || '',
      season: result.value.season || 0,
      episode: result.value.episode || 0,
      tmdb_poster: result.value.tmdb_poster || '',
      tmdb_backdrop: result.value.tmdb_backdrop || '',
      tmdb_rating: result.value.tmdb_rating || 0,
      tech_info: result.value.tech_info || {},
    })
    if (res.code === 0) {
      execSuccess.value = res.message || '整理完成'
    } else {
      execError.value = res.message || '整理失败'
    }
  } catch (e: any) {
    execError.value = e.message || '整理失败'
  } finally {
    executing.value = false
  }
}
</script>

<style scoped>
/* 遮罩：由 glass-overlay 提供 background/backdrop-filter/display/z-index */

/* 弹窗：由 glass-solid 提供 background/blur/border/shadow */
.result-modal {
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 520px;
  overflow: hidden;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

/* ==================== 顶部 Hero ==================== */
.hero-area {
  position: relative;
  min-height: 200px;
  display: flex;
  align-items: flex-end;
  overflow: hidden;
}

.hero-backdrop {
  position: absolute;
  inset: 0;
}

.hero-backdrop img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 渐变遮罩：暗亮自适应，用 token + color-mix */
.backdrop-mask {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to top,
    var(--bg-solid) 0%,
    color-mix(in srgb, var(--bg-solid) 60%, transparent) 40%,
    color-mix(in srgb, black 15%, transparent) 100%
  );
}

/* 占位渐变：accent → purple */
.hero-placeholder {
  background: linear-gradient(135deg, var(--accent) 0%, var(--purple) 100%);
}

/* 关闭按钮：圆形凸起，悬浮于 hero 上 */
/* neu-circle 提供阴影/transition，此处保留半透明黑底保证海报上可读 */
.btn-close-hero {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 32px;
  height: 32px;
  background: color-mix(in srgb, black 30%, transparent);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-inverse);
  z-index: 2;
}

.btn-close-hero:hover {
  background: color-mix(in srgb, black 50%, transparent);
}

.btn-close-hero svg {
  width: 16px;
  height: 16px;
}

.hero-content {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-end;
  gap: 16px;
  padding: 0 24px 20px;
  width: 100%;
}

/* 海报：neu-raised 提供凸起阴影 */
.hero-poster {
  width: 100px;
  height: 150px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--bg-hover);
}

.hero-poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.poster-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
}

.poster-placeholder svg {
  width: 32px;
  height: 32px;
  color: var(--text-tertiary);
}

/* 骨架屏 */
.poster-skeleton {
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-line {
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-title {
  height: 22px;
  width: 70%;
  margin-bottom: 8px;
}

.skeleton-meta {
  height: 16px;
  width: 40%;
}

@keyframes skeleton-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.hero-info {
  flex: 1;
  min-width: 0;
  padding-bottom: 4px;
}

.hero-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.hero-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* 类型标签：紫色语义（电影/电视剧） */
.meta-type {
  font-size: 12px;
  font-weight: 600;
  color: var(--purple);
  background: var(--purple-bg);
  padding: 2px 10px;
  border-radius: var(--radius-full);
}

.meta-year {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

/* 评分：用 warning 语义色（金黄） */
.meta-rating {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--warning);
}

.meta-rating svg {
  width: 14px;
  height: 14px;
}

/* ==================== 加载 / 空状态 ==================== */
.result-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: var(--text-tertiary);
}

.loading-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.result-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 20px;
  color: var(--text-tertiary);
}

.result-empty svg { width: 40px; height: 40px; }
.result-empty p { font-size: 14px; }

/* ==================== 结果内容 ==================== */
.result-body {
  padding: 16px 24px 24px;
  overflow-y: auto;
}

/* 标签行 */
.tag-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.tag {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-full);
}

/* 分类标签：accent 蓝 */
.tag-category {
  color: var(--accent);
  background: var(--accent-bg);
}

/* TMDB ID 标签：中性灰，monospace */
.tag-warn { background: rgba(245, 158, 11, 0.15); color: #d97706; }
.tag-id {
  color: var(--text-secondary);
  background: var(--bg-hover);
  font-family: var(--font-mono);
  font-weight: 500;
}

/* 分区 */
.section {
  margin-bottom: 16px;
}

.section:last-child {
  margin-bottom: 0;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

/* 手动纠错 */
.manual-box {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.manual-row {
  display: flex;
  gap: 8px;
}

.manual-select,
.manual-input {
  height: 34px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  padding: 0 10px;
  font-size: 13px;
}

.manual-input {
  flex: 1;
  min-width: 0;
}

.manual-btn {
  height: 34px;
  padding: 0 12px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: var(--text-inverse);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.manual-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.manual-error {
  margin-top: 8px;
  color: var(--danger);
  font-size: 12px;
}

/* 技术标签容器 */
.tech-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* 默认技术标签 */
.tech-tag {
  padding: 4px 10px;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

/* 来源标签：accent 蓝 */
.tech-tag.tag-source {
  color: var(--accent);
  background: var(--accent-bg);
}

/* 版本标签：warning 橙 */
.tech-tag.tag-edition {
  color: var(--warning);
  background: var(--warning-bg);
}

/* 发布组标签：purple 紫 */
.tech-tag.tag-group {
  color: var(--purple);
  background: var(--purple-bg);
}

/* 目标路径：新拟态凹陷 */
.path-box {
  padding: 10px 14px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-family: var(--font-mono);
  word-break: break-all;
  line-height: 1.5;
  box-shadow: var(--neu-inset);
}

.path-dir {
  color: var(--text-tertiary);
}

.path-file {
  color: var(--text-primary);
  font-weight: 500;
}

/* 简介 */
.overview-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  max-height: 120px;
  overflow-y: auto;
  margin: 0;
}

/* 执行整理按钮区 */
.action-bar {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 主按钮：accent */
.btn-organize {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 11px 20px;
  background: var(--accent);
  color: var(--text-inverse);
  border: none;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-base);
}

.btn-organize:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-organize:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-organize svg {
  width: 16px;
  height: 16px;
}

/* 按钮内 spinner */
.btn-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border);
  border-top-color: var(--text-inverse);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* 错误/成功提示 */
.exec-error {
  padding: 8px 12px;
  background: var(--danger-bg);
  color: var(--danger);
  border-radius: var(--radius-sm);
  font-size: 12px;
}

.exec-success {
  padding: 8px 12px;
  background: var(--success-bg);
  color: var(--success);
  border-radius: var(--radius-sm);
  font-size: 12px;
}

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
  .result-modal {
    max-width: 100%;
    max-height: 100vh;
    border-radius: 0;
  }

  .hero-area {
    min-height: 180px;
  }

  .hero-poster {
    width: 80px;
    height: 120px;
  }

  .hero-title {
    font-size: 17px;
  }

  .result-body {
    padding: 12px 16px 20px;
  }
}
</style>
