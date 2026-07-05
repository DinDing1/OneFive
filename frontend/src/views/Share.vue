<template>
  <div class="share">
    <!-- 文件视图区域 -->
    <div class="file-area">
      <!-- 全局 loading -->
      <div v-if="loadingShares && sources.length === 0" class="loading-state glass-card">
        <div class="loading-spinner"></div>
        <p>加载中...</p>
      </div>

      <!-- 无分享时的空态 -->
      <div v-else-if="sources.length === 0" class="empty-prompt glass-card">
        <div class="empty-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </svg>
        </div>
        <p class="empty-title">暂无分享</p>
        <p class="empty-desc">在上方输入分享链接开始使用</p>
      </div>

      <!-- 有分享时显示文件内容 -->
      <template v-else>
        <!-- 工具栏 -->
        <div class="toolbar glass-card">
          <template v-if="selectedIds.size === 0">
            <!-- 视图切换 -->
            <div class="view-switch">
              <button
                class="view-btn"
                :class="{ active: viewMode === 'original' }"
                @click="switchView('original')"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                </svg>
                <span>原始视图</span>
              </button>
              <button
                class="view-btn"
                :class="{ active: viewMode === 'organized' }"
                @click="switchView('organized')"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="3" width="7" height="7" />
                  <rect x="14" y="3" width="7" height="7" />
                  <rect x="14" y="14" width="7" height="7" />
                  <rect x="3" y="14" width="7" height="7" />
                </svg>
                <span>整理视图</span>
              </button>
            </div>

            <!-- 筛选按钮组（仅原始视图显示） -->
            <div v-if="viewMode === 'original'" class="filter-group">
              <button
                class="filter-btn"
                :class="{ active: fileFilter === 'all' }"
                @click="setFileFilter('all')"
              >全部<span class="filter-count">{{ allCount }}</span></button>
              <button
                class="filter-btn"
                :class="{ active: fileFilter === 'organized' }"
                @click="setFileFilter('organized')"
              >已整理<span class="filter-count">{{ organizedCount }}</span></button>
              <button
                class="filter-btn"
                :class="{ active: fileFilter === 'unorganized' }"
                @click="setFileFilter('unorganized')"
              >未整理<span class="filter-count">{{ unorganizedCount }}</span></button>
              <button
                class="filter-btn"
                :class="{ active: fileFilter === 'valid' }"
                @click="setFileFilter('valid')"
              >有效<span class="filter-count">{{ validCount }}</span></button>
              <button
                class="filter-btn"
                :class="{ active: fileFilter === 'invalid' }"
                @click="setFileFilter('invalid')"
              >失效<span class="filter-count">{{ invalidCount }}</span></button>
            </div>

            <div class="toolbar-spacer"></div>

            <!-- 检测链接按钮 -->
            <button
              v-if="viewMode === 'original'"
              class="btn-check-links"
              :disabled="checkingLinks"
              @click="handleCheckLinks"
            >
              <svg v-if="!checkingLinks" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 12l2 2 4-4" />
                <circle cx="12" cy="12" r="10" />
              </svg>
              <svg v-else class="icon-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 12a9 9 0 1 1-6.219-8.56" />
              </svg>
              <span>{{ checkingLinks ? `检测中 ${checkProgress}` : '检测链接' }}</span>
            </button>

            <!-- 搜索框 -->
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

          <!-- 选中文件后的批量操作 -->
          <template v-else>
            <div class="toolbar-selection">
              <span class="selected-badge">{{ selectedIds.size }}</span>
              <span class="selected-label">已选</span>
            </div>
            <div class="toolbar-divider"></div>
            <button class="toolbar-btn danger" @click="handleBatchDelete">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
              </svg>
              <span>删除分享</span>
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

        <!-- 原始视图 -->
        <div v-if="viewMode === 'original'" class="file-list-container glass-card">
          <div v-if="loadingFiles" class="loading-state">
            <div class="loading-spinner"></div>
            <p>加载中...</p>
          </div>
          <div v-else-if="filteredFiles.length === 0" class="empty-state">
            <div class="empty-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" /></svg>
            </div>
            <p class="empty-title">暂无文件</p>
            <p class="empty-desc">{{ emptyDescText }}</p>
          </div>
          <div v-else class="file-table">
            <!-- 目录导航面包屑 -->
            <div v-if="isInSubDir" class="dir-breadcrumb">
              <button class="breadcrumb-btn" @click="navigateToDir(0)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                </svg>
              </button>
              <template v-for="(crumb, idx) in currentDirBreadcrumbs" :key="idx">
                <span v-if="idx > 0" class="breadcrumb-sep">/</span>
                <button v-if="idx < currentDirBreadcrumbs.length - 1" class="breadcrumb-btn" @click="navigateToDir(idx)">
                  {{ crumb.name }}
                </button>
                <span v-else class="breadcrumb-current">{{ crumb.name }}</span>
              </template>
            </div>
            <div class="table-header">
              <div class="col-check">
                <label class="checkbox-wrapper" @click.prevent="toggleSelectAll">
                  <input type="checkbox" :checked="isAllSelected" :indeterminate="isPartialSelected" />
                  <span class="checkbox-custom"></span>
                </label>
              </div>
              <div class="col-name">名称</div>
              <div class="tbl-col tbl-col-organized">整理名称</div>
              <div class="tbl-col tbl-col-size">大小</div>
              <div class="tbl-col tbl-col-status">状态</div>
              <div class="tbl-col tbl-col-link">有效期</div>
              <div class="tbl-col tbl-col-time">时间</div>
              <div class="col-action"></div>
            </div>
            <div class="table-body">
              <div
                v-for="item in filteredFiles"
                :key="item.id"
                class="table-row"
                :class="{ selected: selectedIds.has(item.file_id) }"
                @click="handleRowClick(item, $event)"
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
                  <span v-if="item.is_dir && item.file_count" class="file-count-badge">{{ item.file_count }}</span>
                </div>
                <div class="tbl-col tbl-col-organized">
                  <span v-if="item.organized && item.title" class="organized-name">
                    {{ item.title }}<span v-if="item.year"> ({{ item.year }})</span><span v-if="item.tmdb_id"> {tmdb={{ item.tmdb_id }}}</span>
                  </span>
                </div>
                <div class="tbl-col tbl-col-size">
                  <span class="file-size">{{ formatSize(item.size) }}</span>
                </div>
                <div class="tbl-col tbl-col-status">
                  <span v-if="item.organized" class="status-tag status-yes">已整理</span>
                  <span v-else class="status-tag status-no">未整理</span>
                </div>
                <div class="tbl-col tbl-col-link">
                  <!-- 数据库只存储两种状态：0=无效，其它均视为有效 -->
                  <span v-if="linkValidMap.get(item.source_id) === 0" class="link-tag link-invalid">无效</span>
                  <span v-else class="link-tag link-valid">有效</span>
                </div>
                <div class="tbl-col tbl-col-time">
                  <span class="file-time">{{ formatTime(item.updated_at) }}</span>
                </div>
                <div class="col-action">
                  <button class="btn-more neu-circle" @click.stop="toggleRowMenu(item, $event)" title="更多操作">
                    <svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.5" /><circle cx="12" cy="12" r="1.5" /><circle cx="12" cy="19" r="1.5" /></svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
          
          <!-- 分页器 -->
          <div v-if="totalItems > pageSize" class="pagination">
            <button class="page-btn" :disabled="currentPage <= 1" @click="currentPage--">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
            <template v-for="p in visiblePages" :key="p">
              <span v-if="p === -1" class="page-ellipsis">...</span>
              <button v-else class="page-btn" :class="{ active: p === currentPage }" @click="currentPage = p">
                {{ p }}
              </button>
            </template>
            <button class="page-btn" :disabled="currentPage >= totalPages" @click="currentPage++">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          </div>
        </div>

        <!-- 行操作下拉菜单（独立于视图，不受 v-if 链影响） -->
        <div v-if="rowMenuVisible" class="row-menu-overlay" @click="closeRowMenu">
          <div class="row-menu glass-solid" :style="rowMenuStyle">
            <button class="row-menu-item" @click="rowMenuRecognize">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
              识别
            </button>
            <button class="row-menu-item" @click="rowMenuProperties">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" /></svg>
              属性
            </button>
            <div class="row-menu-divider"></div>
            <button class="row-menu-item row-menu-danger" @click="rowMenuDelete">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6" /><path d="M14 11v6" /><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /></svg>
              删除分享
            </button>
          </div>
        </div>

        <!-- 整理视图 -->
        <div v-if="viewMode === 'organized'" class="organized-view">
          <!-- 面包屑导航 -->
          <div class="breadcrumb-bar glass-card">
            <button
              v-if="organizedBreadcrumbs.length > 1"
              class="btn-back neu-circle"
              @click="navigateOrganizedTo(organizedBreadcrumbs[organizedBreadcrumbs.length - 2].path)"
              title="返回上级"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
            <nav class="breadcrumbs">
              <span
                v-for="(crumb, index) in organizedBreadcrumbs"
                :key="crumb.path"
                class="crumb"
                :class="{ active: index === organizedBreadcrumbs.length - 1 }"
                @click="navigateOrganizedTo(crumb.path)"
              >
                {{ crumb.name }}
                <span v-if="index < organizedBreadcrumbs.length - 1" class="crumb-sep">/</span>
              </span>
            </nav>
          </div>
          <!-- 内容区 -->
          <div class="file-list-container glass-card">
            <div v-if="loadingOrganized" class="loading-state">
              <div class="loading-spinner"></div>
              <p>加载中...</p>
            </div>
            <div v-else-if="organizedEntries.length === 0" class="empty-state">
              <p class="empty-title">{{ isSearching ? '未找到匹配的文件' : '此目录为空' }}</p>
              <p class="empty-desc">{{ isSearching ? '尝试其他关键词' : '先在原始视图中识别文件' }}</p>
            </div>
            <div v-else class="file-table">
              <div class="table-header">
                <div class="col-name">名称</div>
                <div class="tbl-col tbl-col-count">文件数</div>
                <div class="tbl-col tbl-col-size">大小</div>
              </div>
              <div class="table-body">
                <div
                  v-for="entry in organizedEntries"
                  :key="entry.path"
                  class="table-row"
                  @click="entry.isDir ? enterOrganizedDir(entry) : null"
                  :class="{ clickable: entry.isDir }"
                >
                  <div class="col-name">
                    <div class="file-icon">
                      <svg v-if="entry.isDir" viewBox="0 0 24 24" fill="currentColor" class="icon-folder">
                        <path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z" />
                      </svg>
                      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="icon-file">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                    </div>
                    <span class="file-name">{{ entry.name }}</span>
                  </div>
                  <div class="tbl-col tbl-col-count">
                    <span v-if="entry.isDir" class="count-badge">{{ entry.fileCount }}</span>
                  </div>
                  <div class="tbl-col tbl-col-size">
                    <span v-if="entry.isDir">{{ formatSize(entry.totalSize || 0) }}</span>
                    <span v-else>{{ formatSize(entry.file?.size || 0) }}</span>
                  </div>
                </div>
              </div>
            </div>
            
            <!-- 整理视图分页器 -->
            <div v-if="organizedTotalItems > organizedPageSize" class="pagination">
              <button class="page-btn" :disabled="organizedCurrentPage <= 1" @click="organizedCurrentPage--">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="15 18 9 12 15 6" />
                </svg>
              </button>
              <template v-for="p in organizedVisiblePages" :key="p">
                <span v-if="p === -1" class="page-ellipsis">...</span>
                <button v-else class="page-btn" :class="{ active: p === organizedCurrentPage }" @click="organizedCurrentPage = p">
                  {{ p }}
                </button>
              </template>
              <button class="page-btn" :disabled="organizedCurrentPage >= organizedTotalPages" @click="organizedCurrentPage++">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="showDeleteConfirm" class="glass-overlay" @click.self="showDeleteConfirm = false">
      <div class="modal-card glass-solid">
        <div class="modal-header">
          <h3>删除分享</h3>
          <button class="btn-close neu-circle" @click="showDeleteConfirm = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <p class="delete-msg">确定要删除分享「{{ deletingShareName }}」吗？</p>
          <p class="delete-hint">删除后将无法恢复</p>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showDeleteConfirm = false">取消</button>
          <button class="btn-danger" @click="confirmDeleteShare">删除</button>
        </div>
      </div>
    </div>

    <!-- 识别结果弹窗 -->
    <div v-if="showRecognizeModal" class="glass-overlay" @click.self="closeRecognizeModal">
      <div class="share-recognize-modal">
        <!-- Hero 区域：和 RecognizeModal 结构一致 -->
        <div class="sr-hero">
          <div v-if="recognizeResult?.tmdb_backdrop" class="sr-hero-bg">
            <img :src="recognizeResult.tmdb_backdrop" alt="" />
            <div class="sr-hero-mask"></div>
          </div>
          <div v-else class="sr-hero-bg sr-hero-placeholder">
            <div class="sr-hero-mask"></div>
          </div>

          <!-- 关闭按钮 -->
          <button class="sr-close" @click="closeRecognizeModal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>

          <div class="sr-hero-content">
            <!-- 海报 -->
            <div v-if="recognizeLoading" class="sr-poster sr-poster-skeleton"></div>
            <div v-else-if="recognizeResult?.tmdb_poster" class="sr-poster">
              <img :src="recognizeResult.tmdb_poster" class="sr-poster-img" alt="poster" />
            </div>
            <div v-else class="sr-poster sr-poster-empty">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2" /><line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" /></svg>
            </div>
            <!-- 标题信息 -->
            <div class="sr-hero-info">
              <template v-if="recognizeLoading">
                <div class="sr-skeleton sr-skeleton-title"></div>
                <div class="sr-skeleton sr-skeleton-meta"></div>
              </template>
              <template v-else>
                <h2 class="sr-title">{{ recognizeResult?.title || recognizeItem?.name || '未知' }}</h2>
                <div class="sr-meta">
                  <span v-if="recognizeResult" class="sr-meta-type">{{ recognizeResult.media_type === 'movie' ? '电影' : '电视剧' }}</span>
                  <span v-if="recognizeResult?.year" class="sr-meta-year">{{ recognizeResult.year }}</span>
                  <span v-if="recognizeResult?.tmdb_rating" class="sr-meta-rating">
                    <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" /></svg>
                    {{ recognizeResult.tmdb_rating.toFixed(1) }}
                  </span>
                </div>
              </template>
            </div>
          </div>
        </div>

        <!-- 内容区：加载 / 有结果 / 无结果（单一 v-if 链） -->
        <div class="sr-content">
          <!-- 加载中 -->
          <div v-if="recognizeLoading" class="sr-loading">
            <div class="loading-spinner"></div>
            <p>正在识别...</p>
          </div>

          <!-- 有结果 -->
          <div v-else-if="recognizeResult" class="sr-result">
            <div v-if="pendingOrganizeIds.length > 1" class="sr-batch-hint">
              已选 {{ pendingOrganizeIds.length }} 个文件，以下为首个文件的识别结果
            </div>
            <!-- 标签 -->
            <div class="sr-tags">
              <span v-if="recognizeResult.category" class="sr-tag sr-tag-cat">{{ recognizeResult.category }}</span>
              <span v-if="recognizeResult.tmdb_id" class="sr-tag sr-tag-id">TMDB {{ recognizeResult.tmdb_id }}</span>
            </div>
            <!-- 手动纠错 -->
            <div class="sr-section sr-manual-box">
              <div class="sr-section-title">手动纠错</div>
              <div class="sr-manual-row">
                <select v-model="manualMediaType" class="sr-manual-select">
                  <option value="movie">电影</option>
                  <option value="tv">电视剧</option>
                </select>
                <input v-model="manualTmdbId" class="sr-manual-input" placeholder="输入 TMDB ID" @keyup.enter="manualRecognizeShare" />
                <button class="sr-manual-btn" :disabled="manualLoading" @click="manualRecognizeShare">
                  {{ manualLoading ? '识别中...' : '重新识别' }}
                </button>
              </div>
              <div v-if="manualError" class="sr-footer-msg sr-footer-error">{{ manualError }}</div>
            </div>
            <!-- 技术信息 -->
            <div v-if="hasRecognizeTechInfo" class="sr-section">
              <div class="sr-section-title">技术信息</div>
              <div class="sr-tech-tags">
                <span v-if="recognizeResult.tech_info.videoFormat" class="sr-tech">{{ recognizeResult.tech_info.videoFormat }}</span>
                <span v-if="recognizeResult.tech_info.edition" class="sr-tech sr-tech-edition">{{ recognizeResult.tech_info.edition }}</span>
                <span v-if="recognizeResult.tech_info.videoCodec" class="sr-tech">{{ recognizeResult.tech_info.videoCodec }}</span>
                <span v-if="recognizeResult.tech_info.audioCodec" class="sr-tech">{{ recognizeResult.tech_info.audioCodec }}</span>
                <span v-if="recognizeResult.tech_info.webSource" class="sr-tech sr-tech-source">{{ recognizeResult.tech_info.webSource }}</span>
                <span v-if="recognizeResult.tech_info.releaseGroup" class="sr-tech sr-tech-group">{{ recognizeResult.tech_info.releaseGroup }}</span>
              </div>
            </div>
            <!-- 目标路径 -->
            <div v-if="recognizeResult.target_path" class="sr-section">
              <div class="sr-section-title">目标路径</div>
              <div class="sr-path">
                <span class="sr-path-dir">{{ recognizeResult.target_path.dir }}/</span><span class="sr-path-file">{{ recognizeResult.target_path.filename }}</span>
              </div>
            </div>
            <!-- 简介 -->
            <div v-if="recognizeResult.tmdb_overview" class="sr-section">
              <div class="sr-section-title">简介</div>
              <p class="sr-overview">{{ recognizeResult.tmdb_overview }}</p>
            </div>
          </div>

          <!-- 无结果 -->
          <div v-else class="sr-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /><line x1="8" y1="11" x2="14" y2="11" /></svg>
            <p>未识别到媒体信息</p>
          </div>
        </div>

        <!-- 底部操作栏（始终在最底部，不随内容滚动） -->
        <div v-if="!recognizeLoading && recognizeResult" class="sr-footer">
          <!-- 整理进度面板（整理中或完成后显示） -->
          <div v-if="organizeExecuting || organizeProgressDone" class="sr-progress-panel neu-inset">
            <!-- 顶部：进度条 + 百分比 -->
            <div class="sr-progress-top">
              <div class="sr-progress-bar-wrap">
                <div class="sr-progress-bar" :style="{ width: organizeProgressPercent + '%' }"></div>
              </div>
              <span class="sr-progress-percent">{{ organizeProgressPercent }}%</span>
            </div>
            <!-- 中部：计数统计 -->
            <div class="sr-progress-stats">
              <span class="sr-stat-text">
                {{ organizeProgressIndex }} / {{ organizeProgressTotal }}
              </span>
              <span class="sr-stat-badge sr-stat-success">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12" /></svg>
                {{ organizeProgressSuccess }}
              </span>
              <span v-if="organizeProgressFailed > 0" class="sr-stat-badge sr-stat-fail">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                {{ organizeProgressFailed }}
              </span>
              <span v-if="organizeExecuting && organizeProgressName" class="sr-stat-current">
                正在整理: {{ organizeProgressName }}
              </span>
            </div>
          </div>

          <div v-if="organizeExecError" class="sr-footer-msg sr-footer-error">{{ organizeExecError }}</div>
          <div v-if="organizeExecSuccess" class="sr-footer-msg sr-footer-success">{{ organizeExecSuccess }}</div>
          <button class="sr-btn-organize" :disabled="organizeExecuting || !!organizeExecSuccess" @click="executeOrganize">
            <svg v-if="!organizeExecuting" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg>
            <div v-else class="sr-btn-spinner"></div>
            {{ organizeExecuting ? '整理中...' : '开始整理' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 属性信息弹窗 -->
    <div v-if="showPropertiesModal" class="glass-overlay" @click.self="closePropertiesModal">
      <div class="props-modal">
        <!-- 标题栏 -->
        <div class="props-header">
          <h3 class="props-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" /><line x1="9" y1="3" x2="9" y2="21" /><line x1="3" y1="9" x2="21" y2="9" /></svg>
            属性信息
          </h3>
          <button class="props-close" @click="closePropertiesModal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
          </button>
        </div>

        <!-- 内容区 -->
        <div class="props-content">
          <!-- 加载中 -->
          <div v-if="propertiesLoading" class="props-loading">
            <div class="loading-spinner"></div>
            <p>加载中...</p>
          </div>

          <template v-else-if="propShare">
            <!-- 分享信息区块 -->
            <div class="props-section">
              <div class="props-section-title">分享信息</div>
              <div class="props-grid">
                <div class="props-field">
                  <label class="props-label">名称</label>
                  <input v-model="propShare.share_name" class="props-input" placeholder="分享名称" />
                </div>
                <div class="props-field">
                  <label class="props-label">分享码</label>
                  <input v-model="propShare.share_code" class="props-input" placeholder="分享码" />
                </div>
                <div class="props-field">
                  <label class="props-label">提取码</label>
                  <input v-model="propShare.receive_code" class="props-input" placeholder="提取码" />
                </div>
                <div class="props-field props-field-readonly">
                  <label class="props-label">文件数量</label>
                  <div class="props-value">{{ propShare.file_count }}</div>
                </div>
                <div class="props-field props-field-readonly">
                  <label class="props-label">文件大小</label>
                  <div class="props-value">{{ formatSize(propShare.total_size) }}</div>
                </div>
                <div class="props-field props-field-readonly">
                  <label class="props-label">添加时间</label>
                  <div class="props-value">{{ propShare.created_at || '—' }}</div>
                </div>
              </div>
            </div>

            <!-- 媒体信息区块 -->
            <div class="props-section" v-if="propFile">
              <div class="props-section-title">媒体信息</div>
              <div class="props-grid">
                <div class="props-field props-field-readonly">
                  <label class="props-label">媒体名称</label>
                  <div class="props-value">{{ propFile.title || '—' }}</div>
                </div>
                <div class="props-field props-field-readonly">
                  <label class="props-label">年份</label>
                  <div class="props-value">{{ propFile.year || '—' }}</div>
                </div>
                <div class="props-field props-field-readonly">
                  <label class="props-label">TMDB ID</label>
                  <div class="props-value">{{ propFile.tmdb_id || '—' }}</div>
                </div>
                <div class="props-field props-field-readonly">
                  <label class="props-label">媒体类型</label>
                  <div class="props-value">
                    <span v-if="propFile.media_type === 'movie'" class="props-tag props-tag-movie">电影</span>
                    <span v-else-if="propFile.media_type === 'tv'" class="props-tag props-tag-tv">电视剧</span>
                    <span v-else>—</span>
                  </div>
                </div>
                <!-- 分类：仅在已识别 media_type 时允许编辑 -->
                <div class="props-field">
                  <label class="props-label">分类</label>
                  <select
                    v-if="propFile.media_type && propCategories.length > 0"
                    v-model="propEditingCategory"
                    class="props-select"
                  >
                    <option v-for="cat in propCategories" :key="cat" :value="cat">{{ cat }}</option>
                  </select>
                  <div v-else class="props-value">{{ propFile.category || '—（请先识别）' }}</div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- 底部操作栏 -->
        <div v-if="!propertiesLoading && propShare" class="props-footer">
          <button class="props-btn props-btn-cancel" @click="closePropertiesModal">取消</button>
          <button class="props-btn props-btn-save" :disabled="propertiesSaving" @click="saveProperties">
            <div v-if="propertiesSaving" class="props-btn-spinner"></div>
            {{ propertiesSaving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { shareApi, type ShareSource, type ShareFile } from '@/api/share'
import { showToast } from '@/composables/useToast'
import { handleApiError } from '@/utils/error'
import { useVisiblePages } from '@/composables/usePagination'
import { formatSize, formatTime } from '@/composables/useFormat'
import type { RecognizeResult } from '@/api/organize'

// ==================== 类型定义 ====================

/** 筛选类型 */
type FileFilter = 'all' | 'organized' | 'unorganized' | 'valid' | 'invalid'

// ==================== 状态 ====================

// 分享来源列表
const sources = ref<ShareSource[]>([])

// 链接有效性状态：key=source_id, value=1(有效)/0(无效)
const linkValidMap = ref<Map<number, number>>(new Map())
const checkingLinks = ref(false)
const checkProgress = ref('')
const loadingShares = ref(false)

// 视图模式：原始 / 整理
const viewMode = ref<'original' | 'organized'>('original')

// 原始视图 - 文件列表
const allFiles = ref<ShareFile[]>([])
const loadingFiles = ref(false)

// 原始视图 - 目录导航
interface DirBreadcrumb {
  sourceId: number
  parentId: string
  name: string
}
const currentDirBreadcrumbs = ref<DirBreadcrumb[]>([{ sourceId: 0, parentId: '0', name: '全部' }])
const isInSubDir = computed(() => currentDirBreadcrumbs.value.length > 1)

// 整理视图 - 文件管理器风格
interface OrganizedEntry {
  name: string
  path: string
  isDir: boolean
  fileCount?: number
  totalSize?: number
  file?: ShareFile  // 叶子节点的文件数据
}
const allOrganizedEntries = ref<OrganizedEntry[]>([])
const organizedBreadcrumbs = ref<{ path: string; name: string }[]>([{ path: '', name: '根目录' }])
const organizedCurrentPath = ref('')
const loadingOrganized = ref(false)
// 存储所有已整理的文件，用于按路径筛选
const allOrganizedFiles = ref<ShareFile[]>([])

// 整理视图分页
const organizedCurrentPage = ref(1)
const organizedPageSize = ref(30)

/** 整理视图当前页条目（分页后） */
const organizedEntries = computed(() => {
  const start = (organizedCurrentPage.value - 1) * organizedPageSize.value
  const end = start + organizedPageSize.value
  return allOrganizedEntries.value.slice(start, end)
})

/** 整理视图总条数 */
const organizedTotalItems = computed(() => allOrganizedEntries.value.length)

/** 整理视图总页数 */
const organizedTotalPages = computed(() => {
  const total = Math.ceil(organizedTotalItems.value / organizedPageSize.value)
  return total > 0 ? total : 1
})

/** 整理视图可见页码（-1 表示省略号，逻辑见 usePagination） */
const organizedVisiblePages = useVisiblePages(organizedTotalPages, organizedCurrentPage)

// 搜索
const searchKeyword = ref('')
const isSearching = ref(false)

// 筛选（全部 / 已整理 / 未整理）
const fileFilter = ref<FileFilter>('all')

/** 切换筛选标签时重置分页到第 1 页 */
function setFileFilter(filter: FileFilter) {
  fileFilter.value = filter
  currentPage.value = 1
}

// 多选
const selectedIds = ref<Set<string>>(new Set())

// 删除分享
const showDeleteConfirm = ref(false)
const deletingShareId = ref<number | null>(null)
const deletingShareName = ref('')
const deletingBatchIds = ref<number[]>([])

// 行操作下拉菜单
const rowMenuVisible = ref(false)
const rowMenuTarget = ref<ShareFile | null>(null)
const rowMenuStyle = ref<Record<string, string>>({})

// 属性弹窗状态
const showPropertiesModal = ref(false)
const propertiesLoading = ref(false)
const propertiesSaving = ref(false)
// 属性数据：分享来源信息（可编辑字段）
const propShare = ref<{
  share_name: string
  share_code: string
  receive_code: string
  file_count: number
  total_size: number
  created_at: string
} | null>(null)
// 属性数据：文件信息（媒体信息只读 + 分类可编辑）
const propFile = ref<ShareFile | null>(null)
// 可选分类列表（按 media_type 过滤后的分类策略）
const propCategories = ref<string[]>([])
// 编辑中的分类（独立保存，避免直接修改原对象）
const propEditingCategory = ref('')
// 当前操作的 source_id / file_id
const propTargetIds = ref<{ sourceId: number; fileId: string }>({ sourceId: 0, fileId: '' })

// 识别弹窗状态
const showRecognizeModal = ref(false)
const recognizeLoading = ref(false)
const recognizeResult = ref<RecognizeResult | null>(null)
const recognizeItem = ref<ShareFile | null>(null)
// 待整理的文件ID列表（支持批量：单文件/多文件）
const pendingOrganizeIds = ref<Array<{ sourceId: number; fileId: string }>>([])
// 整理执行状态
const organizeExecuting = ref(false)
const organizeExecError = ref('')
const organizeExecSuccess = ref('')
const manualTmdbId = ref('')
const manualMediaType = ref<'movie' | 'tv'>('movie')
const manualLoading = ref(false)
const manualError = ref('')
const manualOverride = ref(false)
// 流式整理进度（SSE 实时推送）
const organizeProgressTotal = ref(0)          // 总文件数（文件夹会展开为内部真实文件数）
const organizeProgressIndex = ref(0)          // 当前完成数
const organizeProgressName = ref('')          // 当前正在整理的文件名
const organizeProgressSuccess = ref(0)        // 成功计数
const organizeProgressFailed = ref(0)         // 失败计数
const organizeProgressDone = ref(false)       // 是否全部完成
let organizeEventSource: EventSource | null = null

// ==================== 计算属性 ====================

// 分页相关
const currentPage = ref(1)
const pageSize = ref(30)

/** 整理进度百分比（0-100） */
const organizeProgressPercent = computed(() => {
  if (organizeProgressTotal.value === 0) return 0
  return Math.round((organizeProgressIndex.value / organizeProgressTotal.value) * 100)
})

/** 筛选后的所有文件列表（不分页） */
const allFilteredFiles = computed(() => {
  if (viewMode.value !== 'original') return allFiles.value
  if (fileFilter.value === 'all') return allFiles.value
  if (fileFilter.value === 'organized') return allFiles.value.filter(f => f.organized)
  if (fileFilter.value === 'unorganized') return allFiles.value.filter(f => !f.organized)
  if (fileFilter.value === 'valid') return allFiles.value.filter(f => (linkValidMap.value.get(f.source_id) ?? 1) === 1)
  if (fileFilter.value === 'invalid') return allFiles.value.filter(f => linkValidMap.value.get(f.source_id) === 0)
  return allFiles.value
})

/** Tab 计数：全部 / 已整理 / 未整理 / 有效 / 失效 */
const allCount = computed(() => allFiles.value.length)
const organizedCount = computed(() => allFiles.value.filter(f => f.organized).length)
const unorganizedCount = computed(() => allFiles.value.filter(f => !f.organized).length)
const validCount = computed(() => allFiles.value.filter(f => (linkValidMap.value.get(f.source_id) ?? 1) === 1).length)
const invalidCount = computed(() => allFiles.value.filter(f => linkValidMap.value.get(f.source_id) === 0).length)

/** 总条数 */
const totalItems = computed(() => allFilteredFiles.value.length)

/** 总页数 */
const totalPages = computed(() => {
  const total = Math.ceil(totalItems.value / pageSize.value)
  return total > 0 ? total : 1 // 至少1页
})

/** 可见页码列表（-1 表示省略号，逻辑见 usePagination） */
const visiblePages = useVisiblePages(totalPages, currentPage)

/** 当前页的文件列表（分页后） */
const filteredFiles = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return allFilteredFiles.value.slice(start, end)
})

/** 空状态描述文本 */
const emptyDescText = computed(() => {
  if (isSearching.value) return '未找到匹配的文件'
  if (fileFilter.value !== 'all') return '没有符合筛选条件的文件'
  return '当前没有根目录文件'
})

/** 全选状态（基于筛选后的文件） */
const isAllSelected = computed(() =>
  filteredFiles.value.length > 0 &&
  filteredFiles.value.every(f => selectedIds.value.has(f.file_id))
)

/** 部分选中状态 */
const isPartialSelected = computed(() => {
  if (filteredFiles.value.length === 0) return false
  const count = filteredFiles.value.filter(f => selectedIds.value.has(f.file_id)).length
  return count > 0 && count < filteredFiles.value.length
})

/** 识别结果是否有技术信息 */
const hasRecognizeTechInfo = computed(() => {
  if (!recognizeResult.value?.tech_info) return false
  const t = recognizeResult.value.tech_info
  return t.videoFormat || t.edition || t.videoCodec || t.audioCodec || t.webSource || t.releaseGroup
})

// ==================== 生命周期 ====================

onMounted(async () => {
  await loadShares()
  await loadFiles()
})

// ==================== 分享来源 ====================

/** 加载分享列表 */
async function loadShares() {
  loadingShares.value = true
  try {
    const res = await shareApi.listShares()
    if (res.code === 0 && res.data) {
      sources.value = res.data.shares || []
      // 初始化链接有效性 Map（从数据库已存储的 link_valid 字段读取）
      const map = new Map<number, number>()
      for (const s of sources.value) {
        map.set(s.id, s.link_valid ?? 1)
      }
      linkValidMap.value = map
    } else {
      sources.value = []
    }
  } catch (e) {
    console.error('加载分享列表失败:', e)
    sources.value = []
  } finally {
    loadingShares.value = false
  }
}

/** 批量检测分享链接有效性（SSE 流式）
 * 说明：数据库只存储两种状态（1=有效 / 0=无效），不引入"检测中"中间态。
 * 检测过程中保留上一次的有效/无效状态，逐个更新为最新结果。
 */
function handleCheckLinks() {
  if (checkingLinks.value) return
  checkingLinks.value = true
  checkProgress.value = ''

  const es = shareApi.checkAllLinksStream()

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'start') {
        checkProgress.value = `0/${data.total}`
      } else if (data.type === 'progress') {
        // 更新对应分享的有效性状态
        const m = new Map(linkValidMap.value)
        m.set(data.source_id, data.valid ? 1 : 0)
        linkValidMap.value = m
        checkProgress.value = `${data.current}/${data.total}`
      } else if (data.type === 'done') {
        checkingLinks.value = false
        checkProgress.value = ''
        es.close()
        const msg = `检测完成：${data.valid_count} 个有效，${data.invalid_count} 个无效`
        showToast(msg, data.invalid_count > 0 ? 'info' : 'success')
      }
    } catch (e) {
      console.error('解析 SSE 数据失败:', e)
    }
  }

  es.onerror = () => {
    checkingLinks.value = false
    checkProgress.value = ''
    es.close()
    showToast('检测中断，请重试', 'error')
  }
}

/** 点击删除按钮（弹出确认框） */
function handleDeleteShare(sourceId: number) {
  const src = sources.value.find(s => s.id === sourceId)
  deletingShareId.value = sourceId
  deletingBatchIds.value = []
  deletingShareName.value = src?.share_name || '未命名分享'
  showDeleteConfirm.value = true
}

/** 确认删除分享（支持单条和批量） */
async function confirmDeleteShare() {
  try {
    // 批量删除
    if (deletingBatchIds.value.length > 0) {
      const res = await shareApi.deleteSharesBatch(deletingBatchIds.value)
      if (res.code === 0) {
        showToast(`已删除 ${res.data?.success || 0} 个分享`, 'success')
        showDeleteConfirm.value = false
        deletingBatchIds.value = []
        clearSelection()
        await loadShares()
        await loadFiles()
      } else {
        showToast(res.message || '删除失败', 'error')
      }
      return
    }
    // 单条删除
    if (!deletingShareId.value) return
    const res = await shareApi.deleteShare(deletingShareId.value)
    if (res.code === 0) {
      showToast('分享已删除', 'success')
      showDeleteConfirm.value = false
      deletingShareId.value = null
      await loadShares()
      await loadFiles()
    } else {
      showToast(res.message || '删除失败', 'error')
    }
  } catch (e: any) {
    handleApiError(e, '删除失败')
  }
}

// ==================== 行操作菜单 ====================

/** 右键菜单预估高度（px）：识别 + 属性 + 分隔线 + 删除 4 项之和的近似值 */
const MENU_HEIGHT_PX = 140

/** 打开/关闭行菜单 */
function toggleRowMenu(item: ShareFile, event: MouseEvent) {
  if (rowMenuVisible.value && rowMenuTarget.value?.file_id === item.file_id) {
    closeRowMenu()
    return
  }
  rowMenuTarget.value = item
  // 定位到点击位置
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  
  const menuHeight = MENU_HEIGHT_PX
  const spaceBelow = window.innerHeight - rect.bottom
  const spaceAbove = rect.top
  
  // 判断下方空间是否足够，不够则向上展开
  const shouldOpenUpward = spaceBelow < menuHeight && spaceAbove > spaceBelow
  
  rowMenuStyle.value = {
    position: 'fixed',
    top: shouldOpenUpward ? 'auto' : `${rect.bottom + 4}px`,
    bottom: shouldOpenUpward ? `${window.innerHeight - rect.top + 4}px` : 'auto',
    right: `${window.innerWidth - rect.right}px`,
  }
  rowMenuVisible.value = true
}

function closeRowMenu() {
  rowMenuVisible.value = false
  rowMenuTarget.value = null
}

/** 菜单：识别 */
function rowMenuRecognize() {
  const item = rowMenuTarget.value
  closeRowMenu()
  if (item) handleOrganize(item)
}

/** 菜单：删除分享 */
function rowMenuDelete() {
  const item = rowMenuTarget.value
  closeRowMenu()
  if (item) handleDeleteShare(item.source_id)
}

/** 菜单：属性 - 打开属性面板并加载数据 */
function rowMenuProperties() {
  const item = rowMenuTarget.value
  closeRowMenu()
  if (!item) return
  propTargetIds.value = { sourceId: item.source_id, fileId: item.file_id }
  showPropertiesModal.value = true
  loadProperties()
}

/** 加载属性数据（分享信息 + 文件信息 + 可选分类） */
async function loadProperties() {
  propertiesLoading.value = true
  // 重置旧数据
  propShare.value = null
  propFile.value = null
  propCategories.value = []
  propEditingCategory.value = ''
  try {
    const { sourceId, fileId } = propTargetIds.value
    const res = await shareApi.getFileProperties(sourceId, fileId)
    if (res.code === 0 && res.data) {
      const share = res.data.share || {}
      const file = res.data.file || {}
      propShare.value = {
        share_name: share.share_name || '',
        share_code: share.share_code || '',
        receive_code: share.receive_code || '',
        file_count: share.file_count || 0,
        total_size: share.total_size || 0,
        created_at: share.created_at || '',
      }
      propFile.value = file
      propCategories.value = res.data.categories || []
      propEditingCategory.value = file.category || ''
    } else {
      showToast(res.message || '加载属性失败', 'error')
    }
  } catch (e: any) {
    handleApiError(e, '加载属性失败')
  } finally {
    propertiesLoading.value = false
  }
}

/** 保存属性：先保存分享属性，再保存分类（如有变更） */
async function saveProperties() {
  if (!propShare.value) return
  propertiesSaving.value = true
  try {
    const { sourceId, fileId } = propTargetIds.value
    // 第一步：保存分享属性（名称/分享码/提取码）
    const shareRes = await shareApi.updateShareProperties(sourceId, {
      share_name: propShare.value.share_name,
      share_code: propShare.value.share_code,
      receive_code: propShare.value.receive_code,
    })
    if (shareRes.code !== 0) {
      showToast(shareRes.message || '保存分享属性失败', 'error')
      return
    }
    // 第二步：保存分类（仅在分类有变化且 media_type 存在时）
    if (propFile.value && propFile.value.media_type) {
      const oldCategory = propFile.value.category || ''
      if (propEditingCategory.value !== oldCategory) {
        const catRes = await shareApi.updateFileCategory(sourceId, fileId, propEditingCategory.value)
        if (catRes.code !== 0) {
          showToast(catRes.message || '保存分类失败', 'error')
          return
        }
        // 同步更新本地文件对象的分类
        propFile.value.category = propEditingCategory.value
      }
    }
    showToast('属性已保存', 'success')
    // 刷新当前视图（根据面包屑判断是根目录还是子目录）
    await refreshCurrentView()
    showPropertiesModal.value = false
  } catch (e: any) {
    handleApiError(e, '保存失败')
  } finally {
    propertiesSaving.value = false
  }
}

/** 关闭属性弹窗 */
function closePropertiesModal() {
  showPropertiesModal.value = false
}

/** 刷新当前视图（保留面包屑导航位置） */
async function refreshCurrentView() {
  // 整理视图：重新加载整理数据
  if (viewMode.value === 'organized') {
    await loadOrganized()
    return
  }
  // 原始视图：根据面包屑判断是根目录还是子目录
  const crumbs = currentDirBreadcrumbs.value
  if (crumbs.length <= 1) {
    await loadFiles()
  } else {
    const last = crumbs[crumbs.length - 1]
    await loadSubDirFiles(last.sourceId, last.parentId)
  }
}

/**
 * 刷新当前视图的文件列表数据（保持 fileFilter、面包屑、页码不变）
 * 用于整理完成后就地刷新，避免 loadFiles 重置标签导致用户需重新切换。
 */
async function reloadCurrentFiles() {
  try {
    const crumbs = currentDirBreadcrumbs.value
    if (crumbs.length <= 1) {
      // 根目录：重新加载所有分享的根目录文件
      const res = await shareApi.getAllFiles()
      if (res.code === 0 && res.data) {
        allFiles.value = res.data.files || []
      }
    } else {
      // 子目录：重新加载当前子目录文件
      const last = crumbs[crumbs.length - 1]
      const res = await shareApi.listFiles(last.sourceId, last.parentId)
      if (res.code === 0 && res.data) {
        allFiles.value = res.data.items || []
      }
    }
  } catch (e) {
    console.error('刷新文件列表失败:', e)
  }
}

// ==================== 视图切换 ====================

/** 切换视图模式 */
function switchView(mode: 'original' | 'organized') {
  if (viewMode.value === mode) return
  viewMode.value = mode
  selectedIds.value = new Set()
  if (mode === 'organized') {
    loadOrganized()
  }
}

// ==================== 原始视图：文件列表 ====================

/** 加载所有分享的根目录文件 */
async function loadFiles() {
  loadingFiles.value = true
  selectedIds.value = new Set()
  isSearching.value = false
  searchKeyword.value = ''
  fileFilter.value = 'all'
  currentPage.value = 1
  currentDirBreadcrumbs.value = [{ sourceId: 0, parentId: '0', name: '全部' }]
  try {
    const res = await shareApi.getAllFiles()
    if (res.code === 0 && res.data) {
      allFiles.value = res.data.files || []
    } else {
      allFiles.value = []
    }
  } catch (e) {
    console.error('加载文件列表失败:', e)
    allFiles.value = []
  } finally {
    loadingFiles.value = false
  }
}

/** 加载子目录文件 */
async function loadSubDirFiles(sourceId: number, parentId: string) {
  loadingFiles.value = true
  selectedIds.value = new Set()
  fileFilter.value = 'all'
  currentPage.value = 1
  try {
    const res = await shareApi.listFiles(sourceId, parentId)
    if (res.code === 0 && res.data) {
      allFiles.value = res.data.items || []
    } else {
      allFiles.value = []
    }
  } catch (e) {
    console.error('加载子目录失败:', e)
    allFiles.value = []
  } finally {
    loadingFiles.value = false
  }
}

/** 进入目录 */
function enterDir(item: ShareFile) {
  if (!item.is_dir) return
  currentDirBreadcrumbs.value.push({
    sourceId: item.source_id,
    parentId: item.file_id,
    name: item.name,
  })
  loadSubDirFiles(item.source_id, item.file_id)
}

/** 点击面包屑导航 */
function navigateToDir(index: number) {
  if (index === 0) {
    loadFiles()
    return
  }
  currentDirBreadcrumbs.value = currentDirBreadcrumbs.value.slice(0, index + 1)
  const target = currentDirBreadcrumbs.value[index]
  loadSubDirFiles(target.sourceId, target.parentId)
}

/** 点击文件行 */
function handleRowClick(item: ShareFile, event: MouseEvent) {
  // Ctrl/Cmd + 点击：多选
  if (event.ctrlKey || event.metaKey) {
    toggleSelect(item.file_id)
    return
  }
  // 已有选中时：切换选中状态
  if (selectedIds.value.size > 0) {
    toggleSelect(item.file_id)
    return
  }
  // 点击目录：进入
  if (item.is_dir) {
    enterDir(item)
  }
}

// ==================== 整理视图 ====================

/** 加载所有已整理文件并构建文件管理器视图（只显示已整理的文件） */
async function loadOrganized() {
  loadingOrganized.value = true
  try {
    const res = await shareApi.getAllOrganized()
    if (res.code === 0 && res.data) {
      allOrganizedFiles.value = res.data.organized || []
      // 重置到根目录
      organizedCurrentPath.value = ''
      organizedBreadcrumbs.value = [{ path: '', name: '根目录' }]
      buildOrganizedEntries('')
    } else {
      allOrganizedFiles.value = []
      allOrganizedEntries.value = []
    }
  } catch (e) {
    console.error('加载整理视图失败:', e)
    allOrganizedFiles.value = []
    allOrganizedEntries.value = []
  } finally {
    loadingOrganized.value = false
  }
}

/**
 * 根据当前路径，从 allOrganizedFiles 中提取当前层级的目录和文件
 * 完整路径 = category/organized_dir/organized_name
 * 目录排前面，文件排后面
 */
function buildOrganizedEntries(currentPath: string) {
  const dirs = new Map<string, { fileCount: number; totalSize: number }>()
  const files: OrganizedEntry[] = []

  for (const file of allOrganizedFiles.value) {
    // 拼接完整目录路径：category/organized_dir
    const cat = file.category || ''
    const orgDir = file.organized_dir || ''
    const fullDir = cat && orgDir ? `${cat}/${orgDir}` : (cat || orgDir)

    if (!currentPath) {
      // 根目录：取第一层目录名
      const parts = fullDir.split('/').filter(Boolean)
      if (parts.length > 0) {
        const dirName = parts[0]
        const existing = dirs.get(dirName) || { fileCount: 0, totalSize: 0 }
        existing.fileCount++
        existing.totalSize += file.size || 0
        dirs.set(dirName, existing)
      }
    } else if (fullDir === currentPath) {
      // 当前目录直属文件（非子目录）：fullDir 与 currentPath 完全相等
      files.push({
        name: file.organized_name || file.name,
        path: fullDir + '/' + (file.organized_name || file.name),
        isDir: false,
        file,
      })
    } else if (fullDir.startsWith(currentPath + '/')) {
      // 子目录：取下一层
      const remaining = fullDir.slice(currentPath.length + 1)
      const parts = remaining.split('/').filter(Boolean)
      if (parts.length > 0) {
        // 还有子目录
        const dirName = parts[0]
        const fullPath = currentPath + '/' + dirName
        const existing = dirs.get(fullPath) || { fileCount: 0, totalSize: 0 }
        existing.fileCount++
        existing.totalSize += file.size || 0
        dirs.set(fullPath, existing)
      }
    }
  }

  // 构建目录条目
  const entries: OrganizedEntry[] = []
  for (const [path, info] of dirs) {
    const name = path.split('/').pop() || path
    entries.push({
      name,
      path,
      isDir: true,
      fileCount: info.fileCount,
      totalSize: info.totalSize,
    })
  }

  // 目录排前面，文件排后面
  entries.sort((a, b) => a.name.localeCompare(b.name))
  files.sort((a, b) => a.name.localeCompare(b.name))
  allOrganizedEntries.value = [...entries, ...files]
  organizedCurrentPage.value = 1 // 重置到第一页
}

/** 进入子目录 */
function enterOrganizedDir(entry: OrganizedEntry) {
  if (!entry.isDir) return
  organizedCurrentPath.value = entry.path
  organizedBreadcrumbs.value.push({ path: entry.path, name: entry.name })
  buildOrganizedEntries(entry.path)
}

/** 面包屑点击导航 */
function navigateOrganizedTo(targetPath: string) {
  if (targetPath === organizedCurrentPath.value) return
  organizedCurrentPath.value = targetPath
  // 截断面包屑到目标位置
  const idx = organizedBreadcrumbs.value.findIndex(b => b.path === targetPath)
  if (idx >= 0) {
    organizedBreadcrumbs.value = organizedBreadcrumbs.value.slice(0, idx + 1)
  }
  buildOrganizedEntries(targetPath)
}

// ==================== 搜索 ====================

/** 搜索文件 */
async function handleSearch() {
  const keyword = searchKeyword.value.trim()
  if (!keyword) return

  isSearching.value = true
  selectedIds.value = new Set()
  // 根据当前视图设置对应的 loading 状态
  if (viewMode.value === 'organized') {
    loadingOrganized.value = true
  } else {
    loadingFiles.value = true
  }
  try {
    const res = await shareApi.searchFiles(keyword)
    if (res.code === 0 && res.data) {
      const files = res.data.files || []
      if (viewMode.value === 'organized') {
        // 整理视图搜索：只保留已整理文件，按整理结构展示
        allOrganizedFiles.value = files.filter(f => f.organized)
        // 计算匹配文件的公共父目录，直接跳转到该目录
        // 场景：搜"同乐者"匹配到某剧的所有集，跳转到该剧目录而非从根目录开始
        const targetPath = computeOrganizedSearchPath(allOrganizedFiles.value)
        organizedCurrentPath.value = targetPath
        buildOrganizedBreadcrumbs(targetPath)
        buildOrganizedEntries(targetPath)
      } else {
        // 原始视图搜索：结果赋给 allFiles，目录优先（后端已排序）
        allFiles.value = files
      }
      if (files.length === 0) {
        showToast('未找到匹配的文件', 'info')
      }
    } else {
      allFiles.value = []
      showToast(res.message || '搜索失败', 'error')
    }
  } catch (e: any) {
    console.error('搜索失败:', e)
    allFiles.value = []
    handleApiError(e, '搜索失败')
  } finally {
    loadingFiles.value = false
    loadingOrganized.value = false
  }
}

/**
 * 计算整理视图搜索结果的目标跳转路径
 *
 * 规则：
 * - 收集所有匹配文件的完整目录路径（category/organized_dir）
 * - 计算公共前缀
 * - 如果所有文件在同一目录（公共前缀等于每个路径）：
 *   - 电视剧：最后一段是 Season 目录（如 Season 01），跳转到父目录显示季目录列表
 *   - 电影：最后一段是电影目录，跳转到该目录本身显示文件
 * - 多个不同目录，跳转到公共前缀
 */
function computeOrganizedSearchPath(files: ShareFile[]): string {
  // 拼接完整目录路径：category/organized_dir
  const fullDirs = files.map(f => {
    const cat = f.category || ''
    const orgDir = f.organized_dir || ''
    return cat && orgDir ? `${cat}/${orgDir}` : (cat || orgDir)
  }).filter(Boolean)

  if (fullDirs.length === 0) return ''

  // 计算公共前缀
  const splitPaths = fullDirs.map(p => p.split('/'))
  const common: string[] = []
  for (let i = 0; i < splitPaths[0].length; i++) {
    const seg = splitPaths[0][i]
    if (splitPaths.every(sp => sp[i] === seg)) {
      common.push(seg)
    } else {
      break
    }
  }
  const commonPath = common.join('/')

  // 所有文件在同一目录
  if (commonPath && fullDirs.every(p => p === commonPath)) {
    const parts = commonPath.split('/')
    const lastSeg = parts[parts.length - 1] || ''
    // 电视剧：最后一段是 Season 目录，跳转到父目录显示季目录列表
    if (/^season\s*\d+/i.test(lastSeg)) {
      parts.pop()
      return parts.join('/')
    }
    // 电影：跳转到该目录本身，直接显示文件
    return commonPath
  }
  // 多个不同目录：跳转到公共前缀
  return commonPath
}

/** 根据目标路径构建整理视图面包屑 */
function buildOrganizedBreadcrumbs(targetPath: string) {
  const crumbs = [{ path: '', name: '根目录' }]
  if (targetPath) {
    let current = ''
    for (const part of targetPath.split('/').filter(Boolean)) {
      current = current ? `${current}/${part}` : part
      crumbs.push({ path: current, name: part })
    }
  }
  organizedBreadcrumbs.value = crumbs
}

/** 清除搜索 */
function clearSearch() {
  searchKeyword.value = ''
  isSearching.value = false
  if (viewMode.value === 'organized') {
    loadOrganized()
  } else {
    loadFiles()
  }
}

// ==================== 多选 ====================

/** 切换单个文件选中 */
function toggleSelect(fileId: string) {
  const s = new Set(selectedIds.value)
  if (s.has(fileId)) {
    s.delete(fileId)
  } else {
    s.add(fileId)
  }
  selectedIds.value = s
}

/** 全选/取消全选（基于筛选后的文件列表） */
function toggleSelectAll() {
  if (isAllSelected.value) {
    const s = new Set(selectedIds.value)
    filteredFiles.value.forEach(f => s.delete(f.file_id))
    selectedIds.value = s
  } else {
    const s = new Set(selectedIds.value)
    filteredFiles.value.forEach(f => s.add(f.file_id))
    selectedIds.value = s
  }
}

/** 清除选择 */
function clearSelection() {
  selectedIds.value = new Set()
}

// ==================== 识别/整理 ====================

/** 单个文件识别：点击行内"识别"按钮 → 打开识别弹窗 */
async function handleOrganize(item: ShareFile) {
  recognizeItem.value = item
  // 记录待整理文件（单个）
  pendingOrganizeIds.value = [{ sourceId: item.source_id, fileId: item.file_id }]
  // 打开弹窗并自动调用识别
  showRecognizeModal.value = true
  await callRecognize(item.source_id, item.file_id)
}

/** 批量删除分享：收集选中文件对应的分享来源（去重），弹出确认 */
function handleBatchDelete() {
  if (selectedIds.value.size === 0) return
  // 收集选中文件对应的 source_id（去重）
  const sourceIdSet = new Set<number>()
  for (const file of filteredFiles.value) {
    if (selectedIds.value.has(file.file_id)) {
      sourceIdSet.add(file.source_id)
    }
  }
  if (sourceIdSet.size === 0) return
  // 复用单条删除确认弹窗（多条时显示数量）
  deletingShareId.value = null
  deletingBatchIds.value = Array.from(sourceIdSet)
  deletingShareName.value = sourceIdSet.size === 1
    ? (sources.value.find(s => s.id === sourceIdSet.values().next().value)?.share_name || '未命名分享')
    : `选中的 ${sourceIdSet.size} 个分享`
  showDeleteConfirm.value = true
}

/** 调用后端识别 API（只识别不写入数据库） */
async function callRecognize(sourceId: number, fileId: string) {
  recognizeLoading.value = true
  recognizeResult.value = null
  organizeExecError.value = ''
  organizeExecSuccess.value = ''
  manualError.value = ''
  manualOverride.value = false
  organizeExecuting.value = false

  try {
    const res = await shareApi.recognizeFile(sourceId, fileId)
    if (res.code === 0 && res.data) {
      recognizeResult.value = res.data
      manualTmdbId.value = res.data.tmdb_id ? String(res.data.tmdb_id) : ''
      manualMediaType.value = res.data.media_type === 'tv' ? 'tv' : 'movie'
    } else {
      recognizeResult.value = null
    }
  } catch (e) {
    console.error('识别失败:', e)
    recognizeResult.value = null
  } finally {
    recognizeLoading.value = false
  }
}

/** 关闭识别弹窗 */
function closeRecognizeModal() {
  showRecognizeModal.value = false
  recognizeResult.value = null
  recognizeItem.value = null
  recognizeLoading.value = false
  organizeExecError.value = ''
  organizeExecSuccess.value = ''
  manualTmdbId.value = ''
  manualMediaType.value = 'movie'
  manualError.value = ''
  manualLoading.value = false
  manualOverride.value = false
  organizeExecuting.value = false
  // 重置进度状态并关闭 SSE 连接
  organizeProgressTotal.value = 0
  organizeProgressIndex.value = 0
  organizeProgressName.value = ''
  organizeProgressSuccess.value = 0
  organizeProgressFailed.value = 0
  organizeProgressDone.value = false
  if (organizeEventSource) {
    organizeEventSource.close()
    organizeEventSource = null
  }
}

/**
 * 分享文件手动识别入口
 * 与 RecognizeModal 中的普通文件识别不同，此处针对已整理的分享文件，
 * 允许用户手动指定 TMDB ID 和媒体类型进行纠错。
 */
async function manualRecognizeShare() {
  if (!recognizeItem.value) return
  const tmdbId = Number(manualTmdbId.value)
  if (!Number.isInteger(tmdbId) || tmdbId <= 0) {
    manualError.value = '请输入正确的 TMDB ID'
    return
  }

  manualLoading.value = true
  manualError.value = ''
  organizeExecError.value = ''
  organizeExecSuccess.value = ''
  try {
    const res = await shareApi.manualRecognizeFile(
      recognizeItem.value.source_id,
      recognizeItem.value.file_id,
      tmdbId,
      manualMediaType.value
    )
    if (res.code === 0 && res.data) {
      recognizeResult.value = res.data
      manualTmdbId.value = String(res.data.tmdb_id || tmdbId)
      manualMediaType.value = res.data.media_type === 'tv' ? 'tv' : 'movie'
      manualOverride.value = true
    } else {
      manualError.value = res.message || '手动识别失败'
    }
  } catch (e: any) {
    manualError.value = e.message || '手动识别失败'
  } finally {
    manualLoading.value = false
  }
}

/** 执行整理（点击"开始整理"按钮）—— 使用 SSE 流式推送实时进度 */
async function executeOrganize() {
  if (pendingOrganizeIds.value.length === 0) return

  // 重置执行状态与进度
  organizeExecuting.value = true
  organizeExecError.value = ''
  organizeExecSuccess.value = ''
  organizeProgressTotal.value = pendingOrganizeIds.value.length
  organizeProgressIndex.value = 0
  organizeProgressName.value = ''
  organizeProgressSuccess.value = 0
  organizeProgressFailed.value = 0
  organizeProgressDone.value = false

  try {
    // 按 source_id 分组批量调用
    const groups = new Map<number, string[]>()
    for (const item of pendingOrganizeIds.value) {
      const arr = groups.get(item.sourceId) || []
      arr.push(item.fileId)
      groups.set(item.sourceId, arr)
    }

    let successCount = 0
    let failCount = 0

    for (const [sourceId, fileIds] of groups) {
      // 手动纠错（单文件）：走 axios 调用 manualOrganizeFile，不走 SSE
      if (manualOverride.value && pendingOrganizeIds.value.length === 1) {
        organizeProgressName.value = recognizeItem.value?.name || fileIds[0]
        const tmdbId = Number(manualTmdbId.value)
        try {
          const res = await shareApi.manualOrganizeFile(sourceId, fileIds[0], tmdbId, manualMediaType.value)
          const ok = res.code === 0
          if (ok) successCount += 1
          else failCount += 1
        } catch (e: any) {
          failCount += 1
        }
        organizeProgressIndex.value += 1
        organizeProgressSuccess.value = successCount
        organizeProgressFailed.value = failCount
        continue
      }

      // 批量整理：用 EventSource 监听 SSE 流式进度
      await runOrganizeStream(sourceId, fileIds, (evt) => {
        if (evt.type === 'progress') {
          // 用后端推送的 total/index（文件夹已展开为真实文件数），覆盖前端初始值
          organizeProgressTotal.value = evt.total
          organizeProgressIndex.value = evt.index
          organizeProgressName.value = evt.name
          if (evt.success) successCount += 1
          else failCount += 1
          organizeProgressSuccess.value = successCount
          organizeProgressFailed.value = failCount
        }
      })
    }

    organizeProgressDone.value = true
    if (failCount === 0) {
      organizeExecSuccess.value = `${successCount} 个文件整理完成`
    } else {
      organizeExecError.value = `${successCount} 成功，${failCount} 失败`
    }

    // 刷新文件列表（保持当前标签/面包屑/页码，避免整理后被切回"全部"）
    clearSelection()
    await reloadCurrentFiles()
  } catch (e: any) {
    organizeExecError.value = e.message || '整理失败'
  } finally {
    organizeExecuting.value = false
    // 关闭 EventSource 连接
    if (organizeEventSource) {
      organizeEventSource.close()
      organizeEventSource = null
    }
  }
}

/**
 * 用 EventSource 调用 SSE 流式整理端点，Promise 包装便于 await
 * @param sourceId 分享来源 ID
 * @param fileIds 文件 ID 列表
 * @param onProgress 收到 progress 事件时的回调
 */
function runOrganizeStream(
  sourceId: number,
  fileIds: string[],
  onProgress: (evt: any) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    // 关闭旧的连接（如有）
    if (organizeEventSource) {
      organizeEventSource.close()
    }
    const es = shareApi.organizeStream(sourceId, fileIds)
    organizeEventSource = es

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'progress') {
          onProgress(data)
        } else if (data.type === 'done') {
          es.close()
          organizeEventSource = null
          resolve()
        } else if (data.type === 'error') {
          es.close()
          organizeEventSource = null
          reject(new Error(data.message || '整理失败'))
        }
      } catch (err) {
        // JSON 解析失败，忽略此条消息
        console.error('SSE 消息解析失败:', err)
      }
    }
    es.onerror = () => {
      // 浏览器自动重连可能会触发 onerror，若已完成或连接已关闭则视为正常结束
      if (organizeProgressDone.value || es.readyState === EventSource.CLOSED) {
        es.close()
        organizeEventSource = null
        resolve()
      } else {
        // 流式过程中发生错误且未完成：必须 reject，否则 Promise 永远悬挂
        es.close()
        organizeEventSource = null
        reject(new Error('整理流连接异常，请重试'))
      }
    }
  })
}

// ==================== 工具函数 ====================
// formatSize / formatTime 已统一抽至 @/composables/useFormat，保证各视图行为一致
</script>

<style scoped>
/* ==================== 基础布局 ==================== */
.share {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  font-family: var(--font-sans);
  overflow: hidden; /* 不允许整个页面滚动 */
}

/* ==================== 文件视图区域 ==================== */
.file-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden; /* 不允许内容溢出，子元素内部滚动 */
  min-height: 0; /* 防止flex子元素溢出 */
}

/* 无分享时的空态提示 */
.empty-prompt {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border-radius: var(--radius-lg);
  color: var(--text-tertiary);
}

.empty-prompt .empty-icon {
  width: 56px;
  height: 56px;
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-prompt .empty-icon svg {
  width: 28px;
  height: 28px;
  stroke: var(--text-tertiary);
}

.empty-prompt .empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-prompt .empty-desc {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* ==================== 工具栏 ==================== */
.toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

/* 视图切换按钮组 */
.view-switch {
  display: flex;
  gap: 2px;
  background: var(--bg-input);
  box-shadow: var(--neu-inset);
  border-radius: var(--radius-sm);
  padding: 2px;
}

.view-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--transition-base);
}

.view-btn:hover {
  color: var(--text-secondary);
}

.view-btn.active {
  background: var(--bg-solid);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

.view-btn svg {
  width: 14px;
  height: 14px;
}

/* 筛选按钮组 */
.filter-group {
  display: flex;
  gap: 2px;
  background: var(--bg-input);
  box-shadow: var(--neu-inset);
  border-radius: var(--radius-sm);
  padding: 2px;
}

.filter-btn {
  padding: 4px 10px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--transition-base);
}

.filter-btn:hover {
  color: var(--text-secondary);
}

.filter-btn.active {
  background: var(--bg-solid);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

/* Tab 计数徽章 */
.filter-count {
  display: inline-block;
  margin-left: 4px;
  padding: 0 5px;
  min-width: 16px;
  font-size: 10px;
  font-weight: 600;
  line-height: 14px;
  text-align: center;
  color: var(--text-tertiary);
  background: var(--bg-hover);
  border-radius: 8px;
}

.filter-btn.active .filter-count {
  color: var(--accent);
  background: var(--accent-bg);
}

.toolbar-spacer {
  flex: 1;
}

/* 工具栏按钮 */
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

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toolbar-btn svg {
  width: 16px;
  height: 16px;
}

.toolbar-btn.danger {
  color: var(--danger);
}

.toolbar-btn.danger:hover {
  background: var(--danger-bg);
}

.toolbar-btn.ghost {
  color: var(--text-tertiary);
}

.toolbar-btn.ghost:hover {
  color: var(--text-secondary);
  background: var(--bg-hover);
}

/* 搜索框 */
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

/* 选中计数 */
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

/* ==================== 文件列表容器 ==================== */
.file-list-container {
  flex: 1;
  border-radius: var(--radius-lg);
  overflow: hidden; /* 外层不滚动 */
  display: flex;
  flex-direction: column;
  min-height: 0; /* 防止 flex 子元素溢出 */
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

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state .empty-icon {
  width: 56px;
  height: 56px;
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-state .empty-icon svg {
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

/* ==================== 文件表格 ==================== */
.file-table {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto; /* 滚动在表格内 */
  overflow-x: hidden;
  border-radius: var(--radius-lg);
  min-height: 0; /* 关键：允许flex子元素正确计算高度 */
}

/* 目录导航面包屑 */
.dir-breadcrumb {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.breadcrumb-btn {
  display: inline-flex;
  align-items: center;
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px 6px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  transition: all var(--transition-fast);
}

.breadcrumb-btn:hover {
  color: var(--accent);
  background: var(--accent-bg);
}

.breadcrumb-btn svg {
  width: 14px;
  height: 14px;
}

.breadcrumb-sep {
  color: var(--text-tertiary);
  margin: 0 2px;
}

.breadcrumb-current {
  color: var(--text-primary);
  font-weight: 500;
  padding: 4px 6px;
}

/* 表头 */
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

.table-body {
  flex: 1;
  /* 不需要滚动，由父容器 .file-list-container 控制 */
  overflow: visible;
  min-height: 0; /* 允许内容正确计算高度 */
}

/* 文件行 */
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

.table-row:hover {
  background: var(--bg-hover);
}

.table-row.selected {
  background: var(--bg-selected);
  box-shadow: inset 3px 0 0 var(--accent);
}

.table-row:last-child {
  border-bottom: none;
}

/* ==================== 列定义 ==================== */
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

/* 统一列基类：表头和内容共用，确保严格对齐 */
.tbl-col {
  flex-shrink: 0;
  padding: 0 12px;
  box-sizing: border-box;
}

.tbl-col-count {
  width: 80px;
  text-align: left;
}

.tbl-col-organized {
  flex: 1;
  min-width: 200px;
  text-align: left;
  overflow: hidden;
}

.organized-name {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tbl-col-size {
  width: 100px;
  text-align: left;
}

.tbl-col-status {
  width: 90px;
  text-align: left;
}

.tbl-col-link {
  width: 80px;
  text-align: left;
}

.tbl-col-time {
  width: 130px;
  text-align: left;
}

.count-badge {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--bg-hover);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.status-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.status-yes {
  background: var(--success-bg);
  color: var(--success);
}

.status-no {
  background: var(--bg-hover);
  color: var(--text-tertiary);
}

/* 链接有效性标签（仅有效/无效两种状态，无中间态） */
.link-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}
.link-valid {
  background: var(--success-bg);
  color: var(--success);
}
.link-invalid {
  background: var(--danger-bg);
  color: var(--danger);
}

/* 检测链接按钮 */
.btn-check-links {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--transition-base);
  white-space: nowrap;
}
.btn-check-links:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--accent);
  color: var(--accent);
}
.btn-check-links:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-check-links svg {
  width: 16px;
  height: 16px;
}
.icon-spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

.col-action {
  width: 70px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ==================== 复选框 ==================== */
.checkbox-wrapper {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  width: 18px;
  height: 18px;
}

.checkbox-wrapper input {
  display: none;
}

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

.icon-folder {
  width: 20px;
  height: 20px;
  color: var(--folder);
}

.icon-file {
  width: 18px;
  height: 18px;
  color: var(--text-tertiary);
}

.file-name {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 400;
}

.file-count-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  background: var(--bg-hover);
  padding: 1px 6px;
  border-radius: var(--radius-full);
  margin-left: 6px;
  flex-shrink: 0;
}

.file-size {
  font-size: 12px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.file-time {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

/* ==================== 更多按钮（新拟态圆形，和文件管理一致） ==================== */
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

/* ==================== 行操作下拉菜单 ==================== */
.row-menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
}

.row-menu {
  min-width: 140px;
  padding: 4px;
  border-radius: var(--radius-md);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
}

.row-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text-primary);
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.row-menu-item:hover {
  background: var(--bg-hover);
}

.row-menu-item svg {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
}

.row-menu-divider {
  height: 1px;
  background: var(--border);
  margin: 4px 8px;
}

.row-menu-danger {
  color: var(--danger);
}

.row-menu-danger:hover {
  background: var(--danger-bg);
}

.btn-organize svg {
  width: 14px;
  height: 14px;
}

/* ==================== 分页器（新拟态按钮） ==================== */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 12px 0; /* 左右padding改为0，与glass-card边缘对齐 */
  margin: 0 16px; /* 用margin控制左右间距，让border-top延伸到边缘 */
  border-top: none; /* 移除border-top，避免与最后一行的border-bottom重复 */
  flex-shrink: 0;
  background: var(--bg-primary); /* 固定背景，不透明 */
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

/* ==================== 整理视图：文件管理器风格 ==================== */
.organized-view {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%; /* 确保占满高度 */
  overflow: hidden; /* 不允许整个视图溢出 */
}

/* 面包屑导航栏 */
.breadcrumb-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

/* 返回上级按钮 */
.btn-back {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  flex-shrink: 0;
  transition: all var(--transition-base);
}

.btn-back:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.btn-back svg {
  width: 16px;
  height: 16px;
}

/* 面包屑路径 */
.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  overflow: hidden;
}

.crumb {
  cursor: pointer;
  color: var(--text-tertiary);
  white-space: nowrap;
  transition: color var(--transition-fast);
}

.crumb:hover {
  color: var(--accent);
}

.crumb.active {
  color: var(--text-primary);
  font-weight: 600;
  cursor: default;
}

.crumb.active:hover {
  color: var(--text-primary);
}

.crumb-sep {
  color: var(--text-tertiary);
  margin: 0 2px;
  opacity: 0.5;
}

/* 整理视图表格列 */
.col-count {
  width: 80px;
  flex-shrink: 0;
  padding-left: 16px;
  text-align: left;
}

/* 可点击的目录行 */
.table-row.clickable {
  cursor: pointer;
}

.table-row.clickable:hover {
  background: var(--bg-hover);
}

/* 文件数徽章 */
.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  background: var(--accent-bg);
  color: var(--accent);
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 600;
}

/* 原始文件名 */
.original-name {
  color: var(--text-tertiary);
  font-size: 10px;
}

/* ==================== 删除确认弹窗 ==================== */
.modal-card {
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 420px;
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

/* 次要按钮 */
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

.btn-danger:hover {
  opacity: 0.9;
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

  .view-btn span {
    display: none;
  }

  .filter-btn {
    padding: 4px 8px;
    font-size: 11px;
  }

  .tbl-col-time {
    display: none;
  }

  .col-action {
    width: 50px;
  }

  .btn-more {
    opacity: 1;
  }

  .share-recognize-modal {
    max-width: 100%;
    max-height: 100vh;
    border-radius: 0;
  }

  .sr-poster {
    width: 80px;
    height: 120px;
  }

  .sr-title {
    font-size: 17px;
  }

  .sr-result {
    padding: 12px 16px 20px;
  }
}

/* ==================== 分享识别弹窗样式（sr- 前缀，独立不冲突） ==================== */

/* 弹窗容器：圆角 + overflow 裁剪，内部 flex 三段式 */
.share-recognize-modal {
  position: relative;
  width: 100%;
  max-width: 520px;
  max-height: 90vh;
  border-radius: var(--radius-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--bg-solid);
}

/* 关闭按钮 */
.sr-close {
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
  border: none;
  border-radius: 50%;
}

.sr-close:hover {
  background: color-mix(in srgb, black 50%, transparent);
}

.sr-close svg {
  width: 16px;
  height: 16px;
}

/* Hero 区域：和 RecognizeModal 完全一致 */
.sr-hero {
  position: relative;
  flex-shrink: 0;
  min-height: 200px;
  display: flex;
  align-items: flex-end;
  overflow: hidden;
}

.sr-hero-bg {
  position: absolute;
  inset: 0;
}

.sr-hero-bg img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 无背景图时的渐变占位 */
.sr-hero-placeholder {
  background: linear-gradient(135deg, var(--accent) 0%, var(--purple) 100%);
}

/* 渐变遮罩 */
.sr-hero-mask {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to top,
    var(--bg-solid) 0%,
    color-mix(in srgb, var(--bg-solid) 60%, transparent) 40%,
    color-mix(in srgb, black 15%, transparent) 100%
  );
}

.sr-hero-content {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-end;
  gap: 16px;
  padding: 0 24px 20px;
  width: 100%;
}

/* 海报：和 RecognizeModal 一致 */
.sr-poster {
  width: 100px;
  height: 150px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--bg-hover);
}

.sr-poster-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.sr-poster-empty {
  display: flex;
  align-items: center;
  justify-content: center;
}

.sr-poster-empty svg {
  width: 32px;
  height: 32px;
  color: var(--text-tertiary);
}

.sr-poster-skeleton {
  animation: sr-pulse 1.5s ease-in-out infinite;
}

/* 标题信息 */
.sr-hero-info {
  flex: 1;
  min-width: 0;
  padding-bottom: 4px;
}

.sr-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.sr-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sr-meta-type {
  font-size: 12px;
  font-weight: 600;
  color: var(--purple);
  background: var(--purple-bg);
  padding: 2px 10px;
  border-radius: var(--radius-full);
}

.sr-meta-year {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.sr-meta-rating {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--warning);
}

.sr-meta-rating svg {
  width: 14px;
  height: 14px;
}

/* 骨架屏 */
.sr-skeleton {
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  animation: sr-pulse 1.5s ease-in-out infinite;
}

.sr-skeleton-title {
  height: 22px;
  width: 70%;
  margin-bottom: 8px;
}

.sr-skeleton-meta {
  height: 16px;
  width: 40%;
}

@keyframes sr-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 内容区（flex:1 可滚动，中间区域） */
.sr-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

/* 加载中 */
.sr-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: var(--text-tertiary);
}

/* 无结果 */
.sr-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 20px;
  color: var(--text-tertiary);
}

.sr-empty svg {
  width: 40px;
  height: 40px;
}

.sr-empty p {
  font-size: 14px;
  margin: 0;
}

/* 识别结果 */
.sr-result {
  padding: 16px 24px 24px;
}

.sr-batch-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  background: var(--bg-hover);
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  margin-bottom: 12px;
}

/* 标签 */
.sr-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.sr-tag {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-full);
}

.sr-tag-cat {
  color: var(--accent);
  background: var(--accent-bg);
}

.sr-tag-id {
  color: var(--text-secondary);
  background: var(--bg-hover);
  font-family: var(--font-mono);
  font-weight: 500;
}

/* 分区 */
.sr-section {
  margin-bottom: 16px;
}

.sr-section:last-child {
  margin-bottom: 0;
}

.sr-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

/* 手动纠错 */
.sr-manual-box {
  padding: 12px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.sr-manual-row {
  display: flex;
  gap: 8px;
}

.sr-manual-select,
.sr-manual-input {
  height: 34px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  padding: 0 10px;
  font-size: 13px;
}

.sr-manual-input {
  flex: 1;
  min-width: 0;
}

.sr-manual-btn {
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

.sr-manual-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 技术标签 */
.sr-tech-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sr-tech {
  padding: 4px 10px;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.sr-tech-source {
  color: var(--accent);
  background: var(--accent-bg);
}

.sr-tech-edition {
  color: var(--warning);
  background: var(--warning-bg);
}

.sr-tech-group {
  color: var(--purple);
  background: var(--purple-bg);
}

/* 目标路径 */
.sr-path {
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

.sr-path-dir {
  color: var(--text-tertiary);
}

.sr-path-file {
  color: var(--text-primary);
  font-weight: 500;
}

/* 简介 */
.sr-overview {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  max-height: 120px;
  overflow-y: auto;
  margin: 0;
}

/* 底部操作栏（固定不滚动） */
.sr-footer {
  flex-shrink: 0;
  padding: 12px 24px 20px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sr-footer-msg {
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
}

.sr-footer-error {
  background: var(--danger-bg);
  color: var(--danger);
}

.sr-footer-success {
  background: var(--success-bg);
  color: var(--success);
}

/* 整理按钮 */
.sr-btn-organize {
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

.sr-btn-organize:hover:not(:disabled) {
  background: var(--accent-hover);
}

.sr-btn-organize:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sr-btn-organize svg {
  width: 16px;
  height: 16px;
}

.sr-btn-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border);
  border-top-color: var(--text-inverse);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* ==================== 整理进度面板样式 ==================== */

.sr-progress-panel {
  padding: 14px 16px;
  border-radius: var(--radius-md);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 进度条 + 百分比 */
.sr-progress-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sr-progress-bar-wrap {
  flex: 1;
  height: 8px;
  background: var(--bg-secondary, rgba(0, 0, 0, 0.06));
  border-radius: 4px;
  overflow: hidden;
}

.sr-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent-hover, var(--accent)));
  border-radius: 4px;
  transition: width 0.4s ease;
  position: relative;
}

/* 进度条流光动画（整理中才显示） */
.sr-progress-bar::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.4), transparent);
  animation: sr-progress-shine 1.5s infinite;
}

@keyframes sr-progress-shine {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.sr-progress-percent {
  font-size: 13px;
  font-weight: 700;
  color: var(--accent);
  min-width: 38px;
  text-align: right;
}

/* 计数统计行 */
.sr-progress-stats {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sr-stat-text {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 600;
}

.sr-stat-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.sr-stat-badge svg {
  width: 12px;
  height: 12px;
}

.sr-stat-success {
  background: var(--success-bg);
  color: var(--success);
}

.sr-stat-fail {
  background: var(--danger-bg);
  color: var(--danger);
}

.sr-stat-current {
  font-size: 11px;
  color: var(--text-secondary);
  margin-left: auto;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ==================== 属性信息弹窗样式（props- 前缀，独立不冲突） ==================== */

/* 弹窗容器：三段式布局（标题 / 内容 / 底部） */
.props-modal {
  position: relative;
  width: 100%;
  max-width: 560px;
  max-height: 85vh;
  border-radius: var(--radius-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--bg-solid);
}

/* 标题栏 */
.props-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.props-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.props-title svg {
  width: 18px;
  height: 18px;
  color: var(--accent);
}

.props-close {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  border-radius: 50%;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.props-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.props-close svg {
  width: 16px;
  height: 16px;
}

/* 内容区：可滚动 */
.props-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

/* 加载状态 */
.props-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 0;
  color: var(--text-tertiary);
}

/* 分区 */
.props-section {
  margin-bottom: 24px;
}

.props-section:last-child {
  margin-bottom: 0;
}

.props-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}

/* 字段网格：两列布局 */
.props-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px 16px;
}

/* 单个字段 */
.props-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.props-label {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* 可编辑输入框 */
.props-input {
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 13px;
  transition: border-color var(--transition-fast);
}

.props-input:focus {
  outline: none;
  border-color: var(--accent);
}

/* 下拉框 */
.props-select {
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: border-color var(--transition-fast);
}

.props-select:focus {
  outline: none;
  border-color: var(--accent);
}

/* 只读字段值 */
.props-field-readonly .props-value {
  height: 34px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  color: var(--text-primary);
  font-size: 13px;
}

/* 媒体类型标签 */
.props-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.props-tag-movie {
  background: rgba(0, 113, 227, 0.12);
  color: var(--accent);
}

.props-tag-tv {
  background: rgba(52, 199, 89, 0.12);
  color: #34c759;
}

/* 底部操作栏 */
.props-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
}

.props-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 72px;
  height: 34px;
  padding: 0 16px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--transition-fast), opacity var(--transition-fast);
}

.props-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.props-btn-cancel {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.props-btn-cancel:hover:not(:disabled) {
  background: var(--border);
}

.props-btn-save {
  background: var(--accent);
  color: #fff;
}

.props-btn-save:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 88%, black);
}

/* 保存按钮加载小圆圈 */
.props-btn-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* 小屏适配：单列布局 */
@media (max-width: 540px) {
  .props-modal {
    max-width: 100%;
    max-height: 100vh;
    border-radius: 0;
  }

  .props-grid {
    grid-template-columns: 1fr;
  }
}
</style>
