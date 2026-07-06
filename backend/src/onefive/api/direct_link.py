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
    allow_lan: bool = False


@router.get("/settings", summary="获取直链服务设置")
async def get_settings():
    """获取直链服务的当前配置（开关、端口、运行状态）"""
    service = get_direct_link_service()
    settings = await asyncio.to_thread(service.get_settings)
    return ApiResponse(code=0, message="success", data=settings)


@router.post("/settings", summary="保存直链服务设置")
async def save_settings(req: DirectLinkSettingsRequest):
    """保存直链服务配置（开关、端口、局域网访问）"""
    service = get_direct_link_service()
    await asyncio.to_thread(service.save_settings, enabled=req.enabled, port=req.port, allow_lan=req.allow_lan)
    settings = await asyncio.to_thread(service.get_settings)
    return ApiResponse(code=0, message="设置已保存", data=settings)


@router.post("/start", summary="启动直链服务")
async def start_service():
    """启动 302 直链服务

    allow_lan 从配置读取，允许局域网访问时绑定 0.0.0.0，否则仅本机 127.0.0.1 可访问。
    如需允许局域网/公网访问，请先在设置中开启"允许局域网访问"。
    """
    service = get_direct_link_service()
    success = await asyncio.to_thread(service.start)
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
