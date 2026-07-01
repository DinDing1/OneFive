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
import re
import asyncio
from typing import Dict, Any, Optional, List

from .share_service import get_share_service
from .file_info_service import extract_key_info, extract_tech_info, VIDEO_EXTENSIONS
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
        for f in files:
            if not f["is_dir"] and self._is_video_file(f["name"]):
                video_file = f
                break

        # 如果有视频文件，用视频文件名提取季集/技术信息，用目录 TMDB ID 锁定媒体信息
        if video_file:
            result = self._do_recognize(video_file["name"], tmdb_cache,
                                        forced_tmdb_id=folder_tmdb_id,
                                        forced_media_type=folder_media_type)
            data = self._build_recognize_result(dir_file_id, dir_name, result, True)
            data["total_files"] = len(files)
            return data
        else:
            # 没有视频文件，用目录名识别
            result = self._do_recognize(dir_name, tmdb_cache,
                                        forced_tmdb_id=folder_tmdb_id,
                                        forced_media_type=folder_media_type)
            data = self._build_recognize_result(dir_file_id, dir_name, result, True)
            data["total_files"] = len(files)
            return data

    def _is_video_file(self, filename: str) -> bool:
        """判断是否为视频文件（复用 file_info_service 的扩展名集合，保持一致）"""
        return any(filename.lower().endswith(ext) for ext in VIDEO_EXTENSIONS)

    # 季集标记正则：S01E01、第x集、EP01、E01 等（模块级常量，避免重复编译）
    # 第3条正则加前导边界，避免 MOVIE01、SAMPLE01、FILE01 等被误判为剧集标记
    _SEASON_EPISODE_PATTERNS = [
        re.compile(r'[Ss]\d{1,2}[Ee]\d{1,3}'),       # S01E01 / s1e1
        re.compile(r'第\s*\d+\s*集'),                   # 第1集 / 第 01 集
        re.compile(r'(?:^|[\s._\-])[Ee][Pp]?\.?\s*\d{1,3}'),  # EP01 / E01 / ep.1（需前导边界）
    ]

    def _has_season_episode_marker(self, filename: str) -> bool:
        """判断文件名是否包含季集标记（用于区分电视剧/电影）"""
        return any(p.search(filename) for p in self._SEASON_EPISODE_PATTERNS)

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

        # 规则1：任一文件名含季集标记 → tv
        for fname in video_names:
            if self._has_season_episode_marker(fname):
                return "tv"

        # 规则2：多个视频文件 → tv（多集剧集）
        if len(video_names) > 1:
            return "tv"

        # 规则3：单个视频文件，无季集标记 → movie
        return "movie"

    def organize_file(self, source_id: int, file_id: str) -> Dict[str, Any]:
        """整理单个分享文件（识别并写入数据库）

        如果是目录，递归整理内部所有文件。
        """
        share_service = get_share_service()
        tmdb_cache: Dict[tuple, Optional[Dict]] = {}

        file_info = share_service.get_file(source_id, file_id)
        if not file_info:
            return {"success": False, "error": "文件不存在"}

        # 目录：递归整理内部所有文件
        if file_info.get("is_dir"):
            return self._organize_directory(source_id, file_id, share_service, tmdb_cache)

        # 单文件：整理并发送通知
        result = self._organize_single_file(source_id, file_id, file_info["name"], share_service, tmdb_cache, file_info.get("size", 0))
        self._send_single_file_notify(file_info["name"], result)
        return result

    def _send_single_file_notify(self, file_name: str, result: Dict):
        """单文件整理完成后发送通知"""
        try:
            if not result.get("success"):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self._send_notify(
                            success=False, file_name=file_name, title=file_name,
                            category="", target_dir="",
                        ))
                except RuntimeError:
                    pass
                return

            # 成功：发送单文件通知
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._send_notify(
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
                            "_file_size": self._format_size(result.get("size", 0)),
                        }
                    ))
            except RuntimeError:
                pass
        except Exception as e:
            logger.warning(f"发送单文件整理通知失败: {e}")

    def _organize_directory(self, source_id: int, dir_file_id: str,
                           share_service, tmdb_cache: Dict,
                           inherited_tmdb_id: int = 0,
                           inherited_media_type: str = "",
                           send_notify: bool = True) -> Dict[str, Any]:
        """递归整理目录内的所有文件，并标记目录为已整理

        仅在最顶层目录整理完成后发送一条汇总通知（包含集数范围）。
        子目录递归时 send_notify=False，避免嵌套目录发送多条通知。
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

        results = []
        success_count = 0
        for f in files:
            f = dict(f)  # 转换 sqlite3.Row 为 dict
            fid = f["file_id"]
            fname = f["name"]
            if f["is_dir"]:
                sub = self._organize_directory(
                    source_id, fid, share_service, tmdb_cache,
                    inherited_tmdb_id=folder_tmdb_id,
                    inherited_media_type=folder_media_type,
                    send_notify=False
                )
                results.append(sub)
                # 目录整理成功时，按 1 个直接子项计入，避免“成功0、失败1”这种误导统计。
                if sub.get("success"):
                    success_count += 1
            else:
                result = self._organize_single_file(
                    source_id, fid, fname, share_service, tmdb_cache, f.get("size", 0),
                    forced_tmdb_id=folder_tmdb_id,
                    forced_media_type=folder_media_type
                )
                results.append(result)
                if result.get("success"):
                    success_count += 1

        # 标记当前目录为已整理
        share_service.db.execute(
            "UPDATE share_file SET organized = 1, updated_at = datetime('now', 'localtime') WHERE source_id = ? AND file_id = ?",
            (source_id, dir_file_id)
        )
        share_service.db.commit()

        # 仅在顶层目录发送一条汇总通知，子目录递归时不发通知
        if send_notify:
            self._send_directory_notify(dir_name, results, success_count)

        total = len(files)
        return {
            "success": True, "is_directory": True,
            "total": total,
            "organized_count": success_count,
            "failed_count": max(0, total - success_count),
            "direct_children": total,
            "results": results,
        }

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

    def _send_directory_notify(self, dir_name: str, results: list, success_count: int):
        """汇总目录整理结果，发送一条通知"""
        try:
            # 展平子目录嵌套结果，收集所有文件级成功结果
            flat_results = self._flatten_results(results)
            success_results = [r for r in flat_results if r.get("success")]

            if not success_results:
                # 全部失败
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self._send_notify(
                            success=False, file_name=dir_name, title=dir_name,
                            category="", target_dir="",
                        ))
                except RuntimeError:
                    pass
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

            # 格式化文件大小
            file_size_str = self._format_size(total_size) if total_size else ""

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._send_notify(
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
                    ))
            except RuntimeError:
                pass
        except Exception as e:
            logger.warning(f"发送目录整理通知失败: {e}")

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if not size_bytes:
            return ""
        size = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    # ==================== 核心识别逻辑（共享） ====================

    def _do_recognize(self, name: str, tmdb_cache: Dict,
                      forced_tmdb_id: int = 0,
                      forced_media_type: str = "") -> Dict[str, Any]:
        """核心识别逻辑：提取信息 → TMDB 搜索 → 分类 → 生成路径

        media_type 由 TMDB 返回结果判定（比文件名解析更准确）。
        forced_tmdb_id 用于目录整理：目录名已有明确 TMDB ID 时，强制用该 ID 查媒体，避免子文件名搜索错片。
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
        season = key_info.get("season", 0) or 0
        episode = key_info.get("episode", "")
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
            tmdb_details = self._search_tmdb(tmdb_id, title, search_media_type, year,
                                             strict_media_type=strict_media_type)
            tmdb_cache[cache_key] = tmdb_details

        # 3. 从 TMDB 结果提取信息，并以 TMDB 为准判定 media_type
        #    TMDB 的 /movie/{id} 和 /tv/{id} 端点不返回 media_type 字段，
        #    通过 release_date（电影）/ first_air_date（电视剧）判定类型
        poster = ""
        backdrop = ""
        rating = 0
        overview = ""
        media_type = ""
        if tmdb_details:
            tmdb_id = tmdb_details.get("id", tmdb_id)
            tmdb_title = tmdb_service.get_chinese_title(tmdb_details) or tmdb_details.get("title") or tmdb_details.get("name")
            if tmdb_title:
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

        # 4. 分类
        category = ""
        if media_type and tmdb_details:
            category = classify_media(tmdb_details, media_type)

        # 5. 生成整理后的目录路径和文件名
        organized_dir = ""
        organized_name = ""
        if media_type and title and tech_info:
            season_year = ""
            if media_type == "tv" and season and tmdb_id:
                try:
                    season_info = tmdb_service.get_tv_season(int(tmdb_id), int(season))
                    if season_info:
                        air_date = season_info.get("air_date", "")
                        if air_date:
                            season_year = air_date[:4]
                except Exception:
                    pass

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
            files = share_service.db.fetchall(
                "SELECT name, is_dir FROM share_file WHERE source_id = ? AND parent_id = ?",
                (source_id, file_id)
            )
            for f in files:
                if not f["is_dir"] and self._is_video_file(f["name"]):
                    name = f["name"]
                    break

        r = self._do_recognize(name, tmdb_cache, forced_tmdb_id=tmdb_id, forced_media_type=media_type)
        return self._build_recognize_result(file_id, file_info["name"], r, bool(file_info.get("is_dir")))

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

    def _build_recognize_result(self, file_id: str, filename: str,
                                r: Dict[str, Any], is_directory: bool = False) -> Dict[str, Any]:
        """把内部识别结果统一转成前端识别弹窗需要的数据"""
        return {
            "success": True,
            "is_directory": is_directory,
            "file_id": file_id,
            "filename": filename,
            "media_type": r["media_type"],
            "title": r["title"] or filename,
            "year": r["year"],
            "season": r["season"],
            "episode": r["episode"],
            "tmdb_id": r["tmdb_id"],
            "category": r["category"],
            "tech_info": r["tech_info"],
            "target_path": {"dir": r["organized_dir"], "filename": r["organized_name"]} if r["organized_dir"] else None,
            "tmdb_poster": r["poster"] or None,
            "tmdb_backdrop": r["backdrop"] or None,
            "tmdb_overview": r["overview"],
            "tmdb_rating": r["rating"],
        }

    # ==================== 识别（只读，不写入数据库） ====================

    def _recognize_single(self, source_id: int, file_id: str, name: str,
                          share_service, tmdb_cache: Dict) -> Dict[str, Any]:
        """识别单个文件（只读，不写入数据库）"""
        try:
            r = self._do_recognize(name, tmdb_cache)
            return {
                "success": True,
                "file_id": file_id,
                "filename": name,
                "media_type": r["media_type"],
                "title": r["title"] or name,
                "year": r["year"],
                "season": r["season"],
                "episode": r["episode"],
                "tmdb_id": r["tmdb_id"],
                "category": r["category"],
                "tech_info": r["tech_info"],
                "target_path": {"dir": r["organized_dir"], "filename": r["organized_name"]} if r["organized_dir"] else None,
                "tmdb_poster": r["poster"] or None,
                "tmdb_backdrop": r["backdrop"] or None,
                "tmdb_overview": r["overview"],
                "tmdb_rating": r["rating"],
            }
        except Exception as e:
            logger.error(f"分享文件识别失败 ({name}): {e}")
            return {"success": False, "error": str(e)}

    # ==================== 整理（识别 + 写入数据库） ====================

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
            r = self._do_recognize(
                name, tmdb_cache,
                forced_tmdb_id=forced_tmdb_id,
                forced_media_type=forced_media_type
            )

            # 校验：识别失败（media_type 或 organized_dir 为空）不标记为已整理
            if not r.get("media_type") or not r.get("organized_dir"):
                logger.warning(f"分享文件识别失败，跳过整理: {name}（media_type={r.get('media_type')}, organized_dir={r.get('organized_dir')}）")
                return {
                    "success": False, "file_id": file_id, "name": name,
                    "error": "识别失败：未找到 TMDB 信息",
                    "title": r.get("title", ""),
                    "media_type": r.get("media_type", ""),
                    "category": r.get("category", ""),
                    "season": r.get("season"), "episode": r.get("episode"),
                    "tmdb_id": r.get("tmdb_id", 0), "rating": r.get("rating", 0),
                    "tech_info": r.get("tech_info", {}),
                    "poster": r.get("poster", ""), "backdrop": r.get("backdrop", ""),
                    "overview": r.get("overview", ""), "size": file_size,
                }

            # 强制更新数据库（覆盖已整理的结果）
            share_service.update_file_organize(source_id, file_id, {
                "media_type": r["media_type"],
                "title": r["title"],
                "year": r["year"],
                "tmdb_id": r["tmdb_id"],
                "category": r["category"],
                "organized_dir": r["organized_dir"],
                "organized_name": r["organized_name"],
            })



            return {
                "success": True, "file_id": file_id, "name": name,
                "media_type": r["media_type"], "title": r["title"],
                "year": r["year"], "category": r["category"],
                "season": r["season"], "episode": r["episode"],
                "tmdb_id": r["tmdb_id"], "rating": r["rating"],
                "tech_info": r["tech_info"], "poster": r["poster"],
                "backdrop": r["backdrop"], "overview": r["overview"],
                "size": file_size,
            }
        except Exception as e:
            logger.error(f"分享文件整理失败 ({name}): {e}")
            return {"success": False, "error": str(e), "size": file_size}

    def _get_details_by_type(self, tmdb_service, tmdb_id: int,
                             media_type: str) -> Optional[Dict]:
        """按指定媒体类型查询 TMDB 详情（movie 或 tv）"""
        if media_type == "movie":
            return tmdb_service.get_movie_details(tmdb_id)
        return tmdb_service.get_tv_details(tmdb_id)

    def _matches_year(self, details: Optional[Dict], year: str) -> bool:
        """校验 TMDB 详情的年份是否与给定年份一致

        movie 取 release_date，tv 取 first_air_date，格式 YYYY-MM-DD。
        无年份输入或详情无日期字段时返回 False（无法验证）。
        """
        if not details or not year:
            return False
        release_date = details.get("release_date") or details.get("first_air_date") or ""
        return bool(release_date) and release_date[:4] == str(year)

    def _matches_title(self, details: Optional[Dict], title: str) -> bool:
        """校验 TMDB 详情的标题是否与给定标题匹配（考虑别名/译名）

        委托 tmdb_service.matches_title，匹配候选包括：
        原标题、原始标题、中文译名、alternative_titles、translations。
        """
        if not details or not title:
            return False
        tmdb_service = get_tmdb_service()
        return tmdb_service.matches_title(details, title)

    def _matches_details(self, details: Optional[Dict],
                         title: str, year: str) -> bool:
        """综合验证详情是否匹配标题和年份

        - 有年份时必须年份匹配
        - 有标题时必须标题匹配（考虑别名）
        - 都没有时视为匹配（无法验证）
        - 任一不匹配返回 False（tmdbid 可能写错，不采用该结果）
        """
        if not details:
            return False
        if year and not self._matches_year(details, year):
            return False
        if title and not self._matches_title(details, title):
            return False
        return True

    def _search_tmdb(self, tmdb_id: int, title: str,
                     media_type: str, year: str,
                     strict_media_type: bool = False) -> Optional[Dict]:
        """TMDB 搜索，返回详情字典或 None

        优先通过 tmdb_id 查询，否则通过标题搜索。

        名称+年份综合验证 + 智能回退策略：
        1. 主类型查到 + (名称和年份都匹配 或 无可验证) → 直接采用
        2. 主类型查到但验证不匹配 → 尝试另一类型（tmdbid 类型可能写错），
           另一类型验证通过则采用；否则回退标题+年份搜索；都失败返回 None
        3. 主类型查不到：严格模式不回退另一类型；非严格模式尝试另一类型；都允许同类型标题搜索兜底

        Args:
            strict_media_type: True 时主类型查不到不回退到另一类型（避免电影误判为电视剧）
        """
        tmdb_service = get_tmdb_service()

        if tmdb_id:
            # 1. 按指定类型查询主类型
            primary_details = self._get_details_by_type(tmdb_service, tmdb_id, media_type)

            # 2. 主类型查到 + 综合验证通过（名称和年份都匹配，或无可验证）→ 直接采用
            if self._matches_details(primary_details, title, year):
                return primary_details

            # 3. 主类型查到但验证不匹配：tmdbid 类型可能写错，尝试另一类型
            if primary_details:
                fallback_type = "tv" if media_type == "movie" else "movie"
                fallback_details = self._get_details_by_type(tmdb_service, tmdb_id, fallback_type)
                if self._matches_details(fallback_details, title, year):
                    return fallback_details
                # 另一类型也不匹配：tmdbid 可能是错的，回退到标题+年份搜索
                if title:
                    search_result = tmdb_service.search_and_pick(title, media_type, year)
                    if search_result:
                        return search_result
                # 搜索也失败：不采用名称/年份不符的 tmdbid 结果
                return None

            # 4. 主类型查不到：严格模式不回退到另一类型，非严格模式先尝试另一类型
            if not strict_media_type:
                fallback_type = "tv" if media_type == "movie" else "movie"
                fallback_details = self._get_details_by_type(tmdb_service, tmdb_id, fallback_type)
                if self._matches_details(fallback_details, title, year):
                    return fallback_details

            # 5. 严格模式主类型查不到，或非严格模式另一类型也失败：尝试同类型标题搜索兜底
            #    （严格模式不允许跨类型，但允许同类型标题搜索）
            if title:
                search_result = tmdb_service.search_and_pick(title, media_type, year)
                if search_result:
                    return search_result

            # 6. 所有回退都失败：返回 None（不采用名称/年份不符的结果）
            return None

        if title:
            # 通过标题搜索
            return tmdb_service.search_and_pick(title, media_type, year)

        return None

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

    # ==================== 通知 ====================

    async def _send_notify(self, success: bool, file_name: str,
                           title: str, category: str,
                           target_dir: str,
                           media_info: Optional[Dict[str, Any]] = None):
        """发送分享入库通知（参考 organize_service 模板，去掉整理方式）"""
        try:
            from ..notification import get_notification_manager
            manager = get_notification_manager()

            if not media_info:
                media_info = {}

            if not success:
                msg = (
                    f"━━━━━━━━━━━━━━━━\n"
                    f"  ❌  分享入库失败\n"
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

            msg = f"✅ <b>分享入库完成</b>\n\n"
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

            # 不发送整理方式（分享入库无需此字段）

            image_url = media_info.get("tmdb_backdrop") or media_info.get("tmdb_poster") or None
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
