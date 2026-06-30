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
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .paths import SERVICE_PORT
from .logger import setup_logging, get_logger
from .api.auth import router as auth_router
from .api.config import router as config_router
from .api.files import router as files_router
from .api.logs import router as logs_router
from .api.organize import router as organize_router
from .api.notification import router as notification_router
from .api.direct_link import router as direct_link_router
from .api.share import router as share_router
from .db.database import close_db

# 初始化日志
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("壹伍（OneFive）服务启动中...")

    # 启动时自动连接已配置的通知渠道
    try:
        from .notification import get_notification_manager
        manager = get_notification_manager()
        await manager.auto_connect_all()
    except Exception as e:
        logger.warning(f"通知渠道自动连接失败: {e}")

    # 自动启动直链服务
    try:
        from .services.direct_link_service import get_direct_link_service
        dl_service = get_direct_link_service()
        if dl_service.get_settings()["enabled"]:
            dl_service.start()
    except Exception as e:
        logger.warning(f"直链服务自动启动失败: {e}")

    yield
    logger.info("壹伍（OneFive）服务关闭中...")

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

# 配置 CORS（开发环境允许所有来源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth_router)
app.include_router(config_router)
app.include_router(files_router)
app.include_router(logs_router)
app.include_router(organize_router)
app.include_router(notification_router)
app.include_router(direct_link_router)
app.include_router(share_router)


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


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理器"""
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": f"服务器内部错误: {str(exc)}",
            "data": None
        }
    )


if __name__ == "__main__":
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
