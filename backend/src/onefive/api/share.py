"""
分享管理 API 路由 - 管理分享链接的添加、浏览、整理、删除
"""
import asyncio
import json
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from ..models.schemas import ApiResponse
from ..services.share_service import get_share_service
from ..services.share_organize_service import get_share_organize_service
from ..services.classify_service import DEFAULT_STRATEGY, _get_custom_strategy
from ..logger import get_logger
from ..sseutil import (
    SSE_HEADERS,
    job_store,
    streaming_response_from_job,
    streaming_response_from_thread,
    await_with_heartbeat,
    aiter_with_heartbeat,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/share", tags=["分享"])


class AddShareRequest(BaseModel):
    """添加分享请求"""
    share_url: str
    receive_code: str = ""


class FileActionRequest(BaseModel):
    """文件操作请求（识别/整理共用）"""
    source_id: int
    file_id: str


class ManualFileActionRequest(FileActionRequest):
    """手动纠错请求"""
    tmdb_id: int
    media_type: str


class OrganizeBatchRequest(BaseModel):
    """批量整理请求"""
    source_id: int
    file_ids: List[str]


class DeleteBatchRequest(BaseModel):
    """批量删除分享请求"""
    source_ids: List[int]


class UpdateSharePropertiesRequest(BaseModel):
    """更新分享属性请求"""
    share_name: Optional[str] = None
    share_code: Optional[str] = None
    receive_code: Optional[str] = None


class UpdateFileCategoryRequest(BaseModel):
    """更新文件分类请求"""
    category: str


@router.post("/add", summary="添加分享链接")
async def add_share(req: AddShareRequest):
    """添加分享链接，解析并存储文件信息"""
    service = get_share_service()
    # add_share 内部递归遍历 115 分享目录，可能耗时数十秒，必须放到线程池
    result = await asyncio.to_thread(service.add_share, req.share_url, req.receive_code)
    if result.get("success"):
        return ApiResponse(code=0, message="分享添加成功", data=result)
    return ApiResponse(code=-1, message=result.get("error", "添加失败"))


@router.get("/list", summary="列出分享来源")
async def list_shares(limit: int = 50, offset: int = 0):
    """列出已添加的分享来源（强制分页，默认 50，最大 500）。"""
    service = get_share_service()
    lim = 50 if (limit is None or limit <= 0) else min(int(limit), 500)
    result = await asyncio.to_thread(service.list_shares, lim, offset)
    if isinstance(result, list):
        result = {"shares": result, "total": len(result)}
    return ApiResponse(code=0, message="success", data=result)


@router.post("/{source_id}/check", summary="检测单个分享链接有效性")
async def check_link_valid(source_id: int):
    """检测单个分享链接是否有效"""
    try:
        service = get_share_service()
        result = await asyncio.to_thread(service.check_link_valid, source_id)
        skipped = bool((result or {}).get("skipped"))
        valid = bool((result or {}).get("valid"))
        if skipped:
            msg = (result or {}).get("error") or "检测跳过（网络/频控/未登录）"
        elif valid:
            msg = "链接有效"
        else:
            msg = (result or {}).get("error") or "链接无效"
        return ApiResponse(code=0, message=msg, data=result)
    except Exception as e:
        logger.exception(f"检测单个分享链接失败: source_id={source_id}")
        return ApiResponse(
            code=-1,
            message=f"检测失败: {str(e)[:200]}",
            data={"source_id": source_id, "valid": False, "error": str(e)[:200], "skipped": True},
        )


@router.get("/check-stream", summary="批量检测分享链接有效性（SSE 流式）")
async def check_all_links_stream():
    """批量检测所有分享链接有效性，SSE 流式返回每个检测结果。

    单次检测若较慢，期间发送注释心跳，避免飞牛网关空闲断连。

    SSE 事件格式：
    - {"type":"start","total":N}            开始检测
    - {"type":"progress","current":i,"total":N,"source_id":id,"share_name":"...","valid":true/false,"error":"..."}
    - {"type":"done","valid_count":X,"invalid_count":Y}  检测完成
    - 注释行 `: heartbeat` 保活
    """
    service = get_share_service()

    async def event_stream():
        # 获取所有分享（等待期间也心跳）
        shares = None
        async for kind, payload in await_with_heartbeat(
            asyncio.to_thread(service.get_all_shares_for_check)
        ):
            if kind == "heartbeat":
                yield payload
            elif kind == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': str(payload)}, ensure_ascii=False)}\n\n"
                return
            else:
                shares = payload

        total = len(shares or [])
        yield f"data: {json.dumps({'type': 'start', 'total': total}, ensure_ascii=False)}\n\n"

        valid_count = 0
        invalid_count = 0
        skipped_count = 0

        for i, share in enumerate(shares or [], 1):
            source_id = share["id"]
            result = None
            async for kind, payload in await_with_heartbeat(
                asyncio.to_thread(service.check_link_valid, source_id)
            ):
                if kind == "heartbeat":
                    yield payload
                elif kind == "error":
                    result = {"valid": False, "error": str(payload), "skipped": False}
                else:
                    result = payload
            result = result or {"valid": False, "error": "检测无结果", "skipped": False}
            skipped = bool(result.get("skipped"))

            if skipped:
                skipped_count += 1
            elif result.get("valid"):
                valid_count += 1
            else:
                invalid_count += 1

            # 推送进度（含 skipped，前端据此决定是否更新 UI/角标）
            progress_data = {
                "type": "progress",
                "current": i,
                "total": total,
                "source_id": source_id,
                "share_name": share.get("share_name", ""),
                "valid": bool(result.get("valid")),
                "skipped": skipped,
                "error": result.get("error", ""),
            }
            yield f"data: {json.dumps(progress_data, ensure_ascii=False)}\n\n"

            # 限流：p115client 文档警告 share_snap 频繁会封 IP；app 接口也需节流
            # skipped(405/频控) 时额外退避
            if i < total:
                await asyncio.sleep(3.0 if skipped else 1.5)

        # 完成后附带文件级角标计数（与筛选按钮一致）
        file_counts = {}
        async for kind, payload in await_with_heartbeat(
            asyncio.to_thread(service.get_root_file_counts)
        ):
            if kind == "heartbeat":
                yield payload
            elif kind == "error":
                logger.warning(f"检测完成后取角标失败: {payload}")
                file_counts = {}
            else:
                file_counts = payload or {}

        done_data = {
            "type": "done",
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "skipped_count": skipped_count,
            "file_counts": file_counts,
        }
        yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.delete("/{source_id}", summary="删除分享")
async def delete_share(source_id: int):
    """删除分享来源及关联的所有文件，并清理对应分享 STRM"""
    service = get_share_service()
    result = await asyncio.to_thread(service.delete_share, source_id)
    msg = "分享已删除"
    strm_deleted = int((result or {}).get("strm_deleted") or 0)
    if strm_deleted:
        msg += f"，并清理 {strm_deleted} 个分享 STRM"
    return ApiResponse(code=0, message=msg, data=result)


@router.post("/delete-batch", summary="批量删除分享")
async def delete_shares_batch(req: DeleteBatchRequest):
    """批量删除分享来源及关联的所有文件，并清理对应分享 STRM。

    正式环境大量删除请改用两段式 SSE：
    POST /delete-batch-job → GET /delete-batch-stream?job_id=...
    """
    service = get_share_service()
    result = await asyncio.to_thread(service.delete_shares_batch, req.source_ids)
    msg = f"已删除 {result['success']}/{result['total']} 个分享"
    strm_deleted = int(result.get("strm_deleted") or 0)
    if strm_deleted:
        msg += f"，并清理 {strm_deleted} 个分享 STRM"
    return ApiResponse(
        code=0,
        message=msg,
        data=result
    )


@router.post("/delete-batch-job", summary="创建批量删除任务（SSE 前置）")
async def create_delete_batch_job(req: DeleteBatchRequest):
    """创建批量删除任务，返回 job_id 供 delete-batch-stream 使用。"""
    ids = [int(x) for x in (req.source_ids or []) if int(x) > 0]
    if not ids:
        return ApiResponse(code=-1, message="未指定要删除的分享", data=None)
    job_id = job_store.create({"source_ids": ids})
    return ApiResponse(code=0, message="ok", data={"job_id": job_id, "total": len(ids)})


@router.get("/delete-batch-stream", summary="流式批量删除分享（SSE）")
async def delete_batch_stream(job_id: str = Query(..., description="delete-batch-job 返回的任务 ID")):
    """SSE 流式批量删除：绕过 axios 超时，心跳保持飞牛网关连接。

    使用 job claim/订阅模型：EventSource 自动重连时不会再报“任务不存在”，
    且后台删除不会因为首个连接断开而丢失进度。
    """

    def worker_factory(payload):
        source_ids = [int(x) for x in (payload.get("source_ids") or []) if int(x) > 0]

        def worker(on_progress):
            service = get_share_service()
            result = service.delete_shares_batch(source_ids, progress=on_progress)
            msg = f"已删除 {result['success']}/{result['total']} 个分享"
            strm_deleted = int(result.get("strm_deleted") or 0)
            if strm_deleted:
                msg += f"，并清理 {strm_deleted} 个分享 STRM"
            on_progress({"type": "done", "message": msg, **result})

        return worker

    # 先取 payload 仅用于 start_event 展示；真正 claim 在 streaming_response_from_job 内
    job = job_store.get(job_id)
    total_hint = 0
    if job is not None:
        total_hint = len(list((job.payload or {}).get("source_ids") or []))
        logger.info(f"[SSE 删除分享] job_id={job_id}, count={total_hint}")

    return streaming_response_from_job(
        job_id,
        worker_factory,
        start_event={"type": "start", "total": total_hint, "message": "开始删除分享…"},
        not_found_message="删除任务不存在或已过期",
        thread_name="share-delete-batch",
    )


@router.get("/all-files", summary="获取所有分享的根目录文件")
async def get_all_files(
    filter: str = "all",
    limit: int = 50,
    offset: int = 0,
    include_counts: bool = True,
):
    """分页获取所有分享源的根目录文件。

    - filter: all | organized | unorganized | valid | invalid
    - limit/offset: 服务端分页（3 万+ 目录时必须分页，禁止全量拉取）
    - include_counts: 是否返回各筛选角标计数
    """
    if limit is None or limit <= 0:
        limit = 50
    limit = min(int(limit), 200)
    offset = max(0, int(offset))

    service = get_share_service()
    result = await asyncio.to_thread(
        service.get_all_root_files,
        filter,
        limit,
        offset,
        include_counts,
    )
    if isinstance(result, list):
        result = {"files": result, "total": len(result), "limit": limit, "offset": offset}
    return ApiResponse(code=0, message="success", data=result)


@router.get("/organized-browse", summary="分页浏览整理视图虚拟目录")
async def organized_browse(path: str = "", limit: int = 50, offset: int = 0):
    """服务端浏览整理目录树，不加载全量已整理文件。

    - path: 虚拟路径（category/organized_dir 前缀），空=根
    - limit/offset: 当前层目录+文件的统一分页（目录在前）
    """
    if limit is None or limit <= 0:
        limit = 50
    limit = min(int(limit), 200)
    offset = max(0, int(offset))
    service = get_share_service()
    result = await asyncio.to_thread(
        service.list_organized_entries, path, limit, offset
    )
    return ApiResponse(code=0, message="success", data=result)


@router.get("/search", summary="搜索分享文件")
async def search_files(
    keyword: str = "",
    limit: int = 50,
    offset: int = 0,
    scope: str = "all",
):
    """分页搜索分享文件。

    - scope: all | organized | original
    - limit 最大 200
    """
    if limit is None or limit <= 0:
        limit = 50
    limit = min(int(limit), 200)
    offset = max(0, int(offset))
    service = get_share_service()
    result = await asyncio.to_thread(
        service.search_files, keyword, limit, offset, scope
    )
    # 兼容：底层若仍返回 list
    if isinstance(result, list):
        result = {
            "files": result,
            "total": len(result),
            "limit": limit,
            "offset": offset,
            "keyword": keyword,
            "scope": scope,
        }
    return ApiResponse(code=0, message="success", data=result)


@router.get("/{source_id}/files", summary="列出分享文件")
async def list_files(source_id: int, parent_id: str = "0",
                     limit: int = 100, offset: int = 0):
    """列出分享目录中的文件"""
    service = get_share_service()
    result = await asyncio.to_thread(service.list_files, source_id, parent_id, limit, offset)
    return ApiResponse(code=0, message="success", data=result)


@router.post("/recognize", summary="识别文件（只识别不写入数据库）")
async def recognize_file(req: FileActionRequest):
    """识别单个分享文件，返回 TMDB 结果但不写入数据库"""
    service = get_share_organize_service()
    share_service = get_share_service()

    # 获取文件名用于日志（同步数据库查询，放到线程池）
    file_info = await asyncio.to_thread(share_service.get_file, req.source_id, req.file_id)
    file_name = file_info.get("name", req.file_id) if file_info else req.file_id

    logger.info(f"识别分享文件: source_id={req.source_id}, name={file_name}")
    # recognize_file 内部调用 TMDB 同步 requests，放到线程池避免阻塞事件循环
    result = await asyncio.to_thread(
        service.recognize_file, req.source_id, req.file_id
    )
    if result.get("success"):
        title = result.get("title", "")
        media_type = result.get("media_type", "")
        tmdb_id = result.get("tmdb_id") or 0
        recognized = result.get("recognized")
        if recognized is None:
            recognized = bool(tmdb_id and media_type)
        if recognized:
            logger.info(f"识别成功: {title} ({media_type}, tmdb={tmdb_id})")
        else:
            logger.warning(
                f"识别未命中 TMDB: {title or file_name} "
                f"(media_type={media_type!r}, tmdb={tmdb_id}, error={result.get('error')})"
            )
        # 即使未命中也返回 data，方便前端展示解析标题 + 手动纠错
        return ApiResponse(code=0, message="识别完成" if recognized else "未匹配到 TMDB", data=result)
    logger.warning(f"识别失败: {result.get('error', '未知')}")
    return ApiResponse(code=-1, message=result.get("error", "识别失败"))


@router.post("/recognize/manual", summary="手动纠错识别分享文件")
async def manual_recognize_file(req: ManualFileActionRequest):
    """用户指定 TMDB ID 和媒体类型后重新识别分享文件"""
    if req.media_type not in ("movie", "tv"):
        return ApiResponse(code=-1, message="媒体类型只能是 movie 或 tv")
    if req.tmdb_id <= 0:
        return ApiResponse(code=-1, message="TMDB ID 不正确")

    service = get_share_organize_service()
    # 手动纠错也会按 TMDB ID 同步查询详情，放到线程池避免阻塞事件循环
    result = await asyncio.to_thread(
        service.manual_recognize_file,
        req.source_id, req.file_id, req.tmdb_id, req.media_type
    )
    if result.get("success") and result.get("target_path"):
        return ApiResponse(code=0, message="手动识别完成", data=result)
    return ApiResponse(code=-1, message=result.get("error", "手动识别失败"))


@router.post("/organize/manual", summary="手动纠错整理分享文件")
async def manual_organize_file(req: ManualFileActionRequest):
    """按用户指定 TMDB ID 整理分享文件，并覆盖旧结果"""
    if req.media_type not in ("movie", "tv"):
        return ApiResponse(code=-1, message="媒体类型只能是 movie 或 tv")
    if req.tmdb_id <= 0:
        return ApiResponse(code=-1, message="TMDB ID 不正确")

    service = get_share_organize_service()
    # 手动整理内部会同步查询 TMDB，放到线程池避免阻塞事件循环
    result = await asyncio.to_thread(
        service.manual_organize_file,
        req.source_id, req.file_id, req.tmdb_id, req.media_type
    )
    if result.get("success"):
        return ApiResponse(code=0, message="整理完成", data=result)
    return ApiResponse(code=-1, message=result.get("error", "整理失败"))




@router.post("/organize/manual-job", summary="创建手动纠错整理任务（SSE 前置）")
async def create_manual_organize_job(req: ManualFileActionRequest):
    """创建手动整理任务，返回 job_id 供 organize/manual-stream 使用。

    大文件夹整理可能远超 axios 30s，正式环境请走 SSE。
    """
    if req.media_type not in ("movie", "tv"):
        return ApiResponse(code=-1, message="媒体类型只能是 movie 或 tv")
    if req.tmdb_id <= 0:
        return ApiResponse(code=-1, message="TMDB ID 不正确")
    if not req.file_id:
        return ApiResponse(code=-1, message="file_id 不能为空")

    job_id = job_store.create({
        "source_id": int(req.source_id),
        "file_id": str(req.file_id),
        "tmdb_id": int(req.tmdb_id),
        "media_type": str(req.media_type),
    })
    return ApiResponse(code=0, message="ok", data={"job_id": job_id})


@router.get("/organize/manual-stream", summary="流式手动纠错整理（SSE）")
async def manual_organize_stream(job_id: str = Query(..., description="manual-job 返回的任务 ID")):
    """SSE 流式手动整理：绕过 axios 超时，心跳保持飞牛网关连接。

    支持 EventSource 重连：任务只 claim 一次，后续连接重放历史并继续收进度。
    """

    def worker_factory(payload):
        source_id = int(payload.get("source_id") or 0)
        file_id = str(payload.get("file_id") or "")
        tmdb_id = int(payload.get("tmdb_id") or 0)
        media_type = str(payload.get("media_type") or "")

        def worker(on_progress):
            on_progress({
                "type": "progress",
                "stage": "manual_organize",
                "percent": 5,
                "message": "开始手动整理…",
            })
            service = get_share_organize_service()
            result = service.manual_organize_file(source_id, file_id, tmdb_id, media_type)
            if result.get("success"):
                on_progress({
                    "type": "done",
                    "message": result.get("message") or "整理完成",
                    "success": True,
                    "result": result,
                })
            else:
                on_progress({
                    "type": "error",
                    "message": result.get("error") or result.get("message") or "整理失败",
                    "success": False,
                    "result": result,
                })

        return worker

    job = job_store.get(job_id)
    if job is not None:
        p = job.payload or {}
        logger.info(
            f"[SSE 手动整理] job_id={job_id}, source_id={p.get('source_id')}, "
            f"file_id={p.get('file_id')}, tmdb_id={p.get('tmdb_id')}, media_type={p.get('media_type')}"
        )

    return streaming_response_from_job(
        job_id,
        worker_factory,
        start_event={"type": "start", "message": "连接手动整理服务…"},
        not_found_message="整理任务不存在或已过期",
        thread_name="share-manual-organize",
    )


@router.post("/recompute-organized", summary="重算目录已整理标记（修复脏数据）")
async def recompute_organized(source_id: Optional[int] = None):
    """自底向上重算目录 organized 标记。

    规则：目录下所有子目录 + 视频文件均为已整理时，目录才为已整理；
    附属非视频文件（nfo/srt/海报等）不参与判定。
    不传 source_id 时处理全库。

    正式环境全库请改用 GET /recompute-organized-stream。
    """
    service = get_share_organize_service()
    result = await asyncio.to_thread(service.recompute_directory_organized, source_id)
    return ApiResponse(data=result)


@router.get("/recompute-organized-stream", summary="流式重算已整理标记（SSE）")
async def recompute_organized_stream(source_id: Optional[int] = Query(None, description="可选，限定单个分享源")):
    """SSE 流式重算：大库场景避免 axios 30s 超时与网关空闲断连。"""
    logger.info(f"[SSE 重算 organized] source_id={source_id}")

    def worker(on_progress):
        service = get_share_organize_service()
        result = service.recompute_directory_organized(source_id, progress=on_progress)
        on_progress({
            "type": "done",
            "message": (
                f"重算完成：检查 {result.get('checked_dirs', 0)} 个目录，"
                f"变更 {result.get('changed_dirs', 0)} 个"
            ),
            **result,
        })

    return streaming_response_from_thread(
        worker,
        start_event={"type": "start", "message": "开始重算已整理标记…", "source_id": source_id},
        thread_name="share-recompute-organized",
    )


@router.post("/organize", summary="整理单个文件")
async def organize_file(req: FileActionRequest):
    """整理单个分享文件（识别 + 分类）"""
    service = get_share_organize_service()
    share_service = get_share_service()

    # 获取文件名用于日志（同步数据库查询，放到线程池）
    file_info = await asyncio.to_thread(share_service.get_file, req.source_id, req.file_id)
    file_name = file_info.get("name", req.file_id) if file_info else req.file_id

    logger.info(f"整理分享文件: source_id={req.source_id}, name={file_name}")
    # organize_file 内部调用 TMDB 同步 requests，放到线程池避免阻塞事件循环
    result = await asyncio.to_thread(
        service.organize_file, req.source_id, req.file_id
    )
    if result.get("success"):
        logger.info(f"整理完成: {result.get('name', '')} → {result.get('category', '')}")
        return ApiResponse(code=0, message="整理完成", data=result)
    logger.warning(f"整理失败: {result.get('error', '未知')}")
    return ApiResponse(code=-1, message=result.get("error", "整理失败"))


@router.post("/organize-batch", summary="批量整理")
async def organize_batch(req: OrganizeBatchRequest):
    """批量整理分享文件"""
    service = get_share_organize_service()
    logger.info(f"批量整理: source_id={req.source_id}, 文件数={len(req.file_ids)}")
    # 批量整理内部循环调用 TMDB，放到线程池避免阻塞事件循环
    result = await asyncio.to_thread(
        service.organize_batch, req.source_id, req.file_ids
    )
    return ApiResponse(
        code=0,
        message=f"整理完成: {result['success']}/{result['total']}",
        data=result
    )


@router.post("/organize-job", summary="创建批量整理任务（SSE 前置）")
async def create_organize_job(req: OrganizeBatchRequest):
    """创建批量整理任务，返回 job_id 供 organize-stream 使用。

    说明：
    - EventSource 只能 GET，复杂/较长 file_ids 不宜全塞进 URL。
    - 正式环境（飞牛网关）长任务统一：POST 建任务 → GET SSE 拉流。
    """
    id_list = [str(fid).strip() for fid in (req.file_ids or []) if str(fid).strip()]
    if not id_list:
        return ApiResponse(code=-1, message="file_ids 不能为空")
    if int(req.source_id or 0) <= 0:
        return ApiResponse(code=-1, message="source_id 不正确")

    job_id = job_store.create({
        "source_id": int(req.source_id),
        "file_ids": id_list,
    })
    logger.info(
        f"[SSE 整理] 创建任务: job_id={job_id}, source_id={req.source_id}, 文件数={len(id_list)}"
    )
    return ApiResponse(code=0, message="ok", data={"job_id": job_id})


@router.get("/organize-stream", summary="流式批量整理（SSE 实时进度）")
async def organize_stream(
    job_id: Optional[str] = Query(None, description="organize-job 返回的任务 ID"),
    # 兼容旧前端：仍接受 source_id + file_ids 直连（不推荐，URL 易过长）
    source_id: Optional[int] = Query(None, description="兼容旧参数：分享来源 ID"),
    file_ids: Optional[str] = Query(None, description="兼容旧参数：文件 ID 逗号分隔"),
):
    """SSE 流式批量整理：连接后立即发 start，再推 progress/done；空闲时注释心跳保活。

    推荐流程：POST /organize-job → GET /organize-stream?job_id=...
    关键：job 使用 claim/订阅，网关断开后 EventSource 重连不再报“整理任务不存在或已过期”。
    """
    # 兼容旧直连参数（无 job_id）：仍走单连接生成器
    if not job_id:
        sid = int(source_id or 0)
        id_list = [fid.strip() for fid in (file_ids or "").split(",") if fid.strip()]
        if not id_list or sid <= 0:
            async def err_gen2():
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "error", "message": "整理参数无效（缺少 source_id/file_ids）"},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
            return StreamingResponse(
                err_gen2(), media_type="text/event-stream", headers=SSE_HEADERS
            )

        logger.info(f"[SSE 整理] 兼容直连: source_id={sid}, 文件数={len(id_list)}")

        async def legacy_generator():
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "start",
                        "message": "整理任务已连接",
                        "source_id": sid,
                        "total_hint": len(id_list),
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )
            service = get_share_organize_service()
            try:
                async for chunk in aiter_with_heartbeat(
                    service.organize_batch_stream(sid, id_list),
                    heartbeat_sec=2.0,
                ):
                    yield chunk
            except Exception as e:
                logger.error(f"[SSE 整理] 异常: {e}", exc_info=True)
                yield (
                    "data: "
                    + json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
                    + "\n\n"
                )

        return StreamingResponse(
            legacy_generator(),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    def worker_factory(payload):
        sid = int((payload or {}).get("source_id") or 0)
        raw_ids = (payload or {}).get("file_ids") or []
        id_list = [str(x).strip() for x in raw_ids if str(x).strip()]

        def worker(on_progress):
            if sid <= 0 or not id_list:
                on_progress({"type": "error", "message": "整理参数无效（缺少 source_id/file_ids）"})
                return

            service = get_share_organize_service()

            # organize_batch_stream 是 async 生成器；放到独立事件循环中跑，
            # 与 HTTP 连接解耦：连接断开/重连不影响后台整理继续。
            async def _consume():
                async for evt in service.organize_batch_stream(sid, id_list):
                    if isinstance(evt, dict):
                        on_progress(evt)

            asyncio.run(_consume())

        return worker

    job = job_store.get(job_id)
    total_hint = 0
    sid_hint = 0
    if job is not None:
        p = job.payload or {}
        sid_hint = int(p.get("source_id") or 0)
        total_hint = len([str(x).strip() for x in (p.get("file_ids") or []) if str(x).strip()])
        logger.info(
            f"[SSE 整理] 开始拉流: job_id={job_id}, source_id={sid_hint}, 文件数={total_hint}"
        )

    return streaming_response_from_job(
        job_id,
        worker_factory,
        start_event={
            "type": "start",
            "message": "整理任务已连接",
            "source_id": sid_hint,
            "total_hint": total_hint,
        },
        not_found_message="整理任务不存在或已过期",
        thread_name="share-organize-batch",
    )


@router.get("/{source_id}/info", summary="获取分享详情")
async def get_share_info(source_id: int):
    """获取分享来源详情"""
    service = get_share_service()
    info = await asyncio.to_thread(service.get_share_info, source_id)
    if info:
        return ApiResponse(code=0, message="success", data=info)
    return ApiResponse(code=-1, message="分享不存在")


@router.get("/{source_id}/properties", summary="获取文件属性")
async def get_file_properties(source_id: int, file_id: str):
    """获取分享来源信息 + 文件信息 + 可选分类列表"""
    service = get_share_service()
    # 分享来源信息（同步数据库查询，放到线程池）
    share_info = await asyncio.to_thread(service.get_share_info, source_id)
    if not share_info:
        return ApiResponse(code=-1, message="分享不存在")
    # 文件信息（目录自动从子文件补充媒体信息，放到线程池）
    file_info = await asyncio.to_thread(service.get_file_with_media_info, source_id, file_id)
    if not file_info:
        return ApiResponse(code=-1, message="文件不存在")
    # 获取可选分类列表（根据 media_type 过滤）
    media_type = file_info.get("media_type", "")
    custom_strategy = _get_custom_strategy()
    strategy = custom_strategy if custom_strategy else DEFAULT_STRATEGY
    categories = []
    if media_type in strategy:
        categories = [r["category"] for r in strategy[media_type]]
    return ApiResponse(code=0, message="success", data={
        "share": share_info,
        "file": file_info,
        "categories": categories,
    })


@router.put("/{source_id}/properties", summary="更新分享属性")
async def update_share_properties(source_id: int, req: UpdateSharePropertiesRequest):
    """更新分享来源属性（名称、分享码、提取码），同步到 share_file 表"""
    service = get_share_service()
    # 校验分享码唯一性（如果修改了 share_code）
    if req.share_code is not None:
        existing = await asyncio.to_thread(
            service.db.fetchone,
            "SELECT id FROM share_source WHERE share_code = ? AND id != ?",
            (req.share_code, source_id)
        )
        if existing:
            return ApiResponse(code=-1, message="分享码已存在")
    await asyncio.to_thread(
        service.update_share_source,
        source_id,
        share_name=req.share_name,
        share_code=req.share_code,
        receive_code=req.receive_code
    )
    logger.info(f"更新分享属性: source_id={source_id}")
    return ApiResponse(code=0, message="属性已更新")


@router.put("/{source_id}/files/{file_id}/category", summary="更新文件分类")
async def update_file_category(source_id: int, file_id: str, req: UpdateFileCategoryRequest):
    """更新单个文件的分类路径"""
    service = get_share_service()
    await asyncio.to_thread(service.update_file_category, source_id, file_id, req.category)
    logger.info(f"更新文件分类: source_id={source_id}, file_id={file_id}, category={req.category}")
    return ApiResponse(code=0, message="分类已更新")
