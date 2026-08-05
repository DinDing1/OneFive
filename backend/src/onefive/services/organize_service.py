"""
整理执行服务

职责：执行实际的文件整理操作
流程：识别 -> 分类 -> 重命名 -> 移动/复制

文件夹识别逻辑（参考 media-dashboard）：
1. 先从文件夹名提取 TMDB ID
2. 在文件夹内找第一个视频文件，用它提取标题/年份/季集/技术信息
3. 视频文件名没有 TMDB ID 时，补充使用文件夹名的 ID
4. 电视剧文件夹只生成文件夹级路径
"""
import re
import time
import asyncio
from typing import Dict, Any, Optional, List
from .tmdb_service import get_tmdb_service
from .file_info_service import (
    extract_key_info, extract_tech_info, get_video_extensions,
    has_season_episode_marker, format_size,
)
from .classify_service import classify_media
from .rename_service import generate_target_path, normalize_se_number
from .file_service import get_file_service
from .config_service import get_config_service
from ..logger import get_logger

logger = get_logger(__name__)

# ==================== 常量 ====================
# 等待 115 服务端目录创建同步（秒）
DIR_CREATE_WAIT = 0.5
# 等待 115 服务端文件移动同步（秒）
FILE_MOVE_WAIT = 1.0
# TMDB 海报图片尺寸
POSTER_IMAGE_SIZE = "w500"
# TMDB 背景图尺寸
BACKDROP_IMAGE_SIZE = "w780"


def _find_first_video_file(file_names: List[str]) -> Optional[str]:
    """在文件列表中找到第一个视频文件"""
    video_exts = get_video_extensions()
    for name in file_names:
        ext = '.' + name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        if ext in video_exts:
            return name
    return None


def _has_season_pattern(file_names: List[str]) -> bool:
    """检查文件列表中是否有季集标识（委托公共函数 has_season_episode_marker）"""
    return any(has_season_episode_marker(name) for name in file_names)


class OrganizeService:
    """整理执行服务"""

    def __init__(self):
        self.tmdb_service = get_tmdb_service()
        self.file_service = get_file_service()
        self.config_service = get_config_service()
        # 主线程事件循环引用：execute_organize 在线程池中执行，
        # 子线程无法通过 asyncio.get_event_loop() 获取循环，
        # 必须在主线程初始化时保存引用
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        # 批量场景可置 True 抑制逐条通知；云盘整理默认不压制，走手动整理同款模板
        self._suppress_notify: bool = False

    def recognize_file(self, file_info: Dict[str, Any],
                       folder_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """识别单个文件/文件夹

        文件夹模式下采用特殊逻辑：
        1. 先从文件夹名提取 TMDB ID
        2. 用内部第一个视频文件提取标题/年份/季集/技术信息
        3. 补充合并 TMDB ID

        Args:
            file_info: 文件信息（来自 file_service.list_files）
            folder_files: 文件夹内的文件名列表（文件夹模式时传入）

        Returns:
            识别结果，包含 TMDB 信息、分类、建议路径等
        """
        filename = file_info.get("name", "")
        is_dir = file_info.get("is_dir", False)

        # ==================== 文件夹模式 ====================
        if is_dir:
            # folder_files 可能只含直接子文件名（前端只列一层），
            # 如果没有视频文件，尝试用 file_id 作为 CID 递归查找
            if not folder_files or not _find_first_video_file(folder_files):
                recursive_files = self._recursive_list_video_names(file_info.get("file_id", ""))
                if recursive_files:
                    folder_files = recursive_files
                    logger.info(f"递归查找视频文件: 找到 {len(recursive_files)} 个")

            if folder_files:
                logger.info(f"识别文件夹: {filename}，内部文件数: {len(folder_files)}")
                return self._recognize_folder(file_info, filename, folder_files)

        # ==================== 单文件模式 ====================
        logger.info(f"识别文件: {filename}")
        key_info = extract_key_info(filename)
        tech_info = extract_tech_info(filename)

        # TMDB 搜索（使用公共验证方法）
        tmdb_details, resolved_media_type = self.tmdb_service.search_with_validation(
            tmdb_id=key_info.get("tmdbId"),
            title=key_info.get("title", ""),
            media_type=key_info["mediaType"],
            year=key_info.get("year"),
            fallback_query=key_info.get("fallbackQuery") or "",
        )
        # 回退到另一类型时更新 mediaType
        if resolved_media_type:
            key_info["mediaType"] = resolved_media_type
        # 文件名无年份时，用 TMDB 详情回填，供路径/结果共用
        if tmdb_details:
            self._resolve_media_year(key_info, tmdb_details)

        # 分类
        category = ""
        if tmdb_details:
            category = classify_media(tmdb_details, key_info["mediaType"])
            logger.info(f"分类结果: {category}")

        # 生成目标路径
        target_path = None
        if tmdb_details:
            target_path = self._generate_path(tmdb_details, key_info, tech_info)
            if target_path:
                path_str = f"{target_path['dir']}/{target_path['filename']}" if target_path['filename'] else target_path['dir']
                logger.info(f"目标路径: {path_str}")

        return self._build_result(file_info, key_info, tech_info, tmdb_details,
                                  category, target_path)

    def _recognize_folder(self, file_info: Dict[str, Any],
                          folder_name: str, folder_files: List[str]) -> Dict[str, Any]:
        """文件夹识别逻辑

        优先级：
        1. 从文件夹名提取 TMDB ID
        2. 从内部第一个视频文件提取标题/年份/季集/技术信息
        3. 没有视频文件时回退用文件夹名
        """
        # 步骤1：从文件夹名提取 TMDB ID
        folder_info = extract_key_info(folder_name)
        folder_tmdb_id = folder_info.get("tmdbId")
        if folder_tmdb_id:
            logger.info(f"文件夹名提取到 TMDB ID: {folder_tmdb_id}")

        # 步骤2：找内部第一个视频文件
        video_file = _find_first_video_file(folder_files)

        if video_file:
            logger.info(f"使用内部视频文件提取信息: {video_file}")
            # 用视频文件名提取详细信息
            key_info = extract_key_info(video_file)
            tech_info = extract_tech_info(video_file)
            # 补充文件夹名的 TMDB ID
            if not key_info.get("tmdbId") and folder_tmdb_id:
                key_info["tmdbId"] = folder_tmdb_id
                logger.info("补充使用文件夹名的 TMDB ID")
        else:
            logger.info("未找到视频文件，使用文件夹名提取信息")
            # 没有视频文件，回退用文件夹名
            key_info = folder_info
            tech_info = {}

        # 检查文件夹内文件是否有季集标识（辅助判断媒体类型）
        if key_info.get("season") is None and _has_season_pattern(folder_files):
            key_info["mediaType"] = "tv"
            key_info["season"] = 1
            logger.info("检测到季集标识，判定为电视剧")

        # TMDB 搜索（使用公共验证方法）
        tmdb_details, resolved_media_type = self.tmdb_service.search_with_validation(
            tmdb_id=key_info.get("tmdbId"),
            title=key_info.get("title", ""),
            media_type=key_info["mediaType"],
            year=key_info.get("year"),
            fallback_query=key_info.get("fallbackQuery") or "",
        )
        # 回退到另一类型时更新 mediaType
        if resolved_media_type:
            key_info["mediaType"] = resolved_media_type
        # 文件名无年份时，用 TMDB 详情回填，供路径/结果共用
        if tmdb_details:
            self._resolve_media_year(key_info, tmdb_details)

        # 分类
        category = ""
        if tmdb_details:
            category = classify_media(tmdb_details, key_info["mediaType"])
            logger.info(f"分类结果: {category}")

        # 生成目标路径
        target_path = None
        if tmdb_details:
            target_path = self._generate_path(tmdb_details, key_info, tech_info,
                                              is_folder=True)
            if target_path:
                path_str = f"{target_path['dir']}/{target_path['filename']}" if target_path['filename'] else target_path['dir']
                logger.info(f"目标路径: {path_str}")

        return self._build_result(file_info, key_info, tech_info, tmdb_details,
                                  category, target_path)

    def recognize_file_manual(self, file_info: Dict[str, Any], tmdb_id: int,
                              media_type: str,
                              folder_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """手动 TMDB 纠错识别

        用户明确输入 TMDB ID 和媒体类型时，不再按标题搜索，直接按 ID 查询。
        文件名/目录内视频只负责提供季集、分辨率、发布组等整理所需信息。
        """
        filename = file_info.get("name", "")
        is_dir = file_info.get("is_dir", False)

        if is_dir and folder_files:
            video_file = _find_first_video_file(folder_files)
            parse_name = video_file or filename
        else:
            parse_name = filename

        key_info = extract_key_info(parse_name)
        tech_info = extract_tech_info(parse_name)
        key_info["tmdbId"] = tmdb_id
        key_info["mediaType"] = media_type

        # TMDB 搜索（使用公共验证方法）
        tmdb_details, resolved_media_type = self.tmdb_service.search_with_validation(
            tmdb_id=tmdb_id,
            title=key_info.get("title", ""),
            media_type=media_type,
            year=key_info.get("year"),
            fallback_query=key_info.get("fallbackQuery") or "",
        )
        # 回退到另一类型时更新 mediaType
        if resolved_media_type:
            key_info["mediaType"] = resolved_media_type
        category = classify_media(tmdb_details, key_info["mediaType"]) if tmdb_details else ""
        target_path = self._generate_path(tmdb_details, key_info, tech_info, is_folder=is_dir) if tmdb_details else None
        return self._build_result(file_info, key_info, tech_info, tmdb_details, category, target_path)

    @staticmethod
    def _year_from_tmdb_details(tmdb_details: Optional[Dict]) -> str:
        """从 TMDB 详情提取首映/上映年份。

        文件名经常没有年份（如 A.Good.Girls.Guide...），但 TMDB 已匹配到作品时
        必须用 first_air_date / release_date 回填，否则目标路径会出现
        「标题 () {tmdb=...}」空年份。
        """
        if not tmdb_details:
            return ""
        # 电视剧优先 first_air_date，电影用 release_date；兼容详情缺失时的交叉字段
        date = (
            tmdb_details.get("first_air_date")
            or tmdb_details.get("release_date")
            or ""
        )
        year = str(date)[:4]
        return year if year.isdigit() and len(year) == 4 else ""

    def _resolve_media_year(self, key_info: Dict[str, Any], tmdb_details: Optional[Dict]) -> str:
        """解析最终使用的媒体年份：文件名优先，缺失则回填 TMDB。"""
        year = str(key_info.get("year") or "").strip()
        if year.isdigit() and len(year) == 4:
            return year
        tmdb_year = self._year_from_tmdb_details(tmdb_details)
        if tmdb_year:
            # 回写 key_info，后续路径/结果/通知共用同一年份
            key_info["year"] = tmdb_year
            return tmdb_year
        return year

    def _get_season_year(self, tmdb_id: str, season: str,
                          cache: Optional[Dict[tuple, str]] = None) -> str:
        """获取指定季的年份（首播年的前 4 位）。

        用于填充 TV 模板中的 {{seasonYear}} 变量（与 {{year}} 首播年区分）。
        支持 Season 00 特别篇。

        Args:
            tmdb_id: TMDB ID 字符串
            season: 已规范化的季号字符串（"1" / "0" 等，空串表示无季）
            cache: 可选缓存字典，key=(tmdb_id, season)。
                   批量重命名时传入，同一季只调一次 TMDB API（32 集 → 1 次调用）。

        Returns:
            季年份字符串（如 "2026"），失败或无季时返回空字符串
        """
        if not tmdb_id or season == "":
            return ""

        cache_key = (tmdb_id, season)
        if cache is not None and cache_key in cache:
            return cache[cache_key]

        season_year = ""
        try:
            season_info = self.tmdb_service.get_tv_season(int(tmdb_id), int(season))
            if season_info:
                air_date = season_info.get("air_date", "")
                if air_date:
                    season_year = air_date[:4]
        except Exception as e:
            logger.warning(f"获取季年份失败: tmdb_id={tmdb_id}, season={season}, {e}")

        if cache is not None:
            cache[cache_key] = season_year

        return season_year

    def _generate_path(self, tmdb_details: Dict, key_info: Dict[str, Any],
                       tech_info: Dict[str, str],
                       is_folder: bool = False) -> Dict[str, str]:
        """生成目标路径

        文件夹+电视剧：只生成文件夹级路径（不含文件名）
        其他：生成完整文件路径
        """
        tmdb_id = tmdb_details.get("id", "")
        # 标题选择：复用 tmdb_service.resolve_media_title 共享逻辑
        # （TMDB 原名优先 > query 含中文 > details.title 含中文 > get_chinese_title 兜底）
        # 与分享整理共用同一逻辑，避免逻辑漂移
        title = self.tmdb_service.resolve_media_title(
            key_info.get("title", ""), tmdb_details)
        # 文件名无年份时，用 TMDB 首播/上映年回填，避免「标题 () {tmdb=...}」
        year = self._resolve_media_year(key_info, tmdb_details)
        # 特别篇 season=0 合法，不能用 if key_info.get("season") 判空
        season = normalize_se_number(key_info.get("season"))
        episode = normalize_se_number(key_info.get("episode"))
        # 获取季年份（含 Season 00 特别篇）
        season_year = self._get_season_year(str(tmdb_id), season) if key_info["mediaType"] == "tv" else ""

        # 文件夹+电视剧：只返回文件夹路径
        if is_folder and key_info["mediaType"] == "tv":
            dir_path = f"{title} ({year}) {{tmdb={tmdb_id}}}"
            if season != "":
                dir_path += f"/Season {season.zfill(2)}"
            return {"dir": dir_path, "filename": ""}

        return generate_target_path(
            media_type=key_info["mediaType"],
            title=title,
            year=year,
            tmdb_id=str(tmdb_id),
            tech_info=tech_info,
            season_year=season_year,
            season=season,
            episode=episode,
        )

    def _build_result(self, file_info: Dict, key_info: Dict[str, Any],
                      tech_info: Dict[str, str], tmdb_details: Optional[Dict],
                      category: str, target_path: Optional[Dict]) -> Dict[str, Any]:
        """构建识别结果"""
        # 提前计算海报/背景图 URL，避免字典字面量中行过长
        poster_url = self.tmdb_service.build_image_url(
            tmdb_details.get("poster_path", ""), POSTER_IMAGE_SIZE) if tmdb_details else None
        backdrop_url = self.tmdb_service.build_image_url(
            tmdb_details.get("backdrop_path", ""), BACKDROP_IMAGE_SIZE) if tmdb_details else None
        return {
            "file_id": file_info.get("file_id", ""),
            "filename": file_info.get("name", ""),
            "is_dir": file_info.get("is_dir", False),
            "media_type": key_info["mediaType"],
            # 标题选择：与 _generate_path 一致，复用 tmdb_service 共享逻辑，
            # 保证 UI 显示标题与整理后的文件名同名
            "title": self.tmdb_service.resolve_media_title(
                key_info.get("title", ""), tmdb_details),
            # 与路径生成一致：优先文件名年份，否则 TMDB 回填
            "year": self._resolve_media_year(key_info, tmdb_details),
            "season": key_info.get("season"),
            "episode": key_info.get("episode"),
            "tmdb_id": tmdb_details.get("id") if tmdb_details else key_info.get("tmdbId"),
            "category": category,
            "tech_info": tech_info,
            "target_path": target_path,
            "tmdb_poster": poster_url,
            "tmdb_backdrop": backdrop_url,
            "tmdb_overview": tmdb_details.get("overview", "") if tmdb_details else "",
            "tmdb_rating": tmdb_details.get("vote_average", 0) if tmdb_details else 0,
        }

    def execute_organize(self, file_id: str, file_name: str,
                         is_dir: bool, target_path: Dict[str, str],
                         organize_mode: str = "move",
                         category: str = "",
                         target_title: str = "",
                         tmdb_id: int = 0,
                         media_info: Optional[Dict[str, Any]] = None,
                         source_parent_id: Optional[str] = None) -> Dict[str, Any]:
        """执行整理：创建目录 → 移动/复制 → 重命名

        完整路径 = 媒体库路径 + 分类 + target_path.dir

        Args:
            file_id: 文件/文件夹 ID
            file_name: 原文件名
            is_dir: 是否为文件夹
            target_path: {"dir": "目标目录路径", "filename": "目标文件名"}
            organize_mode: "move" 或 "copy"
            category: 分类路径，如 "电影/国产电影"
            target_title: TMDB 中文标题（用于内部文件重命名）
            tmdb_id: TMDB ID（用于内部文件重命名）
            source_parent_id: 移动前父目录 ID（可选；移动成功后用于清理空目录）
        """
        dir_path = target_path.get("dir", "")
        target_filename = target_path.get("filename", "")

        if not dir_path:
            return {"success": False, "message": "目标路径为空"}

        # 拼接完整路径：媒体库路径 + 分类 + 目标目录
        media_library = self.config_service.get("media_library_path") or ""
        full_parts = []
        if media_library and media_library != '/':
            full_parts.append(media_library.strip('/'))
        if category:
            full_parts.append(category)

        # 文件夹模式：目标是分类目录，文件夹会被复制/移动进去
        # 文件模式：目标是具体的电影/剧集目录，文件会被放进去
        if not is_dir:
            full_parts.append(dir_path)
        full_dir = '/'.join(full_parts) if full_parts else dir_path

        logger.info(f"开始整理: {file_name} → {full_dir}/{target_filename}，模式: {organize_mode}")

        try:
            # 步骤1：逐级创建目标目录
            target_cid = self._ensure_directory(full_dir)
            if not target_cid:
                return {"success": False, "message": f"创建目录失败: {full_dir}"}

            logger.info(f"目标目录就绪: {full_dir} (cid={target_cid})")

            # 步骤2：移动或复制文件
            # 移动前记录原父目录，便于事后清理「待整理」下因挪走视频留下的空文件夹
            parent_for_cleanup: Optional[str] = None
            if organize_mode != "copy":
                parent_for_cleanup = (
                    str(source_parent_id).strip()
                    if source_parent_id not in (None, "")
                    else self.file_service.get_parent_id(file_id)
                )

            file_ids = [file_id]
            if organize_mode == "copy":
                self.file_service.copy_files(file_ids, str(target_cid))
                action = "复制"
            else:
                self.file_service.move_files(file_ids, str(target_cid))
                action = "移动"

            logger.info(f"{action}成功: {file_name} → {full_dir}")

            # 步骤3：重命名
            time.sleep(FILE_MOVE_WAIT)  # 等待 115 服务端同步

            if is_dir:
                # 文件夹模式：dir_path 可能包含子目录（如 "标题 (年份) {tmdb=ID}/Season 01"）
                # 拆分：第一部分是文件夹名，其余是子目录
                dir_parts = [p for p in dir_path.split('/') if p.strip()]
                folder_name = dir_parts[0] if dir_parts else dir_path
                sub_dirs = dir_parts[1:] if len(dir_parts) > 1 else []

                # 查找刚复制/移动的文件夹（仍用原始文件名）
                moved_id = self._find_file_in_dir(target_cid, file_name)

                # 检查目标文件夹名是否已存在（同一部剧的不同规格版本）
                existing_folder = self._quick_find_in_dir(target_cid, folder_name, is_dir=True) if folder_name else None

                folder_id = None
                if existing_folder and existing_folder != moved_id:
                    # 目标文件夹已存在 → 合并内容到已有文件夹，避免创建 "(1)" 重复目录
                    if moved_id:
                        self._merge_folder_contents(moved_id, existing_folder)
                        # 合并后删除空的原文件夹
                        try:
                            self.file_service.delete_files([str(moved_id)])
                            logger.info(f"合并到已有文件夹并删除原目录: {file_name} → {folder_name}")
                        except Exception as e:
                            logger.warning(f"删除原文件夹失败: {e}")
                    folder_id = existing_folder
                elif folder_name and folder_name != file_name:
                    # 正常重命名流程
                    if moved_id:
                        self.file_service.rename_file(str(moved_id), folder_name)
                        logger.info(f"重命名文件夹: {file_name} → {folder_name}")
                        folder_id = moved_id
                    else:
                        logger.warning(f"未找到已移动的文件夹: {file_name}")
                else:
                    folder_id = moved_id

                # 文件夹找不到 → 整理失败（复制可能还在同步，重试已耗尽）
                if not folder_id:
                    self._submit_notify(
                        success=False, file_name=file_name,
                        title=target_title or file_name, category=category,
                        action=action, target_dir=full_dir,
                        media_info=media_info or {},
                    )
                    return {"success": False, "message": f"整理失败：复制后未找到文件夹 {file_name}，请稍后重试"}

                # 创建子目录（如 Season 01）
                # 优先使用已有子目录（模糊匹配 Season 01 ≈ Season 1），
                # 避免原始文件夹已有 Season 子目录时创建多余空目录
                final_cid = folder_id
                for sub in sub_dirs:
                    # 1. 精确匹配
                    sub_id = self._quick_find_in_dir(final_cid, sub, is_dir=True)
                    if sub_id:
                        final_cid = sub_id
                        continue
                    # 2. 模糊匹配：原始文件夹可能有 Season 1/S01 等变体
                    sub_id = self._find_season_dir_variant(final_cid, sub)
                    if sub_id:
                        # 重命名为标准名称（如 Season 1 → Season 01）
                        try:
                            self.file_service.rename_file(str(sub_id), sub)
                            logger.info(f"重命名子目录: 变体 → {sub}")
                        except Exception as e:
                            logger.warning(f"重命名子目录失败: {e}")
                        final_cid = sub_id
                        continue
                    # 3. 子目录不存在，直接创建
                    try:
                        self.file_service.create_folder(sub, final_cid)
                        time.sleep(DIR_CREATE_WAIT)
                        sub_id = self._quick_find_in_dir(final_cid, sub, is_dir=True)
                        if sub_id:
                            final_cid = sub_id
                    except Exception:
                        sub_id = self._quick_find_in_dir(final_cid, sub, is_dir=True)
                        if sub_id:
                            final_cid = sub_id

                # 如果有子目录（如 Season 01），需要把视频文件移进去
                if sub_dirs and final_cid != folder_id:
                    self._move_videos_to_subdir(folder_id, final_cid)

                # 遍历内部文件重命名（传入正确的标题和TMDB ID）
                rename_result = self._rename_files_in_folder(final_cid, target_title, str(tmdb_id))
                file_details = rename_result.get("files", [])
                # 收集文件夹整理的额外信息
                if file_details:
                    if not media_info:
                        media_info = {}
                    media_info["_file_count"] = len(file_details)
                    media_info["_file_size"] = format_size(rename_result.get("total_size", 0))
                    # 收集所有集数
                    episodes = [d["episode"] for d in file_details if d.get("episode")]
                    seasons = [d["season"] for d in file_details if d.get("season")]
                    if episodes:
                        media_info["_episode_range"] = (min(episodes), max(episodes))
                    if seasons:
                        media_info["season"] = seasons[0]
                    # 取最后一个文件的技术信息
                    if file_details[-1].get("tech_info"):
                        media_info["tech_info"] = file_details[-1]["tech_info"]
            else:
                # 文件模式：重命名文件
                if target_filename and target_filename != file_name:
                    moved_id = self._find_file_in_dir(target_cid, file_name)
                    if moved_id:
                        self.file_service.rename_file(str(moved_id), target_filename)
                        logger.info(f"重命名成功: {file_name} → {target_filename}")
                    else:
                        # 文件找不到 → 整理失败
                        self._submit_notify(
                            success=False, file_name=file_name,
                            title=target_title or file_name, category=category,
                            action=action, target_dir=full_dir,
                            media_info=media_info or {},
                        )
                        return {"success": False, "message": f"整理失败：复制后未找到文件 {file_name}，请稍后重试"}

            # 异步发送通知（不阻塞返回）
            # execute_organize 在线程池中执行，没有运行中的事件循环，
            # 必须用 run_coroutine_threadsafe 提交到主线程事件循环
            # 移动模式：清理原路径上的空文件夹（不删除「待整理」本身）
            cleaned_dirs = 0
            if organize_mode != "copy" and parent_for_cleanup:
                cleaned_dirs = self.cleanup_empty_ancestors(parent_for_cleanup)

            self._submit_notify(
                success=True, file_name=file_name,
                title=target_title or file_name, category=category,
                action=action, target_dir=full_dir,
                media_info=media_info or {},
            )

            details = {
                "action": action,
                "target_dir": full_dir,
                "target_filename": target_filename or file_name,
            }
            if cleaned_dirs:
                details["cleaned_empty_dirs"] = cleaned_dirs

            return {
                "success": True,
                "message": f"整理完成：已{action}到 {full_dir}",
                "details": details,
            }

        except Exception as e:
            logger.error(f"整理失败: {e}")
            self._submit_notify(
                success=False, file_name=file_name,
                title=target_title or file_name, category=category,
                action="", target_dir="",
                media_info=media_info or {},
            )
            return {"success": False, "message": f"整理失败: {str(e)}"}

    def cleanup_empty_ancestors(
        self,
        start_cid: str | int,
        stop_cid: Optional[str | int] = None,
    ) -> int:
        """从 start_cid 向上删除空祖先目录，直到 stop_cid（不含）或无法再删。

        规则：
        - 仅删除“当前完全为空”的目录（有 nfo/jpg/子项则停止）
        - 不删除 stop_cid 自身；stop 缺省取配置 source_cid（待整理）
        - 未提供 stop 时，最多只尝试删除 start 自身一层
        - 根目录 / 0 永不删除
        """
        try:
            cur = str(int(start_cid))
        except (TypeError, ValueError):
            return 0

        if stop_cid is None:
            stop_cid = (self.config_service.get("source_cid") or "").strip()
        try:
            stop_s = str(int(stop_cid)) if str(stop_cid).strip() not in ("", "None") else ""
        except (TypeError, ValueError):
            stop_s = str(stop_cid).strip() if stop_cid not in (None, "") else ""

        deleted = 0
        seen: set[str] = set()
        # 有 stop 时最多向上 32 层；无 stop 时只处理 start 自身
        max_steps = 32 if stop_s else 1
        # 115 移动后元数据偶发延迟，稍等再判断是否为空
        time.sleep(0.3)

        for _ in range(max_steps):
            if not cur or cur == "0" or cur in seen:
                break
            seen.add(cur)
            # 到达待整理（或指定 stop）本层即停止，不删该层
            if stop_s and cur == stop_s:
                break

            empty = False
            # 空目录判断失败时保守处理：不删
            for attempt in range(2):
                try:
                    empty = self.file_service.is_dir_empty(cur)
                except Exception as e:
                    logger.warning(f"检查空目录失败: cid={cur}, err={e}")
                    empty = False
                    break
                if empty:
                    break
                if attempt == 0:
                    time.sleep(0.5)
            if not empty:
                break

            parent = self.file_service.get_parent_id(cur)
            try:
                self.file_service.delete_files([cur])
                deleted += 1
                logger.info(f"删除空目录: cid={cur}")
            except Exception as e:
                logger.warning(f"删除空目录失败: cid={cur}, err={e}")
                break

            if not parent or parent == "0":
                break
            # 继续向上检查 parent（下一轮若等于 stop 会 break）
            cur = str(parent)

        if deleted:
            logger.info(f"空祖先目录清理完成: deleted={deleted}, stop_cid={stop_s or '-'}")
        return deleted

    def prune_empty_dirs_under(self, root_cid: str | int) -> int:
        """递归清理 root 下所有空目录，不删除 root 自身。

        用于批量云盘整理结束后做一次兜底清扫。
        """
        try:
            root = int(root_cid)
        except (TypeError, ValueError):
            return 0
        if root == 0:
            return 0

        deleted = 0

        def _walk(cid: int, is_root: bool) -> None:
            nonlocal deleted
            try:
                items = self.file_service.iter_all_files(cid)
            except Exception as e:
                logger.warning(f"遍历清理空目录失败: cid={cid}, err={e}")
                return

            for item in items:
                if not item.get("is_dir"):
                    continue
                try:
                    sub_id = int(item.get("file_id"))
                except (TypeError, ValueError):
                    continue
                _walk(sub_id, False)

            if is_root:
                return
            try:
                if self.file_service.is_dir_empty(cid):
                    self.file_service.delete_files([str(cid)])
                    deleted += 1
                    logger.info(f"兜底删除空目录: cid={cid}")
            except Exception as e:
                logger.warning(f"兜底删除空目录失败: cid={cid}, err={e}")

        _walk(root, True)
        if deleted:
            logger.info(f"批量空目录兜底清理完成: root={root}, deleted={deleted}")
        return deleted


    def _ensure_directory(self, dir_path: str) -> Optional[int]:
        """确保目录路径存在，使用 makedir 一次性创建多级目录

        替代逐级创建+sleep 的低效方式：
        - 旧：每级先查找→不存在则创建→sleep→再查找确认，3级目录至少1.5秒+6次API
        - 新：makedir(contain_dir=True) 一次调用创建整条路径，自带 Busy 重试

        Args:
            dir_path: 目录路径，如 "媒体库/电影/国产电影/四喜 (2025) {tmdb=273131}"

        Returns:
            最终目录的 cid，失败返回 None
        """
        parts = [p for p in dir_path.split('/') if p.strip()]
        # "根目录" 就是 cid=0，不应该创建这个文件夹
        while parts and parts[0] in ('根目录', '/', ''):
            parts.pop(0)

        if not parts:
            return 0

        clean_path = '/'.join(parts)
        try:
            cid = self.file_service.create_folder_path(clean_path, pid=0)
            logger.info(f"目录就绪: {clean_path} (cid={cid})")
            return cid
        except Exception as e:
            logger.error(f"创建目录失败: {clean_path}, {e}")
            return None

    def _list_all_files_paged(self, cid: int, page_size: int = 200) -> List[Dict]:
        """拉取目录下全部文件（自动分页，不丢数据）

        使用 file_service.iter_all_files（内部用 fs_files_iter），
        自动分页、自带 P115BusyOSError 重试，替代手动 limit+offset。

        Args:
            cid: 目录 ID
            page_size: 已废弃，保留参数兼容性

        Returns:
            全部文件列表
        """
        try:
            return self.file_service.iter_all_files(cid)
        except Exception as e:
            logger.warning(f"拉取目录文件失败: cid={cid}, {e}")
            return []

    def _recursive_list_video_names(self, cid, depth: int = 0, max_depth: int = 3) -> List[str]:
        """递归列出目录下所有视频文件名（用于识别阶段的嵌套文件夹）

        当前端只传了一层子目录名（如 ["Season 01"]）而没有视频文件名时，
        用此方法递归查找嵌套子目录中的视频文件，解决识别不完整的问题。

        Args:
            cid: 目录 ID（字符串或整数）
            depth: 当前递归深度
            max_depth: 最大递归深度（防止无限递归）

        Returns:
            视频文件名列表
        """
        if depth > max_depth or not cid:
            return []
        video_exts = get_video_extensions()
        video_names = []
        try:
            items = self.file_service.iter_all_files(int(cid))
        except Exception:
            return []
        for item in items:
            if item.get("is_dir"):
                # 递归子目录
                sub_names = self._recursive_list_video_names(item["file_id"], depth + 1, max_depth)
                video_names.extend(sub_names)
            else:
                name = item.get("name", "")
                ext = '.' + name.rsplit('.', 1)[-1].lower() if '.' in name else ''
                if ext in video_exts:
                    video_names.append(name)
        return video_names

    def _merge_folder_contents(self, src_cid: int, dst_cid: int):
        """将源文件夹的所有内容移动到目标文件夹（合并，不重命名）

        用于同一部剧不同规格版本复用同一文件夹的场景：
        整理第二个版本时，目标文件夹已存在，将新文件夹内容合并进去。

        Args:
            src_cid: 源文件夹 ID
            dst_cid: 目标文件夹 ID
        """
        try:
            items = self.file_service.iter_all_files(src_cid)
        except Exception as e:
            logger.warning(f"合并文件夹失败，无法列出源目录: {e}")
            return

        # 收集所有子项 ID（文件和子目录）
        all_ids = [str(item["file_id"]) for item in items]
        if all_ids:
            self.file_service.move_files(all_ids, str(dst_cid))
            logger.info(f"合并 {len(all_ids)} 个项目到已有文件夹")

    def _find_subdir(self, parent_cid: int, name: str) -> Optional[int]:
        """在父目录下查找指定名称的子目录（分页遍历）"""
        try:
            for item in self._list_all_files_paged(parent_cid):
                if item.get("is_dir") and item.get("name") == name:
                    return int(item["file_id"])
        except Exception as e:
            logger.warning(f"查找子目录失败: {parent_cid}/{name}, {e}")
        return None

    def _find_season_dir_variant(self, parent_cid: int, target_name: str) -> Optional[int]:
        """模糊匹配 Season 子目录变体

        目标名 "Season 01" 可匹配的变体：
        - Season 1, season 01, season 1, S01, s01
        避免原始文件夹已有 Season 子目录时创建多余空目录。

        Args:
            parent_cid: 父目录 ID
            target_name: 目标子目录名（如 "Season 01"）

        Returns:
            匹配到的子目录 ID，未匹配返回 None
        """
        # 从目标名提取季号，如 "Season 01" → 1
        season_match = re.search(r'[Ss]eason\s*(\d+)', target_name)
        if not season_match:
            return None
        season_num = int(season_match.group(1))

        # 生成所有可能变体
        variants = {
            f"Season {season_num:02d}",   # Season 01
            f"Season {season_num}",        # Season 1
            f"season {season_num:02d}",    # season 01
            f"season {season_num}",        # season 1
            f"S{season_num:02d}",          # S01
            f"s{season_num:02d}",          # s01
        }
        # 移除目标名自身（已精确匹配过）
        variants.discard(target_name)

        try:
            for item in self._list_all_files_paged(parent_cid):
                if item.get("is_dir") and item.get("name") in variants:
                    logger.info(f"找到 Season 变体: {item['name']} → {target_name}")
                    return int(item["file_id"])
        except Exception:
            pass
        return None

    def _quick_find_in_dir(self, dir_cid: int, name: str, is_dir: bool = False) -> Optional[int]:
        """在目录下快速查找指定名称的项（单次查找，不重试）

        适用于：检查子目录是否存在等场景，不需要等待 115 同步。
        对于复制/移动后需要等待同步的场景，请用 _find_file_in_dir（含重试）。

        Args:
            dir_cid: 目录 ID
            name: 文件/目录名
            is_dir: 是否只匹配目录
        """
        try:
            for item in self._list_all_files_paged(dir_cid):
                if is_dir and not item.get("is_dir"):
                    continue
                if item.get("name") == name:
                    return int(item["file_id"])
        except Exception:
            pass
        return None

    def _find_file_in_dir(self, dir_cid: int, name: str) -> Optional[int]:
        """在目录下查找指定名称的文件（分页遍历）

        Args:
            dir_cid: 目录 ID
            name: 文件名
        """
        try:
            for item in self._list_all_files_paged(dir_cid):
                if item.get("name") == name:
                    return int(item["file_id"])
        except Exception:
            pass
        return None

    def _move_videos_to_subdir(self, parent_cid: int, sub_cid: int):
        """把父目录下的视频文件移动到子目录中（分页遍历，支持大目录）"""
        video_exts = get_video_extensions()
        try:
            video_ids = []
            for item in self._list_all_files_paged(parent_cid):
                if item.get("is_dir"):
                    continue
                name = item.get("name", "")
                ext = '.' + name.rsplit('.', 1)[-1].lower() if '.' in name else ''
                if ext in video_exts:
                    video_ids.append(str(item["file_id"]))

            if video_ids:
                self.file_service.move_files(video_ids, str(sub_cid))
                logger.info(f"移动 {len(video_ids)} 个视频文件到子目录 (cid={sub_cid})")
        except Exception as e:
            logger.warning(f"移动视频文件到子目录失败: {e}")

    def _rename_files_in_folder(self, folder_cid: int, tmdb_title: str = "", tmdb_id: str = "") -> Dict[str, Any]:
        """遍历文件夹内的视频文件，批量按模板重命名

        优化策略：
        - 先遍历收集所有需要重命名的 (file_id, new_name) 对
        - 用 file_service.batch_rename 一次提交（内部用 update_name 批量处理）
        - 40集剧从40次API调用降到1次，自带 P115BusyOSError 自动重试

        Returns:
            {"files": [...], "total_size": int}
        """
        video_exts = get_video_extensions()
        # 季年份缓存：同一 TMDB ID + 同一季只调一次 TMDB API
        # key=(tmdb_id, season), value=season_year（如 "2026"）
        season_year_cache: Dict[tuple, str] = {}

        try:
            items = self.file_service.iter_all_files(folder_cid)
        except Exception as e:
            logger.warning(f"列出文件夹内容失败: {e}")
            return {"files": [], "total_size": 0}

        file_details = []
        total_size = 0
        rename_pairs = []  # 收集 (file_id, new_name) 用于批量重命名

        for item in items:
            if item.get("is_dir"):
                # 递归处理子文件夹（如 Season 01）
                sub_cid = int(item["file_id"])
                sub_result = self._rename_files_in_folder(sub_cid, tmdb_title, tmdb_id)
                file_details.extend(sub_result.get("files", []))
                total_size += sub_result.get("total_size", 0)
                continue

            filename = item.get("name", "")
            file_id = item.get("file_id", "")
            ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

            if ext not in video_exts:
                continue

            # 累加文件大小
            file_size = item.get("size", 0)
            if file_size:
                total_size += int(file_size)

            # 提取文件信息
            key_info = extract_key_info(filename)
            tech_info = extract_tech_info(filename)

            # 使用传入的 TMDB 标题（优先），否则用文件名解析的标题
            title = tmdb_title or key_info.get("title", "")
            use_tmdb_id = tmdb_id or str(key_info.get("tmdbId", ""))
            # 计算季年份（仅 TV）：填充 {{seasonYear}} 变量
            # 同一季复用缓存，避免批量重命名时反复调 TMDB API
            season_str = normalize_se_number(key_info.get("season"))
            season_year = ""
            if key_info["mediaType"] == "tv":
                season_year = self._get_season_year(use_tmdb_id, season_str, season_year_cache)

            # 生成目标文件名
            target = generate_target_path(
                media_type=key_info["mediaType"],
                title=title,
                year=key_info.get("year", ""),
                tmdb_id=use_tmdb_id,
                tech_info=tech_info,
                season_year=season_year,
                season=season_str,
                episode=normalize_se_number(key_info.get("episode")),
            )
            new_name = target.get("filename", "")

            # 收集文件详情
            file_details.append({
                "season": key_info.get("season"),
                "episode": key_info.get("episode"),
                "tech_info": tech_info,
            })

            # 收集需要重命名的条目，稍后批量提交
            if new_name and new_name != filename:
                rename_pairs.append((file_id, new_name))

        # 批量重命名：一次 API 请求处理所有文件
        if rename_pairs:
            try:
                self.file_service.batch_rename(rename_pairs)
                logger.info(f"批量重命名完成: {len(rename_pairs)} 个文件")
            except Exception as e:
                logger.warning(f"批量重命名失败，回退逐个重命名: {e}")
                # 回退：逐个重命名（兼容性保底）
                for file_id, new_name in rename_pairs:
                    try:
                        self.file_service.rename_file(str(file_id), new_name)
                    except Exception as re:
                        logger.warning(f"重命名文件失败: {new_name}, {re}")

        return {"files": file_details, "total_size": total_size}

    def _submit_notify(self, **notify_kwargs):
        """提交通知协程到事件循环（线程池安全）

        execute_organize 在线程池中执行，没有运行中的事件循环，
        直接用 asyncio.create_task 会报 RuntimeError。
        通过 run_coroutine_threadsafe 提交到主线程事件循环。
        """
        if getattr(self, "_suppress_notify", False):
            return
        coro = self._send_notify(**notify_kwargs)
        # 优先使用初始化时保存的主线程事件循环
        loop = self._main_loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, loop)
            return
        # 回退：尝试从当前线程获取
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(coro, loop)
            else:
                asyncio.ensure_future(coro)
        except RuntimeError:
            logger.warning("无法发送通知：无可用事件循环，通知已丢弃")

    async def _send_notify(self, success: bool, file_name: str,
                           title: str, category: str,
                           action: str, target_dir: str,
                           media_info: Optional[Dict[str, Any]] = None):
        """发送整理通知（使用公共格式化器构建消息）"""
        try:
            from ..notification import get_notification_manager
            from ..notification.format import format_organize_notify
            manager = get_notification_manager()

            # 用公共格式化器构建消息，消除与 share_organize_service 的重复代码
            # title 参数是目标媒体名（target_title），file_name 是原文件名
            status_title = "整理完成" if success else "整理失败"
            msg = format_organize_notify(
                success=success,
                title=status_title,
                target_title=title or file_name,
                file_name=file_name,
                category=category,
                media_info=media_info,
                action=action if success else None,
            )

            image_url = (media_info or {}).get("tmdb_backdrop") or (media_info or {}).get("tmdb_poster") or None
            await manager.send_all(msg, image_url)

        except Exception as e:
            logger.warning(f"发送通知失败: {e}")


# 全局单例
_organize_service: Optional[OrganizeService] = None


def get_organize_service() -> OrganizeService:
    """获取整理服务实例"""
    global _organize_service
    if _organize_service is None:
        _organize_service = OrganizeService()
    return _organize_service
