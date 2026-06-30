# 302 直链服务实现计划

## 一、概述

为 OneFive 添加 302 直链服务功能，基于 `p115nano302` 模块提供 302 重定向直链。直链存在有效期，通过数据库缓存提高响应速度。

## 二、当前状态分析

### 已有基础设施
- **p115client** 已安装（`>=0.0.8`）
- **SQLite setting 表** 统一存储配置
- **ConfigService** 提供配置 CRUD（单例）
- **AuthService** 管理 cookies
- **Settings.vue** 已有 4 个卡片区域

### 缺失部分
- `p115nano302` 未安装
- 无 302 服务生命周期管理
- 无直链缓存表
- 无 302 相关 API 和前端设置

## 三、架构设计

### 原理

```
客户端请求直链：
  GET http://IP:自定义端口/d115/{filename}?pickcode=xxx
  或 GET http://IP:自定义端口/d115/?pickcode=xxx
  或 GET http://IP:自定义端口/d115/?id=xxx

                    ┌─────────────────────────────────┐
                    │   OneFive 主服务 (FastAPI:11580)  │
                    │   ┌───────────────────────────┐  │
                    │   │  direct_link_service.py   │  │
                    │   │  - 服务生命周期管理        │  │
                    │   │  - 直链缓存管理            │  │
                    │   └───────────┬───────────────┘  │
                    └───────────────┼──────────────────┘
                                    │
                    ┌───────────────▼──────────────────┐
                    │  302 服务 (p115nano302:自定义端口) │
                    │  路由前缀: /d115                  │
                    │  ┌─────────────────────────────┐ │
                    │  │ 缓存层（拦截请求）           │ │
                    │  │ 1. 查 SQLite 缓存表          │ │
                    │  │ 2. 命中且未过期 → 302 缓存URL│ │
                    │  │ 3. 未命中/已过期 → 调 115 API│ │
                    │  │ 4. 写入缓存 → 302 新URL      │ │
                    │  └─────────────────────────────┘ │
                    └──────────────────────────────────┘
                                    │
                                    ▼
                           115 CDN（302 重定向目标）
```

### 直链有效期说明
- 115 返回的下载 URL 有有效期（通常 2-4 小时）
- 缓存表记录 `expires_at`，过期自动刷新
- 每次请求检查有效期，过期则重新获取

### 数据库缓存表

```sql
CREATE TABLE IF NOT EXISTS direct_link_cache (
    pickcode   TEXT PRIMARY KEY,     -- pickcode（主键）
    file_id    TEXT NOT NULL,        -- 文件 ID（索引）
    url        TEXT NOT NULL,        -- 302 重定向 URL
    expires_at TIMESTAMP NOT NULL,   -- 过期时间
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_direct_link_file_id 
    ON direct_link_cache(file_id);
```

### 配置键（SQLite setting 表）

| 键名 | 说明 | 默认值 |
|------|------|--------|
| `direct_link_enabled` | 是否启用直链服务 | `"0"` |
| `direct_link_port` | 直链服务端口 | `"11581"` |

### 基地址
`http://IP:自定义端口/d115`（注意 `/d115` 前缀）

### 支持的查询格式（p115nano302 原生支持）

基地址设为 `http://host:port/d115`，以下所有格式均在 `/d115` 前缀下生效，优先使用 `/` 斜杠格式：

**1. 带（任意）名字查询 pickcode**（名字在前，pickcode 在后）
```
http://host:port/d115/Novembre.2022.FRENCH.2160p.BluRay.DV.HEVC.DTS-HD.MA.5.1.mkv/pickcode=ecjq9ichcb40lzlvx
http://host:port/d115/Novembre.2022.FRENCH.2160p.BluRay.DV.HEVC.DTS-HD.MA.5.1.mkv/ecjq9ichcb40lzlvx
```

**2. 带（任意）名字查询 id**（名字在前，id 在后）
```
http://host:port/d115/Novembre.2022.FRENCH.2160p.BluRay.DV.HEVC.DTS-HD.MA.5.1.mkv/2691590992858971545
http://host:port/d115/Novembre.2022.FRENCH.2160p.BluRay.DV.HEVC.DTS-HD.MA.5.1.mkv/id=2691590992858971545
```

**3. 带（任意）名字查询 sha1**（名字在前，sha1 在后）
```
http://host:port/d115/Novembre.2022.FRENCH.2160p.BluRay.DV.HEVC.DTS-HD.MA.5.1.mkv/E7FAA0BE343AF2DA8915F2B694295C8E4C91E691
http://host:port/d115/Novembre.2022.FRENCH.2160p.BluRay.DV.HEVC.DTS-HD.MA.5.1.mkv/sha1=E7FAA0BE343AF2DA8915F2B694295C8E4C91E691
```

**4. 用 id 带（任意）名字查询分享文件**（名字在前，参数在后）
```
http://host:port/d115/Cosmos.S01E01.1080p.AMZN.WEB-DL.DD+5.1.H.264-iKA.mkv/share_code=sw68md23w8m/receive_code=q353/id=2580033742990999218
http://host:port/d115/Cosmos.S01E01.1080p.AMZN.WEB-DL.DD+5.1.H.264-iKA.mkv/share_code=sw68md23w8m/id=2580033742990999218
```

## 四、实施步骤

### Step 1: 安装依赖

**修改文件**: `d:\OneFive\backend\requirements.txt` 和 `d:\OneFive\backend\pyproject.toml`

添加：
```
p115nano302>=0.0.6
```

### Step 2: 创建直链缓存数据库表

**修改文件**: `d:\OneFive\backend\src\onefive\db\database.py`

在 `init_db()` 中添加 `direct_link_cache` 表的建表语句。

### Step 3: 创建直链缓存服务

**新建文件**: `d:\OneFive\backend\src\onefive\services\direct_link_cache_service.py`

核心逻辑：
- `DirectLinkCacheService` 类（单例模式）
- `get_url(pickcode)` — 查询缓存，命中且未过期返回 URL
- `get_url_by_file_id(file_id)` — 按 file_id 查询缓存
- `set_url(pickcode, file_id, url, expires_in)` — 写入/更新缓存
- `invalidate(pickcode)` — 使缓存失效
- `cleanup()` — 清理过期缓存

### Step 4: 创建 302 直链服务

**新建文件**: `d:\OneFive\backend\src\onefive\services\direct_link_service.py`

核心逻辑：
- `DirectLinkService` 类（单例模式）
- `start()` — 启动 302 服务（后台守护线程运行 uvicorn）
- `stop()` — 停止 302 服务
- `is_running()` — 查询运行状态
- `get_settings()` / `save_settings()` — 配置读写

p115nano302 集成方式：
- 使用 `p115nano302.make_application(cookies)` 创建 ASGI 应用
- 包裹缓存层中间件，拦截请求先查缓存
- 缓存未命中时放行给 p115nano302 处理，响应后写入缓存

### Step 5: 创建 API 路由

**新建文件**: `d:\OneFive\backend\src\onefive\api\direct_link.py`

接口：
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/direct-link/settings` | 获取设置（enabled, port, running, mode） |
| POST | `/api/direct-link/settings` | 保存设置（enabled, port） |
| POST | `/api/direct-link/start` | 启动服务 |
| POST | `/api/direct-link/stop` | 停止服务 |
| GET | `/api/direct-link/status` | 查询状态 |

### Step 6: 注册路由 + 生命周期

**修改文件**: `d:\OneFive\backend\src\onefive\main.py`

- 导入并注册 `direct_link_router`
- `lifespan` 启动时：如果 `direct_link_enabled == "1"`，自动启动
- `lifespan` 关闭时：停止 302 服务

### Step 7: 前端 API 模块

**新建文件**: `d:\OneFive\frontend\src\api\directLink.ts`

```ts
export interface DirectLinkSettings {
  enabled: boolean
  port: number
  running: boolean
}
```

### Step 8: 前端设置卡片

**修改文件**: `d:\OneFive\frontend\src\views\Settings.vue`

在"通知设置"卡片之后，添加第 5 个卡片："直链服务"

卡片内容：
- 图标：链接图标（紫色语义色）
- 开关：启用/禁用
- 端口输入：自定义端口（默认 11581）
- 状态指示：运行中/已停止
- 启动/停止按钮
- 提示信息：基地址 `http://IP:端口/d115`

## 五、Assumptions & Decisions

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 302 模块 | p115nano302 | 轻量无 p115client 依赖，直接用 cookies |
| 缓存粒度 | pickcode + file_id 双索引 | 查询更灵活 |
| 默认端口 | 11581 | 与主服务 11580 区分 |
| 路由前缀 | /d115 | 用户指定 |
| 缓存有效期 | 由 115 返回的 URL 有效期决定 | 通常 2-4 小时 |
| 服务运行方式 | 后台守护线程 + 独立 uvicorn | 不影响主服务 |

## 六、验证

1. `pip install p115nano302` 安装成功
2. 后端启动无报错，缓存表自动创建
3. 前端设置页显示直链服务卡片
4. 开关切换 + 端口修改 + 保存成功
5. 启动服务后，验证所有查询格式均返回 302：
   - `http://localhost:11581/d115/Movie.mkv/ecjq9ichcb40lzlvx` — 带名字查询 pickcode
   - `http://localhost:11581/d115/Movie.mkv/2691590992858971545` — 带名字查询 id
   - `http://localhost:11581/d115/Movie.mkv/E7FAA0BE...` — 带名字查询 sha1
   - `http://localhost:11581/d115/Movie.mkv/share_code=xxx/id=xxx` — 分享文件查询
6. 第二次请求同 pickcode，从缓存返回（响应更快）
7. 停止服务后，端口释放
8. 重启应用后，如果之前已启用，自动启动
