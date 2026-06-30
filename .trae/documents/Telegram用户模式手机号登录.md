# Telegram 用户模式：手机号+验证码登录

## 概述
将 Telegram 用户模式从手动输入 Session 字符串改为手机号+验证码登录流程，登录成功后自动持久化 Session 到数据库，后续自动使用。

## 当前状态
- 用户模式需要手动输入 `tg_api_id` + `tg_api_hash` + `tg_session_string`
- 普通用户无法独立生成 Session 字符串
- Telethon 本身支持 `client.start(phone=...)` 交互式登录

## 改动计划

### 1. 后端：新增登录 API

**文件**：`d:\OneFive\backend\src\onefive\api\notification.py`

新增 3 个端点：

- `POST /api/notification/telegram/send-code` — 发送验证码
  - 参数：`{phone, api_id, api_hash}`
  - 用 `TelegramClient` + `StringSession('')` 连接
  - 调用 `client.send_code_request(phone)`
  - 保存临时客户端到内存（等待验证码）
  - 返回 `{phone_hash}` 用于后续 sign-in

- `POST /api/notification/telegram/sign-in` — 输入验证码完成登录
  - 参数：`{phone, code, password?}`
  - 调用 `client.sign_in(phone, code)` 或 `client.sign_in(phone, code, password=password)`
  - 登录成功后 `StringSession.save()` 获取 session_string
  - 自动保存到 DB：`tg_session_string`、`tg_api_id`、`tg_api_hash`
  - 返回成功/失败

- `POST /api/notification/telegram/check-login` — 检查当前登录状态
  - 用已保存的 session 尝试连接
  - 返回是否已授权

### 2. 后端：TelegramChannel 添加登录方法

**文件**：`d:\OneFive\backend\src\onefive\notification\telegram\channel.py`

新增方法：
- `async def send_code(phone, api_id, api_hash) -> str` — 发送验证码，返回 phone_hash
- `async def sign_in(phone, code, password=None) -> bool` — 验证码登录，成功后自动保存 session
- `async def check_login() -> bool` — 检查是否已登录

关键：登录过程中需要保持客户端连接（等待验证码），用 `_login_client` 和 `_login_phone_hash` 临时状态管理，设置 5 分钟超时自动清理。

### 3. 前端：Settings.vue 改造用户模式 UI

**文件**：`d:\OneFive\frontend\src\views\Settings.vue`

将"用户模式（可选）"区域从 3 个输入框改为分步登录流程：

**步骤1**：输入 API ID + API Hash + 手机号 → 点击"发送验证码"
**步骤2**：输入验证码 → 点击"登录"
**成功**：显示"已登录"状态，Session 自动保存

如果已登录（session 有效），显示"已登录"状态 + "重新登录"按钮。

### 4. 前端：notification.ts 添加登录 API

**文件**：`d:\OneFive\frontend\src\api\notification.ts`

新增：
```typescript
sendCode(phone: string, apiId: string, apiHash: string): Promise<any>
signIn(phone: string, code: string, password?: string): Promise<any>
checkLogin(): Promise<any>
```

## 涉及文件
| 文件 | 操作 |
|------|------|
| `backend/src/onefive/notification/telegram/channel.py` | 添加 send_code/sign_in/check_login 方法 |
| `backend/src/onefive/api/notification.py` | 添加 3 个登录 API 端点 |
| `frontend/src/api/notification.ts` | 添加 3 个登录 API 方法 |
| `frontend/src/views/Settings.vue` | 改造用户模式 UI 为分步登录流程 |

## 流程图

```
用户输入 API ID + API Hash + 手机号
    ↓
POST /telegram/send-code
    → Telethon 发送验证码
    → 保存临时客户端到内存
    ← 返回成功
    ↓
用户输入验证码
    ↓
POST /telegram/sign-in
    → Telethon 验证码登录
    → StringSession.save() 获取 session
    → 保存 session + api_id + api_hash 到 DB
    ← 返回成功 + 自动重连
    ↓
后续使用：从 DB 读取 session → 自动登录
```

## 验证步骤
1. 输入 API ID + API Hash + 手机号，点击发送验证码，确认收到 Telegram 验证码
2. 输入验证码，点击登录，确认登录成功
3. 刷新页面，确认状态显示"已登录"
4. 点击测试，确认能收到测试消息
5. 重启后端，确认自动使用保存的 session 连接
