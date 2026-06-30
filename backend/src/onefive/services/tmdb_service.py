"""
TMDB 识别服务

职责：调用 TMDB API 搜索和获取媒体详情
配置：tmdb_api_key, tmdb_api_url, tmdb_language（存储在 setting 表）
"""
import re
from difflib import SequenceMatcher
from json import JSONDecodeError
from urllib.parse import urlparse

import requests
from typing import Optional, Dict, Any, List
from .config_service import get_config_service
from ..logger import get_logger

logger = get_logger(__name__)

DEFAULT_API_URL = "https://api.themoviedb.org/3"
DEFAULT_LANGUAGE = "zh-CN"
DEFAULT_API_KEY = "9cb87f133b1860fab0db5130aa4ab023"


class TMDBService:
    """TMDB 识别服务"""

    def __init__(self):
        self.config_service = get_config_service()

    @property
    def api_key(self) -> Optional[str]:
        """获取 API Key，优先使用设置中的，否则使用内置默认"""
        return self.config_service.get("tmdb_api_key") or DEFAULT_API_KEY

    @property
    def api_url(self) -> str:
        """获取 TMDB API 地址

        配置项支持两种写法：
        - https://api.themoviedb.org/3：完整 API 地址，保持原样
        - https://tmdb-proxy.example.com：代理基础域名，自动补 /3
        """
        custom_url = (self.config_service.get("tmdb_api_url") or "").strip()
        if not custom_url:
            return DEFAULT_API_URL

        normalized = custom_url.rstrip("/")
        parsed = urlparse(normalized)
        if not parsed.scheme or not parsed.netloc:
            logger.warning(f"TMDB 代理地址格式不正确，已回退默认地址: {custom_url}")
            return DEFAULT_API_URL
        if normalized.endswith("/3"):
            return normalized
        return f"{normalized}/3"

    @property
    def image_url(self) -> str:
        """获取 TMDB 图片地址

        未配置代理时使用官方图片域名；配置代理时使用同一代理基础域名拼接 /t/p。
        如果配置的是 https://proxy.example.com/3，会自动去掉 /3 后再拼图片路径。
        """
        custom_url = (self.config_service.get("tmdb_api_url") or "").strip()
        if not custom_url:
            return "https://image.tmdb.org/t/p"

        normalized = custom_url.rstrip("/")
        if normalized.endswith("/3"):
            normalized = normalized[:-2].rstrip("/")
        parsed = urlparse(normalized)
        if not parsed.scheme or not parsed.netloc:
            return "https://image.tmdb.org/t/p"
        return f"{normalized}/t/p"

    def build_image_url(self, path: str, size: str) -> Optional[str]:
        """生成图片地址，统一支持 TMDB 图片代理"""
        if not path:
            return None
        return f"{self.image_url}/{size}{path}"

    @property
    def language(self) -> str:
        return self.config_service.get("tmdb_language") or DEFAULT_LANGUAGE

    def is_configured(self) -> bool:
        """检查是否已配置 API Key"""
        return bool(self.api_key)

    def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """调用 TMDB API"""
        if not self.api_key:
            logger.warning("TMDB API Key 未配置")
            return None

        url = f"{self.api_url}{path}"
        p = {"api_key": self.api_key, "language": self.language}
        if params:
            p.update(params)

        try:
            resp = requests.get(url, params=p, timeout=15)
            if not resp.ok:
                text = (resp.text or "")[:200].replace("\n", " ")
                logger.warning(f"TMDB API 请求失败: {resp.status_code}, url={url}, body={text}")
                return None

            content_type = resp.headers.get("Content-Type", "")
            if "json" not in content_type.lower():
                text = (resp.text or "")[:200].replace("\n", " ")
                logger.error(f"TMDB API 返回非 JSON 内容，请检查代理地址是否正确: url={url}, content_type={content_type}, body={text}")
                return None

            try:
                return resp.json()
            except JSONDecodeError as e:
                text = (resp.text or "")[:200].replace("\n", " ")
                logger.error(f"TMDB API JSON 解析失败，请检查代理返回内容: {e}, url={url}, body={text}")
                return None
        except requests.RequestException as e:
            logger.error(f"TMDB API 请求异常: {e}")
            return None

    def search_media(self, query: str, media_type: str = "movie", year: Optional[str] = None) -> List[Dict]:
        """搜索电影/电视剧

        Args:
            query: 搜索关键词
            media_type: "movie" 或 "tv"
            year: 年份过滤

        Returns:
            搜索结果列表
        """
        path = f"/search/{media_type}"
        params: Dict[str, Any] = {"query": query}
        if year:
            if media_type == "movie":
                params["year"] = year
            else:
                params["first_air_date_year"] = year

        # 含中日韩文字时用中文搜索
        if any('\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff' for c in query):
            params["language"] = "zh-CN"
        else:
            params["language"] = self.language

        result = self._get(path, params)
        if result and "results" in result:
            return result["results"]
        return []

    def get_movie_details(self, tmdb_id: int) -> Optional[Dict]:
        """获取电影详情"""
        return self._get(f"/movie/{tmdb_id}", {"append_to_response": "credits,alternative_titles,translations"})

    def get_tv_details(self, tmdb_id: int) -> Optional[Dict]:
        """获取电视剧详情"""
        return self._get(f"/tv/{tmdb_id}", {"append_to_response": "credits,alternative_titles,translations"})

    def get_tv_season(self, tmdb_id: int, season: int) -> Optional[Dict]:
        """获取电视剧某季信息"""
        return self._get(f"/tv/{tmdb_id}/season/{season}")

    def get_chinese_title(self, details: Dict) -> str:
        """获取中文标题（优先级：zh-CN > 原标题 > zh-TW > zh-HK）"""
        # 先检查 translations - 只优先简体中文
        translations = details.get("translations", {}).get("translations", [])
        for t in translations:
            if t.get("iso_639_1") == "zh" and t.get("iso_3166_1") == "CN":
                data = t.get("data", {})
                title = data.get("title") or data.get("name")
                if title:
                    return title

        # 检查 alternative_titles - 只优先简体中文
        alt_titles = details.get("alternative_titles", {}).get("titles", [])
        for t in alt_titles:
            if t.get("iso_3166_1") == "CN" and t.get("title"):
                return t["title"]

        # 返回原标题（英文或其他语言）
        original_title = details.get("title") or details.get("name")
        if original_title:
            return original_title

        # 最后才考虑繁体中文（避免简体环境显示繁体）
        for t in translations:
            if t.get("iso_639_1") == "zh" and t.get("iso_3166_1") in ["TW", "HK"]:
                data = t.get("data", {})
                title = data.get("title") or data.get("name")
                if title:
                    return title

        for t in alt_titles:
            if t.get("iso_3166_1") in ["TW", "HK"] and t.get("title"):
                return t["title"]

        return ""

    def _get_result_year(self, result: Dict, media_type: str) -> str:
        """从搜索结果中提取年份"""
        date = result.get("release_date") if media_type == "movie" else result.get("first_air_date")
        return str(date or "")[:4]

    def _normalize_title(self, text: str) -> str:
        """标题归一化，用于相似度比较"""
        text = (text or "").lower()
        return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text)

    def _title_score(self, query: str, result: Dict) -> float:
        """标题匹配得分，兼顾标题和原始标题"""
        q = self._normalize_title(query)
        if not q:
            return 0

        titles = [
            result.get("title") or result.get("name") or "",
            result.get("original_title") or result.get("original_name") or "",
        ]
        best = 0.0
        for title in titles:
            t = self._normalize_title(title)
            if not t:
                continue
            if q == t:
                best = max(best, 100.0)
            elif q in t or t in q:
                best = max(best, 80.0)
            else:
                best = max(best, SequenceMatcher(None, q, t).ratio() * 70)
        return best

    def _get_result_details(self, result: Dict, media_type: str) -> Optional[Dict]:
        """根据搜索结果 ID 拉取完整详情"""
        tmdb_id = result.get("id")
        if not tmdb_id:
            return None
        if media_type == "movie":
            return self.get_movie_details(tmdb_id)
        return self.get_tv_details(tmdb_id)

    def _alias_score(self, details: Dict, query: str) -> float:
        """用中文译名、别名做额外加分"""
        q = self._normalize_title(query)
        if not q:
            return 0

        candidates = [
            details.get("title") or details.get("name") or "",
            details.get("original_title") or details.get("original_name") or "",
            self.get_chinese_title(details),
        ]

        for item in details.get("alternative_titles", {}).get("titles", []):
            if item.get("title"):
                candidates.append(item["title"])
        for item in details.get("translations", {}).get("translations", []):
            data = item.get("data", {})
            title = data.get("title") or data.get("name")
            if title:
                candidates.append(title)

        best = 0.0
        for title in candidates:
            t = self._normalize_title(title)
            if not t:
                continue
            if q == t:
                best = max(best, 100.0)
            elif q in t or t in q:
                best = max(best, 85.0)
            else:
                best = max(best, SequenceMatcher(None, q, t).ratio() * 60)
        return best

    def _pick_best_result(self, results: List[Dict], query: str,
                          media_type: str, year: Optional[str] = None) -> Optional[Dict]:
        """按标题相似度和年份选择最佳结果，不再盲目取第一个"""
        if not results:
            return None

        year = str(year or "")
        scored = []
        for index, result in enumerate(results):
            score = self._title_score(query, result)
            result_year = self._get_result_year(result, media_type)
            year_matched = bool(year and result_year == year)

            details = self._get_result_details(result, media_type)
            if details:
                score = max(score, self._alias_score(details, query))

            if year:
                # 有年份时，年份必须被强烈优先；年份不一致的同名结果降权，避免 Upstream 2024 命中其它年份/条目。
                score += 60 if year_matched else -80
            score += float(result.get("popularity") or 0) * 2
            score += max(0, 20 - index) * 0.1
            scored.append((score, year_matched, result))

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_year_matched, best = scored[0]
        best_title = best.get("title") or best.get("name") or ""
        best_year = self._get_result_year(best, media_type)

        if year and not best_year_matched:
            logger.warning(f"TMDB 搜索结果年份不匹配，已拒绝: query={query}, year={year}, best={best_title} ({best_year}), score={best_score:.1f}")
            return None
        if best_score < 45:
            logger.warning(f"TMDB 搜索结果标题匹配度过低，已拒绝: query={query}, best={best_title} ({best_year}), score={best_score:.1f}")
            return None

        best_popularity = float(best.get("popularity") or 0)
        logger.info(f"TMDB 最佳匹配: query={query}, year={year or '-'} -> {best_title} ({best_year}), popularity={best_popularity:.1f}, score={best_score:.1f}")
        return best

    def search_and_pick(self, query: str, media_type: str, year: Optional[str] = None) -> Optional[Dict]:
        """搜索并智能匹配最佳结果

        Returns:
            匹配的媒体详情，未匹配返回 None
        """
        results = self.search_media(query, media_type, year)
        if not results:
            return None

        best = self._pick_best_result(results, query, media_type, year)
        if not best:
            return None

        tmdb_id = best.get("id")
        if not tmdb_id:
            return None

        if media_type == "movie":
            return self.get_movie_details(tmdb_id)
        else:
            return self.get_tv_details(tmdb_id)


# 全局单例
_tmdb_service: Optional[TMDBService] = None


def get_tmdb_service() -> TMDBService:
    """获取 TMDB 服务实例"""
    global _tmdb_service
    if _tmdb_service is None:
        _tmdb_service = TMDBService()
    return _tmdb_service
