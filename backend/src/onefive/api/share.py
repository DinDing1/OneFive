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
    service = get_share_service()
    result = await asyncio.to_thread(service.check_link_valid, source_id)
    return ApiResponse(code=0, message="检测完成", data=result)


@router.get("/check-stream", summary="批量检测分享链接有效性（SSE 流式）")
async def check_all_links_stream():
    """批量检测所有分享链接有效性，SSE 流式返回每个检测结果

    SSE 事件格式：
    - {"type":"start","total":N}            开始检测
    - {"type":"progress","current":i,"total":N,"source_id":id,"share_name":"...","valid":true/false,"error":"..."}
    - {"type":"done","valid_count":X,"invalid_count":Y}  检测完成
    """
    service = get_share_service()

    async def event_stream():
        # 获取所有分享
        shares = await asyncio.to_thread(service.get_all_shares_for_check)
        total = len(shares)

        yield f"data: {json.dumps({'type': 'start', 'total': total}, ensure_ascii=False)}\n\n"

        valid_count = 0
        invalid_count = 0
        skipped_count = 0

        for i, share in enumerate(shares, 1):
            source_id = share["id"]
            # 逐个检测（同步方法放线程池）
            result = await asyncio.to_thread(service.check_link_valid, source_id)
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
        file_counts = await asyncio.to_thread(service.get_root_file_counts)
        done_data = {
            "type": "done",
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "skipped_count": skipped_count,
            "file_counts": file_counts,
        }
        yield f"data: {json.dumps(done_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.delete("/{source_id}", summary="删除分享")
async def delete_share(source_id: int):
    """删除分享来源及关联的所有文件"""
    service = get_share_service()
    await asyncio.to_thread(service.delete_share, source_id)
    return ApiResponse(code=0, message="分享已删除")


@router.post("/delete-batch", summary="批量删除分享")
async def delete_shares_batch(req: DeleteBatchRequest):
    """批量删除分享来源及关联的所有文件"""
    service = get_share_service()
    result = await asyncio.to_thread(service.delete_shares_batch, req.source_ids)
    return ApiResponse(
        code=0,
        message=f"已删除 {result['success']}/{result['total']} 个分享",
        data=result
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



@router.post("/recompute-organized", summary="重算目录已整理标记（修复脏数据）")
async def recompute_organized(source_id: Optional[int] = None):
    """自底向上重算目录 organized 标记。

    规则：目录下所有子目录 + 视频文件均为已整理时，目录才为已整理；
    附属非视频文件（nfo/srt/海报等）不参与判定。
    不传 source_id 时处理全库。
    """
    service = get_share_organize_service()
    result = await asyncio.to_thread(service.recompute_directory_organized, source_id)
    return ApiResponse(data=result)


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


@router.get("/organize-stream", summary="流式批量整理（SSE 实时进度）")
async def organize_stream(
    source_id: int = Query(..., description="分享来源 ID"),
    file_ids: str = Query(..., description="文件 ID 列表，逗号分隔"),
):
    """SSE 流式批量整理：每完成一个文件推送一次进度，绕过前端 axios 超时限制

    事件格式：
      data: {"type": "progress", "index": 1, "total": 5, "name": "...", "success": true, ...}
      data: {"type": "done", "total": 5, "success": 4, "failed": 1}
    """
    # 解析 file_ids（逗号分隔 → 列表）
    id_list = [fid.strip() for fid in file_ids.split(",") if fid.strip()]
    if not id_list:
        async def err_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': 'file_ids 不能为空'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    logger.info(f"[SSE 整理] 开始: source_id={source_id}, 文件数={len(id_list)}")

    async def event_generator():
        service = get_share_organize_service()
        try:
            async for evt in service.organize_batch_stream(source_id, id_list):
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"[SSE 整理] 异常: {e}")
            err_payload = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(err_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
