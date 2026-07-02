"""
分类服务

职责：根据 TMDB 媒体信息自动分类到对应目录
采用优先级匹配，先匹配的规则优先生效
"""
import json
from typing import Dict, Any, List, Optional
from .config_service import get_config_service
from ..logger import get_logger

logger = get_logger(__name__)

# ==================== 默认分类策略 ====================

DEFAULT_STRATEGY = {
    "movie": [
        {"category": "电影/动画电影", "conditions": {"genreIds": "16"}},
        {"category": "电影/国产电影", "conditions": {"originCountry": "CN,TW,HK"}},
        {"category": "电影/日韩电影", "conditions": {"originCountry": "JP,KP,KR"}},
        {"category": "电影/欧美电影", "conditions": {}},
    ],
    "tv": [
        {"category": "剧集/国产动漫", "conditions": {"genreIds": "16", "originCountry": "CN,TW,HK"}},
        {"category": "剧集/日本番剧", "conditions": {"genreIds": "16", "originCountry": "JP"}},
        {"category": "剧集/欧美动漫", "conditions": {"genreIds": "16", "originCountry": "US,FR,GB,DE,ES,IT,NL,PT,RU,UK"}},
        {"category": "其他/纪录片", "conditions": {"genreIds": "99"}},
        {"category": "其他/综艺", "conditions": {"genreIds": "10764,10767"}},
        {"category": "剧集/儿童", "conditions": {"genreIds": "10762"}},
        {"category": "剧集/国产剧", "conditions": {"originCountry": "CN,TW,HK"}},
        {"category": "剧集/日韩剧", "conditions": {"originCountry": "JP,KP,KR,TH,IN,SG"}},
        {"category": "剧集/欧美剧", "conditions": {}},
    ],
}


def _parse_genre_ids(genre_ids_str: str) -> List[int]:
    """解析类型ID字符串"""
    return [int(x.strip()) for x in genre_ids_str.split(',') if x.strip().isdigit()]


def _parse_countries(countries_str: str) -> List[str]:
    """解析原产国字符串"""
    return [c.strip().upper() for c in countries_str.split(',') if c.strip()]


def _normalize_to_list(value, parser=None):
    """将值归一化为列表，支持字符串（逗号分隔）和列表两种格式

    TMDB API 返回 origin_country/genres 是列表格式，
    但数据库存储或缓存中可能序列化为逗号分隔字符串。
    """
    if value is None:
        return []
    if isinstance(value, str):
        items = [x.strip() for x in value.split(',') if x.strip()]
        return parser(items) if parser else items
    if isinstance(value, (list, tuple)):
        if parser:
            return parser(value)
        return list(value)
    return [value]


def _match_rule(details: Dict, rule: Dict) -> bool:
    """检查媒体信息是否匹配分类规则

    匹配逻辑（任一匹配 = 命中）：
    1. genreIds：媒体的 genres 中包含规则要求的任一类型ID
    2. originCountry：媒体的原产国中包含规则要求的任一国家代码
    3. 所有指定的条件都必须满足（AND 逻辑）
    """
    conditions = rule.get("conditions", {})

    # 检查类型ID
    if conditions.get("genreIds"):
        required_ids = _parse_genre_ids(conditions["genreIds"])
        # details["genres"] 可能是列表 [{id:16, name:"Animation"}, ...] 或数字列表 [16, 18]
        raw_genres = details.get("genres") or []
        if raw_genres and isinstance(raw_genres[0], dict):
            media_genres = [g.get("id") for g in raw_genres]
        elif isinstance(raw_genres, str):
            media_genres = _parse_genre_ids(raw_genres)
        else:
            media_genres = list(raw_genres)
        if not any(gid in media_genres for gid in required_ids):
            return False

    # 检查原产国
    if conditions.get("originCountry"):
        required_countries = _parse_countries(conditions["originCountry"])
        # TMDB 返回列表 ["CN","TW"]，但数据库/缓存可能是字符串 "CN,TW"
        raw_countries = details.get("origin_country") or details.get("originCountry") or []
        media_countries = _normalize_to_list(raw_countries, lambda items: [c.upper() for c in items])
        if not any(c in media_countries for c in required_countries):
            return False

    return True


def classify_media(details: Dict, media_type: str, strategy: Optional[Dict] = None) -> str:
    """根据媒体信息进行分类

    Args:
        details: TMDB 媒体详情
        media_type: "movie" 或 "tv"
        strategy: 自定义分类策略，默认使用数据库中的策略或默认策略

    Returns:
        分类目录路径，如 "电影/国产电影"
    """
    if strategy is None:
        strategy = _get_custom_strategy() or DEFAULT_STRATEGY

    rules = strategy.get(media_type, [])

    for rule in rules:
        if _match_rule(details, rule):
            return rule["category"]

    return '电影/其他' if media_type == 'movie' else '剧集/其他'


def _get_custom_strategy() -> Optional[Dict]:
    """从数据库获取自定义分类策略"""
    config_service = get_config_service()
    saved = config_service.get("classify_rules")
    if saved:
        try:
            return json.loads(saved)
        except Exception:
            pass
    return None


def get_genre_name(genre_id: int) -> str:
    """根据类型ID获取类型名称"""
    GENRE_MAP = {
        28: '动作', 12: '冒险', 16: '动画', 35: '喜剧', 80: '犯罪',
        99: '纪录片', 18: '剧情', 10751: '家庭', 14: '奇幻', 36: '历史',
        27: '恐怖', 10402: '音乐', 9648: '悬疑', 10749: '爱情', 878: '科幻',
        10770: '电视电影', 53: '惊悚', 10752: '战争', 37: '西部',
        10759: '动作冒险', 10762: '儿童', 10763: '新闻', 10764: '真人秀',
        10765: '科幻奇幻', 10766: '肥皂剧', 10767: '谈话', 10768: '战争政治',
    }
    return GENRE_MAP.get(genre_id, '未知')


def get_country_name(code: str) -> str:
    """根据国家代码获取国家名称"""
    COUNTRY_MAP = {
        'CN': '中国', 'TW': '台湾', 'HK': '香港', 'JP': '日本',
        'KP': '朝鲜', 'KR': '韩国', 'TH': '泰国', 'IN': '印度',
        'SG': '新加坡', 'US': '美国', 'FR': '法国', 'GB': '英国',
        'UK': '英国', 'DE': '德国', 'ES': '西班牙', 'IT': '意大利',
        'NL': '荷兰', 'PT': '葡萄牙', 'RU': '俄罗斯',
    }
    return COUNTRY_MAP.get(code.upper(), code)


# 全局单例
_classify_service = None


def get_classify_service():
    """获取分类服务实例"""
    global _classify_service
    if _classify_service is None:
        _classify_service = True
    return _classify_service
