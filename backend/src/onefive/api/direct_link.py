"""
302 直链 API 路由 - 管理 p115nano302 服务的设置、启停和状态查询
"""
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from ..models.schemas import ApiResponse
from ..services.direct_link_service import get_direct_link_service

router = APIRouter(prefix="/api/direct-link", tags=["直链"])


class DirectLinkSettingsRequest(BaseModel):
    """直链服务配置请求"""
    enabled: bool
    port: int = 11581


@router.get("/settings", summary="获取直链服务设置")
async def get_settings():
    """获取直链服务的当前配置（开关、端口、运行状态）"""
    service = get_direct_link_service()
    settings = await asyncio.to_thread(service.get_settings)
    return ApiResponse(code=0, message="success", data=settings)


@router.post("/settings", summary="保存直链服务设置")
async def save_settings(req: DirectLinkSettingsRequest):
    """保存直链服务配置（开关、端口）"""
    service = get_direct_link_service()
    await asyncio.to_thread(service.save_settings, enabled=req.enabled, port=req.port)
    settings = await asyncio.to_thread(service.get_settings)
    return ApiResponse(code=0, message="设置已保存", data=settings)


@router.post("/start", summary="启动直链服务")
async def start_service(allow_lan: bool = False):
    """启动 302 直链服务

    Args:
        allow_lan: 是否允许局域网访问，默认 False（仅本机 127.0.0.1 可访问）；
                   设为 True 时绑定 0.0.0.0，同局域网设备可访问用户云盘文件，请谨慎开启。
    """
    service = get_direct_link_service()
    success = await asyncio.to_thread(service.start, allow_lan=allow_lan)
    if success:
        return ApiResponse(code=0, message="直链服务已启动", data=await asyncio.to_thread(service.get_settings))
    return ApiResponse(code=-1, message="启动失败，请检查是否已登录", data=None)


@router.post("/stop", summary="停止直链服务")
async def stop_service():
    """停止 302 直链服务"""
    service = get_direct_link_service()
    success = await asyncio.to_thread(service.stop)
    if success:
        return ApiResponse(code=0, message="直链服务已停止", data=await asyncio.to_thread(service.get_settings))
    return ApiResponse(code=-1, message="停止失败", data=None)


@router.get("/status", summary="查询直链服务状态")
async def get_status():
    """查询直链服务的运行状态"""
    service = get_direct_link_service()
    return ApiResponse(code=0, message="success", data=await asyncio.to_thread(service.get_settings))
