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
from .file_info_service import build_search_queries
from ..logger import get_logger

logger = get_logger(__name__)

DEFAULT_API_URL = "https://api.themoviedb.org/3"
DEFAULT_LANGUAGE = "zh-CN"
DEFAULT_API_KEY = "9cb87f133b1860fab0db5130aa4ab023"

# ==================== 常量 ====================
# TMDB API 请求超时时间（秒）
API_TIMEOUT = 15
# 标题匹配阈值：分数达到此值才视为匹配（用于 matches_title 和 _pick_best_result）
MATCH_THRESHOLD = 45.0
# 精确匹配得分（标题或别名完全一致）
SCORE_EXACT_MATCH = 100.0
# 子串匹配得分（标题互为子串）
SCORE_TITLE_SUBSTRING = 80.0
SCORE_ALIAS_SUBSTRING = 85.0
# 模糊匹配乘数（SequenceMatcher 相似度 × 乘数）
SCORE_TITLE_FUZZY_RATIO = 70
SCORE_ALIAS_FUZZY_RATIO = 60
# 年份匹配加分 / 不匹配扣分（有年份输入时强烈优先同年）
YEAR_MATCH_BONUS = 60
YEAR_MISMATCH_PENALTY = -80
# 搜索结果热度权重乘数
POPULARITY_WEIGHT = 2
# 搜索结果位置权重：越靠前加分越多
POSITION_BONUS_MAX = 20
POSITION_BONUS_FACTOR = 0.1


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

        未配置代理或配置的是 TMDB 官方 API 地址时，使用官方图片域名 image.tmdb.org；
        配置了第三方代理时，使用同一代理基础域名拼接 /t/p。
        如果配置的是 https://proxy.example.com/3，会自动去掉 /3 后再拼图片路径。
        """
        custom_url = (self.config_service.get("tmdb_api_url") or "").strip()
        # 官方 API 地址不提供图片服务，必须走 image.tmdb.org
        if not custom_url or "api.themoviedb.org" in custom_url:
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

    def _get(self, path: str, params: Optional[Dict] = None, retries: int = 2) -> Optional[Dict]:
        """调用 TMDB API（网络抖动时自动重试）"""
        if not self.api_key:
            logger.warning("TMDB API Key 未配置")
            return None

        url = f"{self.api_url}{path}"
        p = {"api_key": self.api_key, "language": self.language}
        if params:
            p.update(params)

        last_error = None
        attempts = max(1, int(retries) + 1)
        for attempt in range(1, attempts + 1):
            try:
                resp = requests.get(url, params=p, timeout=API_TIMEOUT)
                if not resp.ok:
                    body = (resp.text or "")[:200].replace("\n", " ")
                    # 404 是试错流程的正常部分（先按 movie 查，404 再回退查 tv，反之亦然），
                    # 用 debug 避免每次带 tmdb_id 的识别都出警告；其他错误码才是真正问题
                    if resp.status_code == 404:
                        logger.debug(f"TMDB API 404（试错正常）: url={url}, body={body}")
                        return None
                    logger.warning(
                        f"TMDB API 请求失败: {resp.status_code}, url={url}, "
                        f"attempt={attempt}/{attempts}, body={body}"
                    )
                    # 5xx 可重试；其余错误码直接返回
                    if resp.status_code < 500 or attempt >= attempts:
                        return None
                    continue

                content_type = resp.headers.get("Content-Type", "")
                if "json" not in content_type.lower():
                    body = (resp.text or "")[:200].replace("\n", " ")
                    logger.error(
                        f"TMDB API 返回非 JSON 内容，请检查代理地址是否正确: "
                        f"url={url}, content_type={content_type}, body={body}"
                    )
                    return None

                try:
                    return resp.json()
                except JSONDecodeError as e:
                    body = (resp.text or "")[:200].replace("\n", " ")
                    logger.error(f"TMDB API JSON 解析失败，请检查代理返回内容: {e}, url={url}, body={body}")
                    return None
            except requests.RequestException as e:
                last_error = e
                if attempt >= attempts:
                    break
                logger.warning(
                    f"TMDB API 请求异常，准备重试 ({attempt}/{attempts}): {e}"
                )

        if last_error is not None:
            logger.error(f"TMDB API 请求异常: {last_error}")
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
        return self._get(f"/movie/{tmdb_id}",
                         {"append_to_response": "credits,alternative_titles,translations"})

    def get_tv_details(self, tmdb_id: int) -> Optional[Dict]:
        """获取电视剧详情"""
        return self._get(f"/tv/{tmdb_id}",
                         {"append_to_response": "credits,alternative_titles,translations"})

    def get_tv_season(self, tmdb_id: int, season: int) -> Optional[Dict]:
        """获取电视剧某季信息"""
        return self._get(f"/tv/{tmdb_id}/season/{season}")

    def get_simplified_chinese_title(self, details: Dict) -> str:
        """获取简体中文标题（仅 zh-CN translations 和 CN alternative_titles）

        找不到返回空字符串。用于在标题优先级中区分简体/繁体：
        简体中文优先于查询标题，查询标题（简体）优先于繁体中文。

        注意：CN 标记的别名可能是拼音（如"Hu die lou: Jing hun"），
        必须验证含中文字符才返回，避免拼音冒充中文。
        """
        # 1. 检查 translations - 简体中文（zh-CN）
        translations = details.get("translations", {}).get("translations", [])
        for t in translations:
            if t.get("iso_639_1") == "zh" and t.get("iso_3166_1") == "CN":
                data = t.get("data", {})
                title = data.get("title") or data.get("name")
                if title and self._contains_chinese(title):
                    return title

        # 2. 检查 alternative_titles - 简体中文（CN）
        alt_titles = details.get("alternative_titles", {}).get("titles", [])
        for t in alt_titles:
            if t.get("iso_3166_1") == "CN" and t.get("title"):
                title = t["title"]
                if self._contains_chinese(title):
                    return title

        return ""

    def get_chinese_title(self, details: Dict) -> str:
        """获取中文标题，尽可能返回中文名称

        优先级（高 → 低）：
        1. zh-CN translations（简体翻译，最准确）
        2. CN alternative_titles（简体别名）
        3. zh-TW/HK translations（繁体翻译，优于英文）
        4. zh-TW/HK alternative_titles（繁体别名）
        5. 遍历所有 alternative_titles/translations，找含中文字符的标题
           （兜底：部分中文别名国家标记非 CN/TW/HK，如 US）
        6. 原始标题（最后兜底，可能是英文）

        无任何可用标题时返回空字符串。
        """
        # 1-2. 先查简体中文
        simplified = self.get_simplified_chinese_title(details)
        if simplified:
            return simplified

        translations = details.get("translations", {}).get("translations", [])
        alt_titles = details.get("alternative_titles", {}).get("titles", [])

        # 3. 检查 translations - 繁体中文（zh-TW/HK，优于英文原始标题）
        for t in translations:
            if t.get("iso_639_1") == "zh" and t.get("iso_3166_1") in ["TW", "HK"]:
                data = t.get("data", {})
                title = data.get("title") or data.get("name")
                if title and self._contains_chinese(title):
                    return title

        # 4. 检查 alternative_titles - 繁体中文（TW/HK）
        for t in alt_titles:
            if t.get("iso_3166_1") in ["TW", "HK"] and t.get("title"):
                title = t["title"]
                if self._contains_chinese(title):
                    return title

        # 5. 优先使用搜索结果的标题
        #    搜索接口可能返回中文本地化标题（如"蝴蝶楼·惊魂"），
        #    但详情接口的 title 字段可能是拼音（如"Hu die lou: Jing hun"）。
        #    search_and_pick 会把搜索结果标题存到 _search_title 字段。
        search_title = details.get("_search_title") or ""
        if search_title and self._contains_chinese(search_title):
            return search_title

        # 6. 兜底：遍历所有别名/翻译，找含中文字符的标题
        #    部分中文别名的国家标记不是 CN/TW/HK（如 US），需要通过内容判断
        for t in alt_titles:
            title = t.get("title") or ""
            if title and self._contains_chinese(title):
                return title
        for t in translations:
            data = t.get("data", {})
            title = data.get("title") or data.get("name") or ""
            if title and self._contains_chinese(title):
                return title

        # 7. 最后兜底：返回原始标题（可能是英文）
        original_title = details.get("title") or details.get("name")
        if original_title:
            return original_title

        return ""

    def _contains_chinese(self, text: str) -> bool:
        """判断字符串是否包含中文字符"""
        return bool(re.search(r"[\u4e00-\u9fff]", text or ""))

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
                best = max(best, SCORE_EXACT_MATCH)
            elif q in t or t in q:
                best = max(best, SCORE_TITLE_SUBSTRING)
            else:
                best = max(best, SequenceMatcher(None, q, t).ratio() * SCORE_TITLE_FUZZY_RATIO)
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
                best = max(best, SCORE_EXACT_MATCH)
            elif q in t or t in q:
                best = max(best, SCORE_ALIAS_SUBSTRING)
            else:
                best = max(best, SequenceMatcher(None, q, t).ratio() * SCORE_ALIAS_FUZZY_RATIO)
        return best

    def matches_title(self, details: Dict, query: str,
                      threshold: float = MATCH_THRESHOLD) -> bool:
        """检查详情的标题（含别名/译名）是否与给定标题匹配

        复用 _alias_score 的匹配逻辑，分数达到阈值即视为匹配。
        匹配候选包括：标题、原始标题、中文译名、alternative_titles、translations。

        Args:
            details: TMDB 详情（需含 alternative_titles/translations 字段）
            query: 待匹配的标题（可能是中文译名、别名等）
            threshold: 匹配阈值，默认 MATCH_THRESHOLD（与 _pick_best_result 一致）
        """
        if not details or not query:
            return False
        return self._alias_score(details, query) >= threshold

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
                # 有年份时强烈优先同年结果；年份不一致的同名结果降权，避免如《Upstream》(2024) 被误命中为其它年份条目
                score += YEAR_MATCH_BONUS if year_matched else YEAR_MISMATCH_PENALTY
            score += float(result.get("popularity") or 0) * POPULARITY_WEIGHT
            score += max(0, POSITION_BONUS_MAX - index) * POSITION_BONUS_FACTOR
            scored.append((score, year_matched, result))

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_year_matched, best = scored[0]
        best_title = best.get("title") or best.get("name") or ""
        best_year = self._get_result_year(best, media_type)

        if year and not best_year_matched:
            logger.warning(
                f"TMDB 搜索结果年份不匹配，已拒绝: query={query}, year={year}, "
                f"best={best_title} ({best_year}), score={best_score:.1f}"
            )
            return None
        if best_score < MATCH_THRESHOLD:
            logger.warning(
                f"TMDB 搜索结果标题匹配度过低，已拒绝: query={query}, "
                f"best={best_title} ({best_year}), score={best_score:.1f}"
            )
            return None

        best_popularity = float(best.get("popularity") or 0)
        logger.info(
            f"TMDB 最佳匹配: query={query}, year={year or '-'} -> {best_title} ({best_year}), "
            f"popularity={best_popularity:.1f}, score={best_score:.1f}"
        )
        return best


    def _details_from_search_result(self, item: Dict, media_type: str) -> Optional[Dict]:
        """搜索命中但详情接口失败时，把 search 结果规整成 details 形状。

        足够支撑识别弹窗（id/title/poster/overview/rating/year）和基础分类。
        """
        if not item or not item.get("id"):
            return None
        details = dict(item)
        # 分类逻辑读 genres；搜索接口只有 genre_ids
        if not details.get("genres") and details.get("genre_ids"):
            details["genres"] = [{"id": gid} for gid in details.get("genre_ids") or []]
        # 确保类型判定字段存在
        if media_type == "tv":
            details.setdefault("first_air_date", item.get("first_air_date") or "")
            if item.get("name") and not details.get("name"):
                details["name"] = item.get("name")
        else:
            details.setdefault("release_date", item.get("release_date") or "")
            if item.get("title") and not details.get("title"):
                details["title"] = item.get("title")
        return details

    def search_and_pick(
        self,
        query: str,
        media_type: str,
        year: Optional[str] = None,
        fallback_query: str = "",
    ) -> Optional[Dict]:
        """搜索并智能匹配最佳结果（多 query 顺序尝试）。

        顺序：title+year → title → fallbackQuery → 中英拆分，命中即停。
        """
        if not media_type:
            media_type = "movie"

        candidates = build_search_queries(query, year, fallback_query)
        if not candidates and (query or "").strip():
            candidates = [((query or "").strip(), str(year).strip() if year else None)]

        for q, y in candidates:
            results = self.search_media(q, media_type, y)
            if not results:
                # 带年份无结果时，同 query 不带年份再试一次（若候选里还没有）
                if y:
                    results = self.search_media(q, media_type, None)
                    y_for_pick = None
                else:
                    continue
            else:
                y_for_pick = y

            if not results:
                continue

            best = self._pick_best_result(results, q, media_type, y_for_pick)
            if not best:
                # 带年份被年份硬拒时，再试无年份打分
                if y_for_pick:
                    best = self._pick_best_result(results, q, media_type, None)
            if not best:
                continue

            tmdb_id = best.get("id")
            if not tmdb_id:
                continue

            if media_type == "movie":
                details = self.get_movie_details(tmdb_id)
            else:
                details = self.get_tv_details(tmdb_id)

            # 详情接口偶发 SSL/网络失败时，用搜索结果兜底，避免"已匹配却无详情"导致前端空白
            if details is None:
                details = self._details_from_search_result(best, media_type)
                if details is not None:
                    logger.warning(
                        f"TMDB details 获取失败，使用搜索结果兜底: type={media_type}, id={tmdb_id}"
                    )

            if details is not None:
                # 搜索接口中文标题兜底
                if best.get("title"):
                    details["_search_title"] = best.get("title")
                elif best.get("name"):
                    details["_search_title"] = best.get("name")
                logger.info(
                    f"TMDB multi-query hit: q={q!r}, year={y_for_pick or '-'}, "
                    f"type={media_type}, id={tmdb_id}"
                )
                return details

        logger.warning(
            f"TMDB multi-query miss: title={query!r}, year={year or '-'}, "
            f"fallback={fallback_query!r}, type={media_type}, tried={len(candidates)}"
        )
        return None

    def search_with_validation(
        self,
        tmdb_id: int,
        title: str,
        media_type: str,
        year: str,
        strict_media_type: bool = False,
        fallback_query: str = "",
    ) -> tuple:
        """TMDB 搜索验证：优先 ID 查询，验证名称和年份，智能回退

        综合策略（合并自 share_organize_service 的搜索验证逻辑）：
        1. 有 tmdb_id 时，按指定类型查询 → 验证名称和年份
        2. 主类型查到 + 验证通过 → 直接采用
        3. 主类型查到但验证不匹配 → 尝试另一类型（tmdbid 类型可能写错），
           另一类型验证通过则采用；否则回退标题+年份搜索
        4. 主类型查不到：严格模式不回退另一类型；非严格模式先尝试另一类型
        5. 都允许同类型标题搜索兜底
        6. 无 tmdb_id 时，直接通过标题搜索

        Args:
            tmdb_id: TMDB ID，可能为 0 或 None
            title: 媒体标题
            media_type: 媒体类型 ("movie" 或 "tv")
            year: 年份字符串
            strict_media_type: True 时主类型查不到不回退到另一类型（避免电影误判为电视剧）
            fallback_query: 清洗后的兜底搜索串（多 query 链路使用）

        Returns:
            (details, resolved_media_type) 元组：
            - details: TMDB 详情字典，未匹配返回 None
            - resolved_media_type: 实际匹配的媒体类型，可能与输入不同（回退到另一类型时），
              未匹配返回 None
        """
        year = str(year or "")

        # ---- 内联年份验证 ----
        def _matches_year(details: Optional[Dict], y: str) -> bool:
            """校验 TMDB 详情的年份是否与给定年份一致

            movie 取 release_date，tv 取 first_air_date，格式 YYYY-MM-DD。
            无年份输入或详情无日期字段时返回 False（无法验证）。
            """
            if not details or not y:
                return False
            release_date = details.get("release_date") or details.get("first_air_date") or ""
            return bool(release_date) and release_date[:4] == str(y)

        # ---- 内联综合验证 ----
        def _matches_details(details: Optional[Dict], t: str, y: str) -> bool:
            """综合验证详情是否匹配标题和年份

            - 有年份时必须年份匹配
            - 有标题时必须标题匹配（考虑别名）
            - 都没有时视为匹配（无法验证）
            - 任一不匹配返回 False（tmdbid 可能写错，不采用该结果）
            """
            if not details:
                return False
            if y and not _matches_year(details, y):
                return False
            # 标题匹配委托给已有的 matches_title（内部使用 _alias_score，覆盖原标题、别名、译名）
            if t and not self.matches_title(details, t):
                return False
            return True

        # ---- 按 ID 查询主类型详情 ----
        if tmdb_id:
            # 1. 按指定类型查询主类型
            if media_type == "movie":
                primary_details = self.get_movie_details(tmdb_id)
            else:
                primary_details = self.get_tv_details(tmdb_id)

            # 2. 主类型查到 + 综合验证通过（名称和年份都匹配，或无可验证）→ 直接采用
            if _matches_details(primary_details, title, year):
                return primary_details, media_type

            # 3. 主类型查到但验证不匹配：tmdbid 类型可能写错，尝试另一类型
            if primary_details:
                fallback_type = "tv" if media_type == "movie" else "movie"
                if fallback_type == "movie":
                    fallback_details = self.get_movie_details(tmdb_id)
                else:
                    fallback_details = self.get_tv_details(tmdb_id)
                if _matches_details(fallback_details, title, year):
                    return fallback_details, fallback_type
                # 另一类型也不匹配：tmdbid 可能是错的，回退到标题+年份搜索
                if title:
                    search_result = self.search_and_pick(title, media_type, year, fallback_query=fallback_query)
                    if search_result:
                        return search_result, media_type
                # 搜索也失败：不采用名称/年份不符的 tmdbid 结果
                return None, None

            # 4. 主类型查不到：严格模式不回退到另一类型，非严格模式先尝试另一类型
            if not strict_media_type:
                fallback_type = "tv" if media_type == "movie" else "movie"
                if fallback_type == "movie":
                    fallback_details = self.get_movie_details(tmdb_id)
                else:
                    fallback_details = self.get_tv_details(tmdb_id)
                if _matches_details(fallback_details, title, year):
                    return fallback_details, fallback_type

            # 5. 严格模式主类型查不到，或非严格模式另一类型也失败：
            #    尝试同类型标题搜索兜底（严格模式不允许跨类型，但允许同类型标题搜索）
            if title:
                search_result = self.search_and_pick(title, media_type, year, fallback_query=fallback_query)
                if search_result:
                    return search_result, media_type

            # 6. 所有回退都失败：返回 None（不采用名称/年份不符的结果）
            return None, None

        # ---- 无 tmdb_id，通过标题多 query 搜索 ----
        if title or fallback_query:
            result = self.search_and_pick(
                title or fallback_query,
                media_type,
                year,
                fallback_query=fallback_query,
            )
            if result:
                return result, media_type
            return None, None

        return None, None


# 全局单例
_tmdb_service: Optional[TMDBService] = None


def get_tmdb_service() -> TMDBService:
    """获取 TMDB 服务实例"""
    global _tmdb_service
    if _tmdb_service is None:
        _tmdb_service = TMDBService()
    return _tmdb_service
