"""
通知消息格式化模块

从 organize_service 和 share_organize_service 的 _send_notify 方法中
提取共同的消息构建逻辑，统一管理通知消息格式。

两个服务的消息模板几乎一样，区别仅在：
- 状态标题不同：整理完成/整理失败 vs 分享入库完成/分享入库失败
- organize_service 额外显示"📦 整理方式"行
"""
from typing import Any, Dict, Optional


def _build_episode_str(season: int, episode_range: Optional[list]) -> Optional[str]:
    """构建集数范围字符串，如 S01E01-E12 或 S01E03

    Args:
        season: 季号
        episode_range: [起始集, 结束集] 列表，如 [1, 12]

    Returns:
        格式化后的集数字符串，无集数信息时返回 None
    """
    if not episode_range:
        return None

    s_str = str(season).zfill(2) if season else "01"
    e_min = str(episode_range[0]).zfill(2)
    e_max = str(episode_range[1]).zfill(2)

    # 起始集和结束集相同时，只显示一集
    if episode_range[0] != episode_range[1]:
        return f"S{s_str}E{e_min}-E{e_max}"
    return f"S{s_str}E{e_min}"


def _build_quality_str(tech: Dict[str, Any]) -> Optional[str]:
    """构建质量描述字符串，由 videoFormat + edition + videoCodec + audioCodec + webSource 拼接

    Args:
        tech: tech_info 字典，包含视频格式、版本、编码等信息

    Returns:
        拼接后的质量字符串，无质量信息时返回 None
    """
    parts = []
    for key in ("videoFormat", "edition", "videoCodec", "audioCodec", "webSource"):
        value = tech.get(key)
        if value:
            parts.append(value)
    return " ".join(parts) if parts else None


def format_organize_notify(
    success: bool,
    title: str,
    target_title: str,
    file_name: str,
    category: str,
    media_info: Optional[Dict[str, Any]] = None,
    action: Optional[str] = None,
) -> str:
    """格式化整理/入库通知消息

    统一处理成功和失败两种场景的消息构建：
    - 失败：显示失败状态标题 + 目标名称 + 原文件名
    - 成功：显示成功状态标题 + 名称(年份)、评分、集数、类别、小组、质量、大小、文件数、整理方式

    调用示例：
        # organize_service
        msg = format_organize_notify(
            success=True, title="整理完成", target_title="Inception",
            file_name="Inception.2010.mkv", category="电影", media_info=info,
            action="硬链接",
        )
        msg = format_organize_notify(
            success=False, title="整理失败", target_title="Inception",
            file_name="Inception.2010.mkv", category="电影",
        )

        # share_organize_service（不传 action，则不显示整理方式行）
        msg = format_organize_notify(
            success=True, title="分享入库完成", target_title="Inception",
            file_name="Inception.2010.mkv", category="电影", media_info=info,
        )

    Args:
        success: 是否整理成功
        title: 状态标题，成功时如 "整理完成"/"分享入库完成"，
               失败时如 "整理失败"/"分享入库失败"
        target_title: 识别出的目标媒体名（如 TMDB 标题）；
                      成功时用于拼接名称(年份)；失败时作为第一行显示
        file_name: 原始文件名，失败时显示为"原文件：xxx"
        category: 媒体类别（如 "电影"、"电视剧"）
        media_info: 媒体信息字典，成功时需包含 year、season、tmdb_rating、
                    tech_info、_file_count、_episode_range、_file_size 等字段
        action: 整理方式（如 "硬链接"、"复制"），仅 organize_service 传入；
                不传或传 None 则不显示整理方式行

    Returns:
        格式化后的通知消息字符串
    """
    if not media_info:
        media_info = {}

    # ---- 失败消息：状态标题 + 目标名称 + 原文件名 ----
    if not success:
        return (
            f"━━━━━━━━━━━━━━━━\n"
            f"  ❌  {title}\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"  {target_title}\n"
            f"  原文件：{file_name}"
        )

    # ---- 成功消息 ----
    # 从 media_info 中提取各字段
    year = media_info.get("year", "")
    season = media_info.get("season", 0)
    rating = media_info.get("tmdb_rating", 0)
    tech = media_info.get("tech_info", {})
    file_count = media_info.get("_file_count", 0)
    episode_range = media_info.get("_episode_range")
    release_group = tech.get("releaseGroup", "")
    file_size = media_info.get("_file_size", "")

    # 媒体名：成功时 target_title 传入识别出的媒体名，拼接年份
    full_title = target_title
    if year:
        full_title += f" ({year})"

    # 逐行构建消息
    msg = f"✅ <b>{title}</b>\n\n"
    msg += f"🎬 <b>名称</b>：{full_title}\n\n"

    if rating:
        msg += f"⭐ <b>评分</b>：{rating:.1f}\n"

    ep_str = _build_episode_str(season, episode_range)
    if ep_str:
        msg += f"📺 <b>集数</b>：{ep_str}\n"

    if category:
        msg += f"📁 <b>类别</b>：{category}\n"

    if release_group:
        msg += f"👥 <b>小组</b>：{release_group}\n"

    quality = _build_quality_str(tech)
    if quality:
        msg += f"🎞️ <b>质量</b>：{quality}\n"

    if file_size:
        msg += f"💾 <b>大小</b>：{file_size}\n"

    if file_count > 1:
        msg += f"📄 <b>文件数</b>：{file_count}\n"

    # 整理方式：仅 organize_service 传入，share_organize_service 不传
    if action:
        msg += f"📦 <b>整理方式</b>：{action}"

    return msg
