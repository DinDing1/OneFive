# Tasks

## Phase 1: 数据库 + 后端核心服务

- [x] Task 1: 数据库表创建
  - 在 `database.py` 的 `_init_tables()` 中新增 `share_source` 和 `share_file` 建表语句
  - share_source.id 为自增唯一关联键
  - share_file.source_id 关联 share_source.id
  - share_file.file_id 存储 115 文件 ID（用于直链查询）
  - 包含所有索引（source、parent、name、category）

- [x] Task 2: 创建 share_service.py（分享链接解析服务）
  - `parse_share_url(url)` — 从 URL 提取 share_code 和 receive_code
  - `add_share(share_url, receive_code, source_type)` — 解析分享链接，调用 p115client share_iterdir 获取文件列表，写入 share_source（获取 source_id）和 share_file（source_id 关联）
  - `list_shares()` — 列出所有分享来源
  - `delete_share(source_id)` — 删除分享来源及关联文件（按 source_id 删除）
  - `list_files(source_id, parent_id, limit, offset)` — 列出分享目录内容（按 source_id + parent_id 查询）
  - `search_files(keyword)` — 搜索分享文件（JOIN share_source 获取 share_code）
  - `get_share_info(source_id)` — 获取分享来源详情（含 share_code、receive_code）

- [x] Task 3: 创建 share_organize_service.py（分享文件整理服务）
  - `organize_file(source_id, file_id)` — 识别单个文件，写入整理结果到 share_file 表
  - `organize_batch(source_id, file_ids)` — 批量整理
  - 复用 classify_service.classify() 和 file_info_service 的提取函数
  - 不执行实际的移动/复制操作
  - 整理完成后更新 share_file 的 organized=1

- [x] Task 4: 创建 api/share.py（API 路由，前缀 /api/share）
  - POST `/add` — 添加分享链接（接收 share_url, receive_code）
  - GET `/list` — 列出分享来源
  - DELETE `/{source_id}` — 删除分享（按 source_id）
  - GET `/{source_id}/files` — 列出原始目录文件（支持 parent_id、limit、offset）
  - GET `/{source_id}/organized` — 列出整理后的分类目录（按 category 分组，返回 categories + unorganized）
  - GET `/search` — 搜索文件（关键词）
  - POST `/organize` — 整理单个文件（接收 source_id, file_id）
  - POST `/organize-batch` — 批量整理（接收 source_id, file_ids[]）
  - GET `/{source_id}/info` — 获取分享来源详情

- [x] Task 5: 注册路由到 main.py

## Phase 2: 前端页面

- [x] Task 6: 创建 frontend/src/api/share.ts（前端 API 模块）
  - addShare(shareUrl, receiveCode)
  - listShares()
  - deleteShare(sourceId)
  - listFiles(sourceId, parentId, limit, offset)
  - searchFiles(keyword)
  - organizeFile(sourceId, fileId)
  - organizeBatch(sourceId, fileIds)
  - getShareInfo(sourceId)

- [x] Task 7: 创建 frontend/src/views/Share.vue（分享管理页面）
  - 顶部：分享链接输入框 + 添加按钮
  - 左侧/顶部：分享来源列表（显示 share_name、file_count、状态，可切换）
  - 视图切换：原始视图 / 整理视图
  - 原始视图：文件列表（表格，支持目录层级展开，按 source_id + parent_id 查询）
  - 整理视图：按分类目录展示（电影/电视剧等），未整理文件单独分组
  - 面包屑导航
  - 操作：识别/批量识别/删除分享/搜索
  - 样式：glass-card + neu-raised，与 Files.vue 风格一致

- [x] Task 8: 修改 router/index.ts 新增 /share 路由

- [x] Task 9: 修改 Layout.vue 侧边栏新增"分享管理"菜单项（文件管理图标下方）

## Phase 3: Bot 集成

- [x] Task 10: 修改 notification/telegram/channel.py，Bot 模式下自动识别分享链接
  - 在消息处理中检测 `115.com/s/` 或 `115cdn.com/s/` 链接
  - 提取 share_code 和 receive_code（从 URL 的 password 参数）
  - 调用 share_service.add_share() 处理
  - 回复处理结果（分享名称、文件数量、总大小、source_id）
  - 失败时回复错误信息

## Task Dependencies

- Task 1 → Task 2 → Task 3 → Task 4 → Task 5（后端串行）
- Task 6 → Task 7（前端串行）
- Task 8, Task 9 可并行
- Task 5 完成后才能 Task 6-9（前端依赖后端 API）
- Task 2 完成后才能 Task 10（Bot 依赖 share_service）
