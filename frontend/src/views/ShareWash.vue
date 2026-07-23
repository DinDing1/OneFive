<template>
  <div class="share-wash">
    <!-- ===== 工具栏 ===== -->
    <section class="toolbar glass-card">
      <div class="filter-group neu-inset">
        <button
          v-for="opt in mediaOptions"
          :key="opt.value"
          type="button"
          class="filter-btn"
          :class="{ active: mediaType === opt.value }"
          @click="mediaType = opt.value"
        >{{ opt.label }}</button>
      </div>
      <div class="action-btns">
        <button
          type="button"
          class="btn btn-primary"
          :disabled="analyzing || deleting"
          @click="runAnalyze"
        >
          <span v-if="analyzing" class="spinner light"></span>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>
          </svg>
          {{ analyzing ? '分析中…' : '开始分析' }}
        </button>
        <button
          type="button"
          class="btn btn-danger"
          :disabled="analyzing || deleting || selectedCount === 0"
          @click="confirmDelete"
        >
          <span v-if="deleting" class="spinner light"></span>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>
            <path d="M10 11v6"/><path d="M14 11v6"/>
          </svg>
          删除选中{{ selectedCount ? ` (${selectedCount})` : '' }}
        </button>
      </div>
    </section>

    <!-- ===== 统计卡片 ===== -->
    <section v-if="summary" class="stats-grid">
      <div class="stat-card glass-card s-groups">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/>
            <rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>
          </svg>
        </div>
        <div class="stat-body">
          <span class="stat-num">{{ summary.groups }}</span>
          <span class="stat-label">重复作品组</span>
        </div>
      </div>
      <div class="stat-card glass-card s-drop">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>
          </svg>
        </div>
        <div class="stat-body">
          <span class="stat-num">{{ summary.deletable_sources }}</span>
          <span class="stat-label">建议删除</span>
        </div>
      </div>
      <div class="stat-card glass-card s-keep">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 6L9 17l-5-5"/>
          </svg>
        </div>
        <div class="stat-body">
          <span class="stat-num">{{ summary.keep_sources }}</span>
          <span class="stat-label">建议保留</span>
        </div>
      </div>
      <div class="stat-card glass-card s-scan">
        <div class="stat-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>
          </svg>
        </div>
        <div class="stat-body">
          <span class="stat-num">{{ summary.sources_scanned }}</span>
          <span class="stat-label">已扫描分享</span>
        </div>
      </div>
    </section>

    <!-- ===== 加载中 ===== -->
    <section v-if="analyzing && !hasReport" class="state-panel glass-card">
      <div class="state-visual loading">
        <div class="orbit">
          <span></span><span></span><span></span>
        </div>
      </div>
      <h2 class="state-title">正在分析分享库</h2>
      <p class="state-desc">{{ analyzeMessage || '按作品归并版本，计算画质分与完整度加成…' }}</p>
      <div class="progress-wrap" v-if="analyzePercent > 0">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: analyzePercent + '%' }"></div>
        </div>
        <span class="progress-text">{{ analyzePercent }}%</span>
      </div>
      <div class="loading-steps">
        <div class="ls-item" :class="{ active: analyzeStageRank >= 1 }"><span class="ls-dot"></span>扫描已整理分享</div>
        <div class="ls-item" :class="{ active: analyzeStageRank >= 2 }"><span class="ls-dot"></span>归并重复作品</div>
        <div class="ls-item" :class="{ active: analyzeStageRank >= 3 }"><span class="ls-dot"></span>评分与排序</div>
      </div>
    </section>

    <!-- ===== 初始空态 ===== -->
    <section v-else-if="!hasReport" class="state-panel glass-card">
      <div class="state-visual idle">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M12 3l1.8 5.5H20l-4.6 3.4 1.8 5.5L12 14.9 6.8 17.4l1.8-5.5L4 8.5h6.2L12 3z"/>
        </svg>
      </div>
      <h2 class="state-title">清理重复分享版本</h2>
      <p class="state-desc">
        同一作品若存在多条分享链接，将按质量标签、发布组与完整度打分，只保留最优那一条。
      </p>
      <div class="guide-cards">
        <div class="guide-card">
          <div class="guide-num">01</div>
          <div class="guide-text">
            <strong>筛选范围</strong>
            <span>可按电影 / 剧集过滤</span>
          </div>
        </div>
        <div class="guide-card">
          <div class="guide-num">02</div>
          <div class="guide-text">
            <strong>开始分析</strong>
            <span>自动找出重复版本组</span>
          </div>
        </div>
        <div class="guide-card">
          <div class="guide-num">03</div>
          <div class="guide-text">
            <strong>勾选删除</strong>
            <span>默认只选中劣质版本</span>
          </div>
        </div>
      </div>
      <p class="state-tip">点击上方「开始分析」即可扫描分享库</p>
    </section>

    <!-- ===== 无重复 ===== -->
    <section v-else-if="groups.length === 0" class="state-panel glass-card">
      <div class="state-visual ok">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <path d="M20 6L9 17l-5-5"/>
        </svg>
      </div>
      <h2 class="state-title">未发现重复分享</h2>
      <p class="state-desc">当前范围内，没有同一作品对应多条已整理分享。库很干净！</p>
      <button type="button" class="btn btn-ghost" :disabled="analyzing" @click="runAnalyze">
        重新分析
      </button>
    </section>

    <!-- ===== 结果列表 ===== -->
    <section v-else class="result-list">
      <div class="result-head">
        <div class="result-head-left">
          <h2>分析结果</h2>
          <span class="result-badge">{{ groups.length }} 组重复</span>
        </div>
        <p class="result-tip">金色标记为建议保留 · 点击劣质版本可勾选删除</p>
      </div>

      <article
        v-for="group in groups"
        :key="group.key"
        class="group glass-card"
      >
        <header class="group-header">
          <div class="group-left">
            <div class="type-badge" :class="group.media_type">
              <svg v-if="group.media_type === 'tv'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="7" width="20" height="15" rx="2"/><path d="M17 2l-5 5-5-5"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="2" width="20" height="20" rx="2.5"/><circle cx="12" cy="12" r="3.5"/>
              </svg>
              {{ group.media_type === 'tv' ? '剧集' : '电影' }}
            </div>
            <div class="group-title-block">
              <h3>
                {{ group.title || '未知标题' }}
                <span v-if="group.year" class="year">{{ group.year }}</span>
              </h3>
              <div class="group-meta">
                <span class="meta-pill">TMDB {{ group.tmdb_id }}</span>
                <span v-if="group.season != null" class="meta-pill season">
                  S{{ String(group.season).padStart(2, '0') }}
                </span>
                <span class="meta-pill count">{{ group.count }} 个版本</span>
              </div>
            </div>
          </div>
          <button type="button" class="btn-select-all" @click="selectAllInferior(group)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
            </svg>
            全选劣质
          </button>
        </header>

        <div class="version-list">
          <div
            v-for="(item, idx) in group.items"
            :key="item.source_id"
            class="version"
            :class="{ keep: item.keep, selected: item.selected, drop: !item.keep }"
            @click="toggleItem(item)"
          >
            <div class="rank" :class="'r' + Math.min(idx + 1, 4)">
              <template v-if="idx === 0">
                <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.2H22l-6 4.4 2.3 7.1L12 16.5 5.7 20.7 8 13.6 2 9.2h7.6z"/></svg>
              </template>
              <template v-else>{{ idx + 1 }}</template>
            </div>

            <label class="checkbox" @click.stop>
              <input
                type="checkbox"
                v-model="item.selected"
                :disabled="item.keep && !allowDeleteKeep"
              />
              <span class="box"></span>
            </label>

            <div class="version-body">
              <div class="row-main">
                <div class="name-wrap">
                  <div class="name">
                    {{ item.share_name || item.share_code || ('分享 #' + item.source_id) }}
                  </div>
                  <div class="flag-row">
                    <span v-if="item.keep" class="flag keep">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
                      建议保留
                    </span>
                    <span v-else class="flag drop">可清理</span>
                    <span v-if="item.multi_title" class="flag warn">多作品源</span>
                    <span v-if="item.link_valid === 0" class="flag warn">链接失效</span>
                    <span v-if="item.release_group" class="flag group">{{ item.release_group }}</span>
                  </div>
                </div>

                <div class="score-ring" :class="levelClass(item.score)">
                  <div class="score-val">{{ item.score }}</div>
                  <div class="score-lv">{{ item.quality_level || '-' }}</div>
                </div>
              </div>

              <div class="meta-row">
                <span class="meta-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h10M4 17h7"/></svg>
                  画质 {{ item.quality_score }}
                </span>
                <span class="meta-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16v12H4z"/><path d="M8 6V4h8v2"/></svg>
                  {{ formatSize(item.total_size) }}
                </span>
                <span class="meta-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9l5 3-5 3z"/></svg>
                  视频 {{ item.episode_count }}
                </span>
                <span
                  v-if="item.media_type === 'tv'"
                  class="meta-item"
                >
                  完整度 {{ Math.round((item.completeness_ratio || 0) * 100) }}%
                  <em>(+{{ item.completeness_bonus || 0 }})</em>
                </span>
                <span class="meta-item mono">#{{ item.source_id }}</span>
              </div>

              <div
                v-if="item.media_type === 'tv'"
                class="progress"
                :title="'完整度 ' + Math.round((item.completeness_ratio || 0) * 100) + '%'"
              >
                <div
                  class="bar"
                  :style="{ width: Math.round((item.completeness_ratio || 0) * 100) + '%' }"
                ></div>
              </div>

              <div v-if="displayTags(item).length" class="tags">
                <span
                  v-for="t in displayTags(item)"
                  :key="t"
                  class="tag"
                  :class="tagClass(t)"
                >{{ t }}</span>
              </div>

              <div v-if="item.share_url" class="url-line" @click.stop>
                <svg class="link-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M10 13a5 5 0 0 0 7.07 0l1.41-1.41a5 5 0 0 0-7.07-7.07L10 5.9"/>
                  <path d="M14 11a5 5 0 0 0-7.07 0L5.5 12.4a5 5 0 0 0 7.07 7.07L14 18.1"/>
                </svg>
                <a :href="item.share_url" target="_blank" rel="noopener">{{ item.share_url }}</a>
                <button type="button" class="copy" @click="copyText(item.share_url)">复制</button>
              </div>
            </div>
          </div>
        </div>
      </article>
    </section>

    <!-- ===== 底部浮动栏 ===== -->
    <transition name="rise">
      <div v-if="selectedCount > 0" class="float-bar glass-solid">
        <div class="float-left">
          <div class="float-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>
            </svg>
          </div>
          <div class="float-text">
            <span class="float-title">已选 <b>{{ selectedCount }}</b> 条分享</span>
            <span class="float-sub">删除后不可恢复，最优版本默认不会被选中</span>
          </div>
        </div>
        <div class="float-actions">
          <button type="button" class="btn btn-ghost" @click="clearAllSelection">清空</button>
          <button type="button" class="btn btn-danger" :disabled="deleting" @click="confirmDelete">
            <span v-if="deleting" class="spinner light"></span>
            删除选中
          </button>
        </div>
      </div>
    </transition>

    <!-- ===== 确认弹窗 ===== -->
    <div v-if="showConfirm" class="glass-overlay" @click.self="showConfirm = false">
      <div class="modal glass-solid">
        <div class="modal-icon danger">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.3L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.3a2 2 0 0 0-3.4 0z"/>
          </svg>
        </div>
        <h3>确认删除劣质分享？</h3>
        <p>
          将删除 <b>{{ selectedCount }}</b> 条分享及其本地目录索引，此操作不可恢复。
          最优版本默认不会被选中。
        </p>
        <div class="modal-actions">
          <button type="button" class="btn btn-ghost" :disabled="deleting" @click="showConfirm = false">取消</button>
          <button type="button" class="btn btn-danger" :disabled="deleting" @click="doDelete">
            <span v-if="deleting" class="spinner light"></span>
            {{ deleting ? '删除中…' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { shareWashApi, type WashAnalyzeResult, type WashGroup, type WashSourceItem } from '@/api/shareWash'
import { formatSize } from '@/composables/useFormat'
import { showToast } from '@/composables/useToast'

const mediaType = ref<'all' | 'movie' | 'tv'>('all')
const analyzing = ref(false)
const analyzePercent = ref(0)
const analyzeMessage = ref('')
const analyzeStage = ref('')
let analyzeEventSource: EventSource | null = null
const deleting = ref(false)
const summary = ref<WashAnalyzeResult['summary'] | null>(null)
const groups = ref<WashGroup[]>([])
const hasReport = ref(false)
const showConfirm = ref(false)
const allowDeleteKeep = false

const mediaOptions = [
  { value: 'all' as const, label: '全部' },
  { value: 'movie' as const, label: '电影' },
  { value: 'tv' as const, label: '剧集' },
]

const selectedCount = computed(() =>
  groups.value.reduce((n, g) => n + g.items.filter(i => i.selected).length, 0)
)

const analyzeStageRank = computed(() => {
  const s = analyzeStage.value
  if (['score', 'rank', 'finish', 'done'].includes(s)) return 3
  if (['load', 'meta'].includes(s)) return 2
  if (['start', 'scan', 'done_prep'].includes(s)) return 1
  return analyzePercent.value > 0 ? 1 : 0
})

function closeAnalyzeStream() {
  if (analyzeEventSource) {
    analyzeEventSource.close()
    analyzeEventSource = null
  }
}


function levelClass(score: number) {
  if (score >= 4000) return 'lv-best'
  if (score >= 3000) return 'lv-good'
  if (score >= 2000) return 'lv-mid'
  return 'lv-bad'
}

function displayTags(item: WashSourceItem) {
  return (item.tags || []).filter(x => x && x !== item.release_group)
}

function tagClass(t: string) {
  const u = t.toUpperCase()
  if (/(2160P|4320P|4K|UHD)/.test(u)) return 'hi'
  if (/(1080P|1440P)/.test(u)) return 'mid'
  if (/(REMUX|DOLBY|HDR|DV|ATMOS|IMAX)/.test(u)) return 'premium'
  return ''
}

function selectAllInferior(group: WashGroup) {
  group.items.forEach((it, idx) => { it.selected = idx !== 0 })
}

function clearAllSelection() {
  groups.value.forEach(g => g.items.forEach(it => { it.selected = false }))
}

function toggleItem(item: WashSourceItem) {
  if (item.keep && !allowDeleteKeep) return
  item.selected = !item.selected
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    showToast('链接已复制', 'success')
  } catch {
    showToast('复制失败', 'error')
  }
}

function runAnalyze() {
  if (analyzing.value) return
  closeAnalyzeStream()
  analyzing.value = true
  analyzePercent.value = 0
  analyzeMessage.value = '连接分析服务…'
  analyzeStage.value = 'start'

  const es = shareWashApi.analyzeStream(mediaType.value)
  analyzeEventSource = es

  es.onmessage = (event) => {
    let data: any
    try {
      data = JSON.parse(event.data)
    } catch {
      return
    }
    const t = data?.type
    if (t === 'start') {
      analyzeMessage.value = '开始扫描…'
      analyzePercent.value = 1
      return
    }
    if (t === 'progress') {
      analyzeStage.value = data.stage || ''
      if (typeof data.percent === 'number') analyzePercent.value = data.percent
      if (data.message) analyzeMessage.value = data.message
      return
    }
    if (t === 'done') {
      summary.value = data.summary || null
      groups.value = data.groups || []
      hasReport.value = true
      analyzePercent.value = 100
      analyzeStage.value = 'done'
      analyzing.value = false
      showToast(data.message || '分析完成', 'success')
      closeAnalyzeStream()
      return
    }
    if (t === 'error') {
      analyzing.value = false
      showToast(data.message || '分析失败', 'error')
      closeAnalyzeStream()
    }
  }

  es.onerror = () => {
    // 正常结束关闭连接时浏览器也可能触发 error，已完成则忽略
    if (!analyzing.value) {
      closeAnalyzeStream()
      return
    }
    if (es.readyState === EventSource.CLOSED) {
      analyzing.value = false
      showToast('分析连接中断（网关或网络），请重试', 'error')
      closeAnalyzeStream()
    }
  }
}

onUnmounted(() => {
  closeAnalyzeStream()
})

function confirmDelete() {
  if (selectedCount.value === 0) return
  showConfirm.value = true
}

async function doDelete() {
  const ids = groups.value.flatMap(g => g.items.filter(i => i.selected).map(i => i.source_id))
  if (!ids.length) return
  deleting.value = true
  try {
    const res = await shareWashApi.deleteSources(ids)
    if (res.code !== 0) {
      showToast(res.message || '删除失败', 'error')
      return
    }
    showToast(res.message || '删除完成', 'success')
    showConfirm.value = false
    runAnalyze()
  } catch (e: any) {
    showToast(e?.message || '删除失败', 'error')
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped>
.share-wash {
  display: flex;
  flex-direction: column;
  gap: 16px;
  font-family: var(--font-sans);
  padding-bottom: 88px;
  min-height: 100%;
}

/* ========== Toolbar ========== */
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
}
.filter-group {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  border-radius: var(--radius-sm);
  width: fit-content;
}
.filter-btn {
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  padding: 7px 16px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-base);
}
.filter-btn:hover { color: var(--text-secondary); }
.filter-btn.active {
  background: var(--bg-solid);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}
.action-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* ========== Buttons ========== */
.btn {
  border: none;
  border-radius: 10px;
  padding: 9px 16px;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  transition: all var(--transition-base);
  white-space: nowrap;
}
.btn svg { width: 15px; height: 15px; flex-shrink: 0; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary {
  background: linear-gradient(180deg, var(--accent-hover), var(--accent));
  color: #fff;
  box-shadow: 0 6px 16px rgba(0, 113, 227, 0.28);
}
.btn-primary:hover:not(:disabled) {
  filter: brightness(1.05);
  transform: translateY(-1px);
}
.btn-danger {
  background: linear-gradient(180deg, #ff6259, var(--danger));
  color: #fff;
  box-shadow: 0 6px 16px rgba(255, 59, 48, 0.24);
}
.btn-danger:hover:not(:disabled) {
  filter: brightness(1.05);
  transform: translateY(-1px);
}
.btn-ghost {
  background: var(--bg-input);
  color: var(--text-secondary);
  border: 1px solid var(--border);
}
.btn-ghost:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.btn-lg {
  padding: 12px 22px;
  font-size: 14px;
  border-radius: 12px;
  margin-top: 4px;
}
.btn-select-all {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  background: var(--bg-solid);
  color: var(--accent);
  font-size: 12px;
  font-weight: 650;
  cursor: pointer;
  padding: 7px 12px;
  border-radius: 999px;
  flex-shrink: 0;
  transition: all var(--transition-base);
}
.btn-select-all svg { width: 14px; height: 14px; }
.btn-select-all:hover {
  background: var(--accent-bg);
  border-color: transparent;
  box-shadow: var(--shadow-sm);
}

/* ========== Stats grid ========== */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.stat-card {
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-lg);
  min-height: 76px;
}
.stat-card::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  border-radius: 3px 0 0 3px;
}
.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.stat-icon svg { width: 18px; height: 18px; }
.stat-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.stat-num {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.5px;
  line-height: 1.1;
  color: var(--text-primary);
}
.stat-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
}
.s-groups::before { background: var(--accent); }
.s-groups .stat-icon { background: var(--accent-bg); color: var(--accent); }
.s-groups .stat-num { color: var(--accent); }
.s-drop::before { background: var(--danger); }
.s-drop .stat-icon { background: var(--danger-bg); color: var(--danger); }
.s-drop .stat-num { color: var(--danger); }
.s-keep::before { background: var(--success); }
.s-keep .stat-icon { background: var(--success-bg); color: var(--success); }
.s-keep .stat-num { color: var(--success); }
.s-scan::before { background: var(--purple); }
.s-scan .stat-icon { background: var(--purple-bg); color: var(--purple); }
.s-scan .stat-num { color: var(--purple); }

/* ========== Empty / loading states ========== */
.state-panel {
  border-radius: var(--radius-xl);
  padding: 48px 28px 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 12px;
}
.state-visual {
  width: 72px;
  height: 72px;
  border-radius: 22px;
  display: grid;
  place-items: center;
  margin-bottom: 4px;
}
.state-visual svg { width: 34px; height: 34px; }
.state-visual.idle {
  color: #fff;
  background: linear-gradient(145deg, #0a84ff, #bf5af2);
  box-shadow: 0 12px 28px rgba(10, 132, 255, 0.25);
}
.state-visual.ok {
  background: var(--success-bg);
  color: var(--success);
}
.state-visual.loading {
  background: var(--accent-bg);
  color: var(--accent);
  position: relative;
}
.orbit {
  position: relative;
  width: 36px;
  height: 36px;
}
.orbit span {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2.5px solid transparent;
  border-top-color: var(--accent);
  animation: spin 0.9s linear infinite;
}
.orbit span:nth-child(2) {
  inset: 5px;
  border-top-color: var(--purple);
  animation-duration: 1.2s;
  animation-direction: reverse;
}
.orbit span:nth-child(3) {
  inset: 10px;
  border-top-color: var(--success);
  animation-duration: 0.7s;
}
.state-title {
  margin: 0;
  font-size: 18px;
  font-weight: 750;
  color: var(--text-primary);
  letter-spacing: -0.2px;
}
.state-tip {
  margin: 10px 0 0;
  font-size: 12px;
  font-weight: 650;
  color: var(--accent);
}
.state-desc {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.65;
  max-width: 440px;
}
.loading-steps {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px 18px;
  margin-top: 8px;
}
.ls-item {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
}
.ls-item.active { color: var(--accent); }
.ls-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.55;
}
.ls-item.active .ls-dot {
  opacity: 1;
  box-shadow: 0 0 0 3px var(--accent-bg);
  animation: pulse 1.2s ease infinite;
}
.guide-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  width: min(560px, 100%);
  margin: 8px 0 4px;
  text-align: left;
}
.guide-card {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 12px;
  border-radius: var(--radius-md);
  background: var(--bg-input);
  border: 1px solid var(--border);
}
.guide-num {
  font-size: 13px;
  font-weight: 800;
  color: var(--accent);
  letter-spacing: -0.3px;
  line-height: 1.2;
}
.guide-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.guide-text strong {
  font-size: 12px;
  color: var(--text-primary);
}
.guide-text span {
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

/* ========== Results ========== */
.result-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.result-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 8px;
  padding: 0 2px;
}
.result-head-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.result-head h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 750;
  color: var(--text-primary);
}
.result-badge {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  background: var(--accent-bg);
  padding: 3px 9px;
  border-radius: 999px;
}
.result-tip {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}
.group {
  border-radius: var(--radius-xl);
  overflow: hidden;
  padding: 0;
  box-shadow: var(--shadow-md);
}
.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  background:
    linear-gradient(135deg, rgba(0, 113, 227, 0.06), transparent 42%),
    linear-gradient(180deg, rgba(127, 127, 127, 0.04), transparent);
}
.group-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.type-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 750;
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--accent-bg);
  color: var(--accent);
  flex-shrink: 0;
}
.type-badge svg { width: 13px; height: 13px; }
.type-badge.tv {
  background: var(--purple-bg);
  color: var(--purple);
}
.group-title-block { min-width: 0; }
.group-title-block h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 750;
  color: var(--text-primary);
  letter-spacing: -0.25px;
  word-break: break-word;
}
.year {
  font-weight: 550;
  color: var(--text-tertiary);
  font-size: 13px;
  margin-left: 6px;
}
.group-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.meta-pill {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  background: var(--bg-input);
  border: 1px solid var(--border);
  padding: 2px 8px;
  border-radius: 999px;
}
.meta-pill.season {
  color: var(--purple);
  background: var(--purple-bg);
  border-color: transparent;
}
.meta-pill.count {
  color: var(--accent);
  background: var(--accent-bg);
  border-color: transparent;
}

/* Version cards */
.version-list {
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.version {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all var(--transition-base);
  background: var(--bg-input);
  position: relative;
}
.version:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
.version.keep {
  background:
    linear-gradient(90deg, rgba(52, 199, 89, 0.14), transparent 56px),
    var(--bg-input);
  border-color: rgba(52, 199, 89, 0.28);
  box-shadow: inset 0 0 0 1px rgba(52, 199, 89, 0.06);
}
.version.drop {
  background:
    linear-gradient(90deg, rgba(255, 59, 48, 0.05), transparent 48px),
    var(--bg-input);
}
.version.selected:not(.keep) {
  background:
    linear-gradient(90deg, rgba(255, 59, 48, 0.16), transparent 56px),
    var(--bg-input);
  border-color: rgba(255, 59, 48, 0.32);
  box-shadow: 0 0 0 1px rgba(255, 59, 48, 0.08);
}
.rank {
  width: 30px;
  height: 30px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 800;
  flex-shrink: 0;
  margin-top: 2px;
  background: var(--bg-solid);
  color: var(--text-tertiary);
  border: 1px solid var(--border);
}
.rank svg { width: 15px; height: 15px; }
.rank.r1 {
  background: linear-gradient(145deg, #ffd60a, #ff9f0a);
  color: #1d1d1f;
  border-color: transparent;
  box-shadow: 0 4px 12px rgba(255, 159, 10, 0.35);
}
.rank.r2 {
  background: linear-gradient(145deg, #e8e8ed, #c7c7cc);
  color: #1d1d1f;
  border-color: transparent;
}
.rank.r3 {
  background: linear-gradient(145deg, #e0a070, #c9825a);
  color: #fff;
  border-color: transparent;
}
.checkbox {
  position: relative;
  width: 18px;
  height: 18px;
  margin-top: 7px;
  flex-shrink: 0;
  cursor: pointer;
}
.checkbox input {
  position: absolute;
  opacity: 0;
  inset: 0;
  margin: 0;
  cursor: pointer;
}
.box {
  width: 18px;
  height: 18px;
  border-radius: 6px;
  border: 1.5px solid var(--border-strong);
  background: var(--bg-solid);
  display: block;
  transition: all var(--transition-base);
}
.checkbox input:checked + .box {
  background: var(--danger);
  border-color: var(--danger);
  box-shadow: inset 0 0 0 2px #fff;
}
.checkbox input:disabled + .box {
  opacity: 0.4;
  cursor: not-allowed;
}
.version-body { flex: 1; min-width: 0; }
.row-main {
  display: flex;
  gap: 12px;
  justify-content: space-between;
  align-items: flex-start;
}
.name-wrap { min-width: 0; flex: 1; }
.name {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.45;
  word-break: break-all;
}
.flag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.flag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 750;
  padding: 3px 8px;
  border-radius: 999px;
}
.flag svg { width: 11px; height: 11px; }
.flag.keep { background: var(--success-bg); color: var(--success); }
.flag.drop { background: var(--danger-bg); color: var(--danger); }
.flag.warn { background: var(--warning-bg); color: var(--warning); }
.flag.group { background: var(--purple-bg); color: var(--purple); }
.score-ring {
  text-align: center;
  flex-shrink: 0;
  min-width: 68px;
  padding: 8px 10px;
  border-radius: 14px;
  border: 1px solid transparent;
}
.score-val {
  font-size: 20px;
  font-weight: 850;
  letter-spacing: -0.5px;
  line-height: 1.05;
}
.score-lv {
  font-size: 11px;
  font-weight: 700;
  margin-top: 3px;
  opacity: 0.92;
}
.lv-best {
  background: linear-gradient(180deg, rgba(52, 199, 89, 0.18), rgba(52, 199, 89, 0.08));
  color: var(--success);
  border-color: rgba(52, 199, 89, 0.2);
}
.lv-good {
  background: linear-gradient(180deg, rgba(0, 113, 227, 0.16), rgba(0, 113, 227, 0.07));
  color: var(--accent);
  border-color: rgba(0, 113, 227, 0.18);
}
.lv-mid {
  background: linear-gradient(180deg, rgba(255, 149, 0, 0.16), rgba(255, 149, 0, 0.07));
  color: var(--warning);
  border-color: rgba(255, 149, 0, 0.18);
}
.lv-bad {
  background: linear-gradient(180deg, rgba(255, 59, 48, 0.14), rgba(255, 59, 48, 0.06));
  color: var(--danger);
  border-color: rgba(255, 59, 48, 0.16);
}
.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-top: 10px;
  font-size: 11.5px;
  color: var(--text-secondary);
}
.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.meta-item svg {
  width: 12px;
  height: 12px;
  opacity: 0.7;
}
.meta-item em {
  font-style: normal;
  color: var(--purple);
  font-weight: 700;
  margin-left: 2px;
}
.meta-item.mono {
  font-family: var(--font-mono);
  color: var(--text-tertiary);
}
.progress {
  margin-top: 10px;
  height: 6px;
  border-radius: 999px;
  background: rgba(127, 127, 127, 0.12);
  overflow: hidden;
}
.progress .bar {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--purple), var(--accent), #30d158);
  box-shadow: 0 0 8px rgba(10, 132, 255, 0.35);
  transition: width 0.35s ease;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.tag {
  font-size: 11px;
  font-weight: 650;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--bg-solid);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}
.tag.hi {
  background: linear-gradient(180deg, rgba(255, 149, 0, 0.18), rgba(255, 149, 0, 0.08));
  color: var(--warning);
  border-color: transparent;
  font-weight: 750;
}
.tag.mid {
  background: var(--accent-bg);
  color: var(--accent);
  border-color: transparent;
}
.tag.premium {
  background: linear-gradient(180deg, rgba(52, 199, 89, 0.16), rgba(52, 199, 89, 0.08));
  color: var(--success);
  border-color: transparent;
  font-weight: 750;
}
.url-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  min-width: 0;
  padding: 7px 10px;
  border-radius: 10px;
  background: var(--bg-solid);
  border: 1px solid var(--border);
}
.link-ico {
  width: 13px;
  height: 13px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}
.url-line a {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  color: var(--text-tertiary);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.url-line a:hover { color: var(--accent); }
.copy {
  border: 1px solid var(--border);
  background: var(--bg-input);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 650;
  padding: 3px 9px;
  border-radius: 7px;
  cursor: pointer;
  flex-shrink: 0;
  transition: all var(--transition-base);
}
.copy:hover {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-bg);
}

/* ========== Float bar ========== */
.float-bar {
  position: sticky;
  bottom: 12px;
  z-index: 20;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  border-radius: 18px;
  box-shadow: var(--shadow-lg), 0 0 0 1px var(--border);
}
.float-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.float-icon {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: var(--danger-bg);
  color: var(--danger);
  flex-shrink: 0;
}
.float-icon svg { width: 18px; height: 18px; }
.float-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.float-title {
  font-size: 13px;
  font-weight: 650;
  color: var(--text-primary);
}
.float-title b {
  color: var(--danger);
  font-size: 16px;
  margin: 0 2px;
}
.float-sub {
  font-size: 11px;
  color: var(--text-tertiary);
}
.float-actions { display: flex; gap: 8px; flex-shrink: 0; }

/* ========== Modal ========== */
.modal {
  width: min(420px, 100%);
  border-radius: 20px;
  padding: 24px;
  text-align: center;
}
.modal-icon {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  margin: 0 auto 14px;
}
.modal-icon.danger {
  background: var(--danger-bg);
  color: var(--danger);
}
.modal-icon svg { width: 26px; height: 26px; }
.modal h3 {
  margin: 0 0 8px;
  font-size: 17px;
  font-weight: 750;
  color: var(--text-primary);
}
.modal p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.65;
}
.modal p b { color: var(--danger); font-size: 15px; }
.modal-actions {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-top: 20px;
}

/* ========== Utils ========== */
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.spinner.light {
  border-color: rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
}
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}
.rise-enter-active,
.rise-leave-active { transition: all 0.24s ease; }
.rise-enter-from,
.rise-leave-to { opacity: 0; transform: translateY(14px); }

/* ========== Responsive ========== */
@media (max-width: 900px) {
  .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 768px) {
  .toolbar { flex-direction: column; align-items: stretch; }
  .action-btns { width: 100%; }
  .action-btns .btn { flex: 1; }
  .guide-cards { grid-template-columns: 1fr; }
  .group-header { flex-direction: column; align-items: flex-start; }
  .row-main { flex-direction: column; }
  .score-ring { align-self: flex-start; text-align: left; min-width: 90px; }
  .float-bar {
    border-radius: 14px;
    flex-direction: column;
    align-items: stretch;
  }
  .float-actions .btn { flex: 1; }
}
@media (max-width: 480px) {
  .stats-grid { grid-template-columns: 1fr 1fr; gap: 8px; }
  .stat-card { padding: 12px; min-height: 68px; }
  .stat-num { font-size: 18px; }
}

.progress-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  width: min(360px, 90%);
  margin: 8px auto 4px;
}
.progress-bar {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.08);
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #3b82f6, #8b5cf6);
  transition: width 0.25s ease;
}
.progress-text {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary, #64748b);
  min-width: 36px;
  text-align: right;
}
</style>
