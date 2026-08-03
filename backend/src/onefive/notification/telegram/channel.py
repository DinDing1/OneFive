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


# 配置键名常量
CFG_ENABLED = "tg_enabled"
CFG_BOT_ENABLED = "tg_bot_enabled"
CFG_BOT_TOKEN = "tg_bot_token"
CFG_BOT_SESSION = "tg_bot_session"  # Bot 模式 StringSession，失效后需清掉并用 token 重建
CFG_USER_ENABLED = "tg_user_enabled"
CFG_API_ID = "tg_api_id"
CFG_API_HASH = "tg_api_hash"
CFG_SESSION = "tg_session_string"
CFG_PROXY_ENABLED = "tg_proxy_enabled"
CFG_PROXY_URL = "tg_proxy_url"
CFG_NOTIFY_CHAT = "tg_notify_chat"
CFG_ADMIN_IDS = "tg_admin_ids"

# 连接参数：避免网络异常时长时间阻塞（Telethon 默认会多次重试）
TG_CLIENT_TIMEOUT = 10          # 单次 socket 超时（秒）
TG_CONNECTION_RETRIES = 1       # 连接重试次数（默认 5，过大易卡死启动/接口）
TG_CONNECT_WAIT = 20            # 单次 connect() 总等待上限（秒）
TG_AUTO_CONNECT_WAIT = 45       # 启动自动连接总等待上限（秒）


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

    def _new_client(self, session, api_id, api_hash, proxy=None):
        """创建带超时/有限重试的 Telethon 客户端，避免网络差时无限卡死。"""
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        return TelegramClient(
            StringSession(session),
            int(api_id),
            api_hash,
            proxy=proxy,
            timeout=TG_CLIENT_TIMEOUT,
            connection_retries=TG_CONNECTION_RETRIES,
            retry_delay=1,
            auto_reconnect=True,
        )

    async def _quiet_disconnect(self, client) -> None:
        if not client:
            return
        try:
            await client.disconnect()
        except Exception:
            pass

    async def _safe_client_connect(self, client, label: str) -> bool:
        """带总超时的 connect。

        成功返回 True；明确失败返回 False；超时/网络错误抛出异常，
        便于上层避免“失败后再二次长重试”。
        """
        try:
            await asyncio.wait_for(client.connect(), timeout=TG_CONNECT_WAIT)
            if client.is_connected():
                return True
            logger.error(f"{label}: 连接后未处于 connected 状态")
            await self._quiet_disconnect(client)
            return False
        except asyncio.TimeoutError:
            logger.error(f"{label}: 连接超时（{TG_CONNECT_WAIT}s）")
            await self._quiet_disconnect(client)
            raise
        except Exception as e:
            logger.error(f"{label}: 连接失败: {e}")
            await self._quiet_disconnect(client)
            raise

    @staticmethod
    def _is_auth_key_error(exc: BaseException) -> bool:
        """判断 Session 授权密钥是否已失效。

        典型场景：同一 session 被两个 IP 同时使用，Telegram 直接作废该 auth key。
        此类错误必须清掉本地 session，再用 bot_token 重新签发，不能当普通网络错误跳过。
        """
        name = type(exc).__name__.lower()
        msg = str(exc).lower()
        # Telethon 常见：AuthKeyDuplicatedError / AuthKeyError 等
        if "authkey" in name or name in {"authorizationerror", "authkeyerror", "authkeyduplicatederror"}:
            return True
        keywords = (
            "authorization key",
            "auth key",
            "authkey",
            "two different ip",
            "different ip addresses",
            "can no longer be used",
            "auth_key_duplicated",
            "auth key unregistered",
            "key is not registered",
        )
        return any(k in msg for k in keywords)

    @staticmethod
    def _is_network_error(exc: BaseException) -> bool:
        """判断是否为网络/超时类错误（此类错误不应立即二次长重试）。

        注意：AuthKey 作废文案里也可能含 connection，必须先排除，避免误判成网络错误
        而跳过 token 重登。
        """
        if TelegramChannel._is_auth_key_error(exc):
            return False
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError)):
            return True
        name = type(exc).__name__
        msg = str(exc).lower()
        if name in {"ConnectionError", "TimeoutError", "OSError", "NetworkError"}:
            return True
        return any(k in msg for k in ("timeout", "timed out", "connection", "network", "unreachable"))

    def _clear_bot_session(self, reason: str = "") -> None:
        """清除已失效的 Bot Session，避免下次启动继续复用坏密钥。"""
        try:
            cfg = get_config_service()
            old = (cfg.get(CFG_BOT_SESSION) or "").strip()
            if not old:
                return
            cfg.set(CFG_BOT_SESSION, "", "Bot Session")
            extra = f"（{reason}）" if reason else ""
            logger.warning(f"Bot: 已清除失效 Session{extra}")
        except Exception as e:
            logger.warning(f"Bot: 清除 Session 失败: {e}")

    async def _sign_in_bot_with_token(
        self,
        bot_token: str,
        api_id: int,
        api_hash: str,
        proxy=None,
    ) -> bool:
        """用 Bot Token 重新登录并保存新 Session。

        Returns:
            True 表示连接并登录成功；False 表示失败（已清理客户端状态）。
        """
        self._bot_client = self._new_client("", api_id, api_hash, proxy)
        try:
            if not await self._safe_client_connect(self._bot_client, "Bot"):
                self._bot_client = None
                self._bot_connected = False
                return False
            await asyncio.wait_for(
                self._bot_client.sign_in(bot_token=bot_token),
                timeout=TG_CONNECT_WAIT,
            )
            self._bot_connected = True
            session_str = self._bot_client.session.save()
            get_config_service().set(CFG_BOT_SESSION, session_str, "Bot Session")
            logger.info("Bot: 连接成功，Session 已保存")
            self._register_bot_handlers()
            return True
        except Exception as e:
            logger.error(f"Bot: Token 登录失败: {e}")
            await self._quiet_disconnect(self._bot_client)
            self._bot_client = None
            self._bot_connected = False
            return False

    async def _ensure_bot(self):
        """确保 Bot 客户端已连接。

        流程：
        1) 优先复用 tg_bot_session
        2) AuthKey/多 IP 作废 → 清 session → bot_token 重登
        3) 其它 session 失效 → 尝试 token 重登（并清坏 session）
        4) 纯网络超时 → 不立刻二次 token 重试，避免启动卡住
        """
        if self._bot_client is not None and self._bot_connected:
            return

        bot_enabled = self._cfg(CFG_BOT_ENABLED) in ("true", "1", "True")
        bot_token = self._cfg(CFG_BOT_TOKEN)
        if not (bot_enabled and bot_token):
            return

        proxy = self._get_proxy()
        use_api_id = int(self._cfg(CFG_API_ID)) if self._cfg(CFG_API_ID) else 17349
        use_api_hash = self._cfg(CFG_API_HASH) or "344583e45741c457fe1862106095a5eb"

        # 优先复用已保存的 session
        bot_session = self._cfg(CFG_BOT_SESSION)
        if bot_session:
            self._bot_client = self._new_client(bot_session, use_api_id, use_api_hash, proxy)
            try:
                if await self._safe_client_connect(self._bot_client, "Bot"):
                    self._bot_connected = True
                    logger.info("Bot: 连接成功（Session 复用）")
                    self._register_bot_handlers()
                    return
                # connect 返回 False：视为 session 不可用，清掉后走 token
                logger.warning("Bot: Session 复用未就绪，改用 Token 重登")
                await self._quiet_disconnect(self._bot_client)
                self._bot_client = None
                self._clear_bot_session("复用连接未就绪")
            except Exception as e:
                logger.warning(f"Bot: Session 复用失败: {e}")
                await self._quiet_disconnect(self._bot_client)
                self._bot_client = None
                # 网络问题：不立刻 token 二次连接，避免卡住；坏 session 先保留
                if self._is_network_error(e):
                    self._bot_connected = False
                    return
                # AuthKey 作废或其它 session 级错误：清 session 后强制 token 重登
                reason = "授权密钥失效/多 IP 冲突" if self._is_auth_key_error(e) else "Session 复用失败"
                self._clear_bot_session(reason)
                logger.info(f"Bot: 准备 Token 重登（原因: {reason}）")

        # 首次登录 / Session 无效后的 token 登录
        await self._sign_in_bot_with_token(bot_token, use_api_id, use_api_hash, proxy)

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

        proxy = self._get_proxy()
        self._user_client = self._new_client(session_string, api_id, api_hash, proxy)
        try:
            if not await self._safe_client_connect(self._user_client, "User"):
                self._user_client = None
                return
            if await self._user_client.is_user_authorized():
                self._user_connected = True
                logger.info("User: 连接成功")
            else:
                logger.warning("User: Session 无效")
                await self._user_client.disconnect()
                self._user_client = None
        except Exception as e:
            logger.error(f"User: 连接失败: {e}")
            await self._quiet_disconnect(self._user_client)
            self._user_client = None
            self._user_connected = False

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
        """处理 Bot 收到的消息：115 分享链接 / ed2k / magnet。"""
        try:
            sender_id = event.sender_id
            if not self.is_admin(sender_id):
                return

            message_text = event.message.text or ""
            if not message_text:
                return

            replies: list[str] = []
            from ..format import format_share_add_notify, format_offline_add_notify

            # ---- 115 分享链接 → 虚拟库 ----
            has_share = ("115.com/s/" in message_text) or ("115cdn.com/s/" in message_text)
            if has_share:
                url_match = re.search(
                    r"https?://\S*(?:115\.com|115cdn\.com)/s/\S+",
                    message_text,
                )
                if url_match:
                    share_url = url_match.group(0)
                    logger.info(f"Bot: 检测到 115 分享链接: {share_url}")
                    from ...services.share_service import get_share_service

                    share_service = get_share_service()
                    result = await asyncio.to_thread(
                        share_service.add_share, share_url, source_type="bot"
                    )
                    # 与离线转存共用统一字段风格模板
                    replies.append(
                        format_share_add_notify(
                            bool(result.get("success")),
                            share_name=result.get("share_name", "") or "",
                            file_count=int(result.get("file_count") or 0),
                            total_size=result.get("total_size", 0),
                            source_id=result.get("source_id"),
                            share_code=result.get("share_code", "") or "",
                            error=result.get("error", "") or "未知错误",
                        )
                    )

            # ---- ed2k / magnet → 115 离线转存 ----
            from ...services.offline_link_parser import extract_offline_links_from_text
            from ...services.offline_download_service import get_offline_download_service

            offline_links = extract_offline_links_from_text(message_text)
            if offline_links:
                logger.info(
                    f"Bot: 检测到离线链接 {len(offline_links)} 条 "
                    f"({', '.join(sorted({x.url_type for x in offline_links}))})"
                )
                offline_service = get_offline_download_service()
                off_result = await asyncio.to_thread(
                    offline_service.add_urls,
                    [x.url for x in offline_links],
                    None,
                    "bot",
                )
                replies.append(
                    format_offline_add_notify(
                        bool(off_result.get("success")),
                        accepted=int(off_result.get("accepted") or 0),
                        total=int(off_result.get("total") or 0),
                        exists=int(off_result.get("exists") or 0),
                        failed=int(off_result.get("failed") or 0),
                        save_path=off_result.get("save_path") or "",
                        items=off_result.get("items") or [],
                        error=off_result.get("error", "") or "未知错误",
                    )
                )

            if not replies:
                return

            # HTML 模板，与整理通知 send_message(parse_mode=html) 一致
            await event.reply("\n\n".join(replies), parse_mode="html")

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
        try:
            success = await asyncio.wait_for(self.connect(), timeout=TG_AUTO_CONNECT_WAIT)
            logger.info(f"Telegram 自动连接{'成功' if success else '失败'}")
        except asyncio.TimeoutError:
            logger.warning(
                f"Telegram 自动连接超时（{TG_AUTO_CONNECT_WAIT}s），"
                "HTTP 服务不受影响，可稍后在通知设置中手动重连"
            )
            try:
                await self.disconnect()
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Telegram 自动连接异常: {e}")
            try:
                await self.disconnect()
            except Exception:
                pass

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

        if self._login_client:
            try:
                await self._login_client.disconnect()
            except Exception:
                pass

        proxy = self._get_proxy()
        try:
            self._login_client = self._new_client("", api_id, api_hash, proxy)
            if not await self._safe_client_connect(self._login_client, "Login"):
                self._login_client = None
                return {"success": False, "message": "连接失败: 超时或网络不可用"}
            await asyncio.wait_for(
                self._login_client.send_code_request(phone),
                timeout=TG_CONNECT_WAIT,
            )
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
            proxy = self._get_proxy()
            client = self._new_client(session_string, api_id, api_hash, proxy)
            if not await self._safe_client_connect(client, "LoginCheck"):
                return {"logged_in": False, "message": "检查失败: 连接超时或网络不可用"}
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
        # Bot Token / 代理 / API 变更后旧 Bot Session 可能失效，需断开并清 bot session
        credential_keys = {
            CFG_BOT_TOKEN, CFG_API_ID, CFG_API_HASH, CFG_SESSION,
            CFG_PROXY_ENABLED, CFG_PROXY_URL,
        }
        need_reconnect = False
        clear_bot_session = False
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
                    # Token 或代理出口变化时，旧 auth key 易触发双 IP/失效
                    if key in {CFG_BOT_TOKEN, CFG_PROXY_ENABLED, CFG_PROXY_URL}:
                        clear_bot_session = True
        if disabled:
            logger.info("Telegram 已关闭，断开现有连接")
            await self.disconnect()
        elif need_reconnect:
            if clear_bot_session:
                self._clear_bot_session("凭据或代理变更")
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
            # 状态查询也限制连接等待，避免通知页在网络异常时卡住
            await asyncio.wait_for(self._ensure_all(), timeout=TG_AUTO_CONNECT_WAIT)
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
