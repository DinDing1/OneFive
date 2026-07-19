"""
Telegram 通知渠道

支持两种模式：
- Bot 模式：使用 Bot Token 通过 Bot API 发送
- 用户模式：使用 Telethon MTProto 协议（需要 API ID/Hash + Session）

两种模式独立运行，各自有独立的客户端实例。
"""
import re
import asyncio
from typing import Dict, Any, Optional, List
from ..base import NotificationChannel
from ...services.config_service import get_config_service
from ...logger import get_logger

logger = get_logger(__name__)


def format_size(size: int) -> str:
    """将字节数格式化为可读的文件大小字符串"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.1f} MB"
    else:
        return f"{size / 1024 ** 3:.2f} GB"


# 配置键名常量
CFG_ENABLED = "tg_enabled"
CFG_BOT_ENABLED = "tg_bot_enabled"
CFG_BOT_TOKEN = "tg_bot_token"
CFG_USER_ENABLED = "tg_user_enabled"
CFG_API_ID = "tg_api_id"
CFG_API_HASH = "tg_api_hash"
CFG_SESSION = "tg_session_string"
CFG_PROXY_ENABLED = "tg_proxy_enabled"
CFG_PROXY_URL = "tg_proxy_url"
CFG_NOTIFY_CHAT = "tg_notify_chat"
CFG_ADMIN_IDS = "tg_admin_ids"


class TelegramChannel(NotificationChannel):
    """Telegram 通知渠道"""

    def __init__(self):
        self._bot_client = None
        self._user_client = None
        self._bot_connected = False
        self._user_connected = False
        # 登录临时状态
        self._login_client = None
        self._login_phone = ""
        self._login_api_id = ""
        self._login_api_hash = ""
        self._login_time = 0

    @property
    def name(self) -> str:
        return "telegram"

    @property
    def display_name(self) -> str:
        return "Telegram"

    def _cfg(self, key: str, default: str = "") -> str:
        return get_config_service().get(key) or default

    def _get_admin_ids(self) -> list:
        raw = self._cfg(CFG_ADMIN_IDS)
        if not raw:
            return []
        result = []
        for x in raw.split(','):
            x = x.strip()
            if not x:
                continue
            # 用 try/except int() 替代 isdigit()，避免 Unicode 数字导致崩溃
            try:
                result.append(int(x))
            except ValueError:
                logger.warning(f"忽略无效的管理员 ID: {x}")
        return result

    def is_admin(self, user_id: int) -> bool:
        admins = self._get_admin_ids()
        if not admins:
            return True
        return user_id in admins

    def _get_proxy(self):
        if self._cfg(CFG_PROXY_ENABLED) not in ("true", "1", "True"):
            return None
        proxy_url = self._cfg(CFG_PROXY_URL)
        if not proxy_url:
            return None

        match = re.match(
            r'(socks[45]|http)://(?:(.+?):(.+?)@)?(.+?):(\d+)',
            proxy_url, re.IGNORECASE
        )
        if not match:
            match = re.match(r'([^:]+):(\d+)$', proxy_url.strip())
            if match:
                import python_socks
                return (python_socks.ProxyType.SOCKS5, match.group(1), int(match.group(2)), True, None, None)
            return None

        proto = match.group(1).lower()
        user = match.group(2)
        password = match.group(3)
        host = match.group(4)
        port = int(match.group(5))

        import python_socks
        proxy_type = python_socks.ProxyType.SOCKS5 if '5' in proto else (python_socks.ProxyType.SOCKS4 if '4' in proto else python_socks.ProxyType.HTTP)

        if user and password:
            return (proxy_type, host, port, True, user, password)
        return (proxy_type, host, port, True, None, None)

    # ==================== 客户端管理 ====================

    async def _ensure_bot(self):
        """确保 Bot 客户端已连接"""
        if self._bot_client is not None and self._bot_connected:
            return

        bot_enabled = self._cfg(CFG_BOT_ENABLED) in ("true", "1", "True")
        bot_token = self._cfg(CFG_BOT_TOKEN)
        if not (bot_enabled and bot_token):
            return

        from telethon import TelegramClient
        from telethon.sessions import StringSession
        proxy = self._get_proxy()
        use_api_id = int(self._cfg(CFG_API_ID)) if self._cfg(CFG_API_ID) else 17349
        use_api_hash = self._cfg(CFG_API_HASH) or "344583e45741c457fe1862106095a5eb"

        # 优先复用已保存的 session
        bot_session = self._cfg("tg_bot_session")
        if bot_session:
            self._bot_client = TelegramClient(StringSession(bot_session), use_api_id, use_api_hash, proxy=proxy, timeout=60)
            try:
                await self._bot_client.connect()
                if self._bot_client.is_connected():
                    self._bot_connected = True
                    logger.info("Bot: 连接成功（Session 复用）")
                    self._register_bot_handlers()
                    return
            except Exception:
                self._bot_client = None

        # 首次登录
        self._bot_client = TelegramClient(StringSession(''), use_api_id, use_api_hash, proxy=proxy, timeout=60)
        try:
            await self._bot_client.connect()
            await self._bot_client.sign_in(bot_token=bot_token)
            self._bot_connected = True
            session_str = self._bot_client.session.save()
            get_config_service().set("tg_bot_session", session_str, "Bot Session")
            logger.info("Bot: 连接成功，Session 已保存")
            self._register_bot_handlers()
        except Exception as e:
            logger.error(f"Bot: 连接失败: {e}")
            self._bot_client = None

    async def _ensure_user(self):
        """确保 User 客户端已连接"""
        if self._user_client is not None and self._user_connected:
            return

        user_enabled = self._cfg(CFG_USER_ENABLED) in ("true", "1", "True")
        api_id = self._cfg(CFG_API_ID)
        api_hash = self._cfg(CFG_API_HASH)
        session_string = self._cfg(CFG_SESSION)
        if not (user_enabled and api_id and api_hash and session_string):
            return

        from telethon import TelegramClient
        from telethon.sessions import StringSession
        proxy = self._get_proxy()

        self._user_client = TelegramClient(StringSession(session_string), int(api_id), api_hash, proxy=proxy, timeout=60)
        try:
            await self._user_client.connect()
            if await self._user_client.is_user_authorized():
                self._user_connected = True
                logger.info("User: 连接成功")
            else:
                logger.warning("User: Session 无效")
                await self._user_client.disconnect()
                self._user_client = None
        except Exception as e:
            logger.error(f"User: 连接失败: {e}")
            self._user_client = None

    async def _ensure_all(self):
        """确保所有已启用的客户端都已连接"""
        await self._ensure_bot()
        await self._ensure_user()

    def _register_bot_handlers(self):
        """注册 Bot 消息事件处理器，用于接收管理员发送的消息"""
        if not self._bot_client:
            return
        from telethon import events
        # 避免重复注册：先移除已有处理器，再重新注册
        self._bot_client.remove_event_handler(self._on_bot_message)
        self._bot_client.add_event_handler(
            self._on_bot_message,
            events.NewMessage(incoming=True)
        )
        logger.info("Bot: 消息事件处理器已注册")

    async def _on_bot_message(self, event):
        """处理 Bot 收到的消息，检测 115 分享链接"""
        try:
            # 仅处理管理员发送的消息
            sender_id = event.sender_id
            if not self.is_admin(sender_id):
                return

            message_text = event.message.text or ""
            if not message_text:
                return

            # 检测是否包含 115 分享链接
            if '115.com/s/' not in message_text and '115cdn.com/s/' not in message_text:
                return

            # 提取分享 URL
            url_match = re.search(r'https?://\S*(?:115\.com|115cdn\.com)/s/\S+', message_text)
            if not url_match:
                return

            share_url = url_match.group(0)
            logger.info(f"Bot: 检测到 115 分享链接: {share_url}")

            # 调用 share_service 处理分享链接（同步方法，用 asyncio.to_thread 包裹避免阻塞 Telethon 事件循环）
            from ...services.share_service import get_share_service
            share_service = get_share_service()
            result = await asyncio.to_thread(share_service.add_share, share_url, source_type='bot')

            # 构造回复消息
            if result.get('success'):
                reply = (
                    f"✅ 分享添加成功\n"
                    f"📁 {result.get('share_name', '')}\n"
                    f"📄 {result.get('file_count', 0)} 个文件\n"
                    f"💾 {format_size(result.get('total_size', 0))}\n"
                    f"🔑 source_id: {result.get('source_id')}"
                )
            else:
                reply = f"❌ 分享添加失败: {result.get('error', '未知错误')}"

            # 回复消息
            await event.reply(reply)

        except Exception as e:
            logger.error(f"Bot: 处理消息时出错: {e}")
            try:
                await event.reply(f"❌ 处理出错: {str(e)}")
            except Exception:
                pass

    # ==================== 发送消息 ====================

    async def send_message(self, message: str, image_url: Optional[str] = None) -> bool:
        """发送消息（Bot 发给管理员，User 发给通知目标）"""
        if not await self.is_enabled():
            logger.info("Telegram 未启用，跳过发送")
            return False

        await self._ensure_all()
        sent = False

        # Bot 模式：发给管理员
        if self._bot_client and self._bot_connected:
            admins = self._get_admin_ids()
            if admins:
                try:
                    if not self._bot_client.is_connected():
                        await self._bot_client.connect()
                    if image_url:
                        try:
                            await self._bot_client.send_message(admins[0], message, file=image_url, link_preview=False, parse_mode='html')
                        except Exception:
                            await self._bot_client.send_message(admins[0], message, link_preview=False, parse_mode='html')
                    else:
                        await self._bot_client.send_message(admins[0], message, link_preview=False, parse_mode='html')
                    sent = True
                    logger.info(f"Bot: 消息已发送给管理员 {admins[0]}")
                except Exception as e:
                    logger.error(f"Bot: 发送失败: {e}")
                    self._bot_connected = False

        # User 模式：发给通知目标
        if self._user_client and self._user_connected:
            target = self._cfg(CFG_NOTIFY_CHAT)
            if target:
                try:
                    if not self._user_client.is_connected():
                        await self._user_client.connect()
                    try:
                        target = int(target)
                    except ValueError:
                        pass
                    if image_url:
                        try:
                            await self._user_client.send_message(target, message, file=image_url, link_preview=False, parse_mode='html')
                        except Exception:
                            await self._user_client.send_message(target, message, link_preview=False, parse_mode='html')
                    else:
                        await self._user_client.send_message(target, message, link_preview=False, parse_mode='html')
                    sent = True
                    logger.info(f"User: 消息已发送到 {target}")
                except Exception as e:
                    logger.error(f"User: 发送失败: {e}")
                    self._user_connected = False

        return sent

    # ==================== 连接管理 ====================

    async def is_configured(self) -> bool:
        return bool(self._cfg(CFG_BOT_TOKEN)) or bool(self._cfg(CFG_API_ID) and self._cfg(CFG_API_HASH) and self._cfg(CFG_SESSION))

    async def is_connected(self) -> bool:
        bot_ok = self._bot_client and self._bot_connected
        user_ok = self._user_client and self._user_connected
        return bot_ok or user_ok

    async def is_enabled(self) -> bool:
        """检查 Telegram 渠道是否启用（与 get_status/auto_connect 使用一致的判断逻辑）"""
        return self._cfg(CFG_ENABLED) in ("true", "1", "True")

    async def connect(self) -> bool:
        """手动连接 Telegram

        总开关未启用时直接拒绝连接，避免用户只是查看状态或误点连接时，
        触发 Telethon 连接代理、注册 Bot 事件等副作用。
        """
        if not await self.is_enabled():
            logger.info("Telegram 未启用，跳过连接")
            return False

        self._bot_client = None
        self._user_client = None
        self._bot_connected = False
        self._user_connected = False
        await self._ensure_all()
        return self._bot_connected or self._user_connected

    async def auto_connect(self) -> None:
        enabled = self._cfg(CFG_ENABLED) in ("true", "1", "True")
        if not enabled:
            return
        if not await self.is_configured():
            return
        logger.info("Telegram 自动连接...")
        success = await self.connect()
        logger.info(f"Telegram 自动连接{'成功' if success else '失败'}")

    async def disconnect(self) -> None:
        if self._bot_client:
            try:
                await self._bot_client.disconnect()
            except Exception:
                pass
            self._bot_client = None
            self._bot_connected = False
        if self._user_client:
            try:
                await self._user_client.disconnect()
            except Exception:
                pass
            self._user_client = None
            self._user_connected = False
        logger.info("Telegram 已断开连接")

    # ==================== 用户模式登录 ====================

    async def send_code(self, phone: str, api_id: str, api_hash: str) -> Dict[str, Any]:
        import time
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        if self._login_client:
            try:
                await self._login_client.disconnect()
            except Exception:
                pass

        proxy = self._get_proxy()
        try:
            self._login_client = TelegramClient(StringSession(''), int(api_id), api_hash, proxy=proxy, timeout=60)
            await self._login_client.connect()
            await self._login_client.send_code_request(phone)
            self._login_phone = phone
            self._login_api_id = api_id
            self._login_api_hash = api_hash
            self._login_time = time.time()
            logger.info(f"验证码已发送到 {phone}")
            return {"success": True, "message": "验证码已发送"}
        except Exception as e:
            logger.error(f"发送验证码失败: {e}")
            if self._login_client:
                try:
                    await self._login_client.disconnect()
                except Exception:
                    pass
                self._login_client = None
            return {"success": False, "message": f"发送失败: {str(e)}"}

    async def sign_in(self, phone: str, code: str, password: str = "") -> Dict[str, Any]:
        import time
        if not self._login_client:
            return {"success": False, "message": "请先发送验证码"}
        if time.time() - self._login_time > 300:
            await self._cleanup_login()
            return {"success": False, "message": "验证码已过期，请重新发送"}
        try:
            await self._login_client.sign_in(phone, code)
            if not await self._login_client.is_user_authorized():
                if password:
                    await self._login_client.sign_in(password=password)
                else:
                    return {"success": False, "message": "需要两步验证密码", "need_password": True}
            session_string = self._login_client.session.save()
            await self._login_client.disconnect()
            self._login_client = None
            cfg = get_config_service()
            cfg.set("tg_session_string", session_string, "Session")
            cfg.set("tg_api_id", self._login_api_id, "API ID")
            cfg.set("tg_api_hash", self._login_api_hash, "API Hash")
            await self.disconnect()
            logger.info("用户模式登录成功，Session 已保存")
            return {"success": True, "message": "登录成功"}
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return {"success": False, "message": f"登录失败: {str(e)}"}

    async def check_login(self) -> Dict[str, Any]:
        if not await self.is_enabled():
            return {"logged_in": False, "message": "Telegram 未启用"}

        session_string = self._cfg(CFG_SESSION)
        api_id = self._cfg(CFG_API_ID)
        api_hash = self._cfg(CFG_API_HASH)
        if not (session_string and api_id and api_hash):
            return {"logged_in": False, "message": "未配置用户模式凭据"}
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            proxy = self._get_proxy()
            client = TelegramClient(StringSession(session_string), int(api_id), api_hash, proxy=proxy, timeout=30)
            await client.connect()
            authorized = await client.is_user_authorized()
            await client.disconnect()
            return {"logged_in": authorized, "message": "Session 有效" if authorized else "Session 已失效，请重新登录"}
        except Exception as e:
            return {"logged_in": False, "message": f"检查失败: {str(e)}"}

    async def _cleanup_login(self):
        if self._login_client:
            try:
                await self._login_client.disconnect()
            except Exception:
                pass
            self._login_client = None
        self._login_phone = ""
        self._login_time = 0

    # ==================== 配置 ====================

    def get_settings_schema(self) -> List[Dict[str, Any]]:
        return [
            {"key": CFG_ENABLED, "label": "启用通知", "type": "toggle"},
            {"key": CFG_BOT_ENABLED, "label": "启用 Bot 模式", "type": "toggle"},
            {"key": CFG_BOT_TOKEN, "label": "Bot Token", "type": "password", "placeholder": "从 @BotFather 获取"},
            {"key": CFG_USER_ENABLED, "label": "启用用户模式", "type": "toggle"},
            {"key": CFG_API_ID, "label": "API ID", "type": "text", "placeholder": "从 my.telegram.org 获取"},
            {"key": CFG_API_HASH, "label": "API Hash", "type": "password", "placeholder": "从 my.telegram.org 获取"},
            {"key": CFG_SESSION, "label": "Session", "type": "password", "placeholder": "登录后自动保存"},
            {"key": CFG_PROXY_ENABLED, "label": "启用代理", "type": "toggle"},
            {"key": CFG_PROXY_URL, "label": "代理地址", "type": "text", "placeholder": "socks5://user:pass@host:port"},
            {"key": CFG_NOTIFY_CHAT, "label": "通知目标", "type": "text", "placeholder": "chat_id 或 @username（用户模式需要）"},
            {"key": CFG_ADMIN_IDS, "label": "管理员 ID", "type": "text", "placeholder": "多个用逗号分隔，留空不限制"},
        ]

    async def get_current_settings(self) -> Dict[str, Any]:
        cfg = get_config_service()
        return {
            CFG_ENABLED: cfg.get(CFG_ENABLED) or "",
            CFG_BOT_ENABLED: cfg.get(CFG_BOT_ENABLED) or "",
            CFG_BOT_TOKEN: cfg.get(CFG_BOT_TOKEN) or "",
            CFG_USER_ENABLED: cfg.get(CFG_USER_ENABLED) or "",
            CFG_API_ID: cfg.get(CFG_API_ID) or "",
            CFG_API_HASH: cfg.get(CFG_API_HASH) or "",
            CFG_SESSION: cfg.get(CFG_SESSION) or "",
            CFG_PROXY_ENABLED: cfg.get(CFG_PROXY_ENABLED) or "",
            CFG_PROXY_URL: cfg.get(CFG_PROXY_URL) or "",
            CFG_NOTIFY_CHAT: cfg.get(CFG_NOTIFY_CHAT) or "",
            CFG_ADMIN_IDS: cfg.get(CFG_ADMIN_IDS) or "",
        }

    async def update_settings(self, settings: Dict[str, Any]) -> None:
        cfg = get_config_service()
        labels = {
            CFG_ENABLED: "通知开关", CFG_BOT_ENABLED: "Bot 模式开关", CFG_BOT_TOKEN: "Bot Token",
            CFG_USER_ENABLED: "用户模式开关", CFG_API_ID: "API ID", CFG_API_HASH: "API Hash",
            CFG_SESSION: "Session", CFG_PROXY_ENABLED: "代理开关", CFG_PROXY_URL: "代理地址",
            CFG_NOTIFY_CHAT: "通知目标", CFG_ADMIN_IDS: "管理员 ID",
        }
        credential_keys = {CFG_BOT_TOKEN, CFG_API_ID, CFG_API_HASH, CFG_SESSION, CFG_PROXY_ENABLED, CFG_PROXY_URL}
        need_reconnect = False
        disabled = False
        for key, value in settings.items():
            if key in labels:
                old_val = cfg.get(key) or ""
                new_val = str(value)
                if old_val != new_val:
                    cfg.set(key, new_val, labels[key])
                    if key == CFG_ENABLED and new_val not in ("true", "1", "True"):
                        disabled = True
                    if key in credential_keys:
                        need_reconnect = True
        if disabled:
            logger.info("Telegram 已关闭，断开现有连接")
            await self.disconnect()
        elif need_reconnect:
            logger.info("凭据变更，断开连接以便重连")
            await self.disconnect()

    def get_status(self) -> Dict[str, Any]:
        cfg = get_config_service()
        enabled = cfg.get(CFG_ENABLED) in ("true", "1", "True")
        if not enabled:
            return {"configured": False, "connected": False, "mode": "", "message": "未启用", "bot_name": "", "user_name": ""}

        bot_ok = self._bot_client and self._bot_connected
        user_ok = self._user_client and self._user_connected
        connected = bot_ok or user_ok

        modes = []
        if cfg.get(CFG_BOT_TOKEN):
            modes.append("bot")
        if cfg.get(CFG_API_ID):
            modes.append("user")

        return {
            "configured": bool(modes),
            "connected": connected,
            "mode": "+".join(modes),
            "message": "已连接" if connected else "未连接",
        }

    async def get_connection_info(self) -> Dict[str, Any]:
        """获取连接详情

        状态查询必须是只读操作。未启用 Telegram 时直接返回 get_status()，
        不能调用 _ensure_all()，否则会在打开页面/刷新状态时偷偷连接代理和 Bot。
        """
        status = self.get_status()
        bot_name = ""
        user_name = ""

        if not await self.is_enabled():
            status["bot_name"] = bot_name
            status["user_name"] = user_name
            return status

        try:
            await self._ensure_all()
            if self._bot_client and self._bot_connected:
                me = await self._bot_client.get_me()
                if me:
                    bot_name = me.first_name or me.username or ""
        except Exception:
            pass
        try:
            if self._user_client and self._user_connected:
                me = await self._user_client.get_me()
                if me:
                    user_name = me.first_name or me.username or ""
                    if me.last_name:
                        user_name = f"{user_name} {me.last_name}".strip()
        except Exception:
            pass
        status["bot_name"] = bot_name
        status["user_name"] = user_name
        return status
