<template>
  <div class="files">
    <!-- 面包屑导航 -->
    <div class="breadcrumb-bar glass-card">
      <button v-if="breadcrumbs.length > 1" class="btn-back neu-circle" @click="goBack" title="返回上级">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="15 18 9 12 15 6" />
        </svg>
      </button>
      <nav class="breadcrumbs">
        <span
          v-for="(crumb, index) in breadcrumbs"
          :key="crumb.id"
          class="crumb"
          :class="{ active: index === breadcrumbs.length - 1 }"
          @click="navigateTo(crumb.id)"
        >
          {{ crumb.name }}
          <span v-if="index < breadcrumbs.length - 1" class="crumb-sep">/</span>
        </span>
      </nav>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar glass-card">
      <template v-if="selectedIds.size === 0">
        <button class="toolbar-btn" @click="loadFiles()" :disabled="loading">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
          <span>刷新</span>
        </button>
        <button class="toolbar-btn" @click="showMkdir = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          <span>新建文件夹</span>
        </button>
        <button class="toolbar-btn" @click="batchRecognize" :disabled="selectedIds.size === 0">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <span>识别</span>
        </button>
        <div class="toolbar-spacer"></div>
        <div class="search-box neu-inset">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            v-model="searchKeyword"
            type="text"
            placeholder="搜索文件..."
            @keyup.enter="handleSearch"
          />
          <button v-if="searchKeyword" class="search-clear" @click="clearSearch">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </template>

      <template v-else>
        <div class="toolbar-selection">
          <span class="selected-badge">{{ selectedIds.size }}</span>
          <span class="selected-label">已选</span>
        </div>
        <div class="toolbar-divider"></div>
        <button class="toolbar-btn" @click="batchMove">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 12h14" />
            <path d="M12 5l7 7-7 7" />
          </svg>
          <span>移动</span>
        </button>
        <button class="toolbar-btn" @click="batchCopy">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
          <span>复制</span>
        </button>
        <button class="toolbar-btn danger" @click="batchDelete">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
          </svg>
          <span>删除</span>
        </button>
        <button class="toolbar-btn ghost" @click="clearSelection">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
          <span>取消</span>
        </button>
      </template>
    </div>

    <!-- 文件列表 -->
    <div class="file-list-container glass-card">
      <div v-if="loading" class="loading-state">
        <div class="loading-spinner"></div>
        <p>加载中...</p>
      </div>

      <div v-else-if="items.length === 0" class="empty-state">
        <div class="empty-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          </svg>
        </div>
        <p class="empty-title">此目录为空</p>
        <p class="empty-desc">没有文件或文件夹</p>
      </div>

      <div v-else class="file-table">
        <!-- 表头 -->
        <div class="table-header">
          <div class="col-check">
            <label class="checkbox-wrapper" @click.prevent="toggleSelectAll">
              <input type="checkbox" :checked="isAllSelected" :indeterminate="isPartialSelected" />
              <span class="checkbox-custom"></span>
            </label>
          </div>
          <div class="col-name sortable" @click="toggleSort('file_name')">
            名称
            <svg v-if="sortOrder === 'file_name' && sortAsc === 1" class="sort-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M7 14l5-5 5 5z"/></svg>
            <svg v-else-if="sortOrder === 'file_name' && sortAsc === 0" class="sort-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
          </div>
          <div class="col-size sortable" @click="toggleSort('file_size')">
            大小
            <svg v-if="sortOrder === 'file_size' && sortAsc === 1" class="sort-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M7 14l5-5 5 5z"/></svg>
            <svg v-else-if="sortOrder === 'file_size' && sortAsc === 0" class="sort-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
          </div>
          <div class="col-time sortable" @click="toggleSort('user_ptime')">
            修改时间
            <svg v-if="sortOrder === 'user_ptime' && sortAsc === 1" class="sort-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M7 14l5-5 5 5z"/></svg>
            <svg v-else-if="sortOrder === 'user_ptime' && sortAsc === 0" class="sort-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
          </div>
          <div class="col-action"></div>
        </div>

        <!-- 文件行 -->
        <div class="table-body">
          <div
            v-for="item in items"
            :key="item.file_id"
            class="table-row"
            :class="{ selected: selectedIds.has(item.file_id) }"
            @click="handleClick(item, $event)"
          >
            <div class="col-check">
              <label class="checkbox-wrapper" @click.prevent.stop="toggleSelect(item.file_id)">
                <input type="checkbox" :checked="selectedIds.has(item.file_id)" />
                <span class="checkbox-custom"></span>
              </label>
            </div>
            <div class="col-name">
              <div class="file-icon">
                <svg v-if="item.is_dir" viewBox="0 0 24 24" fill="currentColor" class="icon-folder">
                  <path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z" />
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="icon-file">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
              </div>
              <span class="file-name">{{ item.name }}</span>
            </div>
            <div class="col-size">
              <span v-if="!item.is_dir" class="file-size">{{ formatSize(item.size) }}</span>
            </div>
            <div class="col-time">
              <span class="file-time">{{ formatTime(item.updated_at) }}</span>
            </div>
            <div class="col-action">
              <button class="btn-more neu-circle" @click.stop="openMenu($event, item)" title="更多操作">
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="5" r="1.5" />
                  <circle cx="12" cy="12" r="1.5" />
                  <circle cx="12" cy="19" r="1.5" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <!-- 分页器 -->
        <div v-if="totalPages > 1" class="pagination">
          <button class="page-btn" :disabled="currentPage <= 1" @click="goToPage(currentPage - 1)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <template v-for="p in pageNumbers" :key="p">
            <span v-if="p === -1" class="page-ellipsis">...</span>
            <button v-else class="page-btn" :class="{ active: p === currentPage }" @click="goToPage(p)">
              {{ p }}
            </button>
          </template>
          <button class="page-btn" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 右键菜单 -->
    <div v-if="menuVisible" class="context-menu-overlay" @click="closeMenu">
      <div class="context-menu glass-solid" :style="menuStyle">
        <button class="menu-option" @click="startMove">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 12h14" />
            <path d="M12 5l7 7-7 7" />
          </svg>
          移动到...
        </button>
        <button class="menu-option" @click="startCopy">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
          复制到...
        </button>
        <div class="menu-divider"></div>
        <button class="menu-option" @click="startRecognize">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          识别
        </button>
        <button class="menu-option" @click="startRename">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
          </svg>
          重命名
        </button>
        <button class="menu-option danger" @click="confirmDelete">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6" />
            <path d="M14 11v6" />
            <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
          </svg>
          删除
        </button>
      </div>
    </div>

    <!-- 目录选择器弹窗 -->
    <div v-if="showPicker" class="glass-overlay" @click.self="cancelPicker">
      <div class="modal-card picker-modal">
        <div class="modal-header">
          <h3>{{ pickerMode === 'move' ? '移动到' : '复制到' }}</h3>
          <button class="btn-close neu-circle" @click="cancelPicker">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div class="picker-breadcrumb">
          <span
            v-for="(crumb, index) in pickerBreadcrumbs"
            :key="crumb.id"
            class="crumb"
            :class="{ active: index === pickerBreadcrumbs.length - 1 }"
            @click="pickerNavigateTo(crumb.id)"
          >
            {{ crumb.name }}
            <span v-if="index < pickerBreadcrumbs.length - 1" class="crumb-sep">/</span>
          </span>
        </div>

        <div class="picker-body">
          <div v-if="pickerLoading" class="picker-loading">
            <div class="loading-spinner"></div>
          </div>
          <div v-else-if="pickerDirs.length === 0" class="picker-empty">
            <p>此目录下没有子文件夹</p>
          </div>
          <div v-else class="picker-list">
            <div
              v-for="dir in pickerDirs"
              :key="dir.file_id"
              class="picker-item"
              @dblclick="pickerEnterDir(dir)"
            >
              <svg viewBox="0 0 24 24" fill="currentColor" class="picker-icon">
                <path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z" />
              </svg>
              <span>{{ dir.name }}</span>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn-secondary" @click="cancelPicker">取消</button>
          <button class="btn-primary" @click="confirmPicker" :disabled="pickerLoading">
            {{ pickerMode === 'move' ? '移动到此处' : '复制到此处' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 新建文件夹弹窗 -->
    <div v-if="showMkdir" class="glass-overlay" @click.self="showMkdir = false">
      <div class="modal-card glass-solid">
        <div class="modal-header">
          <h3>新建文件夹</h3>
          <button class="btn-close neu-circle" @click="showMkdir = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <input
            v-model="newFolderName"
            class="input-field neu-inset"
            placeholder="请输入文件夹名称"
            @keyup.enter="handleMkdir"
            autofocus
          />
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showMkdir = false">取消</button>
          <button class="btn-primary" @click="handleMkdir" :disabled="!newFolderName.trim()">创建</button>
        </div>
      </div>
    </div>

    <!-- 重命名弹窗 -->
    <div v-if="showRename" class="glass-overlay" @click.self="showRename = false">
      <div class="modal-card glass-solid">
        <div class="modal-header">
          <h3>重命名</h3>
          <button class="btn-close neu-circle" @click="showRename = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <input
            v-model="renameName"
            class="input-field neu-inset"
            placeholder="请输入新名称"
            @keyup.enter="handleRename"
            autofocus
          />
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showRename = false">取消</button>
          <button class="btn-primary" @click="handleRename" :disabled="!renameName.trim()">确定</button>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="showDelete" class="glass-overlay" @click.self="showDelete = false">
      <div class="modal-card glass-solid">
        <div class="modal-header">
          <h3>确认删除</h3>
          <button class="btn-close neu-circle" @click="showDelete = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <p class="delete-msg">确定要删除选中的 {{ deleteTargets.length }} 项吗？</p>
          <p class="delete-hint">删除后将移入回收站</p>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showDelete = false">取消</button>
          <button class="btn-danger" @click="handleDelete">删除</button>
        </div>
      </div>
    </div>

    <!-- 识别弹窗 -->
    <RecognizeModal :visible="showRecognize" :item="recognizeItem" @close="showRecognize = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { filesApi, type FileItem } from '@/api/files'
import { showToast } from '@/composables/useToast'
import { handleApiError } from '@/utils/error'
import { formatSize, formatTime } from '@/composables/useFormat'
import RecognizeModal from '@/components/RecognizeModal.vue'

/** 右键菜单尺寸（用于边界检测，避免菜单超出视口） */
const MENU_SIZE = 180

interface Breadcrumb {
  id: string
  name: string
}

const loading = ref(false)
const items = ref<FileItem[]>([])
const breadcrumbs = ref<Breadcrumb[]>([{ id: '0', name: '根目录' }])
const currentCid = ref('0')

const searchKeyword = ref('')

const pageSize = ref(50)
const currentPage = ref(1)
const totalCount = ref(0)

const sortOrder = ref('file_name')
const sortAsc = ref(1)

const selectedIds = ref<Set<string>>(new Set())

const showMkdir = ref(false)
const newFolderName = ref('')

const showRename = ref(false)
const renameName = ref('')

const showDelete = ref(false)
const deleteTargets = ref<string[]>([])

const showPicker = ref(false)
const pickerMode = ref<'move' | 'copy'>('move')
const pickerLoading = ref(false)
const pickerDirs = ref<FileItem[]>([])
const pickerBreadcrumbs = ref<Breadcrumb[]>([{ id: '0', name: '根目录' }])
const pickerCid = ref('0')
const pickerTargets = ref<string[]>([])

const targetItem = ref<FileItem | null>(null)

const showRecognize = ref(false)
const recognizeItem = ref<FileItem | null>(null)

const menuVisible = ref(false)
const menuStyle = ref({})

const isAllSelected = computed(() => items.value.length > 0 && selectedIds.value.size === items.value.length)
const isPartialSelected = computed(() => selectedIds.value.size > 0 && !isAllSelected.value)

onMounted(() => {
  loadFiles()
})

// ==================== 多选 ====================

function toggleSelect(fileId: string) {
  const s = new Set(selectedIds.value)
  if (s.has(fileId)) {
    s.delete(fileId)
  } else {
    s.add(fileId)
  }
  selectedIds.value = s
}

function toggleSelectAll() {
  if (isAllSelected.value) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(items.value.map(i => i.file_id))
  }
}

function clearSelection() {
  selectedIds.value = new Set()
}

function getSelectedIds(): string[] {
  return Array.from(selectedIds.value)
}

// ==================== 文件列表 ====================

function toggleSort(field: string) {
  if (sortOrder.value === field) {
    sortAsc.value = sortAsc.value === 1 ? 0 : 1
  } else {
    sortOrder.value = field
    sortAsc.value = 1
  }
  loadFiles(1)
}

async function loadFiles(page: number = 1) {
  loading.value = true
  selectedIds.value = new Set()
  currentPage.value = page
  try {
    const offset = (page - 1) * pageSize.value
    const res = await filesApi.listFiles(currentCid.value, pageSize.value, offset, sortOrder.value, sortAsc.value)
    if (res.code === 0 && res.data) {
      items.value = res.data.items || []
      totalCount.value = res.data.count || 0
    } else {
      items.value = []
      totalCount.value = 0
    }
  } catch (e) {
    console.error('加载文件列表失败:', e)
    items.value = []
    totalCount.value = 0
  } finally {
    loading.value = false
  }
}

const totalPages = computed(() => Math.max(1, Math.ceil(totalCount.value / pageSize.value)))

// 页码列表（带省略号）
const pageNumbers = computed(() => {
  const total = totalPages.value
  const current = currentPage.value
  const pages: number[] = []

  if (total <= 7) {
    for (let i = 1; i <= total; i++) pages.push(i)
  } else {
    pages.push(1)
    if (current > 3) pages.push(-1) // 省略号
    const start = Math.max(2, current - 1)
    const end = Math.min(total - 1, current + 1)
    for (let i = start; i <= end; i++) pages.push(i)
    if (current < total - 2) pages.push(-1) // 省略号
    pages.push(total)
  }
  return pages
})

function goToPage(page: number) {
  if (page < 1 || page > totalPages.value) return
  loadFiles(page)
}

function handleClick(item: FileItem, event: MouseEvent) {
  if (event.ctrlKey || event.metaKey) {
    toggleSelect(item.file_id)
    return
  }
  if (selectedIds.value.size > 0) {
    toggleSelect(item.file_id)
    return
  }
  if (item.is_dir) {
    enterFolder(item.file_id, item.name)
  }
}

function enterFolder(id: string, name: string) {
  currentCid.value = id
  breadcrumbs.value.push({ id, name })
  loadFiles()
}

function goBack() {
  if (breadcrumbs.value.length > 1) {
    breadcrumbs.value.pop()
    currentCid.value = breadcrumbs.value[breadcrumbs.value.length - 1].id
    loadFiles()
  }
}

function navigateTo(id: string) {
  if (id === currentCid.value) return
  const index = breadcrumbs.value.findIndex(b => b.id === id)
  if (index >= 0) {
    breadcrumbs.value = breadcrumbs.value.slice(0, index + 1)
    currentCid.value = id
    loadFiles()
  }
}

async function handleSearch() {
  const keyword = searchKeyword.value.trim()
  if (!keyword) return

  loading.value = true
  selectedIds.value = new Set()
  try {
    const res = await filesApi.searchFiles(keyword, currentCid.value)
    if (res.code === 0 && res.data) {
      items.value = res.data.items || []
      totalCount.value = res.data.count || 0
      if (items.value.length === 0) {
        showToast('未找到匹配的文件', 'info')
      }
    } else {
      items.value = []
      totalCount.value = 0
      showToast(res.message || '搜索失败', 'error')
    }
  } catch (e: any) {
    console.error('搜索失败:', e)
    items.value = []
    totalCount.value = 0
    handleApiError(e, '搜索失败')
  } finally {
    loading.value = false
  }
}

function clearSearch() {
  searchKeyword.value = ''
  loadFiles(1)
}

// ==================== 右键菜单 ====================

function startRecognize() {
  closeMenu()
  if (!targetItem.value) return
  recognizeItem.value = targetItem.value
  showRecognize.value = true
}

function batchRecognize() {
  // 批量识别入口：取首个选中项作为识别目标（与单选共用同一识别弹窗）
  const firstId = Array.from(selectedIds.value)[0]
  const item = items.value.find(i => i.file_id === firstId)
  if (item) {
    recognizeItem.value = item
    showRecognize.value = true
  }
}

function openMenu(event: MouseEvent, item: FileItem) {
  event.preventDefault()
  targetItem.value = item
  if (!selectedIds.value.has(item.file_id)) {
    selectedIds.value = new Set([item.file_id])
  }
  menuVisible.value = true

  const x = Math.min(event.clientX, window.innerWidth - MENU_SIZE)
  const y = Math.min(event.clientY, window.innerHeight - MENU_SIZE)
  menuStyle.value = { left: `${x}px`, top: `${y}px` }
}

function closeMenu() {
  menuVisible.value = false
}

// ==================== 目录选择器 ====================

async function startMove() {
  closeMenu()
  pickerMode.value = 'move'
  pickerTargets.value = getSelectedIds()
  await openPicker()
}

async function startCopy() {
  closeMenu()
  pickerMode.value = 'copy'
  pickerTargets.value = getSelectedIds()
  await openPicker()
}

function batchMove() {
  pickerMode.value = 'move'
  pickerTargets.value = getSelectedIds()
  openPicker()
}

function batchCopy() {
  pickerMode.value = 'copy'
  pickerTargets.value = getSelectedIds()
  openPicker()
}

async function openPicker() {
  pickerCid.value = '0'
  pickerBreadcrumbs.value = [{ id: '0', name: '根目录' }]
  showPicker.value = true
  await loadPickerDirs()
}

async function loadPickerDirs() {
  pickerLoading.value = true
  try {
    const res = await filesApi.listFiles(pickerCid.value, 200)
    if (res.code === 0 && res.data) {
      pickerDirs.value = (res.data.items || []).filter((i: FileItem) => i.is_dir)
    } else {
      pickerDirs.value = []
    }
  } catch (e) {
    pickerDirs.value = []
  } finally {
    pickerLoading.value = false
  }
}

function pickerEnterDir(dir: FileItem) {
  pickerCid.value = dir.file_id
  pickerBreadcrumbs.value.push({ id: dir.file_id, name: dir.name })
  loadPickerDirs()
}

function pickerNavigateTo(id: string) {
  if (id === pickerCid.value) return
  const index = pickerBreadcrumbs.value.findIndex(b => b.id === id)
  if (index >= 0) {
    pickerBreadcrumbs.value = pickerBreadcrumbs.value.slice(0, index + 1)
    pickerCid.value = id
    loadPickerDirs()
  }
}

function cancelPicker() {
  showPicker.value = false
}

async function confirmPicker() {
  const targets = pickerTargets.value
  if (targets.length === 0) return

  const targetCid = pickerCid.value
  const action = pickerMode.value

  showPicker.value = false

  try {
    let res
    if (action === 'move') {
      res = await filesApi.moveFiles(targets, targetCid)
    } else {
      res = await filesApi.copyFiles(targets, targetCid)
    }

    if (res.code === 0) {
      clearSelection()
      loadFiles()
    } else {
      showToast(res.message || `${action === 'move' ? '移动' : '复制'}失败`, 'error')
    }
  } catch (e: any) {
    handleApiError(e, `${action === 'move' ? '移动' : '复制'}失败`)
  }
}

// ==================== 批量删除 ====================

function batchDelete() {
  deleteTargets.value = getSelectedIds()
  showDelete.value = true
}

function confirmDelete() {
  closeMenu()
  if (!targetItem.value) return
  deleteTargets.value = [targetItem.value.file_id]
  showDelete.value = true
}

async function handleDelete() {
  const targets = deleteTargets.value
  if (targets.length === 0) return
  try {
    const res = await filesApi.deleteFiles(targets)
    if (res.code === 0) {
      showDelete.value = false
      clearSelection()
      loadFiles()
    } else {
      showToast(res.message || '删除失败', 'error')
    }
  } catch (e: any) {
    handleApiError(e, '删除失败')
  }
}

// ==================== 新建文件夹 ====================

async function handleMkdir() {
  const name = newFolderName.value.trim()
  if (!name) return
  try {
    const res = await filesApi.createFolder(name, currentCid.value)
    if (res.code === 0) {
      showMkdir.value = false
      newFolderName.value = ''
      loadFiles()
    } else {
      showToast(res.message || '创建失败', 'error')
    }
  } catch (e: any) {
    handleApiError(e, '创建失败')
  }
}

// ==================== 重命名 ====================

function startRename() {
  closeMenu()
  if (!targetItem.value) return
  renameName.value = targetItem.value.name
  showRename.value = true
}

async function handleRename() {
  const name = renameName.value.trim()
  if (!name || !targetItem.value) return
  try {
    const res = await filesApi.renameFile(targetItem.value.file_id, name)
    if (res.code === 0) {
      showRename.value = false
      loadFiles()
    } else {
      showToast(res.message || '重命名失败', 'error')
    }
  } catch (e: any) {
    handleApiError(e, '重命名失败')
  }
}

// ==================== 工具函数 ====================
// formatSize / formatTime 已统一抽至 @/composables/useFormat，保证各视图行为一致
</script>

<style scoped>
/* ==================== 基础布局 ==================== */
.files {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  font-family: var(--font-sans);
}

/* ==================== 面包屑 ==================== */
.breadcrumb-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: var(--radius-md);
}

/* 返回按钮（新拟态圆形） */
.btn-back {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--accent);
  flex-shrink: 0;
}

.btn-back svg { width: 18px; height: 18px; }

.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 13px;
  overflow-x: auto;
  white-space: nowrap;
}

.crumb {
  cursor: pointer;
  color: var(--accent);
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.crumb:hover { background: var(--accent-bg); }

.crumb.active {
  color: var(--text-primary);
  font-weight: 600;
  cursor: default;
}

.crumb.active:hover { background: transparent; }

.crumb-sep { color: var(--text-tertiary); margin: 0 2px; }

/* ==================== 工具栏 ==================== */
.toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
}

/* 工具栏按钮（新拟态平面） */
.toolbar-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-base);
}

.toolbar-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
  box-shadow: var(--shadow-md);
}

.toolbar-btn:active:not(:disabled) {
  box-shadow: var(--neu-inset);
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toolbar-btn svg { width: 16px; height: 16px; }

.toolbar-btn.danger { color: var(--danger); }
.toolbar-btn.danger:hover { background: var(--danger-bg); }

.toolbar-btn.ghost { color: var(--text-tertiary); }
.toolbar-btn.ghost:hover { color: var(--text-secondary); background: var(--bg-hover); }

.toolbar-divider {
  width: 1px;
  height: 20px;
  background: var(--border);
  margin: 0 4px;
}

.toolbar-selection {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selected-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 6px;
  background: var(--accent);
  color: var(--text-inverse);
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
}

.selected-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.toolbar-spacer {
  flex: 1;
}

/* 搜索框（新拟态凹陷） */
.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: var(--radius-full);
  transition: all var(--transition-base);
}

.search-box:focus-within {
  border-color: var(--accent);
  box-shadow: var(--neu-inset), 0 0 0 3px var(--accent-bg);
}

.search-box svg {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.search-box input {
  border: none;
  background: none;
  outline: none;
  font-size: 13px;
  color: var(--text-primary);
  width: 160px;
}

.search-box input::placeholder {
  color: var(--text-tertiary);
}

.search-clear {
  width: 20px;
  height: 20px;
  background: none;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: var(--radius-full);
  color: var(--text-tertiary);
  flex-shrink: 0;
  transition: all var(--transition-fast);
}

.search-clear:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}

.search-clear svg {
  width: 12px;
  height: 12px;
}

/* ==================== 文件列表容器 ==================== */
.file-list-container {
  flex: 1;
  border-radius: var(--radius-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ==================== 加载 / 空状态 ==================== */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 80px 20px;
  color: var(--text-tertiary);
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

.empty-icon {
  width: 56px;
  height: 56px;
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-icon svg {
  width: 28px;
  height: 28px;
  stroke: var(--text-tertiary);
}

.empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-desc {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* ==================== 表格布局 ==================== */
.file-table {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

/* 表头（粘性吸顶 + 毛玻璃） */
.table-header {
  display: flex;
  align-items: center;
  padding: 0 16px;
  height: 36px;
  background: var(--bg-hover);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  flex-shrink: 0;
  overflow: hidden;
}

.sortable {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: color var(--transition-fast);
}

.sortable:hover {
  color: var(--text-primary);
}

.sort-icon {
  width: 14px;
  height: 14px;
  color: var(--accent);
}

.table-body {
  flex: 1;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

/* 文件行（hover/selected 状态） */
.table-row {
  display: flex;
  align-items: center;
  padding: 0 16px;
  height: 44px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background var(--transition-fast);
  position: relative;
}

.table-row:hover { background: var(--bg-hover); }
.table-row.selected {
  background: var(--bg-selected);
  box-shadow: inset 3px 0 0 var(--accent);
}
.table-row:last-child { border-bottom: none; }

/* ==================== 列定义（对齐关键） ==================== */
.col-check {
  width: 40px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.col-name {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.col-size {
  width: 90px;
  flex-shrink: 0;
  padding-left: 16px;
  text-align: left;
}

.col-time {
  width: 130px;
  flex-shrink: 0;
  padding-left: 16px;
}

.col-action {
  width: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ==================== 复选框（新拟态凹陷） ==================== */
.checkbox-wrapper {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  width: 18px;
  height: 18px;
}

.checkbox-wrapper input { display: none; }

.checkbox-custom {
  width: 16px;
  height: 16px;
  border: 1.5px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  box-shadow: var(--neu-inset);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-base);
}

.checkbox-wrapper input:checked + .checkbox-custom {
  background: var(--accent);
  border-color: var(--accent);
  box-shadow: none;
}

.checkbox-wrapper input:checked + .checkbox-custom::after {
  content: '';
  width: 9px;
  height: 5px;
  border-left: 1.5px solid var(--text-inverse);
  border-bottom: 1.5px solid var(--text-inverse);
  transform: rotate(-45deg) translate(0.5px, -0.5px);
}

.checkbox-wrapper input:indeterminate + .checkbox-custom {
  background: var(--accent);
  border-color: var(--accent);
  box-shadow: none;
}

.checkbox-wrapper input:indeterminate + .checkbox-custom::after {
  content: '';
  width: 8px;
  height: 1.5px;
  background: var(--text-inverse);
  border-radius: 1px;
}

/* ==================== 文件图标 ==================== */
.file-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-folder { width: 20px; height: 20px; color: var(--folder); }
.icon-file { width: 18px; height: 18px; color: var(--text-tertiary); }

.file-name {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 400;
}

.file-size {
  font-size: 12px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.file-size.dim {
  color: var(--text-tertiary);
}

.file-time {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

/* ==================== 更多按钮（新拟态圆形） ==================== */
.btn-more {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  opacity: 0;
  transition: all var(--transition-base);
}

.table-row:hover .btn-more { opacity: 1; }
.btn-more:hover { color: var(--accent); }
.btn-more svg { width: 14px; height: 14px; }

/* ==================== 右键菜单 ==================== */
.context-menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 900;
}

/* 右键菜单（液态玻璃实体） */
.context-menu {
  position: fixed;
  border-radius: var(--radius-md);
  padding: 4px;
  min-width: 160px;
  z-index: 901;
}

.menu-option {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 12px;
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.menu-option:hover { background: var(--bg-hover); }
.menu-option.danger { color: var(--danger); }
.menu-option.danger:hover { background: var(--danger-bg); }
.menu-option svg { width: 15px; height: 15px; flex-shrink: 0; }

.menu-divider {
  height: 1px;
  background: var(--border);
  margin: 4px 8px;
}

/* ==================== 弹窗 ==================== */
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

/* 关闭按钮（新拟态圆形） */
.btn-close {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
}

.btn-close:hover { color: var(--text-primary); }
.btn-close svg { width: 16px; height: 16px; }

.modal-body { padding: 16px 20px; }

/* 输入框（新拟态凹陷） */
.input-field {
  width: 100%;
  padding: 10px 12px;
  font-size: 14px;
  outline: none;
  color: var(--text-primary);
  transition: all var(--transition-base);
}

.input-field:focus {
  border-color: var(--accent);
  box-shadow: var(--neu-inset), 0 0 0 3px var(--accent-bg);
}

.delete-msg {
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.delete-hint {
  font-size: 13px;
  color: var(--text-tertiary);
}

.modal-footer {
  display: flex;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  justify-content: flex-end;
}

/* 次要按钮（新拟态平面） */
.btn-secondary {
  height: 34px;
  padding: 0 16px;
  background: transparent;
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-base);
}

.btn-secondary:hover {
  background: var(--bg-hover);
  box-shadow: var(--shadow-md);
}

.btn-primary {
  height: 34px;
  padding: 0 16px;
  background: var(--accent);
  color: var(--text-inverse);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--transition-base);
}

.btn-primary:hover:not(:disabled) { background: var(--accent-hover); }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-danger {
  height: 34px;
  padding: 0 16px;
  background: var(--danger);
  color: var(--text-inverse);
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--transition-base);
}

.btn-danger:hover { opacity: 0.9; }

/* ==================== 目录选择器 ==================== */
.picker-modal { max-width: 420px; }

.picker-breadcrumb {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 10px 16px;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
  overflow-x: auto;
  white-space: nowrap;
}

.picker-body {
  height: 260px;
  overflow-y: auto;
  padding: 8px 0;
}

.picker-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.picker-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-tertiary);
  font-size: 13px;
}

.picker-list { padding: 0 8px; }

.picker-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary);
  transition: background var(--transition-fast);
}

.picker-item:hover { background: var(--bg-hover); }
.picker-icon { width: 18px; height: 18px; color: var(--folder); flex-shrink: 0; }

/* ==================== 分页器（新拟态按钮） ==================== */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.page-btn {
  min-width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-base);
}

.page-btn:hover:not(:disabled):not(.active) {
  background: var(--bg-hover);
  color: var(--text-primary);
  box-shadow: var(--shadow-md);
}

.page-btn.active {
  background: var(--accent);
  color: var(--text-inverse);
  border-color: var(--accent);
}

.page-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.page-btn svg {
  width: 16px;
  height: 16px;
}

.page-ellipsis {
  width: 32px;
  text-align: center;
  font-size: 13px;
  color: var(--text-tertiary);
}

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
  .toolbar {
    flex-wrap: wrap;
  }

  .toolbar-btn span {
    display: none;
  }

  .toolbar-btn {
    padding: 8px;
  }

  .col-size {
    width: 70px;
  }

  .col-time {
    display: none;
  }

  .btn-more {
    opacity: 1;
  }
}</style>
