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

import statistics
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set

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

COMPLETENESS_BONUS_MAX = 800

def _extract_season(*texts: str):
    """Extract season number from share/file names."""
    import re
    cn = "\u7b2c" + r"\s*([0-9]{1,2})\s*" + "\u5b63"
    cn_re = re.compile(cn)
    for text in texts:
        if not text:
            continue
        m = re.search(r"[Ss]eason[\s._-]*([0-9]{1,2})", text, re.I)
        if m:
            return int(m.group(1))
        m = re.search(r"(?<![A-Za-z0-9])S([0-9]{1,2})(?![0-9])", text, re.I)
        if m:
            return int(m.group(1))
        m = cn_re.search(text)
        if m:
            return int(m.group(1))
    return None

def _is_video_name(name: str) -> bool:
    lower = (name or "").lower()
    return any(lower.endswith(ext) for ext in VIDEO_EXTS)


class ShareWashService:
    """分享洗版：分析多版本分享并删除劣质分享链接。"""

    def __init__(self) -> None:
        self.db = get_db()

    def analyze(self, media_type: str = "all") -> Dict[str, Any]:
        files = self._load_organized_videos(media_type)
        if not files:
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

        source_meta = self._load_source_meta(list(by_source.keys()))
        source_items: List[Dict[str, Any]] = []
        for sid, rows in by_source.items():
            item = self._build_source_item(sid, rows, source_meta.get(sid) or {})
            if item:
                source_items.append(item)

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

        groups.sort(key=lambda g: (-(g["count"] - 1), g.get("title") or "", g.get("tmdb_id") or 0))
        deletable = sum(1 for g in groups for it in g["items"] if it.get("selected"))
        keep = sum(1 for g in groups for it in g["items"] if it.get("keep"))
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

    def delete_sources(self, source_ids: List[int]) -> Dict[str, Any]:
        ids: List[int] = []
        seen: Set[int] = set()
        for sid in source_ids or []:
            try:
                n = int(sid)
            except (TypeError, ValueError):
                continue
            if n > 0 and n not in seen:
                seen.add(n)
                ids.append(n)
        if not ids:
            return {"total": 0, "success": 0, "failed": 0, "source_ids": []}
        service = get_share_service()
        result = service.delete_shares_batch(ids)
        logger.info(
            f"[分享洗版] 删除分享链接 total={result.get('total')} "
            f"success={result.get('success')} failed={result.get('failed')} ids={ids}"
        )
        result["source_ids"] = ids
        return result

    def _load_organized_videos(self, media_type: str) -> List[Dict[str, Any]]:
        condition = (
            "f.is_dir = 0 AND f.organized = 1 AND f.tmdb_id > 0 "
            "AND IFNULL(f.media_type, '') IN ('movie', 'tv')"
        )
        params: List[Any] = []
        mt = (media_type or "all").strip().lower()
        if mt in ("movie", "tv"):
            condition += " AND f.media_type = ?"
            params.append(mt)
        rows = self.db.fetchall(
            f"""
            SELECT f.source_id, f.file_id, f.name, f.organized_name, f.size,
                   f.media_type, f.title, f.year, f.tmdb_id, f.category,
                   f.organized_dir, f.updated_at
            FROM share_file f
            WHERE {condition}
            ORDER BY f.source_id, f.id
            """,
            tuple(params),
        )
        result = []
        for r in rows:
            d = dict(r)
            name = d.get("organized_name") or d.get("name") or ""
            orig = d.get("name") or ""
            # ???????????/?????
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

        scores: List[int] = []
        tags_counter: Counter = Counter()
        release_group_counter: Counter = Counter()
        total_size = 0
        for r in rows:
            if int(r.get("tmdb_id") or 0) != tmdb_id:
                continue
            path = r.get("organized_name") or r.get("name") or ""
            odir = r.get("organized_dir") or ""
            full = f"{odir}/{path}" if odir else path
            size = int(r.get("size") or 0)
            total_size += size
            scores.append(calculate_quality_score(full, size))
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

        episode_count = len([r for r in rows if int(r.get("tmdb_id") or 0) == tmdb_id])
        release_group = release_group_counter.most_common(1)[0][0] if release_group_counter else ""
        # 标签优先展示发布组，再补画质相关标签
        top_tags: List[str] = []
        if release_group:
            top_tags.append(release_group)
        for t, _ in tags_counter.most_common(10):
            if t not in top_tags:
                top_tags.append(t)
            if len(top_tags) >= 8:
                break

        # 剧集：能解析到季号则按季分组，避免 S01/S02 被当成重复版本
        season = None
        if media_type == "tv":
            season_votes = []
            for r in rows:
                if int(r.get("tmdb_id") or 0) != tmdb_id:
                    continue
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
        else:
            group_key = f"{media_type}:{tmdb_id}"

        return {
            "source_id": source_id,
            "share_code": source.get("share_code") or "",
            "receive_code": source.get("receive_code") or "",
            "share_name": share_name,
            "share_url": source.get("share_url") or "",
            "link_valid": int(source.get("link_valid") if source.get("link_valid") is not None else 1),
            "file_count": int(source.get("file_count") or 0),
            "total_size": int(source.get("total_size") or total_size or 0),
            "updated_at": source.get("updated_at") or "",
            "created_at": source.get("created_at") or "",
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "title": title,
            "year": year,
            "group_key": group_key,
            "season": season,
            "episode_count": episode_count,
            "quality_score": quality_score,
            "score": quality_score,
            "tags": top_tags,
            "release_group": release_group,
            "multi_title": multi_title,
            "organized_video_count": episode_count,
            "sample_names": [
                (r.get("organized_name") or r.get("name") or "")[:120]
                for r in rows[:3]
                if int(r.get("tmdb_id") or 0) == tmdb_id
            ],
        }


_service: Optional[ShareWashService] = None


def get_share_wash_service() -> ShareWashService:
    global _service
    if _service is None:
        _service = ShareWashService()
    return _service
