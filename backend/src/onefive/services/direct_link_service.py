"""
直链服务管理 - 管理 p115nano302 服务的生命周期

原理说明：
- p115nano302 是一个基于 115 网盘 cookies 的 302 直链代理服务
- 通过后台守护线程运行 uvicorn 来承载 ASGI 应用
- 使用 PathStripMiddleware 剥离 /d115 前缀，使 p115nano302 正确解析路径
- 使用 threading.Event 作为停止信号，实现优雅关闭
- 配置（开关、端口）持久化到 SQLite setting 表

执行步骤：
1. 启动：从 AuthService 获取 cookies → 创建 ASGI 应用 → 包裹路径前缀中间件 → 在守护线程中运行 uvicorn
2. 停止：设置停止标志 → uvicorn 检测到 should_exit → 线程自然退出
3. 状态查询：检查线程是否存活 + 标志位

============================================================================
支持的直链格式（p115nano302 原生支持）
============================================================================

基地址：http://host:port/d115（/d115 前缀由 PathStripMiddleware 自动剥离）

--- 个人文件查询 ---

1. 用 pickcode 查询
   http://host:port/d115?pickcode=ecjq9ichcb40lzlvx

2. 用 id 查询
   http://host:port/d115?2691590992858971545
   http://host:port/d115?id=2691590992858971545

3. 用 sha1 查询
   http://host:port/d115?sha1=E7FAA0BE343AF2DA8915F2B694295C8E4C91E691

4. 用 name 查询（文件名作为查询参数）
   http://host:port/d115?name=Movie.mkv

5. 带文件名 + pickcode（文件名在路径中）
   http://host:port/d115/Movie.mkv?pickcode=ecjq9ichcb40lzlvx

6. 带文件名 + id
   http://host:port/d115/Movie.mkv?id=2691590992858971545

7. 带文件名 + sha1
   http://host:port/d115/Movie.mkv?sha1=E7FAA0BE343AF2DA8915F2B694295C8E4C91E691

--- 分享文件查询 ---

8. 用 id 查询分享文件
   http://host:port/d115?share_code=swsfpoi3np7&receive_code=jejn&id=3459216959013390231

9. 带文件名 + 分享 id（文件名在路径中）
   http://host:port/d115/Movie.mkv?share_code=swsfpoi3np7&receive_code=jejn&id=3459216959013390231

10. 用 name 查询分享文件
    http://host:port/d115?share_code=swsfpoi3np7&receive_code=jejn&name=Movie.mkv

============================================================================
注意事项：
- receive_code（提取码）可省略，p115nano302 会自动获取
- 文件名中的特殊字符（如中文、冒号）会被浏览器自动 URL 编码
- 302 重定向目标为 115 CDN，有有效期（通常 2-4 小时）
- p115nano302 内置内存 URL 缓存（cache_url=True，进程内 L1）
- OneFive 额外提供 SQLite 持久化缓存（L2）：有效期内直接 302，跨重启复用，降低 115 风控风险
============================================================================
"""
import threading
from typing import Optional, Dict, Any
from urllib.parse import parse_qs

import uvicorn

from ..services.config_service import get_config_service
from time import time as _time

from ..logger import get_logger

logger = get_logger(__name__)


class DirectLinkDbCacheMiddleware:
    """ASGI 中间件：直链 URL 的 SQLite 持久化缓存（L2）

    流程：
    1. 解析请求中的 pickcode / id / share_code / sha1
    2. 若缓存命中且未过期 → 直接 302 到 CDN，不请求 115
    3. 未命中 → 交给 p115nano302；若响应 302，将 Location 写入数据库

    放在 PathStripMiddleware 内侧，看到的是剥离 /d115 后的路径。
    """

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _header_value(headers, name: bytes) -> str:
        name_l = name.lower()
        for k, v in headers or []:
            if k.lower() == name_l:
                try:
                    return v.decode("latin-1")
                except Exception:
                    return v.decode("utf-8", errors="ignore")
        return ""

    @staticmethod
    def _parse_request(scope) -> Dict[str, Any]:
        """从 ASGI scope 提取缓存相关参数"""
        qs = scope.get("query_string", b"") or b""
        try:
            q = parse_qs(qs.decode("latin-1"), keep_blank_values=True)
        except Exception:
            q = {}

        def first(key: str) -> str:
            vals = q.get(key) or []
            return (vals[0] if vals else "").strip()

        pickcode = first("pickcode")
        file_id = first("id")
        share_code = first("share_code")
        sha1 = first("sha1")
        refresh = first("refresh") in ("1", "true", "True", "yes")

        # 兼容 ?2691590992858971545 这种纯 id 查询
        if not any((pickcode, file_id, share_code, sha1)):
            raw = qs.decode("latin-1", errors="ignore")
            # 取第一个非空 token（去掉 =value）
            token = raw.split("&")[0].split("=")[0].strip()
            if token.isdigit():
                file_id = token

        # User-Agent
        headers = scope.get("headers") or []
        user_agent = ""
        for k, v in headers:
            if k.lower() == b"user-agent":
                try:
                    user_agent = v.decode("latin-1")
                except Exception:
                    user_agent = v.decode("utf-8", errors="ignore")
                break

        return {
            "pickcode": pickcode,
            "file_id": file_id,
            "share_code": share_code,
            "sha1": sha1,
            "refresh": refresh,
            "user_agent": user_agent,
            "path": scope.get("path", ""),
        }

    @staticmethod
    async def _send_redirect(send, url: str, cache_status: str = "HIT"):
        # CDN URL 一般为 ASCII；兜底用 utf-8 + latin-1 兼容
        try:
            loc = url.encode("latin-1")
        except UnicodeEncodeError:
            loc = url.encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 302,
            "headers": [
                (b"location", loc),
                (b"content-length", b"0"),
                (b"cache-control", b"no-store"),
                (b"x-onefive-cache", cache_status.encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from .direct_link_cache_service import get_direct_link_cache_service

        cache = get_direct_link_cache_service()
        req = self._parse_request(scope)
        base_params = {
            "pickcode": req["pickcode"],
            "file_id": req["file_id"],
            "share_code": req["share_code"],
            "sha1": req["sha1"],
        }

        # 有可识别键且非 refresh 时尝试命中缓存
        can_cache = any(base_params.values()) and not req["refresh"]
        if can_cache:
            cached_url = cache.get_valid_url(
                user_agent=req["user_agent"],
                **base_params,
            )
            if cached_url:
                logger.info(
                    f"[直链缓存 HIT] path={req['path']} "
                    f"pickcode={req['pickcode'] or '-'} id={req['file_id'] or '-'} "
                    f"share={req['share_code'] or '-'}"
                )
                await self._send_redirect(send, cached_url, "HIT")
                return

        # 未命中：透传并捕获 302 Location
        captured: Dict[str, Any] = {"status": 0, "location": ""}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                captured["status"] = message.get("status", 0)
                if captured["status"] in (301, 302, 303, 307, 308):
                    headers = list(message.get("headers") or [])
                    loc = self._header_value(headers, b"location")
                    if loc:
                        captured["location"] = loc
                        # 附加缓存标记，便于排查
                        headers.append((b"x-onefive-cache", b"MISS"))
                        message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)

        # 将新直链写入数据库
        location = captured.get("location") or ""
        if can_cache and captured.get("status") in (301, 302, 303, 307, 308) and location:
            # Location 可能是相对路径，忽略非 http(s)
            if location.startswith("http://") or location.startswith("https://"):
                ok = cache.set_url(
                    url=location,
                    user_agent=req["user_agent"],
                    **base_params,
                )
                if ok:
                    logger.info(
                        f"[直链缓存 STORE] path={req['path']} "
                        f"pickcode={req['pickcode'] or '-'} id={req['file_id'] or '-'} "
                        f"share={req['share_code'] or '-'}"
                    )


class PathStripMiddleware:
    """ASGI 路径前缀剥离 + 请求日志中间件

    1. 剥离 /d115 前缀，使 p115nano302 能正确解析
    2. 记录每个直链请求的路径、状态码和耗时

    示例：
      /d115/Name.mkv?pickcode=xxx → /Name.mkv?pickcode=xxx
      /d115?pickcode=xxx → /?pickcode=xxx
      /d115/xxx → /xxx
    """

    def __init__(self, app, prefix: str = "/d115"):
        self.app = app
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path: str = scope.get("path", "")
            if path.startswith(self.prefix):
                original_path = path
                stripped = path[len(self.prefix):] or "/"
                scope["path"] = stripped
                scope["root_path"] = scope.get("root_path", "") + self.prefix
                # 同步修改 raw_path，确保依赖 raw_path 路由的下游 ASGI 应用（如 p115nano302）能拿到重写后的路径
                # 保持原始字节，只剥离前缀对应的字节部分
                if "raw_path" in scope:
                    original_raw = scope["raw_path"]
                    prefix_bytes = self.prefix.encode("utf-8")
                    if original_raw.startswith(prefix_bytes):
                        scope["raw_path"] = original_raw[len(prefix_bytes):] or b"/"
                    else:
                        scope["raw_path"] = original_raw

                # 记录请求日志：捕获响应状态码
                start_ts = _time()
                status_code = 0

                async def send_wrapper(message):
                    nonlocal status_code
                    if message["type"] == "http.response.start":
                        status_code = message.get("status", 0)
                    await send(message)

                try:
                    await self.app(scope, receive, send_wrapper)
                except Exception as e:
                    # 记录异常日志（避免访问 request.url，中文路径会报错）
                    elapsed_ms = (_time() - start_ts) * 1000
                    logger.error(
                        f"[直链] 请求处理异常: {original_path} ({elapsed_ms:.0f}ms), 错误: {e}"
                    )
                    raise
                else:
                    elapsed_ms = (_time() - start_ts) * 1000
                    # 按状态码细分日志文案：302 是正常重定向，404 是未找到，其它视为异常
                    if status_code == 302:
                        hit = "重定向"
                    elif status_code == 404:
                        hit = "未找到"
                    else:
                        hit = f"异常:{status_code}"
                    logger.info(
                        f"[直链] {original_path} → {status_code} ({elapsed_ms:.0f}ms) {hit}"
                    )
            else:
                await self.app(scope, receive, send)
        else:
            await self.app(scope, receive, send)

# 配置键名
CONFIG_ENABLED = "direct_link_enabled"
CONFIG_PORT = "direct_link_port"
CONFIG_ALLOW_LAN = "direct_link_allow_lan"
DEFAULT_PORT = 11581


class DirectLinkService:
    """直链服务管理类

    职责：
    - 启动/停止 p115nano302 服务
    - 管理服务配置（开关、端口）
    - 查询服务运行状态
    """

    def __init__(self):
        """初始化直链服务，从数据库读取配置"""
        self.config_service = get_config_service()
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._stopping = threading.Event()
        # 线程锁：保护 _server / _thread 的读写，避免多线程下竞态
        self._lock = threading.Lock()

    def start(self) -> bool:
        """启动 302 直链服务

        在后台守护线程中运行 uvicorn，承载 p115nano302 的 ASGI 应用。
        allow_lan 从配置读取，允许局域网访问时绑定 0.0.0.0，否则仅本机 127.0.0.1。

        Returns:
            是否启动成功
        """
        # 已经在运行则跳过（加锁读取线程状态，避免与 stop 并发）
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
        if running:
            logger.warning("直链服务已在运行中，跳过启动")
            return True

        # 获取 cookies
        from ..services.auth_service import get_auth_service
        cookies = get_auth_service().get_cookies()
        if not cookies:
            logger.error("未登录，无法启动直链服务")
            return False

        # 获取端口配置
        port = self._get_port()
        # 从配置读取是否允许局域网访问
        allow_lan = self.config_service.get(CONFIG_ALLOW_LAN) == "1"
        # 绑定地址：允许局域网访问时绑定 0.0.0.0，否则仅本机访问
        host = "0.0.0.0" if allow_lan else "127.0.0.1"
        logger.info(f"启动直链服务: host={host}, port={port}, allow_lan={allow_lan}")

        try:
            import p115nano302

            # 创建 ASGI 应用（启用内存 URL 缓存 L1）
            nano_app = p115nano302.make_application(cookies, cache_url=True)

            # 启动时清理过期 DB 缓存
            try:
                from .direct_link_cache_service import get_direct_link_cache_service
                cleaned = get_direct_link_cache_service().cleanup_expired()
                stats = get_direct_link_cache_service().stats()
                logger.info(
                    f"直链 DB 缓存就绪: 清理过期 {cleaned} 条, "
                    f"有效 {stats.get('valid', 0)}/{stats.get('total', 0)}"
                )
            except Exception as e:
                logger.warning(f"直链 DB 缓存初始化失败（不影响服务启动）: {e}")

            # 中间件由内到外：
            # p115nano302 → DB 缓存(L2) → 路径前缀剥离/日志
            app = PathStripMiddleware(
                DirectLinkDbCacheMiddleware(nano_app),
                prefix="/d115",
            )

            # 清除停止标志
            self._stopping.clear()

            # 创建 uvicorn 配置和服务器实例
            config = uvicorn.Config(
                app,
                host=host,
                port=port,
                log_level="warning",
            )
            server = uvicorn.Server(config)

            # 在守护线程中启动 uvicorn（加锁保护 _server / _thread 赋值）
            with self._lock:
                self._server = server
                self._thread = threading.Thread(
                    target=self._run_server,
                    name="direct-link-302",
                    daemon=True,
                )
                self._thread.start()

            logger.info(f"直链服务已启动，端口: {port}，绑定: {host}")
            return True

        except Exception as e:
            logger.error(f"启动直链服务失败: {e}")
            with self._lock:
                self._server = None
                self._thread = None
            return False

    def _run_server(self):
        """在线程中运行 uvicorn 服务器"""
        try:
            # 加锁读取 server 引用，避免与 stop 并发置空
            with self._lock:
                server = self._server
            if server is not None:
                server.run()
        except Exception as e:
            if not self._stopping.is_set():
                logger.error(f"直链服务运行异常: {e}")
        finally:
            with self._lock:
                self._server = None
            if not self._stopping.is_set():
                logger.info("直链服务已停止")

    def stop(self) -> bool:
        """停止 302 直链服务

        通过设置 uvicorn 的 should_exit 标志实现优雅关闭，
        并等待守护线程退出（最长 5 秒），避免提前返回"已停止"但实际仍在运行。

        Returns:
            是否已停止（无论线程是否在超时内退出都返回 True）
        """
        # 加锁读取线程和服务器引用
        with self._lock:
            thread = self._thread
            server = self._server
            running = thread is not None and thread.is_alive()
        if not running:
            logger.info("直链服务未在运行")
            return True

        try:
            self._stopping.set()
            if server:
                server.should_exit = True
            logger.info("已发送直链服务停止信号")
            # 等待线程退出（最长 5 秒），join 后无论是否超时都返回 True
            if thread is not None:
                thread.join(timeout=5)
            return True
        except Exception as e:
            logger.error(f"停止直链服务失败: {e}")
            return False

    def is_running(self) -> bool:
        """查询服务是否正在运行

        Returns:
            服务是否运行中
        """
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def get_settings(self) -> dict:
        """获取直链服务设置

        Returns:
            包含 enabled、port、allow_lan、running 的字典
        """
        enabled_str = self.config_service.get(CONFIG_ENABLED)
        return {
            "enabled": enabled_str == "1",
            "port": self._get_port(),
            "allow_lan": self.config_service.get(CONFIG_ALLOW_LAN) == "1",
            "running": self.is_running(),
        }

    def save_settings(self, enabled: bool, port: int, allow_lan: bool = False):
        """保存直链服务配置到数据库

        Args:
            enabled: 是否启用
            port: 端口号
            allow_lan: 是否允许局域网访问（True 绑定 0.0.0.0，False 绑定 127.0.0.1）
        """
        self.config_service.set(
            CONFIG_ENABLED,
            "1" if enabled else "0",
            "直链服务开关"
        )
        self.config_service.set(
            CONFIG_PORT,
            str(port),
            "直链服务端口"
        )
        self.config_service.set(
            CONFIG_ALLOW_LAN,
            "1" if allow_lan else "0",
            "直链服务允许局域网访问"
        )

    def _get_port(self) -> int:
        """从配置中获取端口号

        Returns:
            端口号，默认 11581
        """
        port_str = self.config_service.get(CONFIG_PORT)
        if port_str:
            try:
                return int(port_str)
            except (ValueError, TypeError):
                pass
        return DEFAULT_PORT


# 全局直链服务实例（单例模式）
_direct_link_service: Optional[DirectLinkService] = None
# 单例锁：保护 _direct_link_service 的创建，避免多线程下重复实例化
_singleton_lock = threading.Lock()


def get_direct_link_service() -> DirectLinkService:
    """获取直链服务实例（单例模式）

    Returns:
        直链服务实例
    """
    global _direct_link_service
    with _singleton_lock:
        if _direct_link_service is None:
            _direct_link_service = DirectLinkService()
    return _direct_link_service
