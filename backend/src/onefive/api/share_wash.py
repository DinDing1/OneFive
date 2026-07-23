"""
分享洗版 API

- POST /api/share-wash/analyze  分析已整理分享中的多版本
- POST /api/share-wash/delete   删除劣质分享链接（整源）
"""
import asyncio
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..models.schemas import ApiResponse
from ..services.share_wash_service import get_share_wash_service
from ..logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/share-wash", tags=["分享洗版"])


class AnalyzeRequest(BaseModel):
    """分析请求"""
    media_type: str = Field("all", description="all | movie | tv")


class DeleteWashRequest(BaseModel):
    """删除分享链接请求"""
    source_ids: List[int] = Field(default_factory=list, description="待删除的分享源 ID 列表")


@router.post("/analyze", summary="分析分享多版本")
async def analyze_share_wash(req: Optional[AnalyzeRequest] = None):
    """扫描已整理分享，找出同一作品的多条分享链接并按质量排序。"""
    media_type = (req.media_type if req else "all") or "all"
    service = get_share_wash_service()
    data = await asyncio.to_thread(service.analyze, media_type)
    summary = data.get("summary") or {}
    return ApiResponse(
        code=0,
        message=(
            f"发现 {summary.get('groups', 0)} 组重复，"
            f"可删 {summary.get('deletable_sources', 0)} 条分享"
        ),
        data=data,
    )


@router.post("/delete", summary="删除劣质分享链接")
async def delete_wash_sources(req: DeleteWashRequest):
    """按 source_id 批量删除整条分享（本地库记录）。"""
    if not req.source_ids:
        return ApiResponse(code=1, message="未指定要删除的分享", data=None)
    service = get_share_wash_service()
    result = await asyncio.to_thread(service.delete_sources, req.source_ids)
    return ApiResponse(
        code=0,
        message=f"已删除 {result.get('success', 0)}/{result.get('total', 0)} 条分享链接",
        data=result,
    )
