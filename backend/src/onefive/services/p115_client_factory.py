"""115 客户端工厂

集中管理 P115Client / P115OpenClient 的创建与复用，
避免各业务服务重复初始化。
"""
from __future__ import annotations

import threading
from typing import Optional

from p115client import P115Client, P115OpenClient

from ..exceptions import NotLoggedInError
from .config_service import get_config_service
from .token_service import get_token_service


class P115ClientFactory:
    """统一创建并缓存 115 客户端实例。"""

    def __init__(self):
        self.config_service = get_config_service()
        self.token_service = get_token_service()
        self._lock = threading.RLock()
        self._web_client: Optional[P115Client] = None
        self._web_cookies: Optional[str] = None
        self._web_app: Optional[str] = None
        self._open_client: Optional[P115OpenClient] = None
        self._open_token: Optional[str] = None
        self._open_app_id: Optional[int] = None

    def get_client_app(self) -> str:
        """根据登录设备类型返回 P115Client 初始化 app。"""
        login_device = self.config_service.get("login_device") or "web"
        if login_device in ("android", "115android", "qandroid", "tv", "harmony"):
            return "android"
        if login_device in ("ios", "115ios", "115ipad", "wechatmini", "alipaymini"):
            return "ios"
        return "web"

    def get_cookies(self) -> str:
        """获取已保存 cookies。"""
        cookies = self.config_service.get("cookie115")
        if not cookies:
            raise NotLoggedInError("未登录，请先扫码登录")
        return cookies

    def invalidate(self) -> None:
        """cookie / token 变更后清空缓存，强制下次重建。"""
        with self._lock:
            self._web_client = None
            self._web_cookies = None
            self._web_app = None
            self._open_client = None
            self._open_token = None
            self._open_app_id = None

    def get_web_client(self, app: str | None = None) -> P115Client:
        """获取共享 P115Client（Web Cookie）。"""
        cookies = self.get_cookies()
        use_app = app or self.get_client_app()
        with self._lock:
            if (
                self._web_client is None
                or self._web_cookies != cookies
                or self._web_app != use_app
            ):
                self._web_client = P115Client(cookies, app=use_app)
                self._web_cookies = cookies
                self._web_app = use_app
            return self._web_client

    def get_open_client(self) -> Optional[P115OpenClient]:
        """Open API 开启且 token 有效时返回共享 P115OpenClient。"""
        if not self.token_service.is_open_api_enabled():
            return None
        access_token = self.token_service.get_access_token()
        if not access_token:
            return None
        app_id_raw = self.token_service.get_app_id()
        app_id = int(app_id_raw) if app_id_raw else 0
        with self._lock:
            if (
                self._open_client is None
                or self._open_token != access_token
                or self._open_app_id != app_id
            ):
                self._open_client = P115OpenClient(
                    access_token=access_token,
                    app_id=app_id,
                )
                self._open_token = access_token
                self._open_app_id = app_id
            return self._open_client

    def get_client(self) -> P115Client | P115OpenClient:
        """业务默认客户端：Open API 优先，否则 Web。"""
        open_client = self.get_open_client()
        if open_client is not None:
            return open_client
        return self.get_web_client()

    # ---- 兼容旧接口：统一走共享实例 ----

    def create_web_client(self, app: str | None = None) -> P115Client:
        return self.get_web_client(app=app)

    def create_open_client(self) -> Optional[P115OpenClient]:
        return self.get_open_client()

    def create_client(self) -> P115Client | P115OpenClient:
        return self.get_client()


_factory: Optional[P115ClientFactory] = None
_factory_lock = threading.Lock()


def get_p115_client_factory() -> P115ClientFactory:
    """获取全局 115 客户端工厂。"""
    global _factory
    if _factory is None:
        with _factory_lock:
            if _factory is None:
                _factory = P115ClientFactory()
    return _factory


def invalidate_p115_clients() -> None:
    """便捷方法：清空全局客户端缓存。"""
    factory = get_p115_client_factory()
    factory.invalidate()
