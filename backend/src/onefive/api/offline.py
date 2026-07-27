"""离线转存 API - ed2k / magnet 提交到 115 云下载。"""
from __future__ import annotations

import asyncio
from typing import Optional, Union

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ..models.schemas import ApiResponse
from ..services.offline_download_service import get_offline_download_service

router = APIRouter(prefix="/api/offline", tags=["离线转存"])


class OfflineAddRequest(BaseModel):
    """提交离线链接请求。"""

    urls: Union[str, list[str]] = Field(..., description="ed2k/magnet 链接，支持字符串或多条列表")
    wp_path_id: Optional[str] = Field(
        default=None,
        description="可选，覆盖默认保存目录 cid；默认使用设置页「保存路径」",
    )


@router.get("/settings", summary="获取离线转存设置")
async def get_offline_settings():
    service = get_offline_download_service()
    data = await asyncio.to_thread(service.get_settings)
    return ApiResponse(code=0, message="success", data=data)


@router.post("/add", summary="提交 ed2k/magnet 离线转存")
async def add_offline_urls(req: OfflineAddRequest):
    service = get_offline_download_service()
    result = await asyncio.to_thread(
        service.add_urls,
        req.urls,
        req.wp_path_id,
        "api",
    )
    if result.get("success"):
        msg = f"已提交 {result.get('accepted', 0)}/{result.get('total', 0)}"
        if result.get("failed"):
            msg = result.get("error") or msg
        return ApiResponse(code=0, message=msg, data=result)
    return ApiResponse(code=-1, message=result.get("error") or "提交失败", data=result)


@router.get("/quota", summary="查询离线配额")
async def get_offline_quota():
    service = get_offline_download_service()
    result = await asyncio.to_thread(service.get_quota)
    if result.get("success"):
        return ApiResponse(code=0, message="success", data=result)
    return ApiResponse(code=-1, message=result.get("error") or "查询失败", data=result)


@router.get("/tasks", summary="离线任务列表")
async def list_offline_tasks(page: int = Query(1, ge=1, description="页码，从 1 开始")):
    service = get_offline_download_service()
    result = await asyncio.to_thread(service.list_tasks, page)
    if result.get("success"):
        return ApiResponse(code=0, message="success", data=result)
    return ApiResponse(code=-1, message=result.get("error") or "获取失败", data=result)
