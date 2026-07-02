<template>
  <Teleport to="body">
    <Transition name="log-panel">
      <div v-if="visible" class="log-overlay glass-overlay" @click.self="close">
        <div class="log-panel glass-solid">
          <!-- 头部 -->
          <div class="log-header">
            <div class="log-header-left">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="log-icon">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
              <h3>日志</h3>
              <span class="log-count">{{ filteredLines.length }}</span>
            </div>
            <div class="log-header-right">
              <button class="log-btn neu-circle" :class="{ active: autoScroll }" @click="autoScroll = !autoScroll" title="自动滚动">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 5v14M5 12l7 7 7-7" />
                </svg>
              </button>
              <button class="log-btn neu-circle" @click="loadLogs" title="刷新">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="23 4 23 10 17 10" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
              </button>
              <button class="log-btn neu-circle" @click="close" title="关闭">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>

          <!-- 筛选栏 -->
          <div class="log-toolbar">
            <select v-model="selectedLevel" class="filter-select neu-inset">
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARN</option>
              <option value="ERROR">ERROR</option>
            </select>
            <select v-model="selectedModule" class="filter-select neu-inset">
              <option value="">全部模块</option>
              <option v-for="m in modules" :key="m" :value="m">{{ m }}</option>
            </select>
            <div class="search-input neu-inset">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input v-model="keyword" type="text" placeholder="搜索..." />
            </div>
          </div>

          <!-- 日志内容 -->
          <div class="log-body" ref="logBodyRef">
            <div v-if="loading" class="log-loading">
              <div class="loading-spinner"></div>
            </div>
            <div v-else-if="filteredLines.length === 0" class="log-empty">
              <p>暂无日志</p>
            </div>
            <table v-else class="log-table">
              <thead>
                <tr>
                  <th class="col-time">时间</th>
                  <th class="col-level">级别</th>
                  <th class="col-module">模块</th>
                  <th class="col-msg">消息</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(line, index) in filteredLines"
                  :key="index"
                  class="log-row"
                >
                  <td class="col-time">{{ line.time }}</td>
                  <td class="col-level">
                    <span class="level-tag" :class="line.level.toLowerCase()">{{ line.level }}</span>
                  </td>
                  <td class="col-module">{{ line.module }}</td>
                  <td class="col-msg">{{ line.message }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { logsApi, type LogLine } from '@/api/logs'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits(['close'])

const loading = ref(false)
const lines = ref<LogLine[]>([])
const selectedLevel = ref('INFO')
const selectedModule = ref('')
const keyword = ref('')
const autoScroll = ref(true)
const logBodyRef = ref<HTMLElement | null>(null)

// 日志级别优先级：DEBUG < INFO < WARNING < ERROR
const levelPriority: Record<string, number> = {
  'DEBUG': 0,
  'INFO': 1,
  'WARNING': 2,
  'ERROR': 3,
}

// 从日志中提取唯一模块列表
const modules = computed(() => {
  const set = new Set(lines.value.map(l => l.module).filter(Boolean))
  return Array.from(set).sort()
})

const filteredLines = computed(() => {
  let result = lines.value

  // 级别筛选：选中级别及以上的日志
  if (selectedLevel.value) {
    const minPriority = levelPriority[selectedLevel.value] ?? 1
    result = result.filter(l => (levelPriority[l.level] ?? 0) >= minPriority)
  }

  // 模块筛选
  if (selectedModule.value) {
    result = result.filter(l => l.module === selectedModule.value)
  }

  // 关键词搜索
  if (keyword.value) {
    const kw = keyword.value.toLowerCase()
    result = result.filter(l => l.message.toLowerCase().includes(kw) || l.module.toLowerCase().includes(kw))
  }

  return result
})

// 自动滚动
watch(() => filteredLines.value.length, () => {
  if (autoScroll.value) {
    nextTick(() => {
      if (logBodyRef.value) {
        logBodyRef.value.scrollTop = logBodyRef.value.scrollHeight
      }
    })
  }
})

// SSE 流
let eventSource: EventSource | null = null

function startStream() {
  if (eventSource) return
  try {
    eventSource = new EventSource('/app/onefive/api/logs/stream')
    eventSource.onmessage = (event) => {
      try {
        const line = JSON.parse(event.data)
        lines.value.push(line)
        if (lines.value.length > 2000) {
          lines.value = lines.value.slice(-1500)
        }
      } catch {}
    }
    eventSource.onerror = () => {
      stopStream()
      setTimeout(() => { startStream() }, 3000)
    }
  } catch {}
}

function stopStream() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

async function loadLogs() {
  loading.value = true
  try {
    const res = await logsApi.getLogs(500)
    lines.value = res.lines || []
  } catch (e) {
    console.error('加载日志失败:', e)
  } finally {
    loading.value = false
  }
}

function close() {
  stopStream()
  emit('close')
}

// visible 变化时加载/停止
watch(() => props.visible, (val) => {
  if (val) {
    loadLogs()
    startStream()
  } else {
    stopStream()
  }
})
</script>

<style scoped>
/* 遮罩：由 glass-overlay 提供 background/backdrop-filter/z-index/align */
.log-overlay {
  justify-content: flex-end;
  padding: 0;
  z-index: 500;
}

/* 面板：由 glass-solid 提供 background/blur/border/shadow */
.log-panel {
  width: 100%;
  max-width: 640px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: 0;
}

/* 头部 */
.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.log-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.log-icon {
  width: 18px;
  height: 18px;
  color: var(--purple);
}

.log-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.log-count {
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-hover);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.log-header-right {
  display: flex;
  align-items: center;
  gap: 2px;
}

/* 按钮由 neu-circle 提供 background/shadow/transition */
.log-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all var(--transition-fast);
}

.log-btn:hover {
  color: var(--text-secondary);
}

.log-btn.active {
  color: var(--accent);
}

.log-btn svg {
  width: 16px;
  height: 16px;
}

/* 筛选栏 */
.log-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
}

/* select 由 neu-inset 提供 background/shadow/border */
.filter-select {
  padding: 6px 28px 6px 10px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-secondary);
  outline: none;
  cursor: pointer;
  min-width: 90px;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
}

.filter-select:focus {
  border-color: var(--accent);
}

.filter-select option {
  background: var(--bg-solid);
  color: var(--text-primary);
}

/* 搜索框由 neu-inset 提供 background/shadow/border */
.search-input {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
}

.search-input:focus-within {
  border-color: var(--accent);
}

.search-input svg {
  width: 14px;
  height: 14px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.search-input input {
  border: none;
  background: none;
  outline: none;
  font-size: 13px;
  color: var(--text-primary);
  width: 100%;
  min-width: 0;
}

.search-input input::placeholder {
  color: var(--text-tertiary);
}

/* 日志内容区 */
.log-body {
  flex: 1;
  overflow: auto;
}

.log-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.log-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px;
  color: var(--text-tertiary);
  font-size: 14px;
}

/* 日志表格 */
.log-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12px;
  font-family: var(--font-mono);
}

.log-table thead {
  position: sticky;
  top: 0;
  z-index: 1;
}

.log-table th {
  background: var(--bg-solid);
  color: var(--text-tertiary);
  font-weight: 500;
  text-align: left;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.log-table td {
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}

.log-row:hover td {
  background: var(--bg-hover);
}

.col-time {
  width: 80px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.col-level {
  width: 80px;
}

/* 级别标签 token 化 */
.level-tag {
  display: inline-block;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.level-tag.debug {
  background: var(--purple-bg);
  color: var(--purple);
}

.level-tag.info {
  background: var(--accent-bg);
  color: var(--accent);
}

.level-tag.warning {
  background: var(--warning-bg);
  color: var(--warning);
}

.level-tag.error {
  background: var(--danger-bg);
  color: var(--danger);
}

.col-module {
  width: 80px;
  color: var(--purple);
  white-space: nowrap;
}

.col-msg {
  color: var(--text-primary);
  word-break: break-all;
}

/* 进入/退出动画 */
.log-panel-enter-active,
.log-panel-leave-active {
  transition: all 0.25s ease;
}

.log-panel-enter-active .log-panel,
.log-panel-leave-active .log-panel {
  transition: transform 0.25s ease;
}

.log-panel-enter-from,
.log-panel-leave-to {
  opacity: 0;
}

.log-panel-enter-from .log-panel,
.log-panel-leave-to .log-panel {
  transform: translateX(100%);
}

/* 滚动条 */
.log-body::-webkit-scrollbar {
  width: 6px;
}

.log-body::-webkit-scrollbar-track {
  background: transparent;
}

.log-body::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 3px;
}

.log-body::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}

/* 响应式 */
@media (max-width: 768px) {
  .log-panel {
    max-width: 100%;
  }
}
</style>
