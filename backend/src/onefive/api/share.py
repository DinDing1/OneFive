"""
分享管理 API 路由 - 管理分享链接的添加、浏览、整理、删除
"""
from fastapi import APIRouter
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
    try:
        service = get_share_service()
        result = service.add_share(req.share_url, req.receive_code)
        if result.get("success"):
            return ApiResponse(code=0, message="分享添加成功", data=result)
        else:
            return ApiResponse(code=-1, message=result.get("error", "添加失败"))
    except Exception as e:
        logger.error(f"添加分享失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.get("/list", summary="列出分享来源")
async def list_shares():
    """列出所有已添加的分享来源"""
    try:
        service = get_share_service()
        shares = service.list_shares()
        return ApiResponse(code=0, message="success", data={"shares": shares})
    except Exception as e:
        logger.error(f"列出分享失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.delete("/{source_id}", summary="删除分享")
async def delete_share(source_id: int):
    """删除分享来源及关联的所有文件"""
    try:
        service = get_share_service()
        service.delete_share(source_id)
        return ApiResponse(code=0, message="分享已删除")
    except Exception as e:
        logger.error(f"删除分享失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/delete-batch", summary="批量删除分享")
async def delete_shares_batch(req: DeleteBatchRequest):
    """批量删除分享来源及关联的所有文件"""
    try:
        service = get_share_service()
        result = service.delete_shares_batch(req.source_ids)
        return ApiResponse(
            code=0,
            message=f"已删除 {result['success']}/{result['total']} 个分享",
            data=result
        )
    except Exception as e:
        logger.error(f"批量删除分享失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.get("/all-files", summary="获取所有分享的根目录文件")
async def get_all_files(organized_only: bool = False, unorganized_only: bool = False):
    """获取所有分享来源的根目录文件，附带来源信息"""
    try:
        service = get_share_service()
        files = service.get_all_root_files(organized_only, unorganized_only)
        return ApiResponse(code=0, message="success", data={"files": files})
    except Exception as e:
        logger.error(f"获取所有文件失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.get("/all-organized", summary="获取所有已整理的文件")
async def get_all_organized():
    """获取所有分享来源的已整理文件，用于构建统一虚拟目录树"""
    try:
        service = get_share_service()
        result = service.get_all_organized_files()
        return ApiResponse(code=0, message="success", data=result)
    except Exception as e:
        logger.error(f"获取所有整理文件失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.get("/{source_id}/files", summary="列出分享文件")
async def list_files(source_id: int, parent_id: str = "0",
                     limit: int = 100, offset: int = 0):
    """列出分享目录中的文件"""
    try:
        service = get_share_service()
        result = service.list_files(source_id, parent_id, limit, offset)
        return ApiResponse(code=0, message="success", data=result)
    except Exception as e:
        logger.error(f"列出分享文件失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.get("/{source_id}/organized", summary="获取整理后的分类目录")
async def get_organized(source_id: int):
    """获取整理后的虚拟分类目录结构"""
    try:
        service = get_share_service()
        result = service.get_organized_files(source_id)
        return ApiResponse(code=0, message="success", data=result)
    except Exception as e:
        logger.error(f"获取整理目录失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.get("/search", summary="搜索分享文件")
async def search_files(keyword: str):
    """搜索所有分享中的文件"""
    try:
        service = get_share_service()
        results = service.search_files(keyword)
        return ApiResponse(code=0, message="success", data={"files": results})
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/recognize", summary="识别文件（只识别不写入数据库）")
async def recognize_file(req: FileActionRequest):
    """识别单个分享文件，返回 TMDB 结果但不写入数据库"""
    try:
        service = get_share_organize_service()
        share_service = get_share_service()
        
        # 获取文件名用于日志
        file_info = share_service.get_file(req.source_id, req.file_id)
        file_name = file_info.get("name", req.file_id) if file_info else req.file_id
        
        logger.info(f"识别分享文件: source_id={req.source_id}, name={file_name}")
        result = service.recognize_file(req.source_id, req.file_id)
        if result.get("success"):
            title = result.get("title", "")
            media_type = result.get("media_type", "")
            tmdb_id = result.get("tmdb_id", 0)
            logger.info(f"识别成功: {title} ({media_type}, tmdb={tmdb_id})")
            return ApiResponse(code=0, message="识别完成", data=result)
        else:
            logger.warning(f"识别失败: {result.get('error', '未知')}")
            return ApiResponse(code=-1, message=result.get("error", "识别失败"))
    except Exception as e:
        logger.error(f"识别分享文件异常: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/recognize/manual", summary="手动纠错识别分享文件")
async def manual_recognize_file(req: ManualFileActionRequest):
    """用户指定 TMDB ID 和媒体类型后重新识别分享文件"""
    try:
        if req.media_type not in ("movie", "tv"):
            return ApiResponse(code=-1, message="媒体类型只能是 movie 或 tv")
        if req.tmdb_id <= 0:
            return ApiResponse(code=-1, message="TMDB ID 不正确")

        service = get_share_organize_service()
        result = service.manual_recognize_file(req.source_id, req.file_id, req.tmdb_id, req.media_type)
        if result.get("success") and result.get("target_path"):
            return ApiResponse(code=0, message="手动识别完成", data=result)
        return ApiResponse(code=-1, message=result.get("error", "手动识别失败"))
    except Exception as e:
        logger.error(f"手动识别分享文件异常: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/organize/manual", summary="手动纠错整理分享文件")
async def manual_organize_file(req: ManualFileActionRequest):
    """按用户指定 TMDB ID 整理分享文件，并覆盖旧结果"""
    try:
        if req.media_type not in ("movie", "tv"):
            return ApiResponse(code=-1, message="媒体类型只能是 movie 或 tv")
        if req.tmdb_id <= 0:
            return ApiResponse(code=-1, message="TMDB ID 不正确")

        service = get_share_organize_service()
        result = service.manual_organize_file(req.source_id, req.file_id, req.tmdb_id, req.media_type)
        if result.get("success"):
            return ApiResponse(code=0, message="整理完成", data=result)
        return ApiResponse(code=-1, message=result.get("error", "整理失败"))
    except Exception as e:
        logger.error(f"手动整理分享文件异常: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/organize", summary="整理单个文件")
async def organize_file(req: FileActionRequest):
    """整理单个分享文件（识别 + 分类）"""
    try:
        service = get_share_organize_service()
        share_service = get_share_service()
        
        # 获取文件名用于日志
        file_info = share_service.get_file(req.source_id, req.file_id)
        file_name = file_info.get("name", req.file_id) if file_info else req.file_id
        
        logger.info(f"整理分享文件: source_id={req.source_id}, name={file_name}")
        result = service.organize_file(req.source_id, req.file_id)
        if result.get("success"):
            logger.info(f"整理完成: {result.get('name', '')} → {result.get('category', '')}")
            return ApiResponse(code=0, message="整理完成", data=result)
        else:
            logger.warning(f"整理失败: {result.get('error', '未知')}")
            return ApiResponse(code=-1, message=result.get("error", "整理失败"))
    except Exception as e:
        logger.error(f"整理分享文件异常: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/organize-batch", summary="批量整理")
async def organize_batch(req: OrganizeBatchRequest):
    """批量整理分享文件"""
    try:
        service = get_share_organize_service()
        logger.info(f"批量整理: source_id={req.source_id}, 文件数={len(req.file_ids)}")
        result = service.organize_batch(req.source_id, req.file_ids)
        return ApiResponse(
            code=0,
            message=f"整理完成: {result['success']}/{result['total']}",
            data=result
        )
    except Exception as e:
        logger.error(f"批量整理失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.get("/{source_id}/info", summary="获取分享详情")
async def get_share_info(source_id: int):
    """获取分享来源详情"""
    try:
        service = get_share_service()
        info = service.get_share_info(source_id)
        if info:
            return ApiResponse(code=0, message="success", data=info)
        else:
            return ApiResponse(code=-1, message="分享不存在")
    except Exception as e:
        logger.error(f"获取分享详情失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.get("/{source_id}/properties", summary="获取文件属性")
async def get_file_properties(source_id: int, file_id: str):
    """获取分享来源信息 + 文件信息 + 可选分类列表"""
    try:
        service = get_share_service()
        # 分享来源信息
        share_info = service.get_share_info(source_id)
        if not share_info:
            return ApiResponse(code=-1, message="分享不存在")
        # 文件信息（目录自动从子文件补充媒体信息）
        file_info = service.get_file_with_media_info(source_id, file_id)
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
    except Exception as e:
        logger.error(f"获取文件属性失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.put("/{source_id}/properties", summary="更新分享属性")
async def update_share_properties(source_id: int, req: UpdateSharePropertiesRequest):
    """更新分享来源属性（名称、分享码、提取码），同步到 share_file 表"""
    try:
        service = get_share_service()
        # 校验分享码唯一性（如果修改了 share_code）
        if req.share_code is not None:
            existing = service.db.fetchone(
                "SELECT id FROM share_source WHERE share_code = ? AND id != ?",
                (req.share_code, source_id)
            )
            if existing:
                return ApiResponse(code=-1, message="分享码已存在")
        service.update_share_source(
            source_id,
            share_name=req.share_name,
            share_code=req.share_code,
            receive_code=req.receive_code
        )
        logger.info(f"更新分享属性: source_id={source_id}")
        return ApiResponse(code=0, message="属性已更新")
    except Exception as e:
        logger.error(f"更新分享属性失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.put("/{source_id}/files/{file_id}/category", summary="更新文件分类")
async def update_file_category(source_id: int, file_id: str, req: UpdateFileCategoryRequest):
    """更新单个文件的分类路径"""
    try:
        service = get_share_service()
        service.update_file_category(source_id, file_id, req.category)
        logger.info(f"更新文件分类: source_id={source_id}, file_id={file_id}, category={req.category}")
        return ApiResponse(code=0, message="分类已更新")
    except Exception as e:
        logger.error(f"更新文件分类失败: {e}")
        return ApiResponse(code=-1, message=str(e))
