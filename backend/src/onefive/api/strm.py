"""
STRM 文件生成 API 路由 - 提供设置读写、授权路径查询和生成接口

接口列表：
- GET  /api/strm/settings          获取 STRM 配置
- POST /api/strm/settings          保存 STRM 配置
- GET  /api/strm/accessible-paths  获取飞牛授权目录列表
- POST /api/strm/generate          生成 STRM 文件
"""
from fastapi import APIRouter
from pydantic import BaseModel

from ..models.schemas import ApiResponse
from ..services.strm_service import get_strm_service
from ..logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/strm", tags=["STRM"])


class StrmSettingsRequest(BaseModel):
    """STRM 配置请求"""
    direct_link_base_url: str = "http://127.0.0.1:11581"
    output_path: str = ""


@router.get("/settings", summary="获取 STRM 配置")
async def get_settings():
    """获取 STRM 直链基地址和输出路径配置"""
    try:
        service = get_strm_service()
        settings = service.get_settings()
        return ApiResponse(code=0, message="success", data=settings)
    except Exception as e:
        logger.error(f"获取 STRM 配置失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/settings", summary="保存 STRM 配置")
async def save_settings(req: StrmSettingsRequest):
    """保存 STRM 直链基地址和输出路径

    保存时会校验：
    - 基地址必须以 http:// 或 https:// 开头
    - 输出路径非空时必须位于飞牛授权目录下
    """
    try:
        service = get_strm_service()
        settings = service.save_settings(
            direct_link_base_url=req.direct_link_base_url,
            output_path=req.output_path,
        )
        return ApiResponse(code=0, message="设置已保存", data=settings)
    except ValueError as e:
        # 业务校验失败，返回 code=-1，HTTP 200
        return ApiResponse(code=-1, message=str(e))
    except Exception as e:
        logger.error(f"保存 STRM 配置失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.get("/accessible-paths", summary="获取飞牛授权目录列表")
async def get_accessible_paths():
    """获取飞牛授权的可访问路径列表（TRIM_DATA_ACCESSIBLE_PATHS）"""
    try:
        service = get_strm_service()
        paths = service.get_accessible_paths()
        return ApiResponse(code=0, message="success", data={"paths": paths})
    except Exception as e:
        logger.error(f"获取授权目录列表失败: {e}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/generate", summary="生成 STRM 文件")
async def generate():
    """根据已整理的分享文件生成 STRM 文件到配置的输出目录

    生成前会再次校验输出路径是否在飞牛授权目录内。
    """
    try:
        service = get_strm_service()
        result = service.generate()
        return ApiResponse(code=0, message="生成完成", data=result)
    except ValueError as e:
        # 配置缺失或路径未授权
        return ApiResponse(code=-1, message=str(e))
    except Exception as e:
        logger.error(f"生成 STRM 文件失败: {e}")
        return ApiResponse(code=-1, message=str(e))
