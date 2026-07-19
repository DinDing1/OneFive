"""115 客户端工厂

集中管理 P115Client / P115OpenClient 初始化，避免各业务服务分散创建客户端。
"""
from p115client import P115Client, P115OpenClient

from ..exceptions import NotLoggedInError
from .config_service import get_config_service
from .token_service import get_token_service


class P115ClientFactory:
    """统一创建 115 客户端"""

    def __init__(self):
        self.config_service = get_config_service()
        self.token_service = get_token_service()

    def get_client_app(self) -> str:
        """根据登录设备类型返回 P115Client 初始化 app"""
        login_device = self.config_service.get("login_device") or "web"
        if login_device in ("android", "115android", "qandroid", "tv", "harmony"):
            return "android"
        if login_device in ("ios", "115ios", "115ipad", "wechatmini", "alipaymini"):
            return "ios"
        return "web"

    def get_cookies(self) -> str:
        """获取已保存 cookies"""
        cookies = self.config_service.get("cookie115")
        if not cookies:
            raise NotLoggedInError("未登录，请先扫码登录")
        return cookies

    def create_web_client(self, app: str | None = None) -> P115Client:
        """创建 P115Client，不走 Open API"""
        return P115Client(self.get_cookies(), app=app or self.get_client_app())

    def create_open_client(self) -> P115OpenClient | None:
        """Open API 开启且 token 有效时创建 P115OpenClient"""
        if not self.token_service.is_open_api_enabled():
            return None
        access_token = self.token_service.get_access_token()
        if not access_token:
            return None
        app_id = self.token_service.get_app_id()
        return P115OpenClient(
            access_token=access_token,
            app_id=int(app_id) if app_id else 0,
        )

    def create_client(self) -> P115Client | P115OpenClient:
        """创建业务默认客户端：Open API 优先，否则 P115Client"""
        open_client = self.create_open_client()
        if open_client is not None:
            return open_client
        return self.create_web_client()


_factory: P115ClientFactory | None = None


def get_p115_client_factory() -> P115ClientFactory:
    """获取全局 115 客户端工厂"""
    global _factory
    if _factory is None:
        _factory = P115ClientFactory()
    return _factory
