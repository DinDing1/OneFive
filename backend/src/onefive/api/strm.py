"""
STRM 文件生成 API 路由 - 提供设置读写、授权路径查询和生成接口

接口列表：
- GET  /api/strm/settings          获取 STRM 配置
- POST /api/strm/settings          保存 STRM 配置
- GET  /api/strm/accessible-paths  获取飞牛授权目录列表
- POST /api/strm/generate          生成分享 STRM 文件
- POST /api/strm/generate-cloud    生成云盘 STRM 文件
"""
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel

from ..models.schemas import ApiResponse
from ..services.strm_service import get_strm_service

router = APIRouter(prefix="/api/strm", tags=["STRM"])


class StrmSettingsRequest(BaseModel):
    """STRM 配置请求"""
    direct_link_base_url: str = "http://127.0.0.1:11581"
    output_path: str = ""
    cloud_output_path: str = ""
    video_extensions: str = ""


@router.get("/settings", summary="获取 STRM 配置")
async def get_settings():
    """获取 STRM 直链基地址、分享输出路径、云盘输出路径配置"""
    service = get_strm_service()
    settings = await asyncio.to_thread(service.get_settings)
    return ApiResponse(code=0, message="success", data=settings)


@router.post("/settings", summary="保存 STRM 配置")
async def save_settings(req: StrmSettingsRequest):
    """保存 STRM 直链基地址和输出路径

    保存时会校验：
    - 基地址必须以 http:// 或 https:// 开头
    - 分享/云盘输出路径非空时必须位于飞牛授权目录下
    """
    service = get_strm_service()
    # 数据库写入为同步 I/O，放到线程池避免阻塞事件循环
    settings = await asyncio.to_thread(
        service.save_settings,
        direct_link_base_url=req.direct_link_base_url,
        output_path=req.output_path,
        cloud_output_path=req.cloud_output_path,
        video_extensions=req.video_extensions,
    )
    return ApiResponse(code=0, message="设置已保存", data=settings)


@router.get("/accessible-paths", summary="获取飞牛授权目录列表")
async def get_accessible_paths():
    """获取飞牛授权的可访问路径列表（TRIM_DATA_ACCESSIBLE_PATHS）"""
    service = get_strm_service()
    paths = await asyncio.to_thread(service.get_accessible_paths)
    return ApiResponse(code=0, message="success", data={"paths": paths})


@router.get("/accessible-paths/children", summary="列出授权目录下的子目录")
async def list_accessible_children(path: str = ""):
    """列出指定授权目录下的子目录（一层）

    前端选择 STRM 存储路径时，先选授权目录，再逐级浏览子目录，
    最终路径 = 授权目录 + 选中的子目录路径。

    Args:
        path: 要列出的目录路径，为空时返回所有授权目录
    """
    from pathlib import Path
    service = get_strm_service()

    # path 为空：返回所有授权目录
    if not path:
        paths = await asyncio.to_thread(service.get_accessible_paths)
        return ApiResponse(code=0, message="success", data={"dirs": paths})

    # 校验 path 在授权范围内
    accessible = await asyncio.to_thread(service.get_accessible_paths)
    if not service._is_path_authorized(path, accessible):
        return ApiResponse(code=0, message="success", data={"dirs": [], "error": "路径不在授权范围内"})

    # 列出子目录
    def _list_subdirs(p: str):
        result = []
        try:
            for entry in sorted(Path(p).iterdir(), key=lambda x: x.name.lower()):
                if entry.is_dir():
                    result.append(str(entry))
        except (PermissionError, FileNotFoundError, OSError):
            pass
        return result

    dirs = await asyncio.to_thread(_list_subdirs, path)
    return ApiResponse(code=0, message="success", data={"dirs": dirs})


@router.post("/generate", summary="生成分享 STRM 文件")
async def generate():
    """根据已整理的分享文件生成 STRM 文件到配置的输出目录

    生成前会再次校验输出路径是否在飞牛授权目录内。
    """
    service = get_strm_service()
    # 内部含数据库查询 + 文件 I/O，可能耗时数十秒到数分钟，必须放到线程池
    result = await asyncio.to_thread(service.generate)
    return ApiResponse(code=0, message="生成完成", data=result)


@router.post("/generate-cloud", summary="生成云盘 STRM 文件")
async def generate_cloud():
    """根据云盘媒体库目录生成 STRM 文件到配置的输出目录

    遍历 media_library_path 配置指定的云盘目录，为其中所有视频文件
    生成 STRM 文件，目录结构与云盘结构一致（剥离媒体库前缀）。
    直链使用 pickcode 格式：{base_url}/d115/{filename}?pickcode=xxx
    """
    service = get_strm_service()
    # 内部含数据库查询 + 文件 I/O，可能耗时数十秒到数分钟，必须放到线程池
    result = await asyncio.to_thread(service.generate_cloud)
    return ApiResponse(code=0, message="生成完成", data=result)
