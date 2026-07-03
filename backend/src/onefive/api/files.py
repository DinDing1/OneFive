"""
文件管理 API 路由

提供 115 云盘文件浏览、搜索、创建目录等接口。
"""
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from ..models.schemas import ApiResponse
from ..services.file_service import get_file_service

router = APIRouter(prefix="/api/files", tags=["文件管理"])


class MkdirRequest(BaseModel):
    """创建目录请求"""
    name: str
    pid: int = 0


@router.get("/list", summary="列出目录内容")
async def list_files(
    cid: int = 0,
    limit: int = 100,
    offset: int = 0,
    order: str = "file_name",
    asc: int = 1,
):
    """列出指定目录下的文件和文件夹

    Args:
        cid: 目录 ID，0 表示根目录
        limit: 分页大小
        offset: 分页偏移
        order: 排序字段 (file_name/file_size/file_type/user_utime/user_ptime)
        asc: 排序方向 (1=升序 0=降序)
    """
    file_service = get_file_service()
    # 115 API 网络请求为同步 I/O，放到线程池避免阻塞事件循环
    result = await asyncio.to_thread(
        file_service.list_files, cid=cid, limit=limit, offset=offset, order=order, asc=asc
    )
    return ApiResponse(code=0, message="success", data=result)


@router.get("/info/{file_id}", summary="获取文件详情")
async def get_file_info(file_id: str):
    """获取文件或目录的详细信息"""
    file_service = get_file_service()
    # 115 API 网络请求为同步 I/O，放到线程池避免阻塞事件循环
    result = await asyncio.to_thread(file_service.get_file_info, file_id)
    return ApiResponse(code=0, message="success", data=result)


@router.post("/mkdir", summary="创建目录")
async def create_folder(req: MkdirRequest):
    """创建新目录"""
    file_service = get_file_service()
    # 115 API 网络请求为同步 I/O，放到线程池避免阻塞事件循环
    result = await asyncio.to_thread(file_service.create_folder, name=req.name, pid=req.pid)
    return ApiResponse(code=0, message="创建目录成功", data=result)


@router.get("/search", summary="搜索文件")
async def search_files(keyword: str, cid: int = 0):
    """搜索文件"""
    file_service = get_file_service()
    # 115 API 网络请求为同步 I/O，放到线程池避免阻塞事件循环
    result = await asyncio.to_thread(file_service.search_files, keyword=keyword, cid=cid)
    return ApiResponse(code=0, message="success", data=result)


# ==================== 批量操作 ====================

class MoveRequest(BaseModel):
    """移动文件请求"""
    file_ids: list[str]
    to_cid: str


class CopyRequest(BaseModel):
    """复制文件请求"""
    file_ids: list[str]
    to_cid: str


class DeleteRequest(BaseModel):
    """删除文件请求"""
    file_ids: list[str]


class RenameRequest(BaseModel):
    """重命名文件请求"""
    file_id: str
    new_name: str


@router.post("/move", summary="批量移动文件")
async def move_files(req: MoveRequest):
    """批量移动文件/目录到目标目录"""
    file_service = get_file_service()
    # 115 API 网络请求为同步 I/O，放到线程池避免阻塞事件循环
    await asyncio.to_thread(file_service.move_files, file_ids=req.file_ids, to_cid=req.to_cid)
    return ApiResponse(code=0, message="移动成功", data=None)


@router.post("/copy", summary="批量复制文件")
async def copy_files(req: CopyRequest):
    """批量复制文件/目录到目标目录"""
    file_service = get_file_service()
    # 115 API 网络请求为同步 I/O，放到线程池避免阻塞事件循环
    await asyncio.to_thread(file_service.copy_files, file_ids=req.file_ids, to_cid=req.to_cid)
    return ApiResponse(code=0, message="复制成功", data=None)


@router.post("/delete", summary="批量删除文件")
async def delete_files(req: DeleteRequest):
    """批量删除文件/目录（移入回收站）"""
    file_service = get_file_service()
    # 115 API 网络请求为同步 I/O，放到线程池避免阻塞事件循环
    await asyncio.to_thread(file_service.delete_files, file_ids=req.file_ids)
    return ApiResponse(code=0, message="删除成功", data=None)


@router.post("/rename", summary="重命名文件")
async def rename_file(req: RenameRequest):
    """重命名单个文件/目录"""
    file_service = get_file_service()
    # 115 API 网络请求为同步 I/O，放到线程池避免阻塞事件循环
    await asyncio.to_thread(file_service.rename_file, file_id=req.file_id, new_name=req.new_name)
    return ApiResponse(code=0, message="重命名成功", data=None)
