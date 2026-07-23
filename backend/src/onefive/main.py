"""
壹伍（OneFive）- FastAPI 主入口

原理说明：
- 使用 FastAPI 作为 Web 框架
- 使用 uvicorn 作为 ASGI 服务器
- 注册所有 API 路由
- 提供健康检查接口
- 管理应用生命周期
- 支持飞牛 fnOS 统一网关（Unix Socket）和本地开发（HTTP）

飞牛网关说明：
- 飞牛统一网关会自动校验用户登录态
- 通过后会在请求头中添加 X-Trim-Userid、X-Trim-Isadmin、X-Trim-Username
- 应用通过 Unix Socket 接收网关转发的请求
"""
import os
import time

# ==================== 设置时区为北京时间 ====================
# 本地开发时也统一时区，确保数据库时间戳与北京时间一致
os.environ['TZ'] = 'Asia/Shanghai'
try:
    time.tzset()
except AttributeError:
    pass  # Windows 不支持 time.tzset()

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from . import __version__
from .paths import SERVICE_PORT, UI_DIR
from .logger import setup_logging, get_logger
from .exceptions import AppError
from .api.auth import router as auth_router
from .api.config import router as config_router
from .api.files import router as files_router
from .api.logs import router as logs_router
from .api.organize import router as organize_router
from .api.notification import router as notification_router
from .api.direct_link import router as direct_link_router
from .api.share import router as share_router
from .api.strm import router as strm_router
from .api.share_wash import router as share_wash_router
from .db.database import close_db

# 初始化日志
setup_logging()
logger = get_logger(__name__)


async def _auto_connect_notifications() -> None:
    """后台连接通知渠道，失败不影响 HTTP 服务。"""
    try:
        from .notification import get_notification_manager
        manager = get_notification_manager()
        await manager.auto_connect_all()
    except Exception as e:
        logger.warning(f"通知渠道自动连接失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("壹伍（OneFive）服务启动中...")

    # 通知渠道放到后台连接：网络/Telegram 超时不得阻塞 HTTP 就绪
    auto_connect_task = asyncio.create_task(
        _auto_connect_notifications(),
        name="notification-auto-connect",
    )

    # 自动启动直链服务
    try:
        from .services.direct_link_service import get_direct_link_service
        dl_service = get_direct_link_service()
        if dl_service.get_settings()["enabled"]:
            dl_service.start()
    except Exception as e:
        logger.warning(f"直链服务自动启动失败: {e}")

    logger.info("HTTP 服务就绪（通知渠道后台连接中）")
    yield
    logger.info("壹伍（OneFive）服务关闭中...")

    # 取消仍在进行的自动连接，避免关闭阶段挂起
    if not auto_connect_task.done():
        auto_connect_task.cancel()
        try:
            await auto_connect_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"取消通知自动连接任务: {e}")

    # 断开通知渠道
    try:
        from .notification import get_notification_manager
        await get_notification_manager().disconnect_all()
    except Exception:
        pass

    # 停止直链服务
    try:
        from .services.direct_link_service import get_direct_link_service
        get_direct_link_service().stop()
    except Exception:
        pass

    close_db()


# 创建 FastAPI 应用实例
app = FastAPI(
    title="壹伍（OneFive）",
    description="基于 p115client 的 115 网盘管理应用",
    version=__version__,
    lifespan=lifespan
)

# 配置 CORS（显式列出允许的来源，避免通配符 + 凭据的不安全组合）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:11580"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 飞牛网关路径重写 ====================
# 飞牛统一网关不会剥离 gatewayPrefix，请求 /app/onefive/api/xxx 到达后端路径不变。
# 此中间件将 /app/onefive/api/* 重写为 /api/*，使 API 路由无需修改。
class GatewayPrefixMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/app/onefive/api/"):
            # 重写路径：/app/onefive/api/xxx → /api/xxx
            new_path = request.url.path.replace("/app/onefive/api/", "/api/", 1)
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode("utf-8")
        return await call_next(request)

app.add_middleware(GatewayPrefixMiddleware)

# 注册路由
app.include_router(auth_router)
app.include_router(config_router)
app.include_router(files_router)
app.include_router(logs_router)
app.include_router(organize_router)
app.include_router(notification_router)
app.include_router(direct_link_router)
app.include_router(share_router)
app.include_router(strm_router)
app.include_router(share_wash_router)

# ==================== 前端静态文件 ====================
# 飞牛网关通过 gatewayPrefix="/app/onefive" 转发请求，
# 所有 /app/onefive 开头的非 API 请求需要返回前端页面。
# 静态资源（JS/CSS/图片等）挂载在 /app/onefive/assets，
# SPA fallback：其他 /app/onefive/* 路径返回 index.html。
if UI_DIR.exists() and UI_DIR.is_dir():
    # 挂载静态资源目录（assets/ 下的 JS/CSS/图片等）
    assets_dir = UI_DIR / "assets"
    if assets_dir.exists():
        app.mount("/app/onefive/assets", StaticFiles(directory=str(assets_dir)), name="static_assets")

    @app.get("/app/onefive/{path:path}", tags=["前端"])
    async def serve_spa(path: str):
        """SPA fallback：非静态资源路径返回 index.html"""
        # 尝试匹配 UI 目录下的具体文件（如 favicon.ico、vite.svg 等）
        file_path = UI_DIR / path
        if path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # SPA fallback：返回 index.html 让前端路由处理
        index_path = UI_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return JSONResponse(status_code=404, content={"detail": "前端页面未找到"})

    @app.get("/app/onefive", tags=["前端"])
    async def serve_spa_root():
        """前端入口"""
        index_path = UI_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return JSONResponse(status_code=404, content={"detail": "前端页面未找到"})

    logger.info(f"前端 UI 目录: {UI_DIR}")


@app.get("/api/gateway/user", tags=["网关"])
async def get_gateway_user(request: Request):
    """获取飞牛网关透传的用户信息"""
    return {
        "uid": request.headers.get("X-Trim-Userid"),
        "is_admin": request.headers.get("X-Trim-Isadmin", "false").lower() == "true",
        "username": request.headers.get("X-Trim-Username")
    }


@app.get("/health", tags=["健康检查"])
async def health_check():
    """健康检查接口"""
    return {"status": "healthy"}


@app.exception_handler(AppError)
async def app_error_handler(request, exc: AppError):
    """业务错误处理器：返回友好的业务错误消息"""
    return JSONResponse(
        status_code=200,
        content={"code": exc.code, "message": exc.message, "data": None}
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """系统异常处理器：记录完整堆栈到日志，返回 HTTP 200 + 业务错误码

    返回 HTTP 200 而非 500，确保前端 axios 拦截器能正常解析 ApiResult，
    前端统一通过 code 字段判断成功/失败，不依赖 HTTP 状态码。
    """
    err = str(exc)[:300] if exc is not None else "unknown"
    logger.exception(f"未处理异常: {request.url.path} | {type(exc).__name__}: {err}")
    return JSONResponse(
        status_code=200,
        content={
            "code": -1,
            "message": f"服务器内部错误: {type(exc).__name__}: {err}",
            "data": None,
        },
    )


def start_server():
    """启动服务器"""
    import uvicorn

    # 获取配置
    socket_path = os.environ.get("ONEFIVE_SOCKET")  # Unix Socket 路径（飞牛环境）

    if socket_path:
        # 飞牛环境：使用 Unix Socket
        logger.info(f"启动 Unix Socket 服务: {socket_path}")
        uvicorn.run(
            "onefive.main:app",
            uds=socket_path,
            log_level="info"
        )
    else:
        # 本地开发：使用 HTTP
        logger.info(f"启动 HTTP 服务: http://0.0.0.0:{SERVICE_PORT}")
        uvicorn.run(
            "onefive.main:app",
            host="0.0.0.0",
            port=SERVICE_PORT,
            reload=True
        )


if __name__ == "__main__":
    start_server()
