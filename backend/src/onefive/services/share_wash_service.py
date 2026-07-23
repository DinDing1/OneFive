"""
分享洗版服务

规则（产品确认）：
- 以 share_source（分享链接）为单位去重
- 仅「已完成识别整理」的视频参与：organized=1 AND tmdb_id>0 AND is_dir=0
- 电影：按 media_type + tmdb_id 分组
- 剧集：能解析到季号时按 tv+tmdb+Sxx；否则系列级整包比较
- 完整度开启：剧集按集数相对完整度加成
- 删除：删除整条分享链接（复用 delete_shares_batch）
"""
from __future__ import annotations

import re
import statistics
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ..db.database import get_db
from ..logger import get_logger
from .quality_score import (
    calculate_quality_score,
    extract_release_group,
    generate_video_tags,
    get_quality_level,
)
from .share_service import get_share_service

logger = get_logger(__name__)

VIDEO_EXTS = (
    ".mkv", ".mp4", ".ts", ".iso", ".avi", ".wmv", ".flv",
    ".m2ts", ".rmvb", ".mov", ".webm", ".mpg", ".mpeg",
)

# 每个分享源最多参与打分的视频数（取体积最大的若干个，足够反映画质）
MAX_SCORE_SAMPLES = 8

COMPLETENESS_BONUS_MAX = 800

_SEASON_CN_RE = re.compile("\u7b2c" + r"\s*([0-9]{1,2})\s*" + "\u5b63")
_SEASON_EN_RE = re.compile(r"[Ss]eason[\s._-]*([0-9]{1,2})", re.I)
_SEASON_S_RE = re.compile(r"(?<![A-Za-z0-9])S([0-9]{1,2})(?![0-9])", re.I)


def _extract_season(*texts: str):
    """Extract season number from share/file names."""
    for text in texts:
        if not text:
            continue
        m = _SEASON_EN_RE.search(text)
        if m:
            return int(m.group(1))
        m = _SEASON_S_RE.search(text)
        if m:
            return int(m.group(1))
        m = _SEASON_CN_RE.search(text)
        if m:
            return int(m.group(1))
    return None


def _is_video_name(name: str) -> bool:
    lower = (name or "").lower()
    return any(lower.endswith(ext) for ext in VIDEO_EXTS)


def _video_ext_sql(alias: str = "f") -> str:
    """SQL 片段：name 或 organized_name 以视频扩展名结尾。"""
    parts = []
    for ext in VIDEO_EXTS:
        # SQLite GLOB 大小写敏感，用 lower() + LIKE
        parts.append(f"lower(IFNULL({alias}.name, '')) LIKE '%{ext}'")
        parts.append(f"lower(IFNULL({alias}.organized_name, '')) LIKE '%{ext}'")
    return "(" + " OR ".join(parts) + ")"


class ShareWashService:
    """分享洗版：分析多版本分享并删除劣质分享链接。"""

    def __init__(self) -> None:
        self.db = get_db()

    def analyze(
        self,
        media_type: str = "all",
        progress: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """扫描已整理分享，找出同一作品的多条分享链接并按质量排序。

        progress: 可选回调 progress(event_dict)，用于 SSE 进度推送。
        """
        t0 = time.time()
        mt = (media_type or "all").strip().lower()

        def emit(stage: str, percent: int, message: str, **extra: Any) -> None:
            if not progress:
                return
            try:
                payload = {
                    "type": "progress",
                    "stage": stage,
                    "percent": max(0, min(100, int(percent))),
                    "message": message,
                }
                payload.update(extra)
                progress(payload)
            except Exception:
                pass

        emit("start", 1, "开始分析分享库…", media_type=mt)

        # 1) 先找出「同一 media_type + tmdb_id 下存在 ≥2 个分享源」的候选
        emit("scan", 8, "扫描已整理视频，查找多版本作品…")
        multi_keys = self._find_multi_source_keys(mt)
        if not multi_keys:
            elapsed = round(time.time() - t0, 2)
            org_cnt, src_cnt = self._count_organized(mt)
            logger.info(
                f"[分享洗版] 分析完成(无多版本候选) media_type={mt} "
                f"organized={org_cnt} sources={src_cnt} elapsed={elapsed}s"
            )
            emit("done_prep", 100, "未发现多版本重复", organized=org_cnt, sources=src_cnt)
            return {
                "summary": {
                    "organized_videos": org_cnt,
                    "sources_scanned": src_cnt,
                    "groups": 0,
                    "deletable_sources": 0,
                    "keep_sources": 0,
                },
                "groups": [],
            }

        emit(
            "load",
            20,
            f"发现 {len(multi_keys)} 部多版本作品，加载候选视频…",
            multi_works=len(multi_keys),
        )

        # 2) 仅加载这些多版本作品的视频行（大幅减少扫描量）
        files = self._load_videos_for_keys(multi_keys, mt)
        if not files:
            elapsed = round(time.time() - t0, 2)
            logger.info(f"[分享洗版] 分析完成(候选无视频) media_type={mt} elapsed={elapsed}s")
            emit("done_prep", 100, "候选作品无视频文件")
            return {
                "summary": {
                    "organized_videos": 0,
                    "sources_scanned": 0,
                    "groups": 0,
                    "deletable_sources": 0,
                    "keep_sources": 0,
                },
                "groups": [],
            }

        by_source: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for f in files:
            by_source[int(f["source_id"])].append(f)

        emit(
            "meta",
            35,
            f"加载 {len(by_source)} 条分享源元数据…",
            sources=len(by_source),
            videos=len(files),
        )
        source_meta = self._load_source_meta(list(by_source.keys()))

        source_items: List[Dict[str, Any]] = []
        source_ids = list(by_source.keys())
        total_src = max(len(source_ids), 1)
        for idx, sid in enumerate(source_ids):
            rows = by_source[sid]
            item = self._build_source_item(sid, rows, source_meta.get(sid) or {})
            if item:
                source_items.append(item)
            # 打分阶段进度 40% → 85%
            if progress and (idx % 5 == 0 or idx + 1 == total_src):
                pct = 40 + int(45 * (idx + 1) / total_src)
                emit(
                    "score",
                    pct,
                    f"评分与标签提取 {idx + 1}/{total_src}…",
                    current=idx + 1,
                    total=total_src,
                )

        groups_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in source_items:
            groups_map[item["group_key"]].append(item)

        groups: List[Dict[str, Any]] = []
        for key, items in groups_map.items():
            if len(items) < 2:
                continue
            max_eps = max(int(i.get("episode_count") or 0) for i in items) or 1
            for it in items:
                it["completeness_ratio"] = round(
                    (int(it.get("episode_count") or 0) / max_eps) if max_eps else 0.0,
                    4,
                )
                if it.get("media_type") == "tv":
                    bonus = int(round(it["completeness_ratio"] * COMPLETENESS_BONUS_MAX))
                else:
                    bonus = 0
                it["completeness_bonus"] = bonus
                it["score"] = int(it.get("quality_score") or 0) + bonus
                it["quality_level"] = get_quality_level(it["score"])

            items.sort(
                key=lambda x: (
                    -int(x.get("score") or 0),
                    -int(x.get("total_size") or 0),
                    str(x.get("updated_at") or ""),
                    -int(x.get("source_id") or 0),
                )
            )
            for idx, it in enumerate(items):
                it["keep"] = idx == 0
                it["selected"] = idx != 0

            head = items[0]
            groups.append({
                "key": key,
                "media_type": head.get("media_type") or "",
                "tmdb_id": head.get("tmdb_id") or 0,
                "title": head.get("title") or "",
                "year": head.get("year") or "",
                "season": head.get("season"),
                "count": len(items),
                "items": items,
            })

        emit("rank", 90, "排序并生成洗版建议…")
        groups.sort(key=lambda g: (-(g["count"] - 1), g.get("title") or "", g.get("tmdb_id") or 0))
        deletable = sum(1 for g in groups for it in g["items"] if not it.get("keep"))
        keep = sum(1 for g in groups for it in g["items"] if it.get("keep"))
        elapsed = round(time.time() - t0, 2)
        emit(
            "finish",
            99,
            f"分析完成：{len(groups)} 组重复，可删 {deletable} 条",
            groups=len(groups),
            deletable=deletable,
        )
        logger.info(
            f"[分享洗版] 分析完成 media_type={mt} videos={len(files)} "
            f"sources={len(by_source)} groups={len(groups)} "
            f"deletable={deletable} elapsed={elapsed}s"
        )
        return {
            "summary": {
                "organized_videos": len(files),
                "sources_scanned": len(by_source),
                "groups": len(groups),
                "deletable_sources": deletable,
                "keep_sources": keep,
            },
            "groups": groups,
        }

    def delete_sources(self, source_ids: Sequence[int]) -> Dict[str, Any]:
        ids = sorted({int(x) for x in source_ids if int(x) > 0})
        if not ids:
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "source_ids": [],
                "strm_deleted": 0,
                "strm_skipped": 0,
                "strm_errors": [],
                "strm_dirs_removed": 0,
                "strm_skip_reason": "",
            }
        share_service = get_share_service()
        result = share_service.delete_shares_batch(ids)
        logger.info(
            f"[分享洗版] 删除分享链接 total={result.get('total')} "
            f"success={result.get('success')} failed={result.get('failed')} "
            f"strm_deleted={result.get('strm_deleted', 0)} "
            f"strm_skipped={result.get('strm_skipped', 0)}"
        )
        return {
            "total": int(result.get("total") or 0),
            "success": int(result.get("success") or 0),
            "failed": int(result.get("failed") or 0),
            "source_ids": ids,
            "strm_deleted": int(result.get("strm_deleted") or 0),
            "strm_skipped": int(result.get("strm_skipped") or 0),
            "strm_errors": list(result.get("strm_errors") or []),
            "strm_dirs_removed": int(result.get("strm_dirs_removed") or 0),
            "strm_skip_reason": str(result.get("strm_skip_reason") or ""),
        }

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def _media_type_clause(self, media_type: str, alias: str = "f") -> Tuple[str, List[Any]]:
        mt = (media_type or "all").strip().lower()
        base = (
            f"{alias}.is_dir = 0 AND {alias}.organized = 1 AND {alias}.tmdb_id > 0 "
            f"AND IFNULL({alias}.media_type, '') IN ('movie', 'tv')"
        )
        params: List[Any] = []
        if mt in ("movie", "tv"):
            base += f" AND {alias}.media_type = ?"
            params.append(mt)
        return base, params

    def _count_organized(self, media_type: str) -> Tuple[int, int]:
        """统计已整理视频数与涉及的分享源数（用于无重复时的摘要）。"""
        condition, params = self._media_type_clause(media_type)
        row = self.db.fetchone(
            f"""
            SELECT COUNT(*) AS c,
                   COUNT(DISTINCT f.source_id) AS src
            FROM share_file f
            WHERE {condition}
              AND {_video_ext_sql('f')}
            """,
            tuple(params),
        )
        if not row:
            return 0, 0
        return int(row['c'] or 0), int(row['src'] or 0)

    def _find_multi_source_keys(self, media_type: str) -> List[Tuple[str, int]]:

        """找出同一 media_type+tmdb_id 下至少有 2 个 source 的作品键。"""
        condition, params = self._media_type_clause(media_type)
        rows = self.db.fetchall(
            f"""
            SELECT f.media_type AS media_type,
                   f.tmdb_id AS tmdb_id,
                   COUNT(DISTINCT f.source_id) AS src_cnt
            FROM share_file f
            WHERE {condition}
              AND {_video_ext_sql('f')}
            GROUP BY f.media_type, f.tmdb_id
            HAVING src_cnt >= 2
            """,
            tuple(params),
        )
        keys: List[Tuple[str, int]] = []
        for r in rows:
            mt = (r["media_type"] or "").strip()
            tid = int(r["tmdb_id"] or 0)
            if mt and tid > 0:
                keys.append((mt, tid))
        return keys

    def _load_videos_for_keys(
        self,
        keys: List[Tuple[str, int]],
        media_type: str,
    ) -> List[Dict[str, Any]]:
        """仅加载多版本候选作品的视频行。"""
        if not keys:
            return []
        condition, base_params = self._media_type_clause(media_type)
        result: List[Dict[str, Any]] = []
        # 分批 IN，避免 SQL 过长
        batch = 200
        for i in range(0, len(keys), batch):
            chunk = keys[i:i + batch]
            # (media_type = ? AND tmdb_id = ?) OR ...
            or_parts = []
            params: List[Any] = list(base_params)
            for mt, tid in chunk:
                or_parts.append("(f.media_type = ? AND f.tmdb_id = ?)")
                params.extend([mt, tid])
            rows = self.db.fetchall(
                f"""
                SELECT f.source_id, f.file_id, f.name, f.organized_name, f.size,
                       f.media_type, f.title, f.year, f.tmdb_id, f.category,
                       f.organized_dir, f.updated_at
                FROM share_file f
                WHERE {condition}
                  AND ({' OR '.join(or_parts)})
                  AND {_video_ext_sql('f')}
                ORDER BY f.source_id, f.size DESC
                """,
                tuple(params),
            )
            for r in rows:
                d = dict(r)
                name = d.get("organized_name") or d.get("name") or ""
                orig = d.get("name") or ""
                if not (_is_video_name(name) or _is_video_name(orig)):
                    continue
                result.append(d)
        return result

    def _load_source_meta(self, source_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if not source_ids:
            return {}
        meta: Dict[int, Dict[str, Any]] = {}
        batch = 400
        for i in range(0, len(source_ids), batch):
            chunk = source_ids[i:i + batch]
            placeholders = ",".join("?" * len(chunk))
            rows = self.db.fetchall(
                f"""
                SELECT id, share_code, receive_code, share_name, share_url,
                       file_count, total_size, status, link_valid, updated_at, created_at
                FROM share_source
                WHERE id IN ({placeholders})
                """,
                tuple(chunk),
            )
            for r in rows:
                d = dict(r)
                meta[int(d["id"])] = d
        return meta

    def _build_source_item(
        self,
        source_id: int,
        rows: List[Dict[str, Any]],
        source: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not rows:
            return None
        tmdb_counter = Counter(
            int(r.get("tmdb_id") or 0) for r in rows if int(r.get("tmdb_id") or 0) > 0
        )
        type_counter = Counter(
            (r.get("media_type") or "").strip()
            for r in rows
            if (r.get("media_type") or "").strip() in ("movie", "tv")
        )
        if not tmdb_counter:
            return None
        tmdb_id, _ = tmdb_counter.most_common(1)[0]
        media_type = type_counter.most_common(1)[0][0] if type_counter else "movie"
        multi_title = len(tmdb_counter) >= 2

        title = ""
        year = ""
        for r in rows:
            if int(r.get("tmdb_id") or 0) == tmdb_id:
                title = r.get("title") or title
                year = r.get("year") or year
                if title:
                    break

        # 仅对体积最大的若干文件打分，避免剧集上百集重复 regex
        matched = [r for r in rows if int(r.get("tmdb_id") or 0) == tmdb_id]
        matched.sort(key=lambda r: -int(r.get("size") or 0))
        score_rows = matched[:MAX_SCORE_SAMPLES]

        scores: List[int] = []
        tags_counter: Counter = Counter()
        release_group_counter: Counter = Counter()
        total_size = sum(int(r.get("size") or 0) for r in matched)

        for r in score_rows:
            path = r.get("organized_name") or r.get("name") or ""
            odir = r.get("organized_dir") or ""
            full = f"{odir}/{path}" if odir else path
            scores.append(calculate_quality_score(full, int(r.get("size") or 0)))
            for t in generate_video_tags(full):
                tags_counter[t] += 1
            rg = extract_release_group(full)
            if rg:
                release_group_counter[rg] += 1

        if not scores:
            return None
        quality_score = scores[0] if len(scores) == 1 else int(round(statistics.median(scores)))

        share_name = source.get("share_name") or ""
        if share_name:
            for t in generate_video_tags(share_name):
                tags_counter[t] += 1
            rg = extract_release_group(share_name)
            if rg:
                release_group_counter[rg] += 2  # 分享名权重略高
            # 分享名也参与打分中位数
            scores.append(calculate_quality_score(share_name, int(source.get("total_size") or total_size or 0)))
            quality_score = int(round(statistics.median(scores)))

        episode_count = len(matched)
        release_group = release_group_counter.most_common(1)[0][0] if release_group_counter else ""
        top_tags: List[str] = []
        if release_group:
            top_tags.append(release_group)
        for t, _ in tags_counter.most_common(10):
            if t not in top_tags:
                top_tags.append(t)
            if len(top_tags) >= 8:
                break

        season = None
        if media_type == "tv":
            season_votes = []
            for r in matched:
                season_votes.append(
                    _extract_season(
                        r.get("organized_name") or "",
                        r.get("organized_dir") or "",
                        r.get("name") or "",
                    )
                )
            season_votes = [x for x in season_votes if x is not None]
            if season_votes:
                season = Counter(season_votes).most_common(1)[0][0]
            else:
                season = _extract_season(share_name)

        if media_type == "tv" and season is not None:
            group_key = f"tv:{tmdb_id}:S{int(season):02d}"
        elif media_type == "tv":
            group_key = f"tv:{tmdb_id}"
        else:
            group_key = f"movie:{tmdb_id}"

        return {
            "source_id": source_id,
            "share_code": source.get("share_code") or "",
            "receive_code": source.get("receive_code") or "",
            "share_name": share_name,
            "share_url": source.get("share_url") or "",
            "link_valid": int(source.get("link_valid") if source.get("link_valid") is not None else 1),
            "file_count": int(source.get("file_count") or 0),
            "total_size": int(total_size or source.get("total_size") or 0),
            "updated_at": source.get("updated_at") or "",
            "created_at": source.get("created_at") or "",
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "title": title,
            "year": year or "",
            "season": season,
            "group_key": group_key,
            "episode_count": episode_count,
            "quality_score": quality_score,
            "score": quality_score,
            "tags": top_tags,
            "release_group": release_group,
            "multi_title": multi_title,
            "organized_video_count": episode_count,
            "sample_names": [
                (r.get("organized_name") or r.get("name") or "")
                for r in matched[:3]
            ],
            "keep": False,
            "selected": False,
        }


_service: Optional[ShareWashService] = None


def get_share_wash_service() -> ShareWashService:
    global _service
    if _service is None:
        _service = ShareWashService()
    return _service
