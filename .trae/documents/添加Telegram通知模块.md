# 添加 Telegram 通知模块（模块化架构）

## 概述
为 OneFive 添加通知模块，采用模块化架构便于多平台扩展。首期实现 Telegram（Bot + 用户模式），使用 Telethon 库。

## 模块化架构

```
backend/src/onefive/
├── notification/                    # 通知模块包
│   ├── __init__.py                  # 导出 NotificationManager
│   ├── base.py                      # 抽象基类 NotificationChannel
│   ├── manager.py                   # 通知管理器（统一调度）
│   ├── telegram/                    # Telegram 渠道
│   │   ├── __init__.py
│   │   └── channel.py              # TelegramChannel 实现
│   └── [future]                     # 未来扩展
│       └── wechat/
│           └── channel.py
├── api/
│   └── notification.py              # 通知 API 路由
```

### base.py — 抽象基类
```python
class NotificationChannel(ABC):
    name: str           # 渠道名（telegram/wechat/...）
    @abstractmethod async def send_message(message, image_url=None)
    @abstractmethod async def is_configured() -> bool
    @abstractmethod async def is_connected() -> bool
    @abstractmethod async def connect()
    @abstractmethod async def disconnect()
    @abstractmethod def get_settings_schema() -> dict  # 返回该渠道的配置项定义
    @abstractmethod def get_status() -> dict           # 返回连接状态
```

### manager.py — 通知管理器
```python
class NotificationManager:
    channels: Dict[str, NotificationChannel]  # 已注册的渠道
    
    def register(channel)          # 注册渠道
    async def send_all(message)    # 向所有已启用渠道发送
    async def send_to(name, msg)   # 向指定渠道发送
    def get_channel(name)          # 获取渠道实例
    def list_channels()            # 列出所有渠道及状态
```

### telegram/channel.py — Telegram 实现
- Bot 模式：`TelegramClient(bot_token=token)`
- 用户模式：`TelegramClient(session_string=session)`
- 代理：`proxy = (socks.SOCKS5, host, port, ...)` 或 HTTP 代理
- 发送：`client.send_message(target, message, file=image_url)`

## 实施步骤

### 1. 添加依赖
**文件**：`backend/pyproject.toml` + `backend/requirements.txt`
- `telethon>=1.36.0`
- `pysocks>=1.7.1`

### 2. 创建 notification 包
**新建**：
- `notification/__init__.py` — 导出 manager
- `notification/base.py` — NotificationChannel 抽象基类
- `notification/manager.py` — NotificationManager
- `notification/telegram/__init__.py`
- `notification/telegram/channel.py` — TelegramChannel

### 3. 通知 API
**新建**：`api/notification.py`
- `GET /api/notification/settings` — 获取所有渠道配置
- `PUT /api/notification/settings` — 更新指定渠道配置
- `POST /api/notification/test` — 发送测试消息
- `POST /api/notification/connect` — 连接指定渠道
- `GET /api/notification/status` — 获取所有渠道状态

**修改**：`main.py` 注册路由

### 4. 整理完成后触发通知
**修改**：`organize_service.py` 的 `execute_organize` 成功后调用 `manager.send_all()`

### 5. 前端
**新建**：`frontend/src/api/notification.ts`
**修改**：`frontend/src/views/Settings.vue` 添加通知设置卡片

### 6. 日志映射
**修改**：`logger.py` 添加 `"onefive.notification": "通知"` 等映射

## Telegram 配置项
| Key | 说明 |
|-----|------|
| `tg_enabled` | 启用 |
| `tg_bot_token` | Bot Token |
| `tg_api_id` | API ID（用户模式） |
| `tg_api_hash` | API Hash（用户模式） |
| `tg_session_string` | Session（用户模式） |
| `tg_proxy_enabled` | 代理开关 |
| `tg_proxy_url` | 代理地址 |
| `tg_notify_chat` | 通知目标 |

## 扩展示例
添加微信通知只需：
1. 创建 `notification/wechat/channel.py` 实现 `NotificationChannel`
2. 在 `manager.py` 中 `register(WechatChannel())`
3. 前端设置页自动生成配置表单（通过 `get_settings_schema()`）

## 涉及文件
| 文件 | 操作 |
|------|------|
| `backend/pyproject.toml` | 添加依赖 |
| `backend/requirements.txt` | 添加依赖 |
| `backend/src/onefive/notification/__init__.py` | 新建 |
| `backend/src/onefive/notification/base.py` | 新建 |
| `backend/src/onefive/notification/manager.py` | 新建 |
| `backend/src/onefive/notification/telegram/__init__.py` | 新建 |
| `backend/src/onefive/notification/telegram/channel.py` | 新建 |
| `backend/src/onefive/api/notification.py` | 新建 |
| `backend/src/onefive/main.py` | 注册路由 |
| `backend/src/onefive/logger.py` | 添加映射 |
| `backend/src/onefive/services/organize_service.py` | 触发通知 |
| `frontend/src/api/notification.ts` | 新建 |
| `frontend/src/views/Settings.vue` | 通知设置卡片 |
