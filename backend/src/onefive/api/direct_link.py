"""
302 直链 API 路由 - 管理 p115nano302 服务的设置、启停和状态查询
"""
from fastapi import APIRouter
from pydantic import BaseModel
from ..models.schemas import ApiResponse
from ..services.direct_link_service import get_direct_link_service
from ..logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/direct-link", tags=["直链"])


class DirectLinkSettingsRequest(BaseModel):
    """直链服务配置请求"""
    enabled: bool
    port: int = 11581


@router.get("/settings", summary="获取直链服务设置")
async def get_settings():
    """获取直链服务的当前配置（开关、端口、运行状态）"""
    try:
        service = get_direct_link_service()
        settings = service.get_settings()
        return ApiResponse(code=0, message="success", data=settings)
    except Exception as e:
        logger.error(f"获取直链服务设置失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/settings", summary="保存直链服务设置")
async def save_settings(req: DirectLinkSettingsRequest):
    """保存直链服务配置（开关、端口）"""
    try:
        service = get_direct_link_service()
        service.save_settings(enabled=req.enabled, port=req.port)
        settings = service.get_settings()
        return ApiResponse(code=0, message="设置已保存", data=settings)
    except Exception as e:
        logger.error(f"保存直链服务设置失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/start", summary="启动直链服务")
async def start_service():
    """启动 302 直链服务"""
    try:
        service = get_direct_link_service()
        success = service.start()
        if success:
            return ApiResponse(code=0, message="直链服务已启动", data=service.get_settings())
        else:
            return ApiResponse(code=-1, message="启动失败，请检查是否已登录")
    except Exception as e:
        logger.error(f"启动直链服务失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/stop", summary="停止直链服务")
async def stop_service():
    """停止 302 直链服务"""
    try:
        service = get_direct_link_service()
        success = service.stop()
        if success:
            return ApiResponse(code=0, message="直链服务已停止", data=service.get_settings())
        else:
            return ApiResponse(code=-1, message="停止失败")
    except Exception as e:
        logger.error(f"停止直链服务失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.get("/status", summary="查询直链服务状态")
async def get_status():
    """查询直链服务的运行状态"""
    try:
        service = get_direct_link_service()
        return ApiResponse(code=0, message="success", data=service.get_settings())
    except Exception as e:
        logger.error(f"查询直链服务状态失败: {e}")
        return ApiResponse(code=-1, message=str(e))
