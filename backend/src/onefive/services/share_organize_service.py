"""
分享文件整理服务 - 对分享文件进行识别和分类

职责：
- 复用 file_info_service 提取文件信息
- 复用 classify_service 生成分类路径
- 复用 tmdb_service 搜索 TMDB
- recognize_file: 只识别不写入数据库（用于预览）
- organize_file: 识别并写入 share_file 表（不执行实际移动/复制）
- 整理完成后发送通知到 Bot 和用户机器人
"""
import asyncio
from typing import Dict, Any, Optional, List, Callable

from .share_service import get_share_service
from .file_info_service import (
    extract_key_info, extract_tech_info, get_video_extensions,
    has_season_episode_marker, format_size,
)
from .classify_service import classify_media
from .tmdb_service import get_tmdb_service
from .rename_service import generate_movie_path, generate_tv_path
from ..logger import get_logger

logger = get_logger(__name__)


class ShareOrganizeService:
    """分享文件整理服务

    优化策略：
    - TMDB 结果缓存：同标题的文件（如同一部剧的多集）只搜索一次 TMDB
    - 批量数据库更新：同一目录下的文件使用同一事务提交

    两种模式：
    - recognize_file: 只识别不写入数据库（用于前端预览确认）
    - organize_file: 识别并写入数据库（确认后执行）
    """

    # ==================== 只读识别 ====================

    def recognize_file(self, source_id: int, file_id: str) -> Dict[str, Any]:
        """识别单个分享文件（只读，不写入数据库）

        如果是目录，递归识别内部所有文件。
        """
        share_service = get_share_service()
        tmdb_cache: Dict[tuple, Optional[Dict]] = {}

        file_info = share_service.get_file(source_id, file_id)
        if not file_info:
            return {"success": False, "error": "文件不存在"}

        # 目录：递归识别内部所有文件
        if file_info.get("is_dir"):
            return self._recognize_directory(source_id, file_id, share_service, tmdb_cache)

        # 文件：直接识别
        return self._recognize_single(source_id, file_id, file_info["name"],
                                      share_service, tmdb_cache)

    def _recognize_single(self, source_id: int, file_id: str, name: str,
                          share_service, tmdb_cache: Dict) -> Dict[str, Any]:
        """识别单个文件（只读，不写入数据库）"""
        try:
            result, _ = self._do_recognize(name, tmdb_cache)
            return {
                "success": True,
                "file_id": file_id,
                "filename": name,
                "media_type": result["media_type"],
                "title": result["title"] or name,
                "year": result["year"],
                "season": result["season"],
                "episode": result["episode"],
                "tmdb_id": result["tmdb_id"],
                "category": result["category"],
                "tech_info": result["tech_info"],
                "target_path": {"dir": result["organized_dir"], "filename": result["organized_name"]} if result["organized_dir"] else None,
                "tmdb_poster": result["poster"] or None,
                "tmdb_backdrop": result["backdrop"] or None,
                "tmdb_overview": result["overview"],
                "tmdb_rating": result["rating"],
            }
        except Exception as e:
            logger.error(f"分享文件识别失败 ({name}): {e}")
            return {"success": False, "error": str(e)}

    def _recognize_directory(self, source_id: int, dir_file_id: str,
                            share_service, tmdb_cache: Dict) -> Dict[str, Any]:
        """递归识别目录内的所有文件

        对于目录，使用目录名+内部第一个视频文件提取信息（参考 organize_service 逻辑）
        """
        # 获取目录信息，并提前提取目录名中的 TMDB ID
        dir_info = share_service.get_file(source_id, dir_file_id)
        dir_name = dir_info.get("name", "") if dir_info else ""
        dir_key_info = extract_key_info(dir_name)
        folder_tmdb_id = dir_key_info.get("tmdbId", 0) or 0

        # 目录带 tmdbid 时，扫描目录内容推断媒体类型，避免 TMDB 同 ID
        # 在电影/电视剧两个空间都存在时默认按电影查询导致误判
        folder_media_type = ""
        if folder_tmdb_id:
            folder_media_type = self._infer_media_type_from_dir(source_id, dir_file_id, share_service)

        # 获取目录内所有文件
        files = share_service.db.fetchall(
            "SELECT file_id, name, is_dir FROM share_file WHERE source_id = ? AND parent_id = ?",
            (source_id, dir_file_id)
        )

        # 找到第一个视频文件
        video_file = None
        for file_row in files:
            if not file_row["is_dir"] and self._is_video_file(file_row["name"]):
                video_file = file_row
                break

        # 如果有视频文件，用视频文件名提取季集/技术信息，用目录 TMDB ID 锁定媒体信息
        if video_file:
            result, _ = self._do_recognize(video_file["name"], tmdb_cache,
                                        forced_tmdb_id=folder_tmdb_id,
                                        forced_media_type=folder_media_type)
            data = self._build_recognize_result(dir_file_id, dir_name, result, True)
            data["total_files"] = len(files)
            return data
        else:
            # 没有视频文件，用目录名识别
            result, _ = self._do_recognize(dir_name, tmdb_cache,
                                        forced_tmdb_id=folder_tmdb_id,
                                        forced_media_type=folder_media_type)
            data = self._build_recognize_result(dir_file_id, dir_name, result, True)
            data["total_files"] = len(files)
            return data

    def _is_video_file(self, filename: str) -> bool:
        """判断是否为视频文件（复用 file_info_service 的扩展名集合，保持一致）"""
        return any(filename.lower().endswith(ext) for ext in get_video_extensions())

    def _collect_video_names(self, source_id: int, dir_file_id: str,
                             share_service, limit: int = 50) -> List[str]:
        """递归收集目录下的视频文件名（广度优先，带数量上限提前终止）

        Args:
            limit: 最多收集的视频文件数，达到后立即停止扫描
        """
        result: List[str] = []
        queue = [dir_file_id]
        visited = set()

        while queue and len(result) < limit:
            current_id = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            rows = share_service.db.fetchall(
                "SELECT file_id, name, is_dir FROM share_file WHERE source_id = ? AND parent_id = ?",
                (source_id, current_id)
            )
            for r in rows:
                if r["is_dir"]:
                    queue.append(r["file_id"])
                elif self._is_video_file(r["name"]):
                    result.append(r["name"])
                    if len(result) >= limit:
                        break

        return result

    def _infer_media_type_from_dir(self, source_id: int, dir_file_id: str,
                                   share_service) -> str:
        """扫描目录内容推断媒体类型（电影/电视剧）

        推断规则（按优先级）：
        1. 任一视频文件名含季集标记（S01E01、第x集、EP01 等）→ tv
        2. 视频文件数量 > 1 → tv（多集剧集）
        3. 否则 → movie（单个视频文件，无季集标记）

        用于目录带 tmdbid 时，避免 TMDB 同一数字 ID 在电影/电视剧两个空间都存在
        导致默认按电影查询命中错误结果。

        安全性：即使推断错误，_search_tmdb 会先查推断类型，查不到再回退查另一类，
        不会导致查询失败。
        """
        video_names = self._collect_video_names(source_id, dir_file_id, share_service)

        if not video_names:
            return ""  # 无视频文件，无法推断，返回空让上层用默认逻辑

        # 规则1：任一文件名含季集标记 → tv（使用公共函数，保持与 organize_service 一致）
        for fname in video_names:
            if has_season_episode_marker(fname):
                return "tv"

        # 规则2：多个视频文件 → tv（多集剧集）
        if len(video_names) > 1:
            return "tv"

        # 规则3：单个视频文件，无季集标记 → movie
        return "movie"

    def manual_recognize_file(self, source_id: int, file_id: str,
                              tmdb_id: int, media_type: str) -> Dict[str, Any]:
        """手动纠错识别分享文件，只预览不写数据库"""
        share_service = get_share_service()
        tmdb_cache: Dict[tuple, Optional[Dict]] = {}
        file_info = share_service.get_file(source_id, file_id)
        if not file_info:
            return {"success": False, "error": "文件不存在"}

        name = file_info["name"]
        if file_info.get("is_dir"):
            # 复用 _collect_video_names 的递归逻辑，支持含季子目录（如 剧名/Season 01/第一集.mp4）的结构
            video_names = self._collect_video_names(source_id, file_id, share_service)
            if video_names:
                name = video_names[0]

        result, _ = self._do_recognize(name, tmdb_cache, forced_tmdb_id=tmdb_id, forced_media_type=media_type)
        return self._build_recognize_result(file_id, file_info["name"], result, bool(file_info.get("is_dir")))

    def _build_recognize_result(self, file_id: str, filename: str,
                                result: Dict[str, Any], is_directory: bool = False) -> Dict[str, Any]:
        """把内部识别结果统一转成前端识别弹窗需要的数据"""
        return {
            "success": True,
            "is_directory": is_directory,
            "file_id": file_id,
            "filename": filename,
            "media_type": result["media_type"],
            "title": result["title"] or filename,
            "year": result["year"],
            "season": result["season"],
            "episode": result["episode"],
            "tmdb_id": result["tmdb_id"],
            "category": result["category"],
            "tech_info": result["tech_info"],
            "target_path": {"dir": result["organized_dir"], "filename": result["organized_name"]} if result["organized_dir"] else None,
            "tmdb_poster": result["poster"] or None,
            "tmdb_backdrop": result["backdrop"] or None,
            "tmdb_overview": result["overview"],
            "tmdb_rating": result["rating"],
        }

    # ==================== 写入整理 ====================

    def organize_file(self, source_id: int, file_id: str,
                      progress_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                      loop: Optional[asyncio.AbstractEventLoop] = None) -> Dict[str, Any]:
        """整理单个分享文件（识别并写入数据库）

        如果是目录，递归整理内部所有文件。
        progress_cb 仅对目录有效：每整理完一个子文件时回调，用于流式进度推送。
        loop: 主线程事件循环。子线程（如 SSE 流式整理）中调用时传入，
              通知会通过 run_coroutine_threadsafe 提交到主循环；
              为 None 时回退到 get_event_loop（兼容主线程直接调用场景）。
        """
        share_service = get_share_service()
        tmdb_cache: Dict[tuple, Optional[Dict]] = {}

        file_info = share_service.get_file(source_id, file_id)
        if not file_info:
            return {"success": False, "error": "文件不存在"}

        # 目录：递归整理内部所有文件（可带进度回调）
        if file_info.get("is_dir"):
            return self._organize_directory(
                source_id, file_id, share_service, tmdb_cache,
                progress_cb=progress_cb, loop=loop
            )

        # 单文件：整理并发送通知
        result = self._organize_single_file(source_id, file_id, file_info["name"], share_service, tmdb_cache, file_info.get("size", 0))
        self._send_single_file_notify(file_info["name"], result, loop=loop)
        return result

    def _organize_directory(self, source_id: int, dir_file_id: str,
                           share_service, tmdb_cache: Dict,
                           inherited_tmdb_id: int = 0,
                           inherited_media_type: str = "",
                           send_notify: bool = True,
                           progress_cb: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                           loop: Optional[asyncio.AbstractEventLoop] = None,
                           is_root: bool = True) -> Dict[str, Any]:
        """递归整理目录内的所有文件，并标记目录为已整理

        仅在最顶层目录整理完成后发送一条汇总通知（包含集数范围）。
        子目录递归时 send_notify=False，避免嵌套目录发送多条通知。
        progress_cb：每整理完一个子文件（非子目录）时回调，用于流式进度推送。
        loop: 主线程事件循环，透传给 _send_directory_notify，支持子线程通知。
        is_root: 是否为最外层目录整理调用。True 时在标记目录 organized=1 后
            统一 commit；False（递归子目录）时不 commit，由根目录统一提交，
            避免嵌套目录每层都 commit 触发多次 fsync。
        """
        dir_info = share_service.get_file(source_id, dir_file_id)
        dir_name = dir_info.get("name", "") if dir_info else ""
        dir_key_info = extract_key_info(dir_name)
        folder_tmdb_id = dir_key_info.get("tmdbId", 0) or inherited_tmdb_id or 0
        folder_media_type = inherited_media_type or ""

        # 目录带 tmdbid（自身或继承）且无继承的 media_type 时，
        # 扫描目录内容推断媒体类型，避免 TMDB 同 ID 在电影/电视剧两个空间
        # 都存在时默认按电影查询导致电视剧被误判为电影
        if not folder_media_type and folder_tmdb_id:
            folder_media_type = self._infer_media_type_from_dir(source_id, dir_file_id, share_service)

        files = share_service.db.fetchall(
            "SELECT file_id, name, is_dir, size FROM share_file WHERE source_id = ? AND parent_id = ?",
            (source_id, dir_file_id)
        )

        logger.info(
            f"[目录整理开始] dir_file_id={dir_file_id}, dir_name={dir_name}, "
            f"direct_children={len(files)}, folder_tmdb_id={folder_tmdb_id}, "
            f"folder_media_type={folder_media_type!r}, send_notify={send_notify}"
        )

        results = []
        success_count = 0

        # 分离子目录和视频文件
        sub_dirs = []
        video_files = []
        for file_row in files:
            file_row = dict(file_row)
            if file_row["is_dir"]:
                sub_dirs.append(file_row)
            else:
                video_files.append(file_row)

        # 批量整理视频文件（同一部剧只查询一次 TMDB，优化整理速度）
        if video_files:
            batch_results = self._organize_batch_files(
                source_id, video_files, share_service, tmdb_cache,
                forced_tmdb_id=folder_tmdb_id,
                forced_media_type=folder_media_type,
                progress_cb=progress_cb
            )
            for result in batch_results:
                results.append(result)
                if result.get("success"):
                    success_count += 1
                else:
                    logger.warning(
                        f"[子文件失败] name={result.get('name')}, file_id={result.get('file_id')}, error={result.get('error')}"
                    )

        # 递归整理子目录
        for f in sub_dirs:
            fid = f["file_id"]
            fname = f["name"]
            sub = self._organize_directory(
                source_id, fid, share_service, tmdb_cache,
                inherited_tmdb_id=folder_tmdb_id,
                inherited_media_type=folder_media_type,
                send_notify=False,
                progress_cb=progress_cb,
                loop=loop,
                is_root=False,
            )
            results.append(sub)
            if sub.get("success"):
                success_count += 1
            logger.info(
                f"[子目录结果] name={fname}, success={sub.get('success')}, "
                f"total={sub.get('total')}, organized_count={sub.get('organized_count')}, "
                f"failed_count={sub.get('failed_count')}"
            )

        # 标记当前目录为已整理
        share_service.db.execute(
            "UPDATE share_file SET organized = 1, updated_at = datetime('now', 'localtime') WHERE source_id = ? AND file_id = ?",
            (source_id, dir_file_id)
        )
        # 只有根目录整理完才 commit，子目录递归时由根目录统一提交，避免每层 commit 触发多次 fsync
        if is_root:
            share_service.db.commit()

        total = len(files)
        logger.info(
            f"[目录整理完成] dir_name={dir_name}, total={total}, "
            f"success_count={success_count}, failed_count={max(0, total - success_count)}"
        )

        # 仅在顶层目录发送一条汇总通知，子目录递归时不发通知
        if send_notify:
            self._send_directory_notify(dir_name, results, success_count, loop=loop)

        return {
            "success": True, "is_directory": True,
            "total": total,
            "organized_count": success_count,
            "failed_count": max(0, total - success_count),
            "direct_children": total,
            "results": results,
        }

    def _organize_batch_files(self, source_id: int, files: list, share_service,
                              tmdb_cache: Dict, forced_tmdb_id: int = 0,
                              forced_media_type: str = "",
                              progress_cb: Optional[Callable] = None) -> list:
        """批量整理同目录下的视频文件（优化：同一部剧只查询一次 TMDB）

        核心优化逻辑：
        1. 第一个视频文件完整识别（_do_recognize），获取 TMDB 详情并缓存
        2. 后续文件复用缓存的 TMDB 详情，只重新提取季集+技术信息+生成路径
        3. season_year 也缓存，避免同一季每集都调 get_tv_season API

        相比逐个调用 _organize_single_file，40集剧从40次TMDB查询降到1次。
        """
        if not files:
            return []

        # 季年份缓存（tmdb_id, season → season_year）
        season_year_cache: Dict[tuple, str] = {}
        results = []
        # 已识别的 TMDB 详情（由第一个文件识别后填充，后续文件复用）
        cached_tmdb_details: Optional[Dict] = None
        cached_tmdb_cache_key = None

        for i, f in enumerate(files):
            fid = f["file_id"]
            fname = f["name"]
            file_size = f.get("size", 0)

            try:
                # 第一个文件：完整识别，获取 TMDB 详情
                # 后续文件：复用已缓存的 TMDB 详情，跳过搜索
                if i == 0 or cached_tmdb_details is None:
                    # 完整识别（会查询 TMDB，结果缓存到 tmdb_cache）
                    # 直接用 _do_recognize 返回的 cache_key 查找缓存，
                    # 避免在此处重新计算缓存键导致与 _do_recognize 内部不一致
                    r, cached_tmdb_cache_key = self._do_recognize(
                        fname, tmdb_cache,
                        forced_tmdb_id=forced_tmdb_id,
                        forced_media_type=forced_media_type,
                        season_year_cache=season_year_cache
                    )
                    # 缓存 TMDB 详情供后续文件复用
                    cached_tmdb_details = tmdb_cache.get(cached_tmdb_cache_key) if cached_tmdb_cache_key else None
                else:
                    # 复用 TMDB 详情：只提取季集+技术信息，跳过 TMDB 搜索
                    r = self._recognize_with_cached_tmdb(
                        fname, cached_tmdb_details, tmdb_cache,
                        forced_media_type=forced_media_type,
                        season_year_cache=season_year_cache
                    )

                # 校验：识别失败不标记为已整理
                if not r.get("media_type") or not r.get("organized_dir"):
                    logger.warning(
                        f"[整理失败] file_id={fid}, name={fname}, "
                        f"media_type={r.get('media_type')!r}, organized_dir={r.get('organized_dir')!r}"
                    )
                    result = {
                        "success": False, "file_id": fid, "name": fname,
                        "error": "识别失败：未找到 TMDB 信息",
                        "title": r.get("title", ""), "media_type": r.get("media_type", ""),
                        "category": r.get("category", ""), "season": r.get("season"),
                        "episode": r.get("episode"), "tmdb_id": r.get("tmdb_id", 0),
                        "rating": r.get("rating", 0), "tech_info": r.get("tech_info", {}),
                        "poster": r.get("poster", ""), "backdrop": r.get("backdrop", ""),
                        "overview": r.get("overview", ""), "size": file_size,
                    }
                    results.append(result)
                    if progress_cb:
                        progress_cb(fname, result)
                    continue

                # 写入数据库
                share_service.update_file_organize(source_id, fid, {
                    "media_type": r["media_type"],
                    "title": r["title"],
                    "year": r["year"],
                    "tmdb_id": r["tmdb_id"],
                    "category": r["category"],
                    "organized_dir": r["organized_dir"],
                    "organized_name": r["organized_name"],
                })

                logger.info(
                    f"[整理成功] file_id={fid}, name={fname}, "
                    f"media_type={r['media_type']}, title={r['title']}, "
                    f"tmdb_id={r['tmdb_id']}, organized_dir={r['organized_dir']}, "
                    f"organized_name={r['organized_name']}"
                )

                result = {
                    "success": True, "file_id": fid, "name": fname,
                    "media_type": r["media_type"], "title": r["title"],
                    "year": r["year"], "category": r["category"],
                    "season": r["season"], "episode": r["episode"],
                    "tmdb_id": r["tmdb_id"], "rating": r["rating"],
                    "tech_info": r["tech_info"], "poster": r["poster"],
                    "backdrop": r["backdrop"], "overview": r["overview"],
                    "size": file_size,
                }
                results.append(result)

            except Exception as e:
                logger.error(f"[整理异常] file_id={fid}, name={fname}, error={e}", exc_info=True)
                result = {"success": False, "error": str(e), "size": file_size, "name": fname, "file_id": fid}
                results.append(result)

            # 流式进度回调
            if progress_cb:
                progress_cb(fname, result)

        return results

    def _extract_tmdb_info(self, tmdb_details: Optional[Dict],
                           key_info: Dict, tech_info: Dict,
                           season_year_cache: Optional[Dict] = None) -> Dict[str, Any]:
        """从 TMDB 详情中提取媒体信息并生成整理路径

        合并了 _do_recognize 和 _recognize_with_cached_tmdb 中重复的
        TMDB 详情提取 + 季年缓存 + 路径生成逻辑。

        Args:
            tmdb_details: TMDB API 返回的详情字典，可能为 None
            key_info: extract_key_info 返回的基础信息
            tech_info: extract_tech_info 返回的技术信息
            season_year_cache: 季年缓存字典（批量整理时复用，避免重复 TMDB API 调用）

        Returns:
            包含 media_type, title, year, season, episode, tmdb_id, category,
            tech_info, organized_dir, organized_name, poster, backdrop, rating, overview 的字典
        """
        title = key_info.get("title", "")
        year = key_info.get("year", "")
        season = key_info.get("season", 0) or 0
        episode = key_info.get("episode", "")
        tmdb_id = key_info.get("tmdbId", 0)

        media_type = ""
        category = ""
        poster = ""
        backdrop = ""
        rating = 0
        overview = ""

        if tmdb_details:
            tmdb_service = get_tmdb_service()
            tmdb_id = tmdb_details.get("id", tmdb_id)
            # 标题优先级：TMDB简体中文 > 查询标题(中文) > TMDB繁体/英文
            # - TMDB 有简体：用 TMDB 简体（官方简体译名最准确）
            # - TMDB 无简体、查询标题是中文：保留查询标题（用户认可的简体名，优先于繁体）
            # - TMDB 无简体、查询标题非中文：用 get_chinese_title（返回繁体或英文）
            simplified = tmdb_service.get_simplified_chinese_title(tmdb_details)
            if simplified:
                title = simplified
            else:
                tmdb_title = tmdb_service.get_chinese_title(tmdb_details) or tmdb_details.get("title") or tmdb_details.get("name")
                if tmdb_title:
                    # 查询标题是中文时保留，避免繁体覆盖简体查询名
                    query_is_chinese = bool(title) and tmdb_service._contains_chinese(title)
                    if not query_is_chinese:
                        title = tmdb_title
            release_date = tmdb_details.get("release_date") or tmdb_details.get("first_air_date") or ""
            if release_date and len(release_date) >= 4:
                year = release_date[:4]
            poster_path = tmdb_details.get("poster_path", "")
            poster = tmdb_service.build_image_url(poster_path, "w500")
            backdrop_path = tmdb_details.get("backdrop_path", "")
            backdrop = tmdb_service.build_image_url(backdrop_path, "w780")
            rating = tmdb_details.get("vote_average", 0)
            overview = tmdb_details.get("overview", "")
            # 用 TMDB 结果判定 media_type：有 first_air_date 为 tv，有 release_date 为 movie
            if tmdb_details.get("first_air_date"):
                media_type = "tv"
            elif tmdb_details.get("release_date"):
                media_type = "movie"
            category = classify_media(tmdb_details, media_type)

        # 生成整理后的目录路径和文件名
        organized_dir = ""
        organized_name = ""
        if media_type and title and tech_info:
            season_year = ""
            if media_type == "tv" and season and tmdb_id:
                # 缓存 get_tv_season 结果，避免同一季每集都查询 TMDB API
                season_cache_key = (int(tmdb_id), int(season))
                if season_year_cache and season_cache_key in season_year_cache:
                    season_year = season_year_cache[season_cache_key]
                else:
                    try:
                        tmdb_service = get_tmdb_service()
                        season_info = tmdb_service.get_tv_season(int(tmdb_id), int(season))
                        if season_info:
                            air_date = season_info.get("air_date", "")
                            if air_date:
                                season_year = air_date[:4]
                    except Exception:
                        pass
                    # 缓存结果（即使为空也缓存，避免重复查询）
                    if season_year_cache is not None:
                        season_year_cache[season_cache_key] = season_year

            if media_type == "movie":
                path_info = generate_movie_path(title, year, str(tmdb_id), tech_info)
            else:
                path_info = generate_tv_path(title, year, str(tmdb_id), tech_info,
                                            season_year=season_year, season=str(season) if season else "",
                                            episode=str(episode) if episode else "")
            organized_dir = path_info.get("dir", "")
            organized_name = path_info.get("filename", "")

        return {
            "media_type": media_type,
            "title": title,
            "year": year,
            "season": season,
            "episode": episode,
            "tmdb_id": tmdb_id,
            "category": category,
            "tech_info": tech_info,
            "organized_dir": organized_dir,
            "organized_name": organized_name,
            "poster": poster,
            "backdrop": backdrop,
            "rating": rating,
            "overview": overview,
        }

    def _recognize_with_cached_tmdb(self, name: str, tmdb_details: Optional[Dict],
                                     tmdb_cache: Dict, forced_media_type: str = "",
                                     season_year_cache: Optional[Dict] = None) -> Dict[str, Any]:
        """用已缓存的 TMDB 详情识别文件（跳过 TMDB 搜索，只提取季集+技术信息+生成路径）

        用于同一目录下批量整理时，第二个及之后的文件复用第一个文件的 TMDB 结果。
        相比完整 _do_recognize，跳过了：TMDB 搜索、分类计算。
        """
        key_info = extract_key_info(name)
        tech_info = extract_tech_info(name)

        # 如果有强制媒体类型，覆盖 key_info 中的值
        forced_type = (forced_media_type or "").strip().lower()
        if forced_type in ("movie", "tv"):
            key_info["mediaType"] = forced_type

        return self._extract_tmdb_info(tmdb_details, key_info, tech_info, season_year_cache)

    def _organize_single_file(self, source_id: int, file_id: str, name: str,
                             share_service, tmdb_cache: Dict,
                             file_size: int = 0,
                             forced_tmdb_id: int = 0,
                             forced_media_type: str = "") -> Dict[str, Any]:
        """整理单个文件：调用 _do_recognize 识别，然后写入数据库（强制更新）

        不在此处发送通知，由上层 organize_file / _organize_directory 统一发送。
        识别失败（TMDB 无结果）时不写入数据库，返回失败。
        """
        try:
            result, _ = self._do_recognize(
                name, tmdb_cache,
                forced_tmdb_id=forced_tmdb_id,
                forced_media_type=forced_media_type
            )

            # 校验：识别失败（media_type 或 organized_dir 为空）不标记为已整理
            if not result.get("media_type") or not result.get("organized_dir"):
                # 详细记录各关键字段，便于定位识别失败的根本原因
                logger.warning(
                    f"[整理失败] file_id={file_id}, name={name}, "
                    f"forced_tmdb_id={forced_tmdb_id}, forced_media_type={forced_media_type}, "
                    f"识别结果: media_type={result.get('media_type')!r}, title={result.get('title')!r}, "
                    f"year={result.get('year')!r}, tmdb_id={result.get('tmdb_id')}, "
                    f"tech_info={result.get('tech_info')}, organized_dir={result.get('organized_dir')!r}, "
                    f"organized_name={result.get('organized_name')!r}, category={result.get('category')!r}"
                )
                return {
                    "success": False, "file_id": file_id, "name": name,
                    "error": "识别失败：未找到 TMDB 信息",
                    "title": result.get("title", ""),
                    "media_type": result.get("media_type", ""),
                    "category": result.get("category", ""),
                    "season": result.get("season"), "episode": result.get("episode"),
                    "tmdb_id": result.get("tmdb_id", 0), "rating": result.get("rating", 0),
                    "tech_info": result.get("tech_info", {}),
                    "poster": result.get("poster", ""), "backdrop": result.get("backdrop", ""),
                    "overview": result.get("overview", ""), "size": file_size,
                }

            # 强制更新数据库（覆盖已整理的结果）
            share_service.update_file_organize(source_id, file_id, {
                "media_type": result["media_type"],
                "title": result["title"],
                "year": result["year"],
                "tmdb_id": result["tmdb_id"],
                "category": result["category"],
                "organized_dir": result["organized_dir"],
                "organized_name": result["organized_name"],
            })

            logger.info(
                f"[整理成功] file_id={file_id}, name={name}, "
                f"media_type={result['media_type']}, title={result['title']}, "
                f"tmdb_id={result['tmdb_id']}, organized_dir={result['organized_dir']}, "
                f"organized_name={result['organized_name']}"
            )

            return {
                "success": True, "file_id": file_id, "name": name,
                "media_type": result["media_type"], "title": result["title"],
                "year": result["year"], "category": result["category"],
                "season": result["season"], "episode": result["episode"],
                "tmdb_id": result["tmdb_id"], "rating": result["rating"],
                "tech_info": result["tech_info"], "poster": result["poster"],
                "backdrop": result["backdrop"], "overview": result["overview"],
                "size": file_size,
            }
        except Exception as e:
            logger.error(f"[整理异常] file_id={file_id}, name={name}, error={e}", exc_info=True)
            return {"success": False, "error": str(e), "size": file_size, "name": name, "file_id": file_id}

    def _count_dir_files(self, source_id: int, dir_file_id: str, share_service) -> int:
        """统计目录下所有文件数（不含目录本身，含子目录内文件，单条 SQL）

        用于流式整理时计算真实进度总数，避免文件夹只算 1 导致进度永远卡在 1/1。

        优化：用 WITH RECURSIVE 一次查出所有后代文件数，避免递归 N+1 查询。
        """
        row = share_service.db.fetchone(
            """WITH RECURSIVE descendants(file_id) AS (
                   SELECT file_id FROM share_file
                   WHERE source_id = ? AND parent_id = ?
                   UNION ALL
                   SELECT f.file_id FROM share_file f
                   JOIN descendants d ON f.parent_id = d.file_id
                   WHERE f.source_id = ?
               )
               SELECT COUNT(*) as cnt FROM share_file
               WHERE file_id IN (SELECT file_id FROM descendants) AND is_dir = 0""",
            (source_id, dir_file_id, source_id)
        )
        return row["cnt"] if row else 0

    def manual_organize_file(self, source_id: int, file_id: str,
                             tmdb_id: int, media_type: str) -> Dict[str, Any]:
        """手动纠错整理分享文件，按用户指定 TMDB ID 覆盖旧整理结果"""
        share_service = get_share_service()
        tmdb_cache: Dict[tuple, Optional[Dict]] = {}
        file_info = share_service.get_file(source_id, file_id)
        if not file_info:
            return {"success": False, "error": "文件不存在"}

        if file_info.get("is_dir"):
            return self._organize_directory(
                source_id, file_id, share_service, tmdb_cache,
                inherited_tmdb_id=tmdb_id, inherited_media_type=media_type
            )

        result = self._organize_single_file(
            source_id, file_id, file_info["name"], share_service, tmdb_cache,
            file_info.get("size", 0), forced_tmdb_id=tmdb_id,
            forced_media_type=media_type
        )
        self._send_single_file_notify(file_info["name"], result)
        return result

    def organize_batch(self, source_id: int, file_ids: list) -> Dict:
        """批量整理分享文件"""
        results = []
        success_count = 0

        for file_id in file_ids:
            result = self.organize_file(source_id, file_id)
            results.append(result)
            if result.get("success"):
                success_count += 1

        return {
            "total": len(file_ids),
            "success": success_count,
            "failed": len(file_ids) - success_count,
            "results": results,
        }

    async def organize_batch_stream(self, source_id: int, file_ids: list):
        """流式批量整理分享文件（生成器模式，供 SSE 端点使用）

        每整理完一个文件，yield 一个进度事件 dict：
          {type: "progress", index, total, name, success, title, category, error}
        全部完成后，yield 一个完成事件 dict：
          {type: "done", total, success, failed}

        关键：文件夹会展开统计内部文件数作为进度总数，整理文件夹时
        每完成一个子文件就推送一次进度，避免"一部剧永远是 1/1"的问题。
        """
        share_service = get_share_service()

        # 预查文件信息 + 统计每个 file_id 的实际工作量（文件夹展开统计内部文件数）
        file_infos: Dict[str, Dict] = {}
        total = 0
        for fid in file_ids:
            info = share_service.get_file(source_id, fid)
            if not info:
                file_infos[fid] = {"name": fid, "is_dir": False}
                total += 1
                continue
            is_dir = bool(info.get("is_dir"))
            if is_dir:
                weight = self._count_dir_files(source_id, fid, share_service)
            else:
                weight = 1
            # 空目录至少算 1，避免 total 不增长
            weight = max(weight, 1)
            file_infos[fid] = {"name": info.get("name", fid), "is_dir": is_dir}
            total += weight

        # 用队列桥接同步回调与异步生成器：整理在线程执行，回调 put 进度，生成器 get 并 yield
        queue: asyncio.Queue = asyncio.Queue()
        counters = {"done": 0, "success": 0, "fail": 0}

        # 捕获主线程事件循环：整理在子线程执行，通知需要通过 run_coroutine_threadsafe 提交回主循环，
        # 否则子线程中 asyncio.get_event_loop() 会抛 RuntimeError，通知被 except 吞掉全部丢失
        main_loop = asyncio.get_running_loop()

        def push_progress(fname: str, result: Dict[str, Any]):
            """同步回调：单文件整理完成时入队一条进度事件"""
            counters["done"] += 1
            ok = bool(result.get("success"))
            if ok:
                counters["success"] += 1
            else:
                counters["fail"] += 1
            queue.put_nowait({
                "type": "progress",
                "index": counters["done"],
                "total": total,
                "name": fname,
                "success": ok,
                "title": result.get("title", ""),
                "category": result.get("category", ""),
                "error": result.get("error", ""),
            })

        async def run_organize():
            """在线程中逐个整理，文件夹内部进度通过回调实时入队"""
            try:
                for fid in file_ids:
                    info = file_infos[fid]
                    try:
                        if info["is_dir"]:
                            # 文件夹：传 progress_cb，内部每完成一个子文件就回调入队
                            # 传 main_loop 让子线程内通知能通过 run_coroutine_threadsafe 回主循环
                            await asyncio.to_thread(
                                self.organize_file, source_id, fid, push_progress, main_loop
                            )
                        else:
                            # 单文件：整理后手动推送一条进度
                            result = await asyncio.to_thread(
                                self.organize_file, source_id, fid, None, main_loop
                            )
                            push_progress(info["name"], result)
                    except Exception as e:
                        logger.error(f"[流式整理] 文件异常: {info['name']}, 错误: {e}")
                        push_progress(info["name"], {"success": False, "error": str(e)})
            finally:
                # 整理全部结束，入队完成事件
                queue.put_nowait({
                    "type": "done",
                    "total": total,
                    "success": counters["success"],
                    "failed": counters["fail"],
                })

        # 启动后台整理任务
        task = asyncio.create_task(run_organize())

        # 从队列读取进度并实时 yield，直到收到完成事件
        try:
            while True:
                item = await queue.get()
                yield item
                if item.get("type") == "done":
                    break
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    # ==================== TMDB 搜索 ====================

    def _do_recognize(self, name: str, tmdb_cache: Dict,
                      forced_tmdb_id: int = 0,
                      forced_media_type: str = "",
                      season_year_cache: Optional[Dict] = None) -> tuple[Dict[str, Any], tuple]:
        """执行单个文件的识别流程：提取信息 → TMDB 搜索 → 分类 → 生成路径

        media_type 由 TMDB 返回结果判定（比文件名解析更准确）。

        Args:
            forced_tmdb_id: 用户手动指定的 TMDB ID（优先级最高，跳过搜索）。用于目录整理：
                目录名已有明确 TMDB ID 时，强制用该 ID 查媒体，避免子文件名搜索错片
            forced_media_type: 用户手动指定的媒体类型（movie/tv）；非空时启用严格模式，
                按推断类型查询不回退到另一类型
            season_year_cache: 季-年份缓存字典（批量整理时复用，避免重复查询 TMDB）

        Returns:
            (result_dict, cache_key) 元组：
            - result_dict 含 title/year/mediaType/tmdbId 等字段
            - cache_key 为本次 TMDB 搜索用的缓存键，供批量整理复用 TMDB 详情时查找缓存，
              避免键计算不一致导致缓存 miss
        """
        # 0. 归一化 forced_media_type，防止上游传入 "Movie"/"tv " 等异常值
        forced_media_type = (forced_media_type or "").strip().lower()
        if forced_media_type not in ("movie", "tv"):
            forced_media_type = ""

        # 1. 从文件名提取基础信息
        key_info = extract_key_info(name)
        tech_info = extract_tech_info(name)

        # 用文件名解析的 media_type 作为 TMDB 搜索的 hint（不是最终值）
        search_media_type = forced_media_type or key_info.get("mediaType", "")
        title = key_info.get("title", "")
        year = key_info.get("year", "")
        tmdb_id = key_info.get("tmdbId", 0)
        if forced_tmdb_id:
            tmdb_id = forced_tmdb_id

        # 2. TMDB 搜索（带缓存）
        # forced_media_type 非空时启用严格模式：按推断类型查询，不回退到另一类型，
        # 避免 movie 端查不到时回退命中 tv 端同 ID 导致电影被误判为电视剧
        strict_media_type = bool(forced_media_type)
        tmdb_service = get_tmdb_service()
        cache_key = ("tmdb", tmdb_id, search_media_type, strict_media_type) if tmdb_id else (title, year, search_media_type)
        if cache_key in tmdb_cache:
            tmdb_details = tmdb_cache[cache_key]
        else:
            tmdb_details, _resolved_type = tmdb_service.search_with_validation(
                tmdb_id, title, search_media_type, year,
                strict_media_type=strict_media_type)
            tmdb_cache[cache_key] = tmdb_details

        # 3. 从 TMDB 结果提取信息并生成整理路径（委托给公共方法，消除与 _recognize_with_cached_tmdb 的重复）
        result = self._extract_tmdb_info(tmdb_details, key_info, tech_info, season_year_cache)

        # 识别结果详细日志，便于定位 organized_dir 为空等识别失败场景
        logger.info(
            f"[识别结果] name={name}, media_type={result['media_type']!r}, title={result['title']!r}, "
            f"year={result['year']!r}, tmdb_id={result['tmdb_id']}, season={result['season']}, episode={result['episode']}, "
            f"category={result['category']!r}, organized_dir={result['organized_dir']!r}, organized_name={result['organized_name']!r}, "
            f"tech_info_empty={not tech_info}, tmdb_details_found={bool(tmdb_details)}"
        )

        return {
            "media_type": result["media_type"],
            "title": result["title"],
            "year": result["year"],
            "season": result["season"],
            "episode": result["episode"],
            "tmdb_id": result["tmdb_id"],
            "category": result["category"],
            "tech_info": result["tech_info"],
            "organized_dir": result["organized_dir"],
            "organized_name": result["organized_name"],
            "poster": result["poster"],
            "backdrop": result["backdrop"],
            "rating": result["rating"],
            "overview": result["overview"],
        }, cache_key

    # ==================== 通知 ====================

    def _submit_notify(self, loop: Optional[asyncio.AbstractEventLoop], **notify_kwargs):
        """提交通知协程到事件循环（统一处理主线程/子线程两种场景）

        子线程场景（loop 不为 None）：用 run_coroutine_threadsafe 提交到主循环，
        避免子线程无事件循环导致通知被 except RuntimeError 吞掉。
        主线程场景（loop 为 None）：用 get_event_loop + create_task。
        两者都失败时静默忽略，不影响整理流程。
        """
        coro = self._send_notify(**notify_kwargs)
        if loop is not None:
            # 子线程场景：提交到主线程事件循环
            asyncio.run_coroutine_threadsafe(coro, loop)
            return
        # 主线程场景：需要运行中的事件循环
        try:
            cur_loop = asyncio.get_event_loop()
            if cur_loop.is_running():
                asyncio.create_task(coro)
        except RuntimeError:
            pass

    def _send_single_file_notify(self, file_name: str, result: Dict,
                                  loop: Optional[asyncio.AbstractEventLoop] = None):
        """单文件整理完成后发送通知"""
        try:
            if not result.get("success"):
                self._submit_notify(
                    loop,
                    success=False, file_name=file_name, title=file_name,
                    category="", target_dir="",
                )
                return

            # 成功：发送单文件通知
            self._submit_notify(
                loop,
                success=True,
                file_name=file_name,
                title=result.get("title") or file_name,
                category=result.get("category", ""),
                target_dir="",
                media_info={
                    "media_type": result.get("media_type", ""),
                    "year": result.get("year", ""),
                    "season": result.get("season", 0),
                    "tmdb_rating": result.get("rating", 0),
                    "tech_info": result.get("tech_info", {}),
                    "tmdb_poster": result.get("poster") or None,
                    "tmdb_backdrop": result.get("backdrop") or None,
                    "_file_count": 1,
                    "_file_size": format_size(result.get("size", 0)),
                }
            )
        except Exception as e:
            logger.warning(f"发送单文件整理通知失败: {e}")

    def _send_directory_notify(self, dir_name: str, results: list, success_count: int,
                                loop: Optional[asyncio.AbstractEventLoop] = None):
        """汇总目录整理结果，发送一条通知

        loop 不为 None 时（子线程场景）通过 _submit_notify 用 run_coroutine_threadsafe 提交，
        避免子线程无事件循环导致通知丢失。
        """
        try:
            # 展平子目录嵌套结果，收集所有文件级成功结果
            flat_results = self._flatten_results(results)
            success_results = [r for r in flat_results if r.get("success")]
            failed_results = [r for r in flat_results if not r.get("success")]

            # 详细记录展平后的统计，便于定位"0成功1失败"类问题
            logger.info(
                f"[通知统计] dir_name={dir_name}, 上层success_count={success_count}, "
                f"展平后: total={len(flat_results)}, success={len(success_results)}, failed={len(failed_results)}"
            )
            if failed_results:
                for r in failed_results:
                    logger.warning(
                        f"[通知失败项] name={r.get('name')}, file_id={r.get('file_id')}, "
                        f"error={r.get('error')}, media_type={r.get('media_type')!r}"
                    )

            if not success_results:
                # 全部失败
                self._submit_notify(
                    loop,
                    success=False, file_name=dir_name, title=dir_name,
                    category="", target_dir="",
                )
                return

            # 取第一个成功结果作为代表（同一目录下的文件信息应该一致）
            first = success_results[0]
            title = first.get("title", dir_name)
            category = first.get("category", "")
            media_type = first.get("media_type", "")
            year = first.get("year", "")
            tmdb_id = first.get("tmdb_id", 0)
            rating = first.get("rating", 0)
            tech_info = first.get("tech_info", {})
            poster = first.get("poster", "")
            backdrop = first.get("backdrop", "")

            # 计算集数范围
            episodes = []
            season = 0
            total_size = 0
            for r in success_results:
                ep = r.get("episode")
                s = r.get("season")
                if s:
                    season = s
                if ep:
                    try:
                        episodes.append(int(ep))
                    except (ValueError, TypeError):
                        pass
                # 累加文件大小
                try:
                    total_size += r.get("size", 0)
                except (ValueError, TypeError):
                    pass

            episode_range = None
            if episodes:
                episode_range = (min(episodes), max(episodes))

            # 格式化文件大小（使用公共 format_size，保持与 organize_service 一致）
            file_size_str = format_size(total_size) if total_size else ""

            self._submit_notify(
                loop,
                success=True,
                file_name=dir_name,
                title=title or dir_name,
                category=category,
                target_dir="",
                media_info={
                    "media_type": media_type,
                    "year": year,
                    "season": season,
                    "tmdb_rating": rating,
                    "tech_info": tech_info,
                    "tmdb_poster": poster or None,
                    "tmdb_backdrop": backdrop or None,
                    "_episode_range": episode_range,
                    "_file_count": len(success_results),
                    "_file_size": file_size_str,
                }
            )
        except Exception as e:
            logger.warning(f"发送目录整理通知失败: {e}")

    def _flatten_results(self, results: list) -> list:
        """将嵌套的子目录结果展平为扁平的文件结果列表

        子目录整理结果格式为 {"is_directory": True, "results": [...]}，
        展平后只保留文件级结果，便于顶层通知汇总所有文件的集数/大小等信息。
        """
        flat = []
        for r in results:
            if r.get("is_directory"):
                flat.extend(self._flatten_results(r.get("results", [])))
            else:
                flat.append(r)
        return flat

    async def _send_notify(self, success: bool, file_name: str,
                           title: str, category: str,
                           target_dir: str,
                           media_info: Optional[Dict[str, Any]] = None):
        """发送分享入库通知（使用公共格式化器构建消息，不含整理方式）

        Args:
            success: 是否成功
            file_name: 原始文件名/目录名
            title: 识别出的目标媒体名（TMDB 标题）
            category: 媒体类别
            target_dir: 目标目录（本方法未使用）
            media_info: 媒体信息字典
        """
        try:
            from ..notification import get_notification_manager
            from ..notification.format import format_organize_notify
            manager = get_notification_manager()

            # 用公共格式化器构建消息，不传 action 则不显示整理方式行
            # title 参数是目标媒体名（target_title），file_name 是原始文件名
            status_title = "分享入库完成" if success else "分享入库失败"
            msg = format_organize_notify(
                success=success,
                title=status_title,
                target_title=title or file_name,
                file_name=file_name,
                category=category,
                media_info=media_info,
            )

            image_url = (media_info or {}).get("tmdb_backdrop") or (media_info or {}).get("tmdb_poster") or None
            await manager.send_all(msg, image_url)

        except Exception as e:
            logger.warning(f"发送分享入库通知失败: {e}")


# 单例
_share_organize_service: Optional[ShareOrganizeService] = None


def get_share_organize_service() -> ShareOrganizeService:
    """获取分享整理服务实例"""
    global _share_organize_service
    if _share_organize_service is None:
        _share_organize_service = ShareOrganizeService()
    return _share_organize_service
