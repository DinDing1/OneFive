# 壹伍（OneFive）项目初始化计划

## 项目概述

**项目名称**：壹伍（OneFive）  
**定位**：基于 p115client 的 115 网盘管理应用，部署于飞牛 fnOS，打包为原生应用（.fpk）  
**技术栈**：Python 3.12+ 后端 + Vue 3 前端  
**架构支持**：x86_64 + ARM  
**开发流程**：本地开发测试 → 飞牛正式环境部署

---

## 一、p115client 模块深度解析

### 1.1 核心架构

p115client 是一个 115 网盘的 Python 客户端，提供最底层的 API 接口封装，支持**同步和异步**调用。

```
┌─────────────────────────────────────────────────────┐
│                  p115client 核心架构                   │
├─────────────────────┬───────────────────────────────┤
│  P115Client         │  P115OpenClient               │
│  (Cookie 认证)      │  (OAuth2 认证)                │
│  461 个方法          │  43 个方法                    │
│  webapi.115.com     │  proapi.115.com               │
│  20+ 个 API 域名    │  统一域名                      │
├─────────────────────┴───────────────────────────────┤
│  底层依赖:                                           │
│  p115cipher (加解密) ← p115pickcode (ID转换)         │
│  p115oss (OSS上传)   ← p115qrcode (扫码登录)         │
└─────────────────────────────────────────────────────┘
```

### 1.2 认证方式

| 方式 | 类 | 特点 |
|------|-----|------|
| Cookie 认证 | P115Client | 功能最全（461个方法），支持 web/app/open 接口 |
| OAuth2 认证 | P115OpenClient | 功能精简（43个方法），需申请 AppID，access_token 2小时过期 |

**推荐方案**：使用 P115Client（Cookie 认证），功能覆盖面最广。

### 1.3 API 功能全景（P115Client 共 461 个方法）

#### 核心文件管理（~60 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 文件列表 | `fs_files`, `fs_files_app`, `fs_files_aps` | 列出目录内容，支持多种 API 源 |
| 文件详情 | `fs_file`, `fs_file_skim`, `fs_info` | 获取单个文件/目录详情 |
| 创建目录 | `fs_mkdir`, `fs_mkdir_app`, `fs_makedirs` | 创建单级/多级目录 |
| 重命名 | `fs_rename`, `fs_rename_app` | 重命名文件/目录 |
| 复制 | `fs_copy`, `fs_copy_app` | 复制文件/目录 |
| 移动 | `fs_move`, `fs_move_app`, `fs_move_check_conflict` | 移动文件，支持冲突检测 |
| 删除 | `fs_delete`, `fs_delete_app` | 删除文件/目录 |
| 搜索 | `fs_search`, `fs_search_app`, `fs_shasearch` | 按名称/SHA1 搜索 |
| 重复文件 | `fs_repeat_sha1`, `fs_repeat_sha1_app` | 查找重复文件 |
| 目录ID获取 | `fs_dir_getid`, `fs_dir_getid_app` | 根据路径获取目录ID |
| 空间信息 | `fs_space_report`, `fs_storage_info` | 空间使用情况 |
| 文件预览 | `fs_preview` | 预览文件内容 |
| 导出目录 | `fs_export_dir`, `fs_export_dir_status` | 导出目录结构 |

#### 文件属性与标签（~30 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 描述 | `fs_desc`, `fs_desc_set` | 获取/设置文件描述 |
| 星标 | `fs_star_set` | 设置/取消星标 |
| 置顶 | `fs_top_set` | 设置/取消置顶 |
| 评分 | `fs_score_set` | 设置评分 |
| 封面 | `fs_cover_set` | 设置文件封面 |
| 排序 | `fs_order_set` | 设置排序方式 |
| 标签 | `fs_label_add/del/edit/list/set/batch` | 标签的增删改查 |
| 隐藏 | `fs_hide`, `fs_hidden_switch` | 隐藏/显示文件 |
| 分类 | `fs_category_get`, `fs_category_shortcut` | 获取文件分类 |

#### 上传功能（~16 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 上传初始化 | `upload_init`, `upload_info`, `upload_key` | 初始化上传任务 |
| 上传文件 | `upload_resume`, `upload_file` | 上传/恢复上传 |
| 图片上传 | `upload_image`, `upload_image_init` | 上传图片 |
| 头像上传 | `upload_avatar` | 上传用户头像 |
| 高级封装 | `upload_file_init`, `upload_file_image`, `upload_file_sample` | 文件上传的高级封装 |

#### 下载功能（~8 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 获取下载链接 | `download_url`, `download_url_app`, `download_url_web` | 获取文件下载直链 |
| 批量下载 | `download_urls`, `download_files_app` | 批量获取下载链接 |
| 文件夹下载 | `download_folders_app`, `download_downfolder_app` | 下载整个文件夹 |

#### 分享功能（~34 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 创建分享 | `share_send`, `share_send_app` | 创建分享链接 |
| 管理分享 | `share_list`, `share_info`, `share_update` | 列出/查看/更新分享 |
| 接收分享 | `share_receive`, `share_recvcode` | 接收/提取分享 |
| 分享下载 | `share_download_url`, `share_downlist` | 获取分享下载链接 |
| 免登录下载 | `share_skip_login_down`, `share_skip_login_download_url` | 免登录下载分享文件 |

#### 用户共享（~26 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 共享管理 | `usershare_share`, `usershare_list`, `usershare_info` | 创建/列出/查看共享 |
| 共享操作 | `usershare_copy`, `usershare_delete`, `usershare_invite` | 复制/删除/邀请 |
| 共享下载 | `usershare_download_url`, `usershare_download_urls` | 获取共享下载链接 |

#### 离线下载（~22 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 任务管理 | `offline_add_url/urls`, `offline_remove`, `offline_clear` | 添加/删除/清空任务 |
| 任务列表 | `offline_list`, `offline_task_cnt` | 查看离线任务 |
| 种子下载 | `offline_add_torrent`, `offline_torrent_info` | 种子离线下载 |
| 配额 | `offline_quota_info`, `offline_quota_package_info` | 查看离线配额 |

#### 视频功能（~12 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 视频信息 | `fs_video`, `fs_video_app` | 获取视频播放信息 |
| 字幕 | `fs_video_subtitle`, `fs_video_subtitle_set` | 获取/设置字幕 |
| 清晰度 | `fs_video_def_set` | 设置视频清晰度 |
| M3U8 | `fs_video_m3u8` | 获取 M3U8 播放列表 |
| 转码 | `fs_video_transcode` | 视频转码 |

#### 音乐功能（~24 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 音乐管理 | `fs_music`, `fs_music_list`, `fs_music_info` | 音乐列表/详情 |
| 收藏 | `fs_music_fond_list`, `fs_music_fond_set` | 音乐收藏 |
| 播放 | `fs_music_include_list`, `fs_music_set` | 播放列表管理 |

#### 图片相册（~20 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 相册管理 | `photo_album_add`, `photo_album_list`, `photo_album_update` | 创建/列出/更新相册 |
| 图片列表 | `photo_list`, `photo_timeline` | 图片列表/时间线 |
| 共享相册 | `photo_sharealbum_add`, `photo_sharealbum_list` | 共享相册管理 |

#### 笔记功能（~24 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 笔记管理 | `note_save`, `note_list`, `note_detail`, `note_del` | 增删改查笔记 |
| 分类 | `note_cate_add/del/update/list` | 笔记分类管理 |
| 收藏 | `note_fav_set`, `note_fav_list` | 笔记收藏 |

#### 回收站（~8 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 列表 | `recyclebin_list`, `recyclebin_list_app` | 回收站文件列表 |
| 还原 | `recyclebin_revert`, `recyclebin_revert_app` | 还原已删除文件 |
| 清空 | `recyclebin_clean`, `recyclebin_clean_app` | 清空回收站 |

#### 压缩文件提取（~18 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 提取管理 | `extract_add_file`, `extract_push`, `extract_progress` | 提取压缩文件 |
| 浏览 | `extract_folders`, `extract_info`, `extract_list` | 浏览压缩包内容 |
| 下载 | `extract_download_url`, `extract_file` | 下载提取的文件 |

#### 用户信息与设置（~35 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 用户信息 | `user_info`, `user_info2`, `user_info3` | 获取用户信息 |
| 空间信息 | `user_space_info`, `user_count_space_nums` | 空间使用统计 |
| 设置 | `user_setting`, `user_setting_set` | 用户设置管理 |
| 签到 | `user_sign`, `user_sign_set`, `user_points_balance` | 签到/积分 |
| VIP | `user_vip_check_spw`, `user_vip_limit` | VIP 相关 |

#### 登录认证（~30 个方法）
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 登录 | `login`, `login_with_app`, `login_without_app` | 多种登录方式 |
| 设备管理 | `login_devices`, `login_device` | 设备列表/登录 |
| 在线状态 | `login_online`, `login_status` | 在线状态检查 |
| 登出 | `logout`, `logout_by_app` | 登出操作 |

#### 其他功能
| 功能分类 | 主要方法 | 说明 |
|----------|---------|------|
| 生活记录 | `diary_add/list/edit/del`, `life_*` | 日记/生活记录 |
| 消息 | `msg_contacts_ls`, `msg_get_websocket_host` | 私信/消息 |
| 工具 | `tool_clear_empty_folder`, `tool_repeat` | 清理/重复扫描 |
| 活动 | `act_xys_*` | 115 平台活动 |

### 1.4 衍生模块生态（24 个模块）

```
┌──────────────────────────────────────────────────────────────┐
│                    p115client 生态系统                         │
├─────────────┬────────────────────────────────────────────────┤
│  核心基础    │  p115client（底层 API 客户端）                  │
├─────────────┼────────────────────────────────────────────────┤
│  文件访问    │  p115dav      WebDAV + 302（功能最全）          │
│  协议服务    │  p115wsgidav  轻量 WebDAV                      │
│  (把网盘变成 │  p115ftp      FTP 服务器                       │
│   各种协议)  │  p115sftp     SFTP 服务器                      │
│             │  p115fuse     FUSE 本地挂载                     │
├─────────────┼────────────────────────────────────────────────┤
│  302 直链    │  p115open302  基于开放接口的 302                │
│  转发服务    │  p115image302 图片专用 302 + 上传               │
│             │  p115tiny302  极简 302                          │
│             │  p115nano302  纳米级 302                        │
├─────────────┼────────────────────────────────────────────────┤
│  数据库      │  p115updatedb 遍历网盘 → 导出 SQLite           │
│  索引系统    │  p115servedb  挂载数据库为 WebDAV/FUSE          │
├─────────────┼────────────────────────────────────────────────┤
│  底层工具库  │  p115cipher    加解密                           │
│             │  p115rsacipher RSA 加解密                       │
│             │  p115pickcode  pickcode ↔ id 转换              │
│             │  p115oss       OSS 上传                         │
│             │  p115qrcode    扫码登录                         │
├─────────────┼────────────────────────────────────────────────┤
│  异步辅助    │  @@p115download  异步下载工具                   │
│             │  @@p115upload    异步上传工具                   │
│             │  @@p115transfer  异步转存工具                   │
├─────────────┼────────────────────────────────────────────────┤
│  高级封装    │  @p115           高级客户端封装                 │
│             │  @p115captcha    验证码处理                     │
│             │  @p115checkin    签到功能                       │
│             │  @p115iterdir    目录迭代                       │
└─────────────┴────────────────────────────────────────────────┘
```

---

## 二、项目目录架构

### 2.1 源码目录结构（开发阶段）

```
d:\OneFive\
├── backend/                           # Python 后端
│   ├── src/
│   │   └── onefive/
│   │       ├── __init__.py
│   │       ├── main.py               # FastAPI 主入口
│   │       ├── config.py             # 配置管理
│   │       ├── api/                  # API 路由
│   │       │   ├── __init__.py
│   │       │   ├── files.py          # 文件管理 API
│   │       │   ├── download.py       # 下载 API
│   │       │   ├── upload.py         # 上传 API
│   │       │   ├── share.py          # 分享 API
│   │       │   ├── offline.py        # 离线下载 API
│   │       │   ├── video.py          # 视频 API
│   │       │   ├── user.py           # 用户信息 API
│   │       │   └── auth.py           # 认证 API
│   │       ├── services/             # 业务逻辑层
│   │       │   ├── __init__.py
│   │       │   ├── client_manager.py # P115Client 实例管理
│   │       │   └── file_service.py   # 文件服务封装
│   │       └── models/               # 数据模型
│   │           └── __init__.py
│   ├── tests/                        # 后端测试
│   │   └── ...
│   ├── pyproject.toml                # Python 项目配置
│   └── requirements.txt              # Python 依赖
│
├── frontend/                          # Vue 3 前端
│   ├── src/
│   │   ├── main.ts                   # Vue 入口
│   │   ├── App.vue                   # 根组件
│   │   ├── router/                   # 路由配置
│   │   ├── stores/                   # Pinia 状态管理
│   │   ├── views/                    # 页面组件
│   │   │   ├── Login.vue             # 登录页
│   │   │   ├── FileManager.vue       # 文件管理页
│   │   │   ├── Download.vue          # 下载管理页
│   │   │   ├── Share.vue             # 分享管理页
│   │   │   ├── Offline.vue           # 离线下载页
│   │   │   └── Settings.vue          # 设置页
│   │   ├── components/               # 通用组件
│   │   │   ├── FileList.vue          # 文件列表组件
│   │   │   ├── FileTree.vue          # 目录树组件
│   │   │   └── UploadDialog.vue      # 上传对话框
│   │   ├── api/                      # API 请求封装
│   │   └── assets/                   # 静态资源
│   ├── public/
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── onefive/                           # 飞牛打包目录（构建时生成）
│   ├── app/
│   │   ├── server/                   # 后端代码（从 backend 复制）
│   │   ├── ui/                       # 前端构建产物（从 frontend/dist 复制）
│   │   │   ├── config                # 飞牛入口配置
│   │   │   └── images/               # 图标资源
│   │   └── vendor/                   # Python 依赖（pip install --target）
│   ├── cmd/                          # 生命周期脚本
│   │   ├── main                      # 启动/停止/状态
│   │   ├── install_init
│   │   ├── install_callback
│   │   ├── uninstall_init
│   │   ├── uninstall_callback
│   │   ├── upgrade_init
│   │   ├── upgrade_callback
│   │   ├── config_init
│   │   └── config_callback
│   ├── config/
│   │   ├── privilege                 # 权限配置
│   │   └── resource                  # 资源配置
│   ├── wizard/
│   │   ├── install                   # 安装向导
│   │   ├── uninstall                 # 卸载向导
│   │   └── config                    # 配置向导
│   ├── manifest                      # 应用元数据
│   ├── ICON.PNG                      # 64x64 图标
│   ├── ICON_256.PNG                  # 256x256 图标
│   └── LICENSE                       # 许可证
│
├── data/                              # 本地测试数据目录
│   ├── config/                       # 配置文件
│   │   └── cookies.txt               # 115 cookies 文件
│   ├── logs/                         # 日志目录
│   └── db/                           # 数据库目录
│
├── scripts/                           # 构建脚本
│   ├── build.py                      # 主构建脚本
│   ├── build_fpk.py                  # 飞牛打包脚本
│   └── dev.py                        # 本地开发启动脚本
│
├── .gitignore
└── README.md
```

### 2.2 核心依赖

**后端（Python）**
```
p115client>=0.0.8
fastapi>=0.110.0
uvicorn>=0.27.0
python-multipart>=0.0.9
orjson>=3.9.0
```

**前端（Vue 3）**
```
vue@3.x
vue-router@4.x
pinia@2.x
element-plus@2.x
axios@1.x
vite@5.x
```

---

## 三、飞牛 fnOS 应用配置

### 3.1 manifest
```ini
appname=onefive
version=0.1.0
display_name=壹伍
desc=基于 p115client 的 115 网盘管理应用，提供文件管理、下载、分享等功能
platform=all
source=thirdparty
maintainer=OneFive Team
distributor=OneFive Team
os_min_version=0.9.27
desktop_uidir=ui
desktop_applaunchname=onefive.APPLICATION
service_port=11580
checkport=true
```

### 3.2 config/privilege
```json
{
  "defaults": {
    "run-as": "package"
  },
  "username": "onefive",
  "groupname": "onefive"
}
```

### 3.3 config/resource
```json
{
  "data-share": {
    "shares": [
      {
        "name": "onefive",
        "permission": {
          "rw": ["onefive"]
        }
      }
    ]
  }
}
```

### 3.4 cmd/main 生命周期脚本
```bash
#!/bin/bash

case $1 in
start)
  # 启动 FastAPI 服务器
  cd "$TRIM_APPDEST/app"
  python -m uvicorn server.main:app --host 0.0.0.0 --port $TRIM_SERVICE_PORT \
    --log-level info --log-config logging.conf &
  echo $! > "$TRIM_PKGVAR/app.pid"
  exit 0
  ;;
stop)
  # 停止服务器
  if [ -f "$TRIM_PKGVAR/app.pid" ]; then
    kill $(cat "$TRIM_PKGVAR/app.pid") 2>/dev/null
    rm -f "$TRIM_PKGVAR/app.pid"
  fi
  exit 0
  ;;
status)
  # 检查运行状态
  if [ -f "$TRIM_PKGVAR/app.pid" ] && kill -0 $(cat "$TRIM_PKGVAR/app.pid") 2>/dev/null; then
    exit 0
  else
    exit 3
  fi
  ;;
*)
  exit 1
  ;;
esac
```

### 3.5 环境变量（飞牛系统提供）

| 变量名 | 说明 |
|--------|------|
| `TRIM_APPNAME` | 应用名称 |
| `TRIM_APPVER` | 应用版本 |
| `TRIM_APPDEST` | 应用安装目录 |
| `TRIM_PKGETC` | 配置文件目录 |
| `TRIM_PKGVAR` | 数据目录 |
| `TRIM_SERVICE_PORT` | 服务端口 |
| `TRIM_USERNAME` | 应用用户名 |
| `TRIM_TEMP_LOGFILE` | 日志文件路径 |

---

## 四、实现计划

### 第一阶段：项目骨架搭建

#### 4.1 后端骨架
1. 创建 Python 项目结构（backend/）
2. 配置 pyproject.toml 和依赖
3. 实现 FastAPI 主入口
4. 实现配置管理模块
5. 实现 P115Client 管理器

#### 4.2 前端骨架
1. 使用 Vite 创建 Vue 3 项目
2. 配置 Element Plus UI 框架
3. 配置 Vue Router 路由
4. 配置 Pinia 状态管理
5. 配置 Axios 请求封装

#### 4.3 本地测试环境
1. 创建 data/ 目录结构
2. 配置本地开发启动脚本
3. 配置 CORS 跨域（开发环境）

### 第二阶段：核心功能实现

#### 4.4 认证模块
- Cookie 文件管理
- 扫码登录集成
- 自动重登录

#### 4.5 文件管理模块
- 目录浏览 API
- 文件搜索 API
- 文件操作 API（创建/重命名/移动/复制/删除）

#### 4.6 下载模块
- 获取下载链接
- 批量下载链接
- 302 直链转发

#### 4.7 上传模块
- 文件上传
- 分片上传

#### 4.8 分享模块
- 创建/管理分享
- 接收分享

#### 4.9 离线下载模块
- 添加离线任务
- 任务列表
- 配额查询

### 第三阶段：前端界面开发

#### 4.10 登录页面
- 扫码登录界面
- 登录状态管理

#### 4.11 文件管理页面
- 目录树组件
- 文件列表组件
- 文件操作工具栏
- 文件预览

#### 4.12 下载管理页面
- 下载链接列表
- 批量下载

#### 4.13 分享管理页面
- 分享列表
- 创建分享

#### 4.14 离线下载页面
- 离线任务列表
- 添加任务

### 第四阶段：飞牛打包

#### 4.15 构建脚本
```python
# scripts/build.py 功能：
# 1. 构建前端：cd frontend && npm run build
# 2. 安装后端依赖：pip install --target onefive/app/vendor -r requirements.txt
# 3. 复制后端代码到 onefive/app/server/
# 4. 复制前端产物到 onefive/app/ui/
# 5. 复制飞牛配置文件
```

#### 4.16 fnpack 打包
```bash
cd onefive
fnpack build
# 生成 onefive-0.1.0.fpk
```

---

## 五、关键技术决策

### 5.1 为什么选择 P115Client（Cookie 认证）？
- 461 个方法，覆盖所有功能
- 支持自动重新登录
- 对个人 NAS 应用更简单实用

### 5.2 为什么选择 FastAPI？
- 原生异步支持，与 p115client 完美配合
- 自动生成 API 文档
- 轻量级，适合嵌入式部署

### 5.3 为什么选择 Vue 3 + Element Plus？
- Vue 3 组合式 API，开发效率高
- Element Plus 组件丰富，开箱即用
- 构建产物体积小，适合嵌入式部署

### 5.4 为什么选择原生应用而非 Docker？
- 更轻量，无需 Docker 运行时
- 直接使用飞牛文件系统权限管理
- 与飞牛桌面集成更紧密

### 5.5 架构兼容策略
- Python 依赖：使用纯 Python 包，避免平台特定二进制
- 前端：纯静态文件，架构无关
- manifest：`platform=all`

---

## 六、验证步骤

### 6.1 本地开发验证
```bash
# 1. 安装后端依赖
cd backend
pip install -e .

# 2. 启动后端
python -m uvicorn onefive.main:app --port 11580 --reload

# 3. 启动前端
cd frontend
npm install
npm run dev

# 4. 访问 http://localhost:5173 测试
```

### 6.2 本地集成测试
```bash
# 1. 构建前端
cd frontend
npm run build

# 2. 启动完整服务
cd ..
python scripts/dev.py

# 3. 访问 http://localhost:11580 测试
```

### 6.3 飞牛打包测试
```bash
# 1. 构建应用
python scripts/build.py

# 2. 打包
cd onefive
fnpack build

# 3. 安装到飞牛设备测试
```

---

## 七、待确认问题

1. **功能优先级**：首版需要实现哪些核心功能？建议先实现登录 + 文件浏览 + 下载链接获取。
2. **115 账号数量**：是否需要支持多个 115 账号切换？
