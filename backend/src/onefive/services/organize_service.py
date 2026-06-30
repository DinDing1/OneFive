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
import asyncio
from typing import Dict, Any, Optional, List
from .tmdb_service import get_tmdb_service
from .file_info_service import extract_key_info, extract_tech_info, VIDEO_EXTENSIONS
from .classify_service import classify_media
from .rename_service import generate_target_path
from .file_service import get_file_service
from .config_service import get_config_service
from ..logger import get_logger

logger = get_logger(__name__)


def _find_first_video_file(file_names: List[str]) -> Optional[str]:
    """在文件列表中找到第一个视频文件"""
    for name in file_names:
        ext = '.' + name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        if ext in VIDEO_EXTENSIONS:
            return name
    return None


def _has_season_pattern(file_names: List[str]) -> bool:
    """检查文件列表中是否有季集标识"""
    for name in file_names:
        if re.search(r'\bS\d{1,2}E\d{1,3}\b', name, re.IGNORECASE):
            return True
        if re.search(r'Season\s*\d{1,2}', name, re.IGNORECASE):
            return True
        if re.search(r'第\d+集', name):
            return True
    return False


class OrganizeService:
    """整理执行服务"""

    def __init__(self):
        self.tmdb_service = get_tmdb_service()
        self.file_service = get_file_service()
        self.config_service = get_config_service()

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
        if is_dir and folder_files:
            logger.info(f"识别文件夹: {filename}，内部文件数: {len(folder_files)}")
            return self._recognize_folder(file_info, filename, folder_files)

        # ==================== 单文件模式 ====================
        logger.info(f"识别文件: {filename}")
        key_info = extract_key_info(filename)
        tech_info = extract_tech_info(filename)

        tmdb_details, key_info = self._search_tmdb(key_info)

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

        # TMDB 搜索
        tmdb_details, key_info = self._search_tmdb(key_info)

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

        tmdb_details, key_info = self._search_tmdb(key_info)
        category = classify_media(tmdb_details, key_info["mediaType"]) if tmdb_details else ""
        target_path = self._generate_path(tmdb_details, key_info, tech_info, is_folder=is_dir) if tmdb_details else None
        return self._build_result(file_info, key_info, tech_info, tmdb_details, category, target_path)

    def _search_tmdb(self, key_info: Dict[str, Any]):
        """TMDB 搜索，返回 (tmdb_details, key_info)"""
        tmdb_details = None
        tmdb_id = key_info.get("tmdbId")
        title = key_info.get("title", "")
        media_type = key_info["mediaType"]

        if tmdb_id:
            logger.info(f"通过 TMDB ID 查询: {tmdb_id}，类型: {media_type}")
            if media_type == "movie":
                tmdb_details = self.tmdb_service.get_movie_details(tmdb_id)
                if not tmdb_details:
                    tmdb_details = self.tmdb_service.get_tv_details(tmdb_id)
                    if tmdb_details:
                        key_info["mediaType"] = "tv"
                        logger.info("电影查询无结果，切换为电视剧")
            else:
                tmdb_details = self.tmdb_service.get_tv_details(tmdb_id)
                if not tmdb_details:
                    tmdb_details = self.tmdb_service.get_movie_details(tmdb_id)
                    if tmdb_details:
                        key_info["mediaType"] = "movie"
                        logger.info("电视剧查询无结果，切换为电影")
        else:
            year = key_info.get("year")
            if title:
                logger.info(f"通过标题搜索: {title}，类型: {media_type}，年份: {year}")
                tmdb_details = self.tmdb_service.search_and_pick(
                    title, media_type, year
                )

        if tmdb_details:
            tmdb_title = tmdb_details.get("title") or tmdb_details.get("name")
            logger.info(f"TMDB 匹配成功: {tmdb_title} (ID={tmdb_details.get('id')})")
        else:
            logger.warning(f"TMDB 未匹配到结果: {title}")

        return tmdb_details, key_info

    def _generate_path(self, tmdb_details: Dict, key_info: Dict[str, Any],
                       tech_info: Dict[str, str],
                       is_folder: bool = False) -> Dict[str, str]:
        """生成目标路径

        文件夹+电视剧：只生成文件夹级路径（不含文件名）
        其他：生成完整文件路径
        """
        tmdb_id = tmdb_details.get("id", "")
        title = (self.tmdb_service.get_chinese_title(tmdb_details)
                 or tmdb_details.get("title")
                 or tmdb_details.get("name")
                 or key_info.get("title", ""))
        year = key_info.get("year", "")
        season_year = ""
        season = str(key_info.get("season", "")) if key_info.get("season") else ""
        episode = str(key_info.get("episode", "")) if key_info.get("episode") else ""

        # 获取季年份
        if key_info["mediaType"] == "tv" and season and tmdb_id:
            season_info = self.tmdb_service.get_tv_season(int(tmdb_id), int(season))
            if season_info:
                air_date = season_info.get("air_date", "")
                if air_date:
                    season_year = air_date[:4]

        # 文件夹+电视剧：只返回文件夹路径
        if is_folder and key_info["mediaType"] == "tv":
            dir_path = f"{title} ({year}) {{tmdb={tmdb_id}}}"
            if season:
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
        return {
            "file_id": file_info.get("file_id", ""),
            "filename": file_info.get("name", ""),
            "is_dir": file_info.get("is_dir", False),
            "media_type": key_info["mediaType"],
            "title": (tmdb_details.get("title") or tmdb_details.get("name")
                      or key_info.get("title", "")) if tmdb_details
                     else key_info.get("title", ""),
            "year": key_info.get("year"),
            "season": key_info.get("season"),
            "episode": key_info.get("episode"),
            "tmdb_id": tmdb_details.get("id") if tmdb_details else key_info.get("tmdbId"),
            "category": category,
            "tech_info": tech_info,
            "target_path": target_path,
            "tmdb_poster": self.tmdb_service.build_image_url(tmdb_details.get("poster_path", ""), "w500") if tmdb_details else None,
            "tmdb_backdrop": self.tmdb_service.build_image_url(tmdb_details.get("backdrop_path", ""), "w780") if tmdb_details else None,
            "tmdb_overview": tmdb_details.get("overview", "") if tmdb_details else "",
            "tmdb_rating": tmdb_details.get("vote_average", 0) if tmdb_details else 0,
        }

    def execute_organize(self, file_id: str, file_name: str,
                         is_dir: bool, target_path: Dict[str, str],
                         organize_mode: str = "move",
                         category: str = "",
                         target_title: str = "",
                         tmdb_id: int = 0,
                         media_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
            file_ids = [file_id]
            if organize_mode == "copy":
                self.file_service.copy_files(file_ids, str(target_cid))
                action = "复制"
            else:
                self.file_service.move_files(file_ids, str(target_cid))
                action = "移动"

            logger.info(f"{action}成功: {file_name} → {full_dir}")

            # 步骤3：重命名
            import time
            time.sleep(1)  # 等待 115 服务端同步

            if is_dir:
                # 文件夹模式：dir_path 可能包含子目录（如 "标题 (年份) {tmdb=ID}/Season 01"）
                # 拆分：第一部分是文件夹名，其余是子目录
                dir_parts = [p for p in dir_path.split('/') if p.strip()]
                folder_name = dir_parts[0] if dir_parts else dir_path
                sub_dirs = dir_parts[1:] if len(dir_parts) > 1 else []

                # 重命名文件夹
                folder_id = None
                if folder_name and folder_name != file_name:
                    moved_id = self._find_file_in_dir(target_cid, file_name)
                    if moved_id:
                        self.file_service.rename_file(str(moved_id), folder_name)
                        logger.info(f"重命名文件夹: {file_name} → {folder_name}")
                        folder_id = moved_id
                    else:
                        logger.warning(f"未找到已移动的文件夹: {file_name}")
                else:
                    folder_id = self._find_file_in_dir(target_cid, file_name)

                if folder_id:
                    # 创建子目录（如 Season 01）
                    final_cid = folder_id
                    for sub in sub_dirs:
                        sub_id = self._find_subdir(final_cid, sub)
                        if sub_id:
                            final_cid = sub_id
                        else:
                            try:
                                result = self.file_service.create_folder(sub, final_cid)
                                time.sleep(0.5)
                                sub_id = self._find_subdir(final_cid, sub)
                                if sub_id:
                                    final_cid = sub_id
                            except Exception:
                                sub_id = self._find_subdir(final_cid, sub)
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
                        media_info["_file_size"] = self._format_size(rename_result.get("total_size", 0))
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
                        logger.warning(f"未找到已移动的文件，跳过重命名: {file_name}")

            # 异步发送通知（不阻塞返回）
            asyncio.create_task(self._send_notify(
                success=True, file_name=file_name,
                title=target_title or file_name, category=category,
                action=action, target_dir=full_dir,
                media_info=media_info or {},
            ))

            return {
                "success": True,
                "message": f"整理完成：已{action}到 {full_dir}",
                "details": {
                    "action": action,
                    "target_dir": full_dir,
                    "target_filename": target_filename or file_name,
                }
            }

        except Exception as e:
            logger.error(f"整理失败: {e}")
            # 失败也发通知
            asyncio.create_task(self._send_notify(
                success=False, file_name=file_name,
                title=target_title or file_name, category=category,
                action="", target_dir="",
                media_info=media_info or {},
            ))
            return {"success": False, "message": f"整理失败: {str(e)}"}

    def _ensure_directory(self, dir_path: str) -> Optional[int]:
        """确保目录路径存在，逐级创建缺失的目录

        Args:
            dir_path: 目录路径，如 "媒体库/电影/国产电影/四喜 (2025) {tmdb=273131}"

        Returns:
            最终目录的 cid，失败返回 None
        """
        parts = [p for p in dir_path.split('/') if p.strip()]
        # "根目录" 就是 cid=0，不应该创建这个文件夹
        while parts and parts[0] in ('根目录', '/', ''):
            parts.pop(0)
        current_cid = 0

        for part in parts:
            # 先查找是否已存在
            found_cid = self._find_subdir(current_cid, part)
            if found_cid is not None:
                current_cid = found_cid
                logger.debug(f"目录已存在: {part} (cid={current_cid})")
                continue

            # 不存在则创建
            try:
                result = self.file_service.create_folder(part, current_cid)
                logger.info(f"创建目录: {part}，返回: {result}")
            except Exception as e:
                logger.warning(f"创建目录异常（可能已存在）: {part}, {e}")

            # 创建后再查找（无论 create_folder 返回什么）
            import time
            time.sleep(0.5)
            found_cid = self._find_subdir(current_cid, part)
            if found_cid is not None:
                current_cid = found_cid
                logger.info(f"确认目录: {part} (cid={current_cid})")
            else:
                logger.error(f"创建目录后未找到: {part}")
                return None

        return current_cid

    def _find_subdir(self, parent_cid: int, name: str) -> Optional[int]:
        """在父目录下查找指定名称的子目录"""
        try:
            result = self.file_service.list_files(parent_cid, limit=200)
            items = result.get("items", [])
            for item in items:
                if item.get("is_dir") and item.get("name") == name:
                    return int(item["file_id"])
            # 如果 200 条没找到，不继续翻页（避免性能问题）
        except Exception as e:
            logger.warning(f"查找子目录失败: {parent_cid}/{name}, {e}")
        return None

    def _find_file_in_dir(self, dir_cid: int, name: str) -> Optional[int]:
        """在目录下查找指定名称的文件"""
        try:
            result = self.file_service.list_files(dir_cid, limit=200)
            items = result.get("items", [])
            for item in items:
                if item.get("name") == name:
                    return int(item["file_id"])
        except Exception:
            pass
        return None

    def _move_videos_to_subdir(self, parent_cid: int, sub_cid: int):
        """把父目录下的视频文件移动到子目录中"""
        from .file_info_service import VIDEO_EXTENSIONS
        try:
            result = self.file_service.list_files(parent_cid, limit=200)
            items = result.get("items", [])
            video_ids = []
            for item in items:
                if item.get("is_dir"):
                    continue
                name = item.get("name", "")
                ext = '.' + name.rsplit('.', 1)[-1].lower() if '.' in name else ''
                if ext in VIDEO_EXTENSIONS:
                    video_ids.append(str(item["file_id"]))

            if video_ids:
                self.file_service.move_files(video_ids, str(sub_cid))
                logger.info(f"移动 {len(video_ids)} 个视频文件到子目录 (cid={sub_cid})")
        except Exception as e:
            logger.warning(f"移动视频文件到子目录失败: {e}")

    def _rename_files_in_folder(self, folder_cid: int, tmdb_title: str = "", tmdb_id: str = "") -> Dict[str, Any]:
        """遍历文件夹内的视频文件，逐个按模板重命名

        Returns:
            {"files": [...], "total_size": int}
        """
        from .file_info_service import extract_key_info, extract_tech_info, VIDEO_EXTENSIONS
        from .rename_service import generate_target_path

        try:
            result = self.file_service.list_files(folder_cid, limit=200)
            items = result.get("items", [])
        except Exception as e:
            logger.warning(f"列出文件夹内容失败: {e}")
            return []

        renamed_count = 0
        file_details = []
        total_size = 0

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

            if ext not in VIDEO_EXTENSIONS:
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

            # 生成目标文件名
            target = generate_target_path(
                media_type=key_info["mediaType"],
                title=title,
                year=key_info.get("year", ""),
                tmdb_id=use_tmdb_id,
                tech_info=tech_info,
                season=str(key_info.get("season", "")) if key_info.get("season") else "",
                episode=str(key_info.get("episode", "")) if key_info.get("episode") else "",
            )
            new_name = target.get("filename", "")

            # 收集文件详情
            file_details.append({
                "season": key_info.get("season"),
                "episode": key_info.get("episode"),
                "tech_info": tech_info,
            })

            if new_name and new_name != filename:
                try:
                    self.file_service.rename_file(str(file_id), new_name)
                    logger.info(f"重命名文件: {filename} → {new_name}")
                    renamed_count += 1
                except Exception as e:
                    logger.warning(f"重命名文件失败: {filename}, {e}")

        if renamed_count > 0:
            logger.info(f"文件夹内重命名完成: {renamed_count} 个文件")

        return {"files": file_details, "total_size": total_size}

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes <= 0:
            return ""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}" if unit != 'B' else f"{size_bytes} B"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"

    async def _send_notify(self, success: bool, file_name: str,
                           title: str, category: str,
                           action: str, target_dir: str,
                           media_info: Optional[Dict[str, Any]] = None):
        """发送整理通知"""
        try:
            from ..notification import get_notification_manager
            manager = get_notification_manager()

            if not media_info:
                media_info = {}

            if not success:
                msg = (
                    f"━━━━━━━━━━━━━━━━\n"
                    f"  ❌  整理失败\n"
                    f"━━━━━━━━━━━━━━━━\n\n"
                    f"  {title}\n"
                    f"  原文件：{file_name}"
                )
                await manager.send_all(msg)
                return

            media_type = media_info.get("media_type", "")
            year = media_info.get("year", "")
            season = media_info.get("season", 0)
            rating = media_info.get("tmdb_rating", 0)
            tech = media_info.get("tech_info", {})
            file_count = media_info.get("_file_count", 0)
            episode_range = media_info.get("_episode_range")
            release_group = tech.get("releaseGroup", "")
            file_size = media_info.get("_file_size", "")

            # 标题
            full_title = title
            if year:
                full_title += f" ({year})"

            type_label = "电影" if media_type == "movie" else "电视剧"

            msg = f"✅ <b>整理完成</b>\n\n"
            msg += f"🎬 <b>名称</b>：{full_title}\n\n"

            if rating:
                msg += f"⭐ <b>评分</b>：{rating:.1f}\n"

            if episode_range:
                s_str = str(season).zfill(2) if season else "01"
                e_min = str(episode_range[0]).zfill(2)
                e_max = str(episode_range[1]).zfill(2)
                ep_str = f"S{s_str}E{e_min}-E{e_max}" if episode_range[0] != episode_range[1] else f"S{s_str}E{e_min}"
                msg += f"📺 <b>集数</b>：{ep_str}\n"

            if category:
                msg += f"📁 <b>类别</b>：{category}\n"

            if release_group:
                msg += f"👥 <b>小组</b>：{release_group}\n"

            # 质量
            tech_parts = []
            if tech.get("videoFormat"):
                tech_parts.append(tech["videoFormat"])
            if tech.get("edition"):
                tech_parts.append(tech["edition"])
            if tech.get("videoCodec"):
                tech_parts.append(tech["videoCodec"])
            if tech.get("audioCodec"):
                tech_parts.append(tech["audioCodec"])
            if tech.get("webSource"):
                tech_parts.append(tech["webSource"])
            if tech_parts:
                msg += f"🎞️ <b>质量</b>：{' '.join(tech_parts)}\n"

            if file_size:
                msg += f"💾 <b>大小</b>：{file_size}\n"

            if file_count > 1:
                msg += f"📄 <b>文件数</b>：{file_count}\n"

            msg += f"📦 <b>整理方式</b>：{action}"

            image_url = media_info.get("tmdb_backdrop") or media_info.get("tmdb_poster") or None
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
