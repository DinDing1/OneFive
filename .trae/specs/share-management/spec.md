# 分享管理模块 Spec

## Why

用户需要管理 115 网盘分享链接中的文件信息。当前项目只能管理自己网盘中的文件，无法处理他人分享的文件。用户希望通过 Telegram 机器人发送分享链接，自动解析文件信息、应用分类策略，形成虚拟文件目录结构，为后续直链播放做准备。

## What Changes

### 新增数据库表
- `share_source` — 分享来源表（存储分享链接元信息，自增 ID 作为唯一关联键）
- `share_file` — 虚拟文件表（通过 `source_id` 关联 share_source，支持目录层级）

### 新增后端模块
- `services/share_service.py` — 分享链接解析服务（调用 p115client 分享接口）
- `services/share_organize_service.py` — 分享文件整理服务（复用 classify_service，结果写入 DB）
- `api/share.py` — 分享管理 API 路由

### 修改后端模块
- `db/database.py` — 新增 share_source 和 share_file 建表语句
- `main.py` — 注册分享路由

### 新增前端模块
- `views/Share.vue` — 分享管理页面
- `api/share.ts` — 分享管理 API

### 修改前端模块
- `router/index.ts` — 新增 /share 路由
- `views/Layout.vue` — 侧边栏新增"分享管理"菜单项

## Impact

### Affected code
- `backend/src/onefive/db/database.py` — 新增表
- `backend/src/onefive/main.py` — 注册路由
- `frontend/src/router/index.ts` — 新增路由
- `frontend/src/views/Layout.vue` — 新增菜单

## 数据库设计

### share_source 表（分享来源）

```sql
CREATE TABLE IF NOT EXISTS share_source (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,  -- 唯一关联键
    share_code   TEXT NOT NULL UNIQUE,                -- 115 分享码
    receive_code TEXT DEFAULT '',                     -- 提取码
    share_name   TEXT DEFAULT '',                     -- 分享名称（根目录名）
    share_url    TEXT DEFAULT '',                     -- 原始分享链接
    source_type  TEXT DEFAULT 'manual',               -- 来源：manual/bot
    file_count   INTEGER DEFAULT 0,                   -- 文件总数
    total_size   INTEGER DEFAULT 0,                   -- 总大小
    status       TEXT DEFAULT 'pending',              -- pending/parsed/organized/error
    error_msg    TEXT DEFAULT '',                     -- 错误信息
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### share_file 表（虚拟文件）

关键：通过 `source_id` 关联 share_source.id，不通过 share_code。

```sql
CREATE TABLE IF NOT EXISTS share_file (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    INTEGER NOT NULL,                    -- 关联 share_source.id（唯一码）
    file_id      TEXT NOT NULL,                       -- 115 文件 ID（用于直链查询）
    parent_id    TEXT DEFAULT '0',                    -- 父目录 ID（0=根目录）
    name         TEXT NOT NULL,                       -- 原始文件名
    is_dir       INTEGER DEFAULT 0,                   -- 是否目录
    size         INTEGER DEFAULT 0,                   -- 文件大小
    sha1         TEXT DEFAULT '',                     -- 文件 SHA1

    -- 整理信息（由 share_organize_service 填充）
    media_type   TEXT DEFAULT '',                     -- movie/tv
    title        TEXT DEFAULT '',                     -- 识别标题
    year         TEXT DEFAULT '',                     -- 年份
    season       INTEGER DEFAULT 0,                   -- 季号
    episode      TEXT DEFAULT '',                     -- 集号
    tmdb_id      INTEGER DEFAULT 0,                   -- TMDB ID
    tmdb_poster  TEXT DEFAULT '',                     -- 海报 URL
    tmdb_rating  REAL DEFAULT 0,                      -- 评分
    category     TEXT DEFAULT '',                     -- 分类路径
    tech_info    TEXT DEFAULT '{}',                   -- 技术信息 JSON
    overview     TEXT DEFAULT '',                     -- 简介

    organized    INTEGER DEFAULT 0,                   -- 是否已整理
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(source_id, file_id)                        -- 同一来源下文件 ID 唯一
);
CREATE INDEX IF NOT EXISTS idx_share_file_source ON share_file(source_id);
CREATE INDEX IF NOT EXISTS idx_share_file_parent ON share_file(source_id, parent_id);
CREATE INDEX IF NOT EXISTS idx_share_file_name ON share_file(name);
CREATE INDEX IF NOT EXISTS idx_share_file_category ON share_file(category);
```

### 关联关系

```
share_source.id (1) ──→ (N) share_file.source_id
```

查询示例：
```sql
-- 列出某个分享的根目录文件
SELECT * FROM share_file WHERE source_id = ? AND parent_id = '0';

-- 搜索所有分享中的文件
SELECT f.*, s.share_code FROM share_file f
JOIN share_source s ON f.source_id = s.id
WHERE f.name LIKE '%keyword%';
```

## 分享直链格式

分享文件的 302 直链使用 `id`（文件 ID），不使用 pickcode：

```
http://host:port/d115?share_code={share_code}&receive_code={receive_code}&id={file_id}
```

示例：
```
http://localhost:11581/d115?share_code=swsfpoi3np7&receive_code=jejn&id=3459216959013390231
```

## ADDED Requirements

### Requirement: 添加分享链接
用户通过输入分享链接（含提取码），系统自动解析并存储文件信息。

#### Scenario: 成功添加
- **WHEN** 用户输入 `https://115.com/s/xxx?password=yyy`
- **THEN** 系统提取 share_code 和 receive_code，调用 p115client share_iterdir 获取文件列表，写入 share_source（返回 source_id）和 share_file（source_id 关联）

#### Scenario: 链接格式错误
- **WHEN** 用户输入非 115 分享链接
- **THEN** 返回错误提示"不是有效的 115 分享链接"

### Requirement: 浏览分享文件（原始视图）
用户可以像浏览自己网盘一样浏览分享文件的原始目录结构。

#### Scenario: 目录展开
- **WHEN** 用户点击一个目录
- **THEN** 从 share_file 表查询 source_id + parent_id，显示子文件列表

#### Scenario: 面包屑导航
- **WHEN** 用户在深层目录中
- **THEN** 显示完整的路径面包屑，支持点击跳转

### Requirement: 查看整理后的分类目录（整理视图）
用户可以查看整理后的虚拟分类目录结构，按分类策略组织文件。

#### Scenario: 切换到整理视图
- **WHEN** 用户点击"整理视图"切换按钮
- **THEN** 显示按 category 字段组织的虚拟目录树

#### Scenario: 整理目录结构
- **WHEN** 用户进入整理视图
- **THEN** 显示分类目录结构，例如：
  ```
  电影/
    动画电影/
      白蛇：浮生 (2024)/
        白蛇：浮生.2024.1080p.BluRay.REMUX...mkv
    日韩电影/
      ...
  电视剧/
    日韩剧/
      降世神通 S02 (2006)/
        S02E01.mkv
        S02E02.mkv
    欧美剧/
      ...
  ```
- **AND** 未整理的文件显示在"未分类"分组中

#### Scenario: 整理视图中的操作
- **WHEN** 用户在整理视图中
- **THEN** 支持点击文件查看详情、支持搜索、不支持移动/复制（虚拟文件）

### Requirement: 整理分享文件
用户可以对分享文件执行整理（识别 + 分类），结果写入数据库而非实际移动文件。

#### Scenario: 单文件整理
- **WHEN** 用户选择一个文件点击"识别"
- **THEN** 系统调用 file_info_service 提取信息，调用 TMDB 搜索，调用 classify_service 生成分类路径，更新 share_file 表

#### Scenario: 批量整理
- **WHEN** 用户选择多个文件点击"批量整理"
- **THEN** 逐个识别并分类，更新 share_file 表

### Requirement: 搜索分享文件
用户可以按文件名搜索所有分享文件。

#### Scenario: 关键词搜索
- **WHEN** 用户输入搜索关键词
- **THEN** 在 share_file 表中模糊匹配 name 字段，返回结果（含来源信息）

### Requirement: 删除分享来源
用户可以删除整个分享链接及其所有文件记录。

#### Scenario: 删除确认
- **WHEN** 用户点击删除分享来源
- **THEN** 弹出确认框，确认后删除 share_source（source_id）和关联的所有 share_file 记录

### Requirement: 分享管理页面
前端新增分享管理页面，包含分享链接输入框和文件列表。

#### Scenario: 页面布局
- **WHEN** 用户访问 /share
- **THEN** 显示分享链接输入区 + 已添加的分享列表 + 文件浏览区

## API 设计

### api/share.py（前缀 /api/share）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/add` | 添加分享链接 |
| GET | `/list` | 列出分享来源 |
| DELETE | `/{source_id}` | 删除分享（按 source_id 级联删除） |
| GET | `/{source_id}/files` | 列出原始目录文件（source_id + parent_id） |
| GET | `/{source_id}/organized` | 列出整理后的分类目录（按 category 分组） |
| GET | `/search` | 搜索文件 |
| POST | `/organize` | 整理单个文件 |
| POST | `/organize-batch` | 批量整理 |
| GET | `/{source_id}/info` | 获取分享来源详情 |

### 整理视图 API 说明

`GET /{source_id}/organized` 返回按 category 分组的虚拟目录结构：

```json
{
  "code": 0,
  "data": {
    "categories": [
      {
        "path": "电影/动画电影",
        "name": "动画电影",
        "files": [
          {"file_id": "xxx", "name": "白蛇.mkv", "title": "白蛇：浮生", "year": "2024", ...}
        ]
      },
      {
        "path": "电视剧/日韩剧",
        "name": "日韩剧",
        "files": [...]
      }
    ],
    "unorganized": [
      {"file_id": "xxx", "name": "未整理文件.mkv", ...}
    ]
  }
}
```

## 设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 关联键 | share_source.id（自增唯一码） | 比 share_code 更规范，支持同一分享码重新添加 |
| 直链标识 | file_id（115 文件 ID） | 分享直链用 id，不用 pickcode |
| 整理逻辑复用 | 复用 classify_service + file_info_service | 保持分类策略一致 |
| 目录层级 | parent_id 自引用 | 与 115 网盘目录结构一致 |
| 整理视图 | 按 category 字段分组展示 | 虚拟分类目录，不移动文件 |
| 移动/复制 | 不支持 | 虚拟文件，不做实际操作 |
| Bot 集成 | 暂不实现 | 后期单独做 |
| 直链生成 | 暂不实现 | 后期单独做 |

### Requirement: Bot 自动识别分享链接
用户通过 Telegram 机器人发送 115 分享链接，系统自动解析并存储。

#### Scenario: Bot 收到分享链接
- **WHEN** 用户向 Bot 发送包含 `115.com/s/` 或 `115cdn.com/s/` 的消息
- **THEN** Bot 自动提取 share_code 和 receive_code（从 URL 的 password 参数），调用 share_service.add_share()，回复处理结果

#### Scenario: Bot 回复格式
- **WHEN** 分享链接解析成功
- **THEN** 回复：分享名称、文件数量、总大小、source_id

#### Scenario: Bot 解析失败
- **WHEN** 分享链接无效或解析失败
- **THEN** 回复错误信息

### Requirement: 直链生成（后期实现）
根据分享文件信息生成本地 302 直链，用于播放。

## 不做的事

- ❌ 不修改现有文件管理功能
- ❌ 不修改现有整理功能
- ❌ 不实现直链生成（后期单独做）
- ❌ 不实现分享文件的移动/复制（虚拟文件无此需求）
