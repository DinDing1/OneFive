<template>
  <div class="settings">
    <!-- 115 开放平台 -->
    <section class="card glass-card">
      <div class="card-head" @click="toggle('api')">
        <div class="card-head-left">
          <div class="card-icon api-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
          </div>
          <div class="card-title">
            <h3>115 开放平台</h3>
            <p>Open API 接入</p>
          </div>
        </div>
        <svg class="chevron" :class="{ open: expanded.api }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div class="card-body" v-show="expanded.api">
        <div class="field field-row">
          <label>启用 Open API</label>
          <label class="toggle">
            <input type="checkbox" v-model="openApiEnabled" @change="saveOpenApiSettings" />
            <span class="slider"></span>
          </label>
        </div>
        <div class="field">
          <label>AppID</label>
          <select v-model="selectedAppId" :disabled="!openApiEnabled" @change="saveOpenApiSettings">
            <option value="">请选择应用</option>
            <option v-for="app in appIds" :key="app.value" :value="app.value">{{ app.label }}</option>
          </select>
        </div>
        <div class="field field-row">
          <label>Token 状态</label>
          <span class="badge" :class="tokenValid ? 'badge-ok' : 'badge-warn'">
            {{ tokenValid ? '已获取' : '未获取' }}
          </span>
        </div>
      </div>
    </section>

    <!-- TMDB 识别 -->
    <section class="card glass-card">
      <div class="card-head" @click="toggle('tmdb')">
        <div class="card-head-left">
          <div class="card-icon tmdb-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 12h8M12 8v8"/></svg>
          </div>
          <div class="card-title">
            <h3>TMDB 识别</h3>
            <p>API 连接参数</p>
          </div>
        </div>
        <svg class="chevron" :class="{ open: expanded.tmdb }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div class="card-body" v-show="expanded.tmdb">
        <div class="field">
          <label>API Key</label>
          <div class="password-field">
            <input :type="showApiKey ? 'text' : 'password'" v-model="tmdbApiKey" placeholder="内置默认 Key，可自定义覆盖" />
            <button class="btn-eye" @click="showApiKey = !showApiKey" type="button" :title="showApiKey ? '隐藏' : '显示'">
              <svg v-if="showApiKey" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
            </button>
          </div>
        </div>
        <div class="field">
          <label>代理地址</label>
          <input type="text" v-model="tmdbApiUrl" placeholder="留空使用官方地址" />
        </div>
        <div class="field">
          <label>偏好语言</label>
          <select v-model="tmdbLanguage">
            <option value="zh-CN">简体中文</option>
            <option value="zh-TW">繁体中文</option>
            <option value="ja-JP">日本語</option>
            <option value="ko-KR">한국어</option>
            <option value="en-US">English</option>
          </select>
        </div>
        <div class="card-actions">
          <button class="btn-save" @click.stop="saveTmdbSettings" :disabled="tmdbSaving">
            {{ tmdbSaving ? '...' : '保存' }}
          </button>
        </div>
      </div>
    </section>

    <!-- 媒体整理 -->
    <section class="card glass-card">
      <div class="card-head" @click="toggle('media')">
        <div class="card-head-left">
          <div class="card-icon media-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
          </div>
          <div class="card-title">
            <h3>媒体整理</h3>
            <p>分类 · 重命名 · 发布组</p>
          </div>
        </div>
        <svg class="chevron" :class="{ open: expanded.media }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div class="card-body" v-show="expanded.media">
        <!-- 基础 -->
        <div class="field-group">
          <div class="group-label">基础</div>
          <div class="field field-row">
            <label>整理方式</label>
            <div class="pill-switch" :class="{ copy: organizeMode === 'copy' }" @click="organizeMode = organizeMode === 'move' ? 'copy' : 'move'">
              <span class="pill-label" :class="{ active: organizeMode === 'move' }">移动</span>
              <span class="pill-indicator"></span>
              <span class="pill-label" :class="{ active: organizeMode === 'copy' }">复制</span>
            </div>
          </div>
          <div class="field-grid">
            <div class="field">
              <label>保存路径</label>
              <div class="path-field">
                <span class="path-text" :class="{ 'path-empty': !sourcePath }">{{ sourcePath || '选择目录' }}</span>
                <button class="btn-ghost" @click.stop="openPathPickerFor('source')">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                </button>
              </div>
            </div>
            <div class="field">
              <label>媒体库路径</label>
              <div class="path-field">
                <span class="path-text" :class="{ 'path-empty': !mediaLibraryPath }">{{ mediaLibraryPath || '选择目录' }}</span>
                <button class="btn-ghost" @click.stop="openPathPickerFor('library')">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 重命名模板 -->
        <div class="field-group">
          <div class="group-label">
            重命名模板
            <button class="btn-icon-reset" @click.stop="resetTemplates" title="恢复默认">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            </button>
          </div>
          <div class="field">
            <label>电影</label>
            <input type="text" v-model="movieTemplate" class="mono-input" placeholder="使用内置默认" />
          </div>
          <div class="field">
            <label>电视剧</label>
            <input type="text" v-model="tvTemplate" class="mono-input" placeholder="使用内置默认" />
          </div>
        </div>

        <!-- 分类策略 -->
        <div class="field-group">
          <div class="group-label">
            分类策略
            <button class="btn-icon-reset" @click.stop="resetRules" title="恢复默认">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            </button>
          </div>
          <div class="rules-section">
            <div class="rules-type"><span class="type-tag type-movie">电影</span></div>
            <div class="rule-list">
              <div v-for="(rule, i) in movieRules" :key="'m'+i" class="rule-row">
                <input v-model="rule.category" class="rule-cat" placeholder="分类路径" />
                <input v-model="rule.conditions" class="rule-cond" placeholder="genreIds=16" />
                <button class="btn-icon-sm danger" @click.stop="movieRules.splice(i, 1)" title="删除">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
              <button class="btn-dashed" @click.stop="movieRules.push({category:'', conditions:''})">+ 添加</button>
            </div>
            <div class="rules-type" style="margin-top:12px"><span class="type-tag type-tv">电视剧</span></div>
            <div class="rule-list">
              <div v-for="(rule, i) in tvRules" :key="'t'+i" class="rule-row">
                <input v-model="rule.category" class="rule-cat" placeholder="分类路径" />
                <input v-model="rule.conditions" class="rule-cond" placeholder="genreIds=16,originCountry=JP" />
                <button class="btn-icon-sm danger" @click.stop="tvRules.splice(i, 1)" title="删除">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
              <button class="btn-dashed" @click.stop="tvRules.push({category:'', conditions:''})">+ 添加</button>
            </div>
          </div>
        </div>

        <!-- 发布组 -->
        <div class="field-group">
          <div class="group-label">内置发布组</div>
          <div class="tags-wrap">
            <span v-for="g in builtinReleaseGroups" :key="g" class="tag">{{ g }}</span>
          </div>
        </div>
        <div class="field-group">
          <div class="group-label">补充发布组</div>
          <div class="tag-input-box">
            <span v-for="(g, i) in customGroupsList" :key="i" class="tag tag-custom">
              {{ g }}
              <button @click.stop="removeCustomGroup(i)">×</button>
            </span>
            <input v-model="newGroupName" class="tag-input" placeholder="回车添加" @keydown.enter.prevent="addCustomGroup" />
          </div>
        </div>

        <div class="card-actions">
          <button class="btn-save" @click.stop="saveMediaSettings" :disabled="mediaSaving">
            {{ mediaSaving ? '...' : '保存全部' }}
          </button>
        </div>
      </div>
    </section>

    <!-- 通知设置 -->
    <section class="card glass-card">
      <div class="card-head" @click="toggle('notify')">
        <div class="card-head-left">
          <div class="card-icon notify-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
          </div>
          <div class="card-title">
            <h3>通知设置</h3>
            <p>Telegram 通知渠道配置</p>
          </div>
        </div>
        <svg class="chevron" :class="{ open: expanded.notify }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div class="card-body" v-show="expanded.notify">
        <!-- Telegram 通知 -->
        <div class="sub-card">
          <div class="sub-card-head">
            <div class="sub-card-left">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="sub-card-icon tg-icon"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              <span class="sub-card-title">Telegram</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="tgEnabled" />
              <span class="slider"></span>
            </label>
          </div>

          <div class="sub-card-body" v-if="tgEnabled">
            <!-- Bot 模式 -->
            <div class="mode-row">
              <div class="mode-info">
                <span class="mode-name">Bot 模式</span>
                <span v-if="tgBotName" class="mode-status">{{ tgBotName }}</span>
              </div>
              <label class="toggle toggle-sm">
                <input type="checkbox" v-model="tgBotEnabled" />
                <span class="slider"></span>
              </label>
            </div>
            <div v-if="tgBotEnabled" class="mode-body">
              <div class="field">
                <label>Bot Token</label>
                <div class="password-field">
                  <input :type="showBotToken ? 'text' : 'password'" v-model="tgBotToken" placeholder="从 @BotFather 获取" />
                  <button class="btn-eye" @click="showBotToken = !showBotToken" type="button" :title="showBotToken ? '隐藏' : '显示'">
                    <svg v-if="showBotToken" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                    </svg>
                    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>
                    </svg>
                  </button>
                </div>
              </div>
            </div>

            <!-- 用户模式 -->
            <div class="mode-row">
              <div class="mode-info">
                <span class="mode-name">用户模式</span>
                <span v-if="tgUserName" class="mode-status">{{ tgUserName }}</span>
              </div>
              <label class="toggle toggle-sm">
                <input type="checkbox" v-model="tgUserEnabled" />
                <span class="slider"></span>
              </label>
            </div>
            <div v-if="tgUserEnabled" class="mode-body">
              <div class="field-grid">
                <div class="field">
                  <label>API ID</label>
                  <input type="text" v-model="tgApiId" placeholder="从 my.telegram.org 获取" />
                </div>
                <div class="field">
                  <label>API Hash</label>
                  <div class="password-field">
                    <input :type="showApiHash ? 'text' : 'password'" v-model="tgApiHash" placeholder="从 my.telegram.org 获取" />
                    <button class="btn-eye" @click="showApiHash = !showApiHash" type="button" :title="showApiHash ? '隐藏' : '显示'">
                      <svg v-if="showApiHash" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                      </svg>
                      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
              <div class="field">
                <label>手机号</label>
                <div class="phone-row">
                  <input type="text" v-model="tgPhone" placeholder="+8613800138000" />
                  <button class="btn-ghost-sm" @click.stop="sendCode" :disabled="codeSending || !tgPhone || !tgApiId || !tgApiHash">
                    {{ codeSending ? '...' : '发送验证码' }}
                  </button>
                </div>
              </div>
              <template v-if="codeSent">
                <div class="field">
                  <label>验证码</label>
                  <div class="phone-row">
                    <input type="text" v-model="tgCode" placeholder="输入收到的验证码" />
                    <button class="btn-ghost-sm" @click.stop="signIn" :disabled="signingIn || !tgCode">
                      {{ signingIn ? '...' : '登录' }}
                    </button>
                  </div>
                </div>
                <div class="field">
                  <label>两步验证密码</label>
                  <div class="password-field">
                    <input :type="showPassword ? 'text' : 'password'" v-model="tgPassword" placeholder="如未开启可留空" />
                    <button class="btn-eye" @click="showPassword = !showPassword" type="button" :title="showPassword ? '隐藏' : '显示'">
                      <svg v-if="showPassword" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                      </svg>
                      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>
                      </svg>
                    </button>
                  </div>
                </div>
              </template>
              <div class="login-status" v-if="loginStatus">
                <span :class="loginStatusOk ? 'status-ok' : 'status-warn'">{{ loginStatus }}</span>
              </div>
              <div class="field">
                <label>通知目标</label>
                <input type="text" v-model="tgNotifyChat" placeholder="chat_id 或 @username" />
              </div>
            </div>

            <!-- 代理 -->
            <div class="mode-row">
              <span class="mode-name">代理</span>
              <label class="toggle toggle-sm">
                <input type="checkbox" v-model="tgProxyEnabled" />
                <span class="slider"></span>
              </label>
            </div>
            <div v-if="tgProxyEnabled" class="mode-body">
              <div class="field">
                <label>代理地址</label>
                <input type="text" v-model="tgProxyUrl" placeholder="socks5://user:pass@host:port" />
              </div>
            </div>

            <!-- 权限 -->
            <div class="mode-body">
              <div class="field">
                <label>管理员 ID</label>
                <input type="text" v-model="tgAdminIds" placeholder="多个用逗号分隔，留空不限制" />
              </div>
            </div>
          </div>
        </div>

        <!-- WeChat 通知（预留） -->
        <div class="sub-card sub-card-disabled">
          <div class="sub-card-head">
            <div class="sub-card-left">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="sub-card-icon wx-icon"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>
              <span class="sub-card-title">微信</span>
            </div>
            <span class="sub-card-badge">即将推出</span>
          </div>
        </div>

        <div class="card-actions">
          <button class="btn-ghost-sm" @click.stop="testNotify" :disabled="tgTesting">
            {{ tgTesting ? '...' : '测试' }}
          </button>
          <button class="btn-save" @click.stop="saveNotifySettings" :disabled="notifySaving">
            {{ notifySaving ? '...' : '保存' }}
          </button>
        </div>
      </div>
    </section>

    <!-- 直链服务 -->
    <section class="card glass-card">
      <div class="card-head" @click="toggle('directLink')">
        <div class="card-head-left">
          <div class="card-icon directlink-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
          </div>
          <div class="card-title">
            <h3>直链服务</h3>
            <p>302 重定向直链</p>
          </div>
        </div>
        <svg class="chevron" :class="{ open: expanded.directLink }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div class="card-body" v-show="expanded.directLink">
        <div class="field field-row">
          <label>启用直链服务</label>
          <label class="toggle">
            <input type="checkbox" v-model="dlEnabled" @change="saveDirectLinkSettings" />
            <span class="slider"></span>
          </label>
        </div>
        <div class="field">
          <label>服务端口</label>
          <input type="text" v-model.number="dlPort" placeholder="默认 11581" @change="saveDirectLinkSettings" />
        </div>
        <div class="field field-row">
          <label>服务状态</label>
          <div class="dl-status">
            <span class="status-dot" :class="dlRunning ? 'status-running' : 'status-stopped'"></span>
            <span>{{ dlRunning ? '运行中' : '已停止' }}</span>
          </div>
        </div>
        <div class="card-actions">
          <button v-if="!dlRunning" class="btn-save" @click.stop="startDirectLink" :disabled="!dlEnabled">启动</button>
          <button v-else class="btn-save btn-danger-outline" @click.stop="stopDirectLink">停止</button>
        </div>
      </div>
    </section>

    <!-- STRM 文件 -->
    <section class="card glass-card">
      <div class="card-head" @click="toggle('strm')">
        <div class="card-head-left">
          <div class="card-icon strm-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9 15 12 12 15 15"/></svg>
          </div>
          <div class="card-title">
            <h3>STRM 文件</h3>
            <p>直链播放</p>
          </div>
        </div>
        <svg class="chevron" :class="{ open: expanded.strm }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div class="card-body" v-show="expanded.strm">
        <!-- 直链基地址 -->
        <div class="field">
          <label>直链服务基地址</label>
          <input type="text" v-model="strmBaseUrl" placeholder="http://127.0.0.1:11581" />
        </div>

        <!-- STRM 输出路径（来自飞牛授权目录） -->
        <div class="field">
          <label>分享 STRM 存储路径</label>
          <select v-model="strmOutputPath" :disabled="strmAccessiblePaths.length === 0">
            <option value="">请选择授权目录</option>
            <option v-for="p in strmAccessiblePaths" :key="p" :value="p">{{ p }}</option>
          </select>
          <p v-if="strmAccessiblePaths.length === 0" class="strm-hint">
            请先在飞牛应用设置中给壹伍授权一个媒体库目录，保存后点击下方"刷新授权目录"。
          </p>
        </div>

        <!-- 生成结果 -->
        <div class="strm-result" v-if="strmResult">
          <div class="strm-result-summary">
            <span class="tag">总数 {{ strmResult.total }}</span>
            <span class="tag" style="background: var(--success-bg); color: var(--success);">成功 {{ strmResult.created }}</span>
            <span class="tag" v-if="strmResult.failed > 0" style="background: var(--danger-bg); color: var(--danger);">失败 {{ strmResult.failed }}</span>
          </div>
          <div class="strm-error-list" v-if="strmResult.errors && strmResult.errors.length > 0">
            <div v-for="(err, i) in strmResult.errors.slice(0, 10)" :key="i" class="strm-error-item">
              <span class="strm-error-name">{{ err.name }}</span>
              <span class="strm-error-msg">{{ err.error }}</span>
            </div>
            <p v-if="strmResult.errors.length > 10" class="strm-hint">仅展示前 10 条错误</p>
          </div>
        </div>

        <div class="card-actions">
          <button class="btn-ghost-sm" @click.stop="loadStrmAccessiblePaths">刷新授权目录</button>
          <button class="btn-ghost-sm" @click.stop="saveStrmSettings" :disabled="strmSaving">
            {{ strmSaving ? '...' : '保存' }}
          </button>
          <button class="btn-save" @click.stop="generateStrmFiles" :disabled="strmGenerating || !strmOutputPath">
            {{ strmGenerating ? '生成中...' : '生成 STRM' }}
          </button>
        </div>
      </div>
    </section>

    <!-- 目录选择器弹窗 -->
    <div v-if="showPathPicker" class="glass-overlay" @click.self="showPathPicker = false">
      <div class="modal glass-solid">
        <div class="modal-head">
          <h4>选择目录</h4>
          <button class="btn-icon-sm neu-circle" @click="showPathPicker = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal-nav">
          <span v-for="(b, i) in pickerBreadcrumbs" :key="b.id" class="nav-item" @click="pickerNavigateTo(b.id, i)">
            {{ b.name }}<span v-if="i < pickerBreadcrumbs.length - 1" class="nav-sep">/</span>
          </span>
        </div>
        <div class="modal-list">
          <div v-if="pickerLoading" class="modal-empty">加载中...</div>
          <div v-else-if="pickerDirs.length === 0" class="modal-empty">此目录为空</div>
          <div v-else v-for="dir in pickerDirs" :key="dir.file_id" class="modal-dir" @click="pickerEnterDir(dir)">
            <svg viewBox="0 0 24 24" fill="currentColor"><path d="M10 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>
            <span>{{ dir.name }}</span>
          </div>
        </div>
        <div class="modal-foot">
          <span class="modal-path">{{ pickerCurrentPath }}</span>
          <div class="modal-btns">
            <button class="btn-ghost" @click="showPathPicker = false">取消</button>
            <button class="btn-save" @click="confirmPathPick">确定</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { filesApi } from '@/api/files'
import { organizeApi } from '@/api/organize'
import { notificationApi } from '@/api/notification'
import { directLinkApi } from '@/api/directLink'
import { strmApi } from '@/api/strm'
import type { FileItem } from '@/api/files'

// 折叠状态
const expanded = reactive<Record<string, boolean>>({ tmdb: false, api: false, media: false, notify: false, directLink: false, strm: false })
function toggle(key: string) { expanded[key] = !expanded[key] }

const openApiEnabled = ref(false)
const selectedAppId = ref('')
const tokenValid = ref(false)
const saving = ref(false)

const tmdbApiKey = ref('')
const tmdbApiUrl = ref('')
const tmdbLanguage = ref('zh-CN')
const tmdbSaving = ref(false)

// 密码显示/隐藏状态
const showApiKey = ref(false)
const showBotToken = ref(false)
const showApiHash = ref(false)
const showPassword = ref(false)

const organizeMode = ref('move')
const sourcePath = ref('')
const mediaLibraryPath = ref('')
const movieTemplate = ref('')
const tvTemplate = ref('')
const mediaSaving = ref(false)

const movieRules = ref<{ category: string; conditions: string }[]>([])
const tvRules = ref<{ category: string; conditions: string }[]>([])

const builtinReleaseGroups = ref<string[]>([])
const customGroupsList = ref<string[]>([])
const newGroupName = ref('')

// 通知配置
const tgEnabled = ref(false)
const tgBotEnabled = ref(true)
const tgNotifyChat = ref('')
const tgBotToken = ref('')
const tgUserEnabled = ref(false)
const tgApiId = ref('')
const tgApiHash = ref('')
const tgProxyEnabled = ref(false)
const tgProxyUrl = ref('')
const tgAdminIds = ref('')
const tgPhone = ref('')
const tgCode = ref('')
const tgPassword = ref('')
const codeSending = ref(false)
const signingIn = ref(false)
const codeSent = ref(false)
const loginStatus = ref('')
const loginStatusOk = ref(false)
const tgBotName = ref('')
const tgUserName = ref('')
const notifySaving = ref(false)
const tgTesting = ref(false)
const tgStatus = ref({ configured: false, connected: false, mode: '', message: '未检查' })

// 直链服务配置
const dlEnabled = ref(false)
const dlPort = ref(11581)
const dlRunning = ref(false)
const dlSaving = ref(false)

// STRM 配置
const strmBaseUrl = ref('http://127.0.0.1:11581')
const strmOutputPath = ref('')
const strmAccessiblePaths = ref<string[]>([])
const strmSaving = ref(false)
const strmGenerating = ref(false)
const strmResult = ref<any>(null)

const showPathPicker = ref(false)
const pickerLoading = ref(false)
const pickerDirs = ref<FileItem[]>([])
const pickerBreadcrumbs = ref<{ id: string; name: string }[]>([{ id: '0', name: '根目录' }])
const pickerCid = ref('0')
const pickerCurrentPath = ref('/')
const pickerTarget = ref<'source' | 'library'>('library')

const appIds = [
  { value: '100195137', label: 'VidHub' },
  { value: '100195793', label: 'Senplayer' },
  { value: '100195145', label: 'Filebar' },
  { value: '100196987', label: 'CloudDrive2' },
  { value: '100195271', label: '飞牛私有云' },
  { value: '100195135', label: '网易爆米花' },
  { value: '100195199', label: '极空间' },
]

onMounted(() => {
  loadOpenApiSettings()
  loadTmdbSettings()
  loadClassifySettings()
  loadNotifySettings()
  // 加载直链设置
  directLinkApi.getSettings().then((res: any) => {
    if (res.code === 0 && res.data) {
      dlEnabled.value = res.data.enabled
      dlPort.value = res.data.port || 11581
      dlRunning.value = res.data.running
    }
  }).catch(() => {})
  // 加载 STRM 设置、授权路径
  loadStrmSettings()
  loadStrmAccessiblePaths()
})

async function loadOpenApiSettings() {
  try {
    const res = await filesApi.getOpenApiSettings()
    if (res.code === 0 && res.data) {
      openApiEnabled.value = res.data.enabled
      selectedAppId.value = res.data.app_id || ''
      tokenValid.value = res.data.token_valid
    }
  } catch (e) { console.error('加载 Open API 设置失败:', e) }
}

async function saveOpenApiSettings() {
  if (saving.value) return
  saving.value = true
  try {
    const res = await filesApi.updateOpenApiSettings(openApiEnabled.value, selectedAppId.value)
    if (res.code === 0 && res.data) tokenValid.value = res.data.token_valid
  } catch (e) { console.error('保存 Open API 设置失败:', e) }
  finally { saving.value = false }
}

async function loadTmdbSettings() {
  try {
    const res = await organizeApi.getSettings()
    if (res.code === 0 && res.data) {
      tmdbApiKey.value = res.data.tmdb_api_key || ''
      tmdbApiUrl.value = res.data.tmdb_api_url || ''
      tmdbLanguage.value = res.data.tmdb_language || 'zh-CN'
      mediaLibraryPath.value = res.data.media_library_path || ''
      movieTemplate.value = res.data.movie_template || ''
      tvTemplate.value = res.data.tv_template || ''
      organizeMode.value = res.data.organize_mode || 'move'
      sourcePath.value = res.data.source_path || ''
    }
  } catch (e) { console.error('加载设置失败:', e) }
}

async function saveTmdbSettings() {
  if (tmdbSaving.value) return
  tmdbSaving.value = true
  try {
    await organizeApi.updateSettings({ tmdb_api_key: tmdbApiKey.value, tmdb_api_url: tmdbApiUrl.value, tmdb_language: tmdbLanguage.value })
  } catch (e) { console.error('保存失败:', e) }
  finally { tmdbSaving.value = false }
}

async function saveMediaSettings() {
  if (mediaSaving.value) return
  mediaSaving.value = true
  try {
    const rules = buildClassifyRules()
    await organizeApi.updateSettings({
      organize_mode: organizeMode.value,
      source_path: sourcePath.value,
      media_library_path: mediaLibraryPath.value,
      movie_template: movieTemplate.value,
      tv_template: tvTemplate.value,
      classify_rules: JSON.stringify(rules),
      release_groups: customGroupsList.value.join('\n'),
    })
  } catch (e) { console.error('保存失败:', e) }
  finally { mediaSaving.value = false }
}

function openPathPickerFor(target: 'source' | 'library') {
  pickerTarget.value = target
  pickerCid.value = '0'
  pickerBreadcrumbs.value = [{ id: '0', name: '根目录' }]
  showPathPicker.value = true
  loadPickerDirs()
}

async function loadPickerDirs() {
  pickerLoading.value = true
  try {
    const res = await filesApi.listFiles(pickerCid.value, 200)
    pickerDirs.value = (res.code === 0 && res.data) ? (res.data.items || []).filter((i: FileItem) => i.is_dir) : []
  } catch (e) { pickerDirs.value = [] }
  finally { pickerLoading.value = false }
}

function pickerEnterDir(dir: FileItem) {
  pickerCid.value = dir.file_id
  pickerBreadcrumbs.value.push({ id: dir.file_id, name: dir.name })
  loadPickerDirs()
}

function pickerNavigateTo(id: string, index: number) {
  if (id === pickerCid.value) return
  pickerBreadcrumbs.value = pickerBreadcrumbs.value.slice(0, index + 1)
  pickerCid.value = id
  loadPickerDirs()
}

function confirmPathPick() {
  // 去掉面包屑中的"根目录"，它只是 cid=0 的显示名
  const parts = pickerBreadcrumbs.value
    .filter(b => b.name !== '根目录')
    .map(b => b.name)
  const value = parts.length === 0 ? '/' : parts.join('/')
  if (pickerTarget.value === 'source') {
    sourcePath.value = value
  } else {
    mediaLibraryPath.value = value
  }
  showPathPicker.value = false
}

function addCustomGroup() {
  const name = newGroupName.value.trim()
  if (!name || customGroupsList.value.includes(name)) { newGroupName.value = ''; return }
  customGroupsList.value.push(name)
  newGroupName.value = ''
}

function removeCustomGroup(i: number) { customGroupsList.value.splice(i, 1) }

async function loadClassifySettings() {
  try {
    const res = await organizeApi.getSettings()
    if (res.code === 0 && res.data) {
      if (res.data.classify_rules) {
        const rules = JSON.parse(res.data.classify_rules)
        movieRules.value = (rules.movie || []).map((r: any) => ({ category: r.category, conditions: Object.entries(r.conditions || {}).map(([k, v]) => `${k}=${v}`).join(',') }))
        tvRules.value = (rules.tv || []).map((r: any) => ({ category: r.category, conditions: Object.entries(r.conditions || {}).map(([k, v]) => `${k}=${v}`).join(',') }))
      }
      if (res.data.builtin_release_groups) builtinReleaseGroups.value = res.data.builtin_release_groups
      if (res.data.custom_release_groups) customGroupsList.value = res.data.custom_release_groups.split('\n').filter((g: string) => g.trim())
    }
  } catch (e) { console.error('加载分类策略失败:', e) }
}

function buildClassifyRules() {
  const pc = (s: string) => { const o: Record<string, string> = {}; s.split(',').forEach(p => { const [k, v] = p.split('='); if (k && v) o[k.trim()] = v.trim() }); return o }
  return {
    movie: movieRules.value.filter(r => r.category).map(r => ({ category: r.category, conditions: pc(r.conditions) })),
    tv: tvRules.value.filter(r => r.category).map(r => ({ category: r.category, conditions: pc(r.conditions) })),
  }
}

async function resetTemplates() { try { await organizeApi.resetTemplates(); await loadTmdbSettings() } catch (e) { console.error(e) } }
async function resetRules() { try { await organizeApi.resetRules(); await loadClassifySettings() } catch (e) { console.error(e) } }

// ==================== 通知配置 ====================

async function loadNotifySettings() {
  try {
    const res = await notificationApi.getSettings('telegram')
    if (res.code === 0 && res.data?.values) {
      const v = res.data.values
      tgEnabled.value = v.tg_enabled === 'true' || v.tg_enabled === '1'
      tgBotEnabled.value = v.tg_bot_enabled !== 'false' && v.tg_bot_enabled !== '0'
      tgNotifyChat.value = v.tg_notify_chat || ''
      tgBotToken.value = v.tg_bot_token || ''
      tgUserEnabled.value = v.tg_user_enabled === 'true' || v.tg_user_enabled === '1'
      tgApiId.value = v.tg_api_id || ''
      tgApiHash.value = v.tg_api_hash || ''
      tgProxyEnabled.value = v.tg_proxy_enabled === 'true' || v.tg_proxy_enabled === '1'
      tgProxyUrl.value = v.tg_proxy_url || ''
      tgAdminIds.value = v.tg_admin_ids || ''
    }
    // 获取连接状态（含 bot_name / user_name）
    const statusRes = await notificationApi.getChannels()
    if (statusRes.code === 0 && statusRes.data) {
      const tg = statusRes.data.channels?.find((c: any) => c.name === 'telegram')
      if (tg) {
        tgStatus.value = tg
        tgBotName.value = tg.bot_name || ''
        tgUserName.value = tg.user_name || ''
      }
    }
  } catch (e) { console.error('加载通知配置失败:', e) }
}

async function saveNotifySettings() {
  if (notifySaving.value) return
  notifySaving.value = true
  try {
    await notificationApi.updateSettings('telegram', {
      tg_enabled: String(tgEnabled.value),
      tg_bot_enabled: String(tgBotEnabled.value),
      tg_bot_token: tgBotToken.value,
      tg_user_enabled: String(tgUserEnabled.value),
      tg_api_id: tgApiId.value,
      tg_api_hash: tgApiHash.value,
      tg_proxy_enabled: String(tgProxyEnabled.value),
      tg_proxy_url: tgProxyUrl.value,
      tg_notify_chat: tgNotifyChat.value,
      tg_admin_ids: tgAdminIds.value,
    })
    await loadNotifySettings()
  } catch (e) { console.error('保存通知配置失败:', e) }
  finally { notifySaving.value = false }
}

async function sendCode() {
  if (codeSending.value) return
  codeSending.value = true
  loginStatus.value = ''
  codeSent.value = false
  try {
    const res = await notificationApi.sendCode(tgPhone.value, tgApiId.value, tgApiHash.value)
    if (res.code === 0) {
      loginStatus.value = '验证码已发送，请查看 Telegram'
      loginStatusOk.value = true
      codeSent.value = true
    } else {
      loginStatus.value = res.message || '发送失败'
      loginStatusOk.value = false
    }
  } catch (e: any) {
    loginStatus.value = e.message || '发送失败'
    loginStatusOk.value = false
  } finally { codeSending.value = false }
}

async function signIn() {
  if (signingIn.value) return
  signingIn.value = true
  loginStatus.value = ''
  try {
    const res = await notificationApi.signIn(tgPhone.value, tgCode.value, tgPassword.value)
    if (res.code === 0) {
      loginStatus.value = '登录成功，Session 已保存'
      loginStatusOk.value = true
      tgCode.value = ''
      tgPassword.value = ''
      await loadNotifySettings()
    } else {
      loginStatus.value = res.message || '登录失败'
      loginStatusOk.value = false
    }
  } catch (e: any) {
    loginStatus.value = e.message || '登录失败'
    loginStatusOk.value = false
  } finally { signingIn.value = false }
}

async function testNotify() {
  if (tgTesting.value) return
  tgTesting.value = true
  try {
    const res = await notificationApi.test('telegram')
    if (res.code === 0) {
      tgStatus.value = { ...tgStatus.value, message: '测试消息已发送', connected: true }
    } else {
      tgStatus.value = { ...tgStatus.value, message: res.message || '发送失败' }
    }
    await loadNotifySettings()
  } catch (e) { console.error(e) }
  finally { tgTesting.value = false }
}

// ==================== 直链服务 ====================

// 保存直链设置
async function saveDirectLinkSettings() {
  dlSaving.value = true
  try {
    const res = await directLinkApi.saveSettings({ enabled: dlEnabled.value, port: dlPort.value })
    if (res.code === 0) {
      dlRunning.value = res.data?.running ?? dlRunning.value
    }
  } catch (e) {
    console.error('保存直链设置失败:', e)
  } finally {
    dlSaving.value = false
  }
}

// 启动直链服务
async function startDirectLink() {
  try {
    const res = await directLinkApi.start()
    if (res.code === 0) {
      dlRunning.value = true
    }
  } catch (e) {
    console.error('启动直链服务失败:', e)
  }
}

// 停止直链服务
async function stopDirectLink() {
  try {
    const res = await directLinkApi.stop()
    if (res.code === 0) {
      dlRunning.value = false
    }
  } catch (e) {
    console.error('停止直链服务失败:', e)
  }
}

// ==================== STRM 文件 ====================

// 加载 STRM 配置
async function loadStrmSettings() {
  try {
    const res = await strmApi.getSettings()
    if (res.code === 0 && res.data) {
      strmBaseUrl.value = res.data.direct_link_base_url || 'http://127.0.0.1:11581'
      strmOutputPath.value = res.data.output_path || ''
    }
  } catch (e) {
    console.error('加载 STRM 配置失败:', e)
  }
}

// 加载飞牛授权目录列表
async function loadStrmAccessiblePaths() {
  try {
    const res = await strmApi.getAccessiblePaths()
    if (res.code === 0 && res.data) {
      strmAccessiblePaths.value = res.data.paths || []
    }
  } catch (e) {
    console.error('加载授权目录失败:', e)
    strmAccessiblePaths.value = []
  }
}

// 保存 STRM 配置
async function saveStrmSettings() {
  if (strmSaving.value) return
  strmSaving.value = true
  try {
    const res = await strmApi.saveSettings({
      direct_link_base_url: strmBaseUrl.value,
      output_path: strmOutputPath.value,
    })
    if (res.code === 0) {
      strmResult.value = null
    } else {
      alert(res.message || '保存失败')
    }
  } catch (e: any) {
    alert(e.message || '保存失败')
  } finally {
    strmSaving.value = false
  }
}

// 生成 STRM 文件
async function generateStrmFiles() {
  if (strmGenerating.value) return
  // 二次确认，避免误操作
  if (!confirm(`确认为所有已整理分享文件生成 STRM 到指定目录？\n\n输出目录：${strmOutputPath.value || '(未配置)'}`)) {
    return
  }
  strmGenerating.value = true
  strmResult.value = null
  try {
    const res = await strmApi.generate()
    if (res.code === 0 && res.data) {
      strmResult.value = res.data
    } else {
      alert(res.message || '生成失败')
    }
  } catch (e: any) {
    alert(e.message || '生成失败')
  } finally {
    strmGenerating.value = false
  }
}
</script>

<style scoped>
.settings { display: flex; flex-direction: column; gap: 10px; font-family: var(--font-sans); }

/* ==================== 卡片（液态玻璃） ==================== */
.card { border-radius: var(--radius-lg); overflow: hidden; }

.card-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; cursor: pointer; user-select: none; transition: background var(--transition-fast);
}
.card-head:hover { background: var(--bg-hover); }

.card-head-left { display: flex; align-items: center; gap: 12px; }

/* 卡片图标（4 个语义色） */
.card-icon { width: 32px; height: 32px; border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.card-icon svg { width: 16px; height: 16px; }
.tmdb-icon { background: var(--accent-bg); color: var(--accent); }
.api-icon { background: var(--success-bg); color: var(--success); }
.media-icon { background: var(--purple-bg); color: var(--purple); }
.notify-icon { background: var(--warning-bg); color: var(--warning); }
.directlink-icon { background: var(--accent-bg); color: var(--accent); }
.strm-icon { background: var(--purple-bg); color: var(--purple); }

/* ==================== STRM 卡片专属样式 ==================== */
.strm-hint {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.5;
}

.strm-result {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-elevated);
}

.strm-result-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.strm-error-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 160px;
  overflow-y: auto;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.strm-error-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
}

.strm-error-name {
  color: var(--text-primary);
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.strm-error-msg {
  color: var(--danger);
}

/* 状态指示 */
.dl-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-running {
  background: var(--success);
  box-shadow: 0 0 6px var(--success-bg);
}

.status-stopped {
  background: var(--text-tertiary);
}

/* 危险按钮描边 */
.btn-danger-outline {
  background: transparent;
  border: 1px solid var(--danger);
  color: var(--danger);
}

.btn-danger-outline:hover {
  background: var(--danger-bg);
}

.card-title h3 { font-size: 14px; font-weight: 600; color: var(--text-primary); margin: 0; }
.card-title p { font-size: 11px; color: var(--text-tertiary); margin: 1px 0 0; }

.chevron { width: 16px; height: 16px; color: var(--text-tertiary); transition: transform var(--transition-base); flex-shrink: 0; }
.chevron.open { transform: rotate(180deg); }

.card-body { padding: 14px 18px 18px; border-top: 1px solid var(--border); }
.card-actions { display: flex; justify-content: flex-end; gap: 10px; padding-top: 12px; margin-top: 12px; border-top: 1px solid var(--border); }

/* ==================== 字段 ==================== */
.field { margin-bottom: 12px; }
.field:last-child { margin-bottom: 0; }
.field label { display: block; font-size: 12px; font-weight: 500; color: var(--text-secondary); margin-bottom: 4px; }

/* 输入框（新拟态凹陷 + focus 主色光环） */
.field input[type="text"], .field input[type="password"],
.field .password-field input,
.field select {
  width: 100%; padding: 8px 10px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  font-size: 13px; color: var(--text-primary);
  background: var(--bg-input); box-shadow: var(--neu-inset);
  outline: none; transition: all var(--transition-base);
}
.field input:focus, .field .password-field input:focus, .field select:focus {
  border-color: var(--accent);
  box-shadow: var(--neu-inset), 0 0 0 3px var(--accent-bg);
}
.field input::placeholder, .field .password-field input::placeholder { color: var(--text-tertiary); }

/* 密码字段容器 */
.password-field {
  position: relative;
  display: flex;
  align-items: center;
}

.password-field input {
  padding-right: 36px;  /* 为眼睛按钮留空间 */
}

/* 眼睛按钮 */
.btn-eye {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 28px;
  height: 28px;
  background: none;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background var(--transition-fast);
}

.btn-eye:hover {
  color: var(--text-secondary);
  background: var(--bg-hover);
}

.btn-eye svg {
  width: 16px;
  height: 16px;
}
.field select:disabled { background: var(--bg-hover); color: var(--text-tertiary); cursor: not-allowed; }

/* select 自定义下拉箭头（macOS 风格） */
.field select {
  appearance: none;
  -webkit-appearance: none;
  padding-right: 32px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236e6e73' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  cursor: pointer;
}

/* select 选项样式 */
.field select option {
  background: var(--bg-solid);
  color: var(--text-primary);
  padding: 8px;
}

.field-row { display: flex; align-items: center; justify-content: space-between; }
.field-row label { margin-bottom: 0; }

.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 768px) { .field-grid { grid-template-columns: 1fr; } }

.mono-input { font-family: var(--font-mono) !important; font-size: 12px !important; }

/* ==================== 子卡片（通知渠道） ==================== */
.sub-card { border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; margin-bottom: 10px; background: var(--bg-elevated); }
.sub-card-disabled { opacity: 0.5; }

.sub-card-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; background: var(--bg-hover);
}
.sub-card-left { display: flex; align-items: center; gap: 10px; }
.sub-card-icon { width: 18px; height: 18px; flex-shrink: 0; }
.tg-icon { color: var(--accent); }
.wx-icon { color: var(--success); }
.sub-card-title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.sub-card-badge { font-size: 11px; color: var(--text-tertiary); background: var(--bg-input); padding: 2px 8px; border-radius: var(--radius-full); }

.sub-card-body { padding: 12px 16px; }

/* 模式行（Bot/User/代理） */
.mode-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 0; border-bottom: 1px solid var(--border);
}
.mode-row:last-of-type { border-bottom: none; }
.mode-info { display: flex; align-items: center; gap: 8px; }
.mode-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.mode-status { font-size: 11px; color: var(--success); background: var(--success-bg); padding: 1px 8px; border-radius: var(--radius-full); }

.mode-body { padding: 8px 0 4px; }

/* ==================== 字段组 ==================== */
.field-group { margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
.field-group:last-of-type { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }

.group-label { display: flex; align-items: center; justify-content: space-between; font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }

.group-status { font-size: 11px; font-weight: 500; text-transform: none; letter-spacing: 0; }
.group-status.status-ok { color: var(--success); }
.group-status.status-warn { color: var(--warning); }

.group-right { display: flex; align-items: center; gap: 8px; }

/* ==================== 路径 ==================== */
.path-field { display: flex; align-items: center; gap: 6px; }
/* 路径文本（新拟态凹陷） */
.path-text {
  flex: 1; font-size: 12px; color: var(--text-primary);
  padding: 8px 10px;
  background: var(--bg-input); border: 1px solid var(--border);
  border-radius: var(--radius-sm); box-shadow: var(--neu-inset);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: var(--font-mono);
}
.path-empty { color: var(--text-tertiary); font-family: inherit; }

/* ==================== 开关（主色统一为 --accent） ==================== */
.toggle { position: relative; width: 40px; height: 22px; cursor: pointer; display: inline-block; }
.toggle input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; inset: 0; background: var(--border-strong); border-radius: var(--radius-full); transition: background var(--transition-base); }
.slider::before { content: ''; position: absolute; width: 16px; height: 16px; left: 3px; bottom: 3px; background: var(--bg-solid); border-radius: 50%; box-shadow: var(--shadow-sm); transition: transform var(--transition-base); }
.toggle input:checked + .slider { background: var(--accent); }
.toggle input:checked + .slider::before { transform: translateX(18px); }

/* ==================== 胶囊开关 ==================== */
.pill-switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  padding: 3px;
  background: var(--bg-input);
  box-shadow: var(--neu-inset);
  border-radius: var(--radius-full);
  cursor: pointer;
  user-select: none;
}

.pill-label {
  position: relative;
  z-index: 1;
  padding: 4px 16px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  transition: color var(--transition-base);
  border-radius: var(--radius-md);
}

.pill-label.active {
  color: var(--text-primary);
}

.pill-indicator {
  position: absolute;
  left: 3px;
  top: 3px;
  width: calc(50% - 3px);
  height: calc(100% - 6px);
  background: var(--bg-solid);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition-base);
  z-index: 0;
}

.pill-switch.copy .pill-indicator {
  transform: translateX(100%);
}

/* 手机号登录行 */
.phone-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.phone-row input {
  flex: 1;
}

.login-status {
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  margin-top: 4px;
  font-size: 12px;
  background: var(--bg-input);
}

.login-status .status-ok { color: var(--success); }
.login-status .status-warn { color: var(--warning); }

/* ==================== 徽章 ==================== */
.badge { display: inline-flex; align-items: center; padding: 3px 10px; border-radius: var(--radius-full); font-size: 11px; font-weight: 600; }
.badge-ok { background: var(--success-bg); color: var(--success); }
.badge-warn { background: var(--warning-bg); color: var(--warning); }

/* ==================== 按钮 ==================== */
/* 保存按钮（主色填充） */
.btn-save {
  padding: 7px 18px; background: var(--accent); color: var(--text-inverse);
  border: none; border-radius: var(--radius-sm);
  font-size: 12px; font-weight: 500; cursor: pointer;
  transition: background var(--transition-base);
}
.btn-save:hover:not(:disabled) { background: var(--accent-hover); }
.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }

/* 小按钮（新拟态平面） */
.btn-ghost-sm {
  padding: 6px 14px;
  background: transparent; border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12px; color: var(--text-primary);
  cursor: pointer; box-shadow: var(--shadow-sm);
  transition: all var(--transition-base);
}
.btn-ghost-sm:hover { background: var(--bg-hover); box-shadow: var(--shadow-md); }
.btn-ghost-sm:disabled { opacity: 0.5; cursor: not-allowed; }

.action-left { display: flex; align-items: center; gap: 10px; }
.status-text { font-size: 12px; color: var(--text-tertiary); }
.status-text.status-ok { color: var(--success); }
.status-text.status-warn { color: var(--warning); }

/* 路径选择按钮（新拟态平面） */
.btn-ghost {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 8px 10px;
  background: transparent; border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12px; color: var(--text-primary);
  cursor: pointer; box-shadow: var(--shadow-sm);
  transition: all var(--transition-base);
}
.btn-ghost:hover { background: var(--bg-hover); box-shadow: var(--shadow-md); }
.btn-ghost svg { width: 14px; height: 14px; }

/* 重置按钮 */
.btn-icon-reset {
  width: 24px; height: 24px; background: none; border: none;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; border-radius: var(--radius-sm);
  color: var(--text-tertiary); transition: all var(--transition-fast);
}
.btn-icon-reset:hover { color: var(--text-secondary); background: var(--bg-hover); }
.btn-icon-reset svg { width: 13px; height: 13px; }

/* 小图标按钮（新拟态圆形） */
.btn-icon-sm {
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--text-tertiary);
  transition: all var(--transition-fast);
}
.btn-icon-sm:hover { color: var(--text-primary); }
.btn-icon-sm svg { width: 13px; height: 13px; }
.btn-icon-sm.danger:hover { color: var(--danger); }

/* 虚线按钮 */
.btn-dashed {
  display: block; width: 100%; padding: 6px;
  background: none;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
  font-size: 11px; color: var(--text-tertiary);
  cursor: pointer; margin-top: 6px;
  transition: all var(--transition-base);
}
.btn-dashed:hover { border-color: var(--purple); color: var(--purple); }

/* ==================== 分类规则 ==================== */
.rules-section { margin-top: 4px; }
.rules-type { margin-bottom: 6px; }
.type-tag { display: inline-block; padding: 2px 8px; border-radius: var(--radius-sm); font-size: 10px; font-weight: 600; }
.type-movie { background: var(--accent-bg); color: var(--accent); }
.type-tv { background: var(--purple-bg); color: var(--purple); }

.rule-list { display: flex; flex-direction: column; gap: 4px; }
.rule-row { display: flex; gap: 4px; align-items: center; }
/* 规则输入框（新拟态凹陷） */
.rule-cat {
  width: 120px; padding: 6px 8px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  font-size: 11px; color: var(--text-primary);
  background: var(--bg-input); box-shadow: var(--neu-inset);
  outline: none; transition: all var(--transition-base);
}
.rule-cat:focus { border-color: var(--accent); box-shadow: var(--neu-inset), 0 0 0 3px var(--accent-bg); }
.rule-cond {
  flex: 1; padding: 6px 8px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  font-size: 11px; color: var(--text-primary);
  background: var(--bg-input); box-shadow: var(--neu-inset);
  outline: none; font-family: var(--font-mono);
  transition: all var(--transition-base);
}
.rule-cond:focus { border-color: var(--accent); box-shadow: var(--neu-inset), 0 0 0 3px var(--accent-bg); }

/* ==================== 标签 ==================== */
.tags-wrap { display: flex; flex-wrap: wrap; gap: 4px; }
.tag { display: inline-flex; align-items: center; gap: 3px; padding: 3px 8px; background: var(--bg-input); border-radius: var(--radius-sm); font-size: 11px; font-weight: 500; color: var(--text-secondary); }
.tag-custom { background: var(--purple-bg); color: var(--purple); }
.tag-custom button { background: none; border: none; color: var(--purple); cursor: pointer; font-size: 13px; line-height: 1; padding: 0; margin-left: 1px; transition: color var(--transition-fast); }
.tag-custom button:hover { color: var(--danger); }

/* 标签输入框（新拟态凹陷） */
.tag-input-box {
  display: flex; flex-wrap: wrap; gap: 4px; align-items: center;
  padding: 6px 8px;
  border: 1px solid var(--border); border-radius: var(--radius-sm);
  min-height: 36px;
  background: var(--bg-input); box-shadow: var(--neu-inset);
  transition: all var(--transition-base);
}
.tag-input-box:focus-within { border-color: var(--accent); box-shadow: var(--neu-inset), 0 0 0 3px var(--accent-bg); }
.tag-input { border: none; outline: none; font-size: 11px; color: var(--text-primary); flex: 1; min-width: 100px; padding: 2px 4px; background: none; }
.tag-input::placeholder { color: var(--text-tertiary); }

/* ==================== 弹窗 ==================== */
.modal {
  border-radius: var(--radius-lg);
  width: 100%; max-width: 440px; max-height: 70vh;
  display: flex; flex-direction: column; overflow: hidden;
}
.modal-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border); }
.modal-head h4 { font-size: 14px; font-weight: 600; color: var(--text-primary); margin: 0; }
.modal-nav { display: flex; flex-wrap: wrap; gap: 2px; padding: 8px 18px; border-bottom: 1px solid var(--border); font-size: 12px; }
.nav-item { cursor: pointer; color: var(--accent); padding: 2px 4px; border-radius: var(--radius-sm); transition: background var(--transition-fast); }
.nav-item:hover { background: var(--accent-bg); }
.nav-sep { color: var(--text-tertiary); margin: 0 1px; }
.modal-list { flex: 1; overflow-y: auto; min-height: 180px; max-height: 300px; }
.modal-empty { display: flex; align-items: center; justify-content: center; height: 180px; color: var(--text-tertiary); font-size: 12px; }
.modal-dir { display: flex; align-items: center; gap: 10px; padding: 9px 18px; cursor: pointer; font-size: 12px; color: var(--text-primary); transition: background var(--transition-fast); }
.modal-dir:hover { background: var(--bg-hover); }
.modal-dir svg { width: 16px; height: 16px; color: var(--folder); flex-shrink: 0; }
.modal-foot { display: flex; align-items: center; justify-content: space-between; padding: 10px 18px; border-top: 1px solid var(--border); gap: 10px; }
.modal-path { font-size: 11px; color: var(--text-tertiary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--font-mono); }
.modal-btns { display: flex; gap: 6px; flex-shrink: 0; }
</style>
