"""
分享洗版 API

- POST /api/share-wash/analyze         分析已整理分享中的多版本（同步，兼容）
- GET  /api/share-wash/analyze-stream  SSE 流式分析（正式环境/网关推荐）
- POST /api/share-wash/delete          删除劣质分享链接（整源）
"""
import asyncio
import json
import queue
import threading
from typing import List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..models.schemas import ApiResponse
from ..services.share_wash_service import get_share_wash_service
from ..logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/share-wash", tags=["分享洗版"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class AnalyzeRequest(BaseModel):
    """分析请求"""
    media_type: str = Field("all", description="all | movie | tv")


class DeleteWashRequest(BaseModel):
    """删除分享链接请求"""
    source_ids: List[int] = Field(default_factory=list, description="待删除的分享源 ID 列表")


@router.post("/analyze", summary="分析分享多版本")
async def analyze_share_wash(req: Optional[AnalyzeRequest] = None):
    """扫描已整理分享，找出同一作品的多条分享链接并按质量排序。

    注意：正式环境（飞牛统一网关）数据量大时请改用 GET /analyze-stream，
    避免 HTTP 长请求被前端 axios 默认 30s 超时或网关空闲切断。
    """
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


@router.get("/analyze-stream", summary="流式分析分享多版本（SSE）")
async def analyze_share_wash_stream(
    media_type: str = Query("all", description="all | movie | tv"),
):
    """SSE 流式分析：绕过 axios 超时，并周期性心跳保持飞牛网关连接。

    事件格式：
    - {"type":"start","media_type":"..."}
    - {"type":"progress","stage":"...","percent":N,"message":"..."}
    - {"type":"done","summary":{...},"groups":[...],"message":"..."}
    - {"type":"error","message":"..."}
    - 注释行 `: heartbeat` 保活
    """
    mt = (media_type or "all").strip().lower() or "all"
    logger.info(f"[分享洗版 SSE] 开始分析 media_type={mt}")

    async def event_generator():
        yield "data: " + json.dumps({"type": "start", "media_type": mt}, ensure_ascii=False) + "\n\n"

        q: queue.Queue = queue.Queue()
        done_flag = {"ok": False}

        def on_progress(evt: dict) -> None:
            q.put(evt)

        def worker() -> None:
            try:
                service = get_share_wash_service()
                data = service.analyze(mt, progress=on_progress)
                summary = data.get("summary") or {}
                msg = (
                    f"发现 {summary.get('groups', 0)} 组重复，"
                    f"可删 {summary.get('deletable_sources', 0)} 条分享"
                )
                q.put({
                    "type": "done",
                    "message": msg,
                    "summary": data.get("summary") or {},
                    "groups": data.get("groups") or [],
                })
            except Exception as e:
                logger.error(f"[分享洗版 SSE] 分析异常: {e}", exc_info=True)
                q.put({"type": "error", "message": str(e)})
            finally:
                done_flag["ok"] = True

        thread = threading.Thread(target=worker, name="share-wash-analyze", daemon=True)
        thread.start()

        while True:
            try:
                evt = q.get(timeout=2.0)
            except queue.Empty:
                # 注释心跳：保持统一网关/反向代理不因空闲断开
                yield ": heartbeat\n\n"
                if done_flag["ok"] and q.empty() and not thread.is_alive():
                    yield "data: " + json.dumps(
                        {"type": "error", "message": "分析线程异常结束"},
                        ensure_ascii=False,
                    ) + "\n\n"
                    break
                continue

            yield "data: " + json.dumps(evt, ensure_ascii=False) + "\n\n"
            if evt.get("type") in ("done", "error"):
                break

        thread.join(timeout=1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
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
