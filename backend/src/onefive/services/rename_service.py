"""
重命名服务

职责：根据模板生成目标文件名
支持 Jinja2 风格的模板语法：{{variable}} 和 {% if %}{% endif %}
"""
import re
from typing import Dict, Any, Optional
from .config_service import get_config_service
from ..logger import get_logger

logger = get_logger(__name__)

# ==================== 默认模板 ====================

DEFAULT_MOVIE_TEMPLATE = "{{title}} ({{year}}) {tmdb={{tmdbid}}}/{{title}}.{{year}}.{{videoFormat}}.{{edition}}.{{videoCodec}}.{{audioCodec}}{% if webSource %}.{{webSource}}{% endif %}{% if releaseGroup %}-{{releaseGroup}}{% endif %}{{fileExt}}"

DEFAULT_TV_TEMPLATE = "{{title}} ({{year}}) {tmdb={{tmdbid}}}/Season {{seasonPadded}}/{{title}}.{{seasonYear}}.{{SXXEXX}}.{{videoFormat}}.{{edition}}.{{videoCodec}}.{{audioCodec}}{% if webSource %}.{{webSource}}{% endif %}{% if releaseGroup %}-{{releaseGroup}}{% endif %}{{fileExt}}"


def render_template(template: str, variables: Dict[str, Any]) -> str:
    """渲染模板

    支持：
    - {{variable}} - 变量替换
    - {% if variable %}content{% endif %} - 条件渲染
    - {% if variable %}if_content{% else %}else_content{% endif %} - 条件分支

    Args:
        template: 模板字符串
        variables: 变量字典

    Returns:
        渲染后的字符串
    """
    result = template

    # 处理条件语句
    # {% if variable %}content{% endif %}
    def replace_if(match):
        var_name = match.group(1).strip()
        if_content = match.group(2)
        else_content = match.group(3) if match.lastindex >= 3 and match.group(3) else ''
        value = variables.get(var_name)
        if value:
            return if_content.strip()
        return else_content.strip()

    result = re.sub(
        r'\{%\s*if\s+(\w+)\s*%\}(.*?)(?:\{%\s*else\s*%\}(.*?))?\{%\s*endif\s*%\}',
        replace_if,
        result,
        flags=re.DOTALL
    )

    # 处理变量替换
    def replace_var(match):
        var_name = match.group(1).strip()
        value = variables.get(var_name, '')
        return str(value) if value else ''

    result = re.sub(r'\{\{(\w+)\}\}', replace_var, result)

    # 清理非法字符（保留 / 用于路径分隔）
    result = re.sub(r'[<>:"\\|?*]', '', result)

    # 清理多余的点号和空格
    result = re.sub(r'\.{2,}', '.', result)
    result = re.sub(r'\s+', ' ', result).strip()

    # 清理空的路径段
    result = re.sub(r'/\./', '/', result)
    result = re.sub(r'/\s*/', '/', result)
    # 无季号时去掉空的 "Season/" 段（Season 00 有数字不会被误删）
    result = re.sub(r'/Season\s*(?=/|$)', '', result, flags=re.IGNORECASE)

    # 清理因空值产生的多余分隔符
    result = re.sub(r'\.-\.', '.', result)     # .-. -> .
    result = re.sub(r'-\.', '.', result)       # -. -> .（如 -releaseGroup为空-.mkv -> .mkv）
    result = re.sub(r'\.-', '.', result)       # .- -> .
    result = re.sub(r'\.{2,}', '.', result)    # .. -> .
    result = re.sub(r'-{2,}', '-', result)     # -- -> -
    result = re.sub(r'\s*[.\-]\s*$', '', result)  # 去掉末尾的 . 或 -
    result = re.sub(r'^[.\-]\s*', '', result)     # 去掉开头的 . 或 -

    return result



def normalize_se_number(value: Any) -> str:
    """将季/集编号规范为字符串。

    重要：0 / "0" / "00" 都是合法值（特别篇 Season 00 / S00E01），
    不能用 ``if season`` 这种真值判断，否则会把 0 当成“空”丢掉。
    只有 None / 空字符串表示缺失。
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    if text == "":
        return ""
    # "00" / "01" → 先转 int 再转回，后续 zfill 得到 00/01
    if re.fullmatch(r"\d{1,4}", text):
        return str(int(text))
    return text


def format_sxxexx(season: str, episode: str) -> str:
    """生成 S00E01 形式；季或集缺失时返回空串。0 为合法季/集。"""
    season = normalize_se_number(season)
    episode = normalize_se_number(episode)
    if season == "" or episode == "":
        return ""
    return f"S{season.zfill(2)}E{episode.zfill(2)}"


def _generate_path(template_key: str, title: str, year: str, tmdb_id: str,
                   tech_info: Dict[str, str], season_year: str = '',
                   season: str = '', episode: str = '') -> Dict[str, str]:
    """生成目标路径（电影/电视剧通用实现）

    合并原 generate_movie_path / generate_tv_path 的重复逻辑：
    仅模板键和默认模板不同，变量字典与渲染流程完全一致。

    Args:
        template_key: 配置键名，"movie_template" 或 "tv_template"
        title: 标题
        year: 年份
        tmdb_id: TMDB ID
        tech_info: 技术信息
        season_year: 季年份
        season: 季数
        episode: 集数

    Returns:
        {"dir": "目录路径", "filename": "文件名"}
    """
    config_service = get_config_service()
    # 按模板键选择配置项和默认模板
    if template_key == "movie_template":
        default_template = DEFAULT_MOVIE_TEMPLATE
    else:
        default_template = DEFAULT_TV_TEMPLATE
    template = config_service.get(template_key) or default_template

    # 0 是特别篇合法季号，必须先规范化，禁止 if season 判空
    season = normalize_se_number(season)
    episode = normalize_se_number(episode)
    season_year = str(season_year or "").strip()

    variables = {
        "title": title,
        "year": year,
        "tmdbid": tmdb_id,
        "videoFormat": tech_info.get("videoFormat", ""),
        "edition": tech_info.get("edition", ""),
        "videoCodec": tech_info.get("videoCodec", ""),
        "audioCodec": tech_info.get("audioCodec", ""),
        "webSource": tech_info.get("webSource", ""),
        "releaseGroup": tech_info.get("releaseGroup", ""),
        "fileExt": tech_info.get("fileExt", ""),
        "seasonYear": season_year,
        "season": season,
        # "0" → "00"；空串才表示无季
        "seasonPadded": season.zfill(2) if season != "" else "",
        "episode": episode,
        "episodePadded": episode.zfill(2) if episode != "" else "",
        "SXXEXX": format_sxxexx(season, episode),
    }

    rendered = render_template(template, variables)
    parts = rendered.rsplit('/', 1)

    if len(parts) == 2:
        return {"dir": parts[0], "filename": parts[1]}
    return {"dir": "", "filename": rendered}


def generate_movie_path(title: str, year: str, tmdb_id: str, tech_info: Dict[str, str],
                        season_year: str = '', season: str = '', episode: str = '') -> Dict[str, str]:
    """生成电影目标路径（薄封装，委托 _generate_path）

    Returns:
        {"dir": "目录路径", "filename": "文件名"}
    """
    return _generate_path("movie_template", title, year, tmdb_id, tech_info,
                          season_year, season, episode)


def generate_tv_path(title: str, year: str, tmdb_id: str, tech_info: Dict[str, str],
                     season_year: str = '', season: str = '', episode: str = '') -> Dict[str, str]:
    """生成电视剧目标路径（薄封装，委托 _generate_path）

    Returns:
        {"dir": "目录路径", "filename": "文件名"}
    """
    return _generate_path("tv_template", title, year, tmdb_id, tech_info,
                          season_year, season, episode)


def generate_target_path(media_type: str, title: str, year: str, tmdb_id: str,
                         tech_info: Dict[str, str], season_year: str = '',
                         season: str = '', episode: str = '') -> Dict[str, str]:
    """根据媒体类型生成目标路径

    Args:
        media_type: "movie" 或 "tv"
        title: 标题
        year: 年份
        tmdb_id: TMDB ID
        tech_info: 技术信息
        season_year: 季年份
        season: 季数
        episode: 集数

    Returns:
        {"dir": "目录路径", "filename": "文件名"}
    """
    if media_type == "movie":
        return generate_movie_path(title, year, tmdb_id, tech_info, season_year, season, episode)
    else:
        return generate_tv_path(title, year, tmdb_id, tech_info, season_year, season, episode)
