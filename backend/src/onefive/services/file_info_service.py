"""
文件名解析服务（混合方案）

职责：从视频文件名中提取关键信息
采用 guessit + 自定义补充 的混合策略：
- guessit：标题、年份、季集
- 自定义：分辨率、视频编码、音频编码、来源、HDR/DV、TMDB ID、WEB来源细分、版本、发布组、声道数
"""
import re
from typing import Optional, Dict, Any, List, Tuple
from ..logger import get_logger

logger = get_logger(__name__)

import guessit

# ==================== 自定义补充模式 ====================

# 标准命名格式：标题 (年份) {tmdb=ID} 或 标题 (年份)
STANDARD_NAME_PATTERN = re.compile(r'^(.+?)\s*\((\d{4})\)\s*(?:\{tmdb[=\-]?(\d+)\})?\s*$', re.IGNORECASE)

# 中文季集模式（guessit 不支持）
SEASON_ONLY_PATTERNS = [
    re.compile(r'\bS(\d{1,2})(?![E\d])', re.IGNORECASE),
    re.compile(r'Season\s*(\d{1,2})', re.IGNORECASE),
    re.compile(r'第(\d{1,2})季'),
]

# 视频文件扩展名（默认值，可被数据库配置覆盖）
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m2ts'}
SUBTITLE_EXTENSIONS = {'.srt', '.ass', '.ssa', '.sub', '.vtt'}

# 模块级缓存：避免每次调用都读数据库
_video_extensions_cache: Optional[set] = None
# 自定义发布组缓存（同上，避免 _extract_release_group 每次都读数据库）
_custom_release_groups_cache: Optional[List[str]] = None
# 模块级预编译正则列表：避免每次 _extract_release_group 都编译 100+ 个正则
# 存放 (编译后的正则, 发布组名) 元组，首次调用时懒加载构建
_compiled_release_patterns: List[Tuple[re.Pattern, str]] = []


def get_video_extensions() -> set:
    """获取视频扩展名集合（优先从数据库读取，回退到默认常量）

    数据库配置格式：逗号分隔的字符串，如 ".mp4,.mkv,.avi"
    用户输入可以带或不带点前缀，内部统一补齐。

    Returns:
        扩展名集合，如 {'.mp4', '.mkv', ...}
    """
    global _video_extensions_cache
    if _video_extensions_cache is not None:
        return _video_extensions_cache

    try:
        from .config_service import get_config_service
        raw = get_config_service().get("video_extensions")
        if raw:
            exts = set()
            for ext in raw.split(","):
                ext = ext.strip().lower()
                if not ext:
                    continue
                # 统一补点前缀
                if not ext.startswith("."):
                    ext = "." + ext
                exts.add(ext)
            if exts:
                _video_extensions_cache = exts
                return exts
    except Exception:
        pass

    # 回退到默认常量
    _video_extensions_cache = VIDEO_EXTENSIONS
    return _video_extensions_cache


def invalidate_video_extensions_cache():
    """使视频扩展名缓存失效

    在 STRM 设置保存后调用，确保后续读取使用新配置。
    """
    global _video_extensions_cache
    _video_extensions_cache = None


# ==================== 公共工具函数（供 organize_service / share_organize_service 复用） ====================

# 季集标记正则：S01E01、第x集、EP01、E01、Season 01 等
# 第3条正则加前导边界，避免 MOVIE01、SAMPLE01、FILE01 等被误判为剧集标记
_SEASON_EPISODE_PATTERNS = [
    re.compile(r'[Ss]\d{1,2}[Ee]\d{1,3}'),                      # S01E01 / s1e1
    re.compile(r'第\s*\d+\s*集'),                                # 第1集 / 第 01 集
    re.compile(r'(?:^|[\s._\-])[Ee][Pp]?\.?\s*\d{1,3}'),        # EP01 / E01 / ep.1（需前导边界）
    re.compile(r'Season\s*\d{1,2}', re.IGNORECASE),             # Season 1
]


def has_season_episode_marker(name: str) -> bool:
    """判断文件名是否包含季集标记（用于区分电视剧/电影）

    统一规则：S01E01、第x集、EP01、E01、Season 01 任一命中即视为电视剧。
    模块级预编译正则，避免每次调用重复编译。
    """
    return any(p.search(name) for p in _SEASON_EPISODE_PATTERNS)


def format_size(size_bytes: int) -> str:
    """格式化文件大小为人类可读字符串

    统一实现：B → KB → MB → GB → TB → PB，保留 1 位小数（B 除外）。
    供 organize_service / share_organize_service 复用，避免两处实现不一致。
    """
    # 处理空值或非正数：返回空字符串（与原 _format_size 行为一致）
    if not size_bytes or size_bytes <= 0:
        return ""
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            # B 不显示小数，其它单位保留 1 位
            return f"{size:.1f} {unit}" if unit != 'B' else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} PB"


# ==================== 发布组列表 ====================

BUILTIN_RELEASE_GROUPS = [
    'SiNNERS', 'EVO', 'AMIABLE', 'SPARKS', 'YIFY', 'FXG', 'LEGi0N',
    'HDMaNiAcS', 'WiKi', 'EuReKa', 'BeAst', 'HiDT', 'CHD', 'CtrlHD',
    'Esir', 'DON', 'Ebp', 'FraMeSToR', 'DEFLATE', 'NTb', 'LOL', 'ASAP',
    'MySilu', 'HDChina', 'HDS', 'QOQ', 'NTG', 'NAISU', 'RARBG', 'MKVTV',
    'blackTV', 'GPTHD', 'OurTV', 'DreamHD', 'CHDWEB', 'Xiaomi', 'HDCTV',
    'Huawei', 'PTerWEB', 'DDHDTV', 'QHStudio', 'SeeWeb', 'TagWeb',
    'LeagueWEB', 'SonyHD', 'ADWEB', 'MiniHD', 'FRDS', 'ALT', 'TLF',
    'CMCT', 'BHD', 'TTG', 'MTeam', 'HDPT', 'HDSky', 'HDRoute', 'HDHome',
    'HDTime', 'HDArea', 'HD4FANS', 'TJUPT', 'AUDiO', 'VARYG', 'FGT',
    'PAHE', 'Ganool', 'YTS', 'ETRG', 'JYK', 'NhaNc3', 'mHD', 'MkvCage',
    'ShAaNiG', 'PlayXD', 'ION10', 'Tigole', 'Joy', 'UTR', 'Qman', 'DHD',
    'iFT', 'SA89', 'BMF', 'SURCODE', 'KiNGDOM', 'MkvHub', 'PSA',
    'STUTTERSHIT', 'NERD', 'TBS', 'VYTO', 'PAXA', 'AOC', 'BLOW', 'CM8',
    'ROBOTS', 'ROB', 'TDP', 'Grym', 'BONE', 'CRiSC', 'SADPANDA', 'Kotenok',
    'HiDt', 'Geek', 'CasStudio', 'NewEdit', 'BiTOR', 'DNL', 'SANTi',
    'FASM', 'ARNT', 'SAPHiRE', 'ALLiANCE', 'COCAiNE', 'DoNE', 'DiAMOND',
    'PUKKA', 'NEPTUNE', 'BESTHD', 'SEPTiC', 'WAF', 'ESiR', 'EbP',
    'PerfectionHD', 'D-Z0N3', 'MySiLU',
]

# ==================== WEB 来源 ====================

WEB_SOURCES = {
    'NF': 'Netflix', 'NETFLIX': 'Netflix',
    'AMZN': 'Amazon', 'AMAZON': 'Amazon', 'PRIMEVIDEO': 'Amazon', 'PRIME': 'Amazon',
    'DSNP': 'Disney+', 'DISNEYPLUS': 'Disney+', 'DISNEY': 'Disney+',
    'HMAX': 'HMAX', 'HBOMAX': 'HMAX', 'MAX': 'MAX', 'MAXPLUS': 'MAXPLUS',
    'ATVP': 'AppleTV+', 'APPLETVPLUS': 'AppleTV+', 'APPLETV': 'AppleTV+',
    'PCOK': 'PCOK', 'PEACOCK': 'PCOK',
    'PMTP': 'PMTP', 'PARAMOUNT': 'PMTP', 'PARAMOUNTPLUS': 'PMTP',
    'HBO': 'HBO', 'HULU': 'Hulu',
    'IT': 'iTunes', 'ITUNES': 'iTunes',
    'BILIBILI': 'BiliBili', 'BGLOBAL': 'B-Global',
    'KKTV': 'KKTV', 'BAHA': 'Baha', 'MYVIDEO': 'MyVideo',
    'FRIDAY': 'friDay', 'LINETV': 'LINETV', 'VIU': 'Viu',
    'CRUNCHYROLL': 'Crunchyroll', 'ABEMA': 'Abema', 'CATCHPLAY': 'CatchPlay',
}


# ==================== 自定义解析函数 ====================

def _extract_tmdb_id(text: str) -> Optional[int]:
    """提取文件名中的 TMDB ID"""
    patterns = [
        re.compile(r'[\{\[]\s*tmdb(id)?\s*[=\-－]?\s*(\d+)\s*[\}\]]', re.IGNORECASE),
        re.compile(r'\btmdb(id)?\s*[=\-－]?\s*(\d+)\b', re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match and match.group(2):
            return int(match.group(2))
    return None


def _extract_video_format(base: str) -> str:
    """提取分辨率"""
    patterns = [
        (r'7680x4320|4320p|\b8k\b', '4320p'),
        (r'3840x2160|2160p|\b4k\b|ultra\s*hd|\buhd\b', '2160p'),
        (r'1920x1080|1080p|\bhd1080p\b', '1080p'),
        (r'1280x720|720p', '720p'),
        (r'1440p|2k', '1440p'),
        (r'480p|480i', '480p'),
        (r'360p', '360p'),
    ]
    for pattern, resolution in patterns:
        if re.search(pattern, base, re.IGNORECASE):
            return resolution
    return ''


def _extract_effects(base: str) -> str:
    """提取特效信息（HDR/DV/色深/帧率）"""
    effects = []
    if re.search(r'\b(DV|DOVI|DOLBY[ .-]?VISION)\b', base, re.IGNORECASE):
        effects.append('DV')
    if re.search(r'\bHDR10\+|\bHDR10PLUS\b', base, re.IGNORECASE):
        effects.append('HDR10+')
    elif re.search(r'\bHDR10\b', base, re.IGNORECASE):
        effects.append('HDR10')
    elif re.search(r'\bHDR\b', base, re.IGNORECASE) and not re.search(r'\bHDR10', base, re.IGNORECASE):
        effects.append('HDR')
    if re.search(r'\bHLG\b', base, re.IGNORECASE):
        effects.append('HLG')

    bit_match = re.search(r'\b(8|10|12)\s*bit\b', base, re.IGNORECASE)
    if bit_match:
        effects.append(f'{bit_match.group(1)}bit')

    fps_match = re.search(r'\b(\d{2,3})\s*fps\b', base, re.IGNORECASE)
    if fps_match:
        effects.append(f'{fps_match.group(1)}fps')

    return ' '.join(effects)


def _extract_web_source(base: str) -> str:
    """提取 WEB 来源（细分平台）"""
    sorted_sources = sorted(WEB_SOURCES.keys(), key=len, reverse=True)
    for source in sorted_sources:
        pattern = re.compile(
            rf'(?:^|[.\s_\-\[\(\{{]){re.escape(source)}(?:$|[.\s_\-\]\)\}}@])',
            re.IGNORECASE
        )
        if pattern.search(base):
            return WEB_SOURCES[source]
    return ''


def _extract_edition(base: str) -> str:
    """提取版本信息"""
    editions = []
    if re.search(r'\bDC\b|Director\'?s?\s*Cut', base, re.IGNORECASE):
        editions.append('DC')
    if re.search(r'\bExtended\b|加长版', base, re.IGNORECASE):
        editions.append('Extended')
    if re.search(r'\bUncut\b|未删减', base, re.IGNORECASE):
        editions.append('Uncut')
    if re.search(r'\bUnrated\b', base, re.IGNORECASE):
        editions.append('Unrated')
    if re.search(r'\bIMAX\b', base, re.IGNORECASE):
        editions.append('IMAX')
    if re.search(r'\b3D\b', base):
        editions.append('3D')
    if re.search(r'\bPROPER\b', base, re.IGNORECASE):
        editions.append('PROPER')
    if re.search(r'\bREPACK\b', base, re.IGNORECASE):
        editions.append('REPACK')
    if re.search(r'\bHQ\b', base, re.IGNORECASE):
        editions.append('HQ')
    if re.search(r'\bHybrid\b', base, re.IGNORECASE):
        editions.append('Hybrid')
    if re.search(r'\bRemastered\b', base, re.IGNORECASE):
        editions.append('Remastered')
    if re.search(r'\bTheatrical\b', base, re.IGNORECASE):
        editions.append('Theatrical')
    if re.search(r'\bComplete\b', base, re.IGNORECASE):
        editions.append('Complete')
    return ' '.join(editions)


def _rebuild_release_patterns():
    """重建发布组正则列表（内置 + 自定义）

    将内置发布组和自定义发布组合并后预编译为正则列表，存入模块级变量
    _compiled_release_patterns。后续 _extract_release_group 直接遍历该列表
    做匹配，避免每次调用都编译 100+ 个正则。

    调用时机：
    1. _extract_release_group 首次调用时懒加载
    2. invalidate_custom_release_groups_cache 清除缓存后同步重建
    """
    custom = _get_custom_release_groups()
    all_groups = BUILTIN_RELEASE_GROUPS + custom
    _compiled_release_patterns.clear()
    for group in all_groups:
        pattern = re.compile(
            rf'(?:^|[.\s_\-\[\(\{{@]){re.escape(group)}(?:$|[.\s_\-\]\)\}}@])',
            re.IGNORECASE
        )
        _compiled_release_patterns.append((pattern, group))


def _extract_release_group(base: str) -> str:
    """提取发布组（内置列表 + 用户自定义列表，使用预编译正则）"""
    # 懒加载：首次调用时构建预编译正则列表
    if not _compiled_release_patterns:
        _rebuild_release_patterns()

    # 遍历预编译正则列表做匹配，命中即返回对应发布组名
    for pattern, group in _compiled_release_patterns:
        if pattern.search(base):
            return group

    match = re.search(r'[-@]([A-Za-z0-9]+)$', base)
    if match and match.group(1):
        candidate = match.group(1)
        bad_groups = {'DL', 'WEB', 'WEBDL', 'WEBRIP', 'BLURAY', 'REMUX', 'BD', 'H264', 'H265', 'X264', 'X265'}
        if candidate.upper() not in bad_groups:
            return candidate
    return ''


def _get_custom_release_groups() -> List[str]:
    """从数据库读取用户自定义发布组列表（带缓存）

    首次调用读数据库并写入模块级缓存，后续调用直接命中缓存，
    避免每次 _extract_release_group 都查库。配置变更时由
    invalidate_custom_release_groups_cache() 清除缓存。
    """
    global _custom_release_groups_cache
    if _custom_release_groups_cache is not None:
        return _custom_release_groups_cache

    try:
        from .config_service import get_config_service
        config = get_config_service()
        raw = config.get("release_groups")
        if raw:
            groups = [g.strip() for g in raw.split('\n') if g.strip()]
            _custom_release_groups_cache = groups
            return groups
    except Exception:
        pass
    # 回退到空列表并缓存，避免反复尝试读库
    _custom_release_groups_cache = []
    return _custom_release_groups_cache


def invalidate_custom_release_groups_cache():
    """使自定义发布组缓存失效

    在用户保存新的 release_groups 配置后调用，确保后续读取使用新值。
    同时重建预编译正则列表，保证 _extract_release_group 用上新配置。
    """
    global _custom_release_groups_cache
    _custom_release_groups_cache = None
    # 同步重建预编译正则列表（_rebuild_release_patterns 内部会重新读库填充缓存）
    _rebuild_release_patterns()


def _extract_audio_channels(base: str) -> str:
    """提取声道数"""
    match = re.search(r'(\d+\.\d+)', base)
    return match.group(1) if match else ''


# ==================== 主解析函数 ====================

def extract_key_info(filename: str, folder_files: Optional[List[str]] = None) -> Dict[str, Any]:
    """从文件名提取关键信息（混合方案）

    优先级：
    1. 标准命名格式（标题 (年份) {tmdb=ID}）→ 直接提取，不走 guessit
    2. guessit 解析标题、年份、季集
    3. 自定义补充 TMDB ID、中文季集、分辨率、特效

    Args:
        filename: 完整文件名（含扩展名）
        folder_files: （已废弃，保留仅为兼容性，当前实现不使用）文件夹内的文件列表

    Returns:
        {"title", "year", "season", "episode", "mediaType", "tmdbId", "fallbackQuery"}
    """
    base = filename.rsplit('.', 1)[0] if '.' in filename else filename

    # 自定义提取 TMDB ID（guessit 不支持）
    tmdb_id = _extract_tmdb_id(base)

    # 自定义提取分辨率（guessit 不支持）
    video_format = _extract_video_format(base)

    # 自定义提取特效（guessit 不支持）
    effects = _extract_effects(base)

    # 优先检测标准命名格式：标题 (年份) {tmdb=ID}
    # 这种格式已经是最规范的，不需要 guessit 干扰
    std_match = STANDARD_NAME_PATTERN.match(base)
    if std_match:
        title = std_match.group(1).strip()
        year = std_match.group(2)
        std_tmdb = std_match.group(3)
        if std_tmdb and not tmdb_id:
            tmdb_id = int(std_tmdb)

        # 检测季集信息（自定义中文季集 + 仅季，统一调用避免重复代码）
        season, episode, season_only = _detect_season_episode(base)
        # 仅当中文季集未命中时，才回退到仅季模式
        if season is None and episode is None and season_only is not None:
            season = season_only

        # 媒体类型：有季或集即为电视剧（兼容季包 S02 无集号的情况）
        media_type = 'tv' if season is not None or episode is not None else 'movie'

        return {
            "title": title,
            "year": year,
            "season": season,
            "episode": episode,
            "mediaType": media_type,
            "tmdbId": tmdb_id,
            "videoFormat": video_format,
            "effects": effects,
            "fallbackQuery": _clean_query(base),
        }

    # 非标准格式，使用 guessit 解析
    try:
        g = guessit.guessit(filename)
    except Exception:
        g = {}

    # 标题：guessit 优先
    title = g.get('title', '')
    if not title:
        # fallback: 用正则提取
        cleaned = _clean_query(base)
        title = cleaned.split()[0] if cleaned else ''

    # 年份
    year = str(g.get('year', '')) if g.get('year') else _extract_year(base)

    # 季集
    # guessit 解析 "S01-S18" 等季度范围时返回 list（如 [1, 18]），取第一个
    season = g.get('season')
    if isinstance(season, list):
        season = season[0] if season else None
    episode = g.get('episode')
    if isinstance(episode, list):
        episode = episode[0] if episode else None
    if season is not None:
        season = int(season)
    if episode is not None:
        episode = int(episode)

    # 自定义中文季集 + 仅季（guessit 不支持，仅在 guessit 未给出时补充）
    if season is None and episode is None:
        cn_season, cn_episode, season_only = _detect_season_episode(base)
        if cn_season is not None:
            season = cn_season
        if cn_episode is not None:
            episode = cn_episode
        # 中文季集仍未命中时，回退到仅季模式
        if season is None and episode is None and season_only is not None:
            season = season_only

    # 媒体类型：有季或集即为电视剧（兼容季包 S02 无集号的情况）
    media_type = 'tv' if season is not None or episode is not None else 'movie'

    return {
        "title": title,
        "year": year,
        "season": season,
        "episode": episode,
        "mediaType": media_type,
        "tmdbId": tmdb_id,
        "videoFormat": video_format,
        "effects": effects,
        "fallbackQuery": _clean_query(base),
    }


def extract_tech_info(filename: str) -> Dict[str, str]:
    """提取技术信息（全自定义方案）

    guessit 只负责标题、年份、季集（在 extract_key_info 中使用）
    技术信息全部由自定义正则提取，更精确可控
    """
    base = filename.rsplit('.', 1)[0] if '.' in filename else filename
    ext = '.' + filename.rsplit('.', 1)[1] if '.' in filename else ''

    # 视频编码：自定义提取
    video_codec = _extract_video_codec(base)

    # 音频编码：自定义提取
    audio_codec = _extract_audio_codec(base)

    # 来源：自定义提取
    source = _extract_source(base)

    # 自定义补充
    video_format = _extract_video_format(base)
    web_source = _extract_web_source(base)
    edition = _extract_edition(base)
    effects = _extract_effects(base)
    release_group = _extract_release_group(base)

    # 组合 edition：来源 + 特效 + 版本
    edition_parts = []
    if source:
        edition_parts.append(source)
    if effects:
        edition_parts.append(effects)
    if edition:
        edition_parts.append(edition)
    combined_edition = ' '.join(edition_parts)

    return {
        "videoFormat": video_format,
        "videoCodec": video_codec,
        "audioCodec": audio_codec,
        "webSource": web_source,
        "edition": combined_edition,
        "releaseGroup": release_group,
        "fileExt": ext,
    }


# ==================== 辅助函数 ====================

def _extract_year(text: str) -> Optional[str]:
    """提取年份"""
    match = re.search(r'\b(19\d{2}|20\d{2})\b', text)
    return match.group(1) if match else None


def _detect_chinese_episode(filename: str) -> Tuple[Optional[int], Optional[int]]:
    """检测中文季集格式（如"第N集"）

    Returns:
        (season, episode) 元组：命中"第N集"时 season 固定为 1，episode 为集号；
        未命中返回 (None, None)
    """
    match = re.search(r'第(\d{1,3})集', filename)
    if match:
        return (1, int(match.group(1)))
    return (None, None)


def _detect_season_only(filename: str) -> Optional[int]:
    """检测仅季数"""
    for pattern in SEASON_ONLY_PATTERNS:
        match = pattern.search(filename)
        if match and match.group(1):
            return int(match.group(1))
    return None


def _detect_season_episode(base: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """统一检测中文季集与仅季信息（guessit 不支持的部分）

    一次调用同时获取两种自定义检测结果，供 extract_key_info 按优先级合并，
    消除标准格式与非标准格式两段几乎相同的"中文季集检测"重复代码。

    Args:
        base: 不含扩展名的文件名主体

    Returns:
        (season, episode, season_only)
        - season / episode：来自 "第N集" 模式（命中时 season 固定为 1）
        - season_only：来自 "第N季" / "Season N" / "S0N" 等仅季模式
    """
    season, episode = _detect_chinese_episode(base)
    season_only = _detect_season_only(base)
    return season, episode, season_only


def _clean_query(text: str) -> str:
    """清理文件名用于搜索"""
    cleaned = text
    cleaned = re.sub(r'\[[^\]]*\]', ' ', cleaned)
    cleaned = re.sub(r'\{[^}]*\}', ' ', cleaned)
    cleaned = re.sub(r'\([^)]*\)', ' ', cleaned)
    cleaned = re.sub(r'S\d{1,2}E\d{1,3}', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\d{1,2}x\d{1,3}', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'第\d+集', ' ', cleaned)
    cleaned = re.sub(r'EP?\d{1,3}', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\b(2160p|1080p|720p|480p|360p|4K|8K|UHD|HD|SD)\b', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r'\b(WEB-?DL|WEBRip|BluRay|BDRip|HDTV|DVDRip|REMUX)\b',
        ' ', cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r'\b(H\.?26[45]|X\.?26[45]|HEVC|AVC|AV1)\b', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r'\b(DTS[-\s.]?HD[-\s.]?MA|DTS[-\s.]?HD|DDP\d*\.?\d*|'
        r'AAC\d*\.?\d*|TrueHD|Atmos|FLAC)\b',
        ' ', cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r'\b(DV|HDR10\+|HDR10|HDR|HLG|SDR)\b', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\btmdb[=＝]?\d+\b', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'[._\-\[\]\(\)\{\}]', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _extract_video_codec(base: str) -> str:
    """自定义提取视频编码"""
    if re.search(r'\b(H\.?265|H265|X265|HEVC)\b', base, re.IGNORECASE):
        return 'H265'
    if re.search(r'\b(H\.?264|H264|X264|AVC)\b', base, re.IGNORECASE):
        return 'H264'
    match = re.search(r'\b(AV1|VP9|MPEG-?2)\b', base, re.IGNORECASE)
    return match.group(1).upper() if match else ''


def _extract_audio_codec(base: str) -> str:
    """自定义提取音频编码

    匹配规则：编码名后面紧跟的数字才是声道数，中间只允许 . - 空格
    Atmos 可在声道数前或后：DTS-HD.MA.Atmos.7.1 或 DTS-HD.MA.7.1.Atmos
    """
    # TrueHD + Dolby Atmos + 声道
    match = re.search(
        r'\bTrueHD[.\s-]*(?:Dolby[.\s-]*)?Atmos[.\s-]*(\d+\.\d+)',
        base, re.IGNORECASE
    )
    if match:
        return f'TrueHD.Atmos.{match.group(1)}'
    # TrueHD + 声道 + Dolby Atmos
    match = re.search(
        r'\bTrueHD[.\s-]*(\d+\.\d+)[.\s-]*(?:Dolby[.\s-]*)?Atmos\b',
        base, re.IGNORECASE
    )
    if match:
        return f'TrueHD.Atmos.{match.group(1)}'
    # TrueHD + 声道
    match = re.search(r'\bTrueHD[.\s-]*(\d+\.\d+)', base, re.IGNORECASE)
    if match:
        return f'TrueHD.{match.group(1)}'
    # TrueHD + Atmos（无声道）
    if re.search(r'\bTrueHD[.\s-]*Atmos\b', base, re.IGNORECASE):
        return 'TrueHD.Atmos'
    # TrueHD（无声道无Atmos）
    if re.search(r'\bTrueHD\b', base, re.IGNORECASE):
        return 'TrueHD'

    # DTS-HD.MA + Atmos + 声道
    match = re.search(r'\bDTS[- .]?HD[- .]?MA[.\s-]*Atmos[.\s-]*(\d+\.\d+)', base, re.IGNORECASE)
    if match:
        return f'DTS-HD.MA.Atmos.{match.group(1)}'
    # DTS-HD.MA + 声道 + Atmos
    match = re.search(
        r'\bDTS[- .]?HD[- .]?MA[.\s-]*(\d+\.\d+)[.\s-]*Atmos\b',
        base, re.IGNORECASE
    )
    if match:
        return f'DTS-HD.MA.Atmos.{match.group(1)}'
    # DTS-HD.MA + 声道
    match = re.search(r'\bDTS[- .]?HD[- .]?MA[.\s-]*(\d+\.\d+)', base, re.IGNORECASE)
    if match:
        return f'DTS-HD.MA.{match.group(1)}'
    # DTS-HD.MA（无声道）
    if re.search(r'\bDTS[- .]?HD[- .]?MA\b', base, re.IGNORECASE):
        return 'DTS-HD.MA'

    # DTS + Atmos + 声道
    match = re.search(r'\bDTS[.\s-]*Atmos[.\s-]*(\d+\.\d+)', base, re.IGNORECASE)
    if match:
        return f'DTS.Atmos.{match.group(1)}'
    # DTS + 声道 + Atmos
    match = re.search(r'\bDTS[.\s-]*(\d+\.\d+)[.\s-]*Atmos\b', base, re.IGNORECASE)
    if match:
        return f'DTS.Atmos.{match.group(1)}'

    # DDP/EAC3 + Atmos + 声道
    match = re.search(r'\b(?:DDP|DD\+|E-?AC-?3)[.\s-]*Atmos[.\s-]*(\d+\.\d+)', base, re.IGNORECASE)
    if match:
        return f'DDP.Atmos.{match.group(1)}'
    # DDP + 声道 + Atmos
    match = re.search(
        r'\b(?:DDP|DD\+|E-?AC-?3)[.\s-]*(\d+\.\d+)[.\s-]*Atmos\b',
        base, re.IGNORECASE
    )
    if match:
        return f'DDP.Atmos.{match.group(1)}'
    # DDP + 声道
    match = re.search(r'\b(?:DDP|DD\+|E-?AC-?3)[.\s-]*(\d+\.\d+)', base, re.IGNORECASE)
    if match:
        return f'DDP.{match.group(1)}'
    # DDP（无声道）
    if re.search(r'\b(?:DDP|DD\+|E-?AC-?3)\b', base, re.IGNORECASE):
        return 'DDP'

    # AAC + 声道
    match = re.search(r'\bAAC[.\s-]*(\d+\.\d+)', base, re.IGNORECASE)
    if match:
        return f'AAC.{match.group(1)}'
    if re.search(r'\bAAC\b', base, re.IGNORECASE):
        return 'AAC'

    # FLAC
    if re.search(r'\bFLAC\b', base, re.IGNORECASE):
        return 'FLAC'

    # DTS + 声道
    match = re.search(r'\bDTS[.\s-]*(\d+\.\d+)', base, re.IGNORECASE)
    if match:
        return f'DTS.{match.group(1)}'
    if re.search(r'\bDTS\b', base, re.IGNORECASE):
        return 'DTS'

    return ''


def _extract_source(base: str) -> str:
    """自定义提取来源

    UHD = Ultra HD，4K蓝光标识
    UHD BluRay REMUX = 4K蓝光原盘重封装
    """
    # 检测 UHD / Ultra HD
    has_uhd = bool(re.search(r'\b(?:UHD|Ultra\s*HD)\b', base, re.IGNORECASE))
    # 检测 REMUX
    has_remux = bool(re.search(r'\bREMUX\b', base, re.IGNORECASE))

    if re.search(r'blu[-\s]?ray', base, re.IGNORECASE):
        if has_uhd and has_remux:
            return 'UHD BluRay REMUX'
        elif has_remux:
            return 'BluRay REMUX'
        elif has_uhd:
            return 'UHD BluRay'
        else:
            return 'BluRay'

    # UHD 独立出现（无 BluRay）
    if has_uhd:
        return 'UHD'

    patterns = [
        (r'web\.?dl|webdl', 'WEB-DL'),
        (r'webrip', 'WEBRip'),
        (r'hdtv', 'HDTV'),
        (r'dvd', 'DVD'),
    ]
    for pattern, source in patterns:
        if re.search(pattern, base, re.IGNORECASE):
            return source
    return ''
