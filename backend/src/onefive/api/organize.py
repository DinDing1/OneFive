"""
整理 API 路由

提供媒体文件识别和整理接口。
"""
import asyncio
import json
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, List, Optional
from ..models.schemas import ApiResponse
from ..services.organize_service import get_organize_service
from ..services.config_service import get_config_service
from ..services.rename_service import DEFAULT_MOVIE_TEMPLATE, DEFAULT_TV_TEMPLATE
from ..services.classify_service import DEFAULT_STRATEGY, invalidate_strategy_cache
from ..services.file_info_service import BUILTIN_RELEASE_GROUPS, invalidate_custom_release_groups_cache
from ..exceptions import NotLoggedInError
from ..logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/organize", tags=["整理"])


class RecognizeRequest(BaseModel):
    """识别请求"""
    file_id: str
    file_name: str
    is_dir: bool = False
    folder_files: Optional[List[str]] = None


class ManualRecognizeRequest(RecognizeRequest):
    """手动纠错识别请求"""
    tmdb_id: int
    media_type: str


class SettingsRequest(BaseModel):
    """设置请求"""
    tmdb_api_key: Optional[str] = None
    tmdb_api_url: Optional[str] = None
    tmdb_language: Optional[str] = None
    media_library_path: Optional[str] = None
    source_path: Optional[str] = None
    movie_template: Optional[str] = None
    tv_template: Optional[str] = None
    organize_mode: Optional[str] = None
    classify_rules: Optional[str] = None
    release_groups: Optional[str] = None


@router.post("/recognize", summary="识别文件")
async def recognize_file(req: RecognizeRequest):
    """识别文件/文件夹，返回 TMDB 匹配结果和建议路径"""
    organize_service = get_organize_service()
    file_info = {
        "file_id": req.file_id,
        "name": req.file_name,
        "is_dir": req.is_dir,
    }
    # 用 asyncio.to_thread 把同步的 TMDB 网络请求放到线程池执行，
    # 避免阻塞 FastAPI 事件循环导致其他请求卡住
    result = await asyncio.to_thread(
        organize_service.recognize_file, file_info, req.folder_files
    )
    return ApiResponse(code=0, message="识别成功", data=result)


@router.post("/recognize/manual", summary="手动纠错识别")
async def manual_recognize_file(req: ManualRecognizeRequest):
    """用户输入 TMDB ID 和媒体类型后，按指定 ID 重新识别"""
    if req.media_type not in ("movie", "tv"):
        return ApiResponse(code=-1, message="媒体类型只能是 movie 或 tv")
    if req.tmdb_id <= 0:
        return ApiResponse(code=-1, message="TMDB ID 不正确")

    organize_service = get_organize_service()
    file_info = {
        "file_id": req.file_id,
        "name": req.file_name,
        "is_dir": req.is_dir,
    }
    # 同步 TMDB 查询放到线程池，避免阻塞事件循环
    result = await asyncio.to_thread(
        organize_service.recognize_file_manual,
        file_info, req.tmdb_id, req.media_type, req.folder_files
    )
    if not result.get("target_path"):
        return ApiResponse(code=-1, message="手动识别失败，请检查 TMDB ID 和媒体类型")
    return ApiResponse(code=0, message="手动识别成功", data=result)


class ExecuteRequest(BaseModel):
    """执行整理请求"""
    file_id: str
    file_name: str
    is_dir: bool = False
    target_path: Dict[str, str]
    organize_mode: str = "move"
    category: str = ""
    target_title: str = ""
    tmdb_id: int = 0
    media_type: str = ""
    year: str = ""
    season: int = 0
    episode: int = 0
    tmdb_poster: str = ""
    tmdb_backdrop: str = ""
    tmdb_rating: float = 0
    tech_info: Optional[Dict[str, str]] = None


@router.post("/execute", summary="执行整理")
async def execute_organize(req: ExecuteRequest):
    """执行文件整理：创建目录 → 移动/复制 → 重命名"""
    organize_service = get_organize_service()
    # 在主线程保存事件循环引用，供子线程 _submit_notify 使用
    # asyncio.to_thread 内部无法通过 get_event_loop() 获取循环
    organize_service._main_loop = asyncio.get_running_loop()
    # execute_organize 内部有 time.sleep 和同步文件操作 API 调用，
    # 用 asyncio.to_thread 放到线程池执行，避免阻塞事件循环
    result = await asyncio.to_thread(
        organize_service.execute_organize,
        file_id=req.file_id,
        file_name=req.file_name,
        is_dir=req.is_dir,
        target_path=req.target_path,
        organize_mode=req.organize_mode,
        category=req.category,
        target_title=req.target_title,
        tmdb_id=req.tmdb_id,
        media_info={
            "media_type": req.media_type,
            "year": req.year,
            "season": req.season,
            "episode": req.episode,
            "tmdb_poster": req.tmdb_poster,
            "tmdb_backdrop": req.tmdb_backdrop,
            "tmdb_rating": req.tmdb_rating,
            "tech_info": req.tech_info or {},
        },
    )
    if result["success"]:
        return ApiResponse(code=0, message=result["message"], data=result)
    return ApiResponse(code=-1, message=result["message"])


@router.get("/settings", summary="获取整理配置")
async def get_settings():
    """获取整理相关的配置项，DB 没有时返回内置默认值"""
    config_service = get_config_service()

    # 分类策略：DB 有就用，没有就用默认
    classify_rules_str = config_service.get("classify_rules")
    if not classify_rules_str:
        classify_rules_str = json.dumps(DEFAULT_STRATEGY, ensure_ascii=False)

    # 重命名模板：DB 有就用，没有就用默认
    movie_tpl = config_service.get("movie_template") or DEFAULT_MOVIE_TEMPLATE
    tv_tpl = config_service.get("tv_template") or DEFAULT_TV_TEMPLATE

    return ApiResponse(
        code=0,
        message="success",
        data={
            "tmdb_api_key": config_service.get("tmdb_api_key") or "",
            "tmdb_api_url": config_service.get("tmdb_api_url") or "https://api.themoviedb.org/3",
            "tmdb_language": config_service.get("tmdb_language") or "zh-CN",
            "media_library_path": config_service.get("media_library_path") or "/媒体库",
            "source_path": config_service.get("source_path") or "",
            "movie_template": movie_tpl,
            "tv_template": tv_tpl,
            "organize_mode": config_service.get("organize_mode") or "move",
            "classify_rules": classify_rules_str,
            "builtin_release_groups": BUILTIN_RELEASE_GROUPS,
            "custom_release_groups": config_service.get("release_groups") or "",
            "has_custom_movie_template": bool(config_service.get("movie_template")),
            "has_custom_tv_template": bool(config_service.get("tv_template")),
            "has_custom_classify_rules": bool(config_service.get("classify_rules")),
        }
    )


@router.put("/settings", summary="更新整理配置")
async def update_settings(req: SettingsRequest):
    """更新整理相关的配置项"""
    config_service = get_config_service()

    if req.tmdb_api_key is not None:
        config_service.set("tmdb_api_key", req.tmdb_api_key, "TMDB API Key")
    if req.tmdb_api_url is not None:
        config_service.set("tmdb_api_url", req.tmdb_api_url, "TMDB API 代理地址")
    if req.tmdb_language is not None:
        config_service.set("tmdb_language", req.tmdb_language, "TMDB 语言")
    if req.media_library_path is not None:
        config_service.set("media_library_path", req.media_library_path, "媒体库根目录")
    if req.source_path is not None:
        config_service.set("source_path", req.source_path, "保存路径")
    if req.movie_template is not None:
        config_service.set("movie_template", req.movie_template, "电影命名模板")
    if req.tv_template is not None:
        config_service.set("tv_template", req.tv_template, "电视剧命名模板")
    if req.organize_mode is not None:
        config_service.set("organize_mode", req.organize_mode, "整理方式")
    if req.classify_rules is not None:
        config_service.set("classify_rules", req.classify_rules, "分类策略")
        # 配置变更后刷新策略缓存，确保后续分类使用新的策略
        invalidate_strategy_cache()
    if req.release_groups is not None:
        config_service.set("release_groups", req.release_groups, "自定义发布组")
        # 配置变更后刷新缓存，确保后续解析使用新的自定义发布组
        invalidate_custom_release_groups_cache()

    return ApiResponse(code=0, message="配置已保存")


@router.post("/settings/reset-templates", summary="恢复默认重命名模板")
async def reset_templates():
    """恢复重命名模板为内置默认值"""
    config_service = get_config_service()
    config_service.set("movie_template", "", "电影命名模板")
    config_service.set("tv_template", "", "电视剧命名模板")
    logger.info("已恢复默认重命名模板")
    return ApiResponse(code=0, message="已恢复默认重命名模板")


@router.post("/settings/reset-rules", summary="恢复默认分类策略")
async def reset_rules():
    """恢复分类策略为内置默认值"""
    config_service = get_config_service()
    config_service.set("classify_rules", "", "分类策略")
    logger.info("已恢复默认分类策略")
    return ApiResponse(code=0, message="已恢复默认分类策略")
