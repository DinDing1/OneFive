"""
通知消息格式化模块

统一管理各业务通知的消息模板，保证 Telegram 等渠道展示风格一致：
- 整理/入库：organize_service / share_organize_service
- 分享添加：Bot 收到 115 分享链接
- 离线转存：Bot 收到 ed2k / magnet

模板约定（HTML，配合 parse_mode=html）：
- 首行：状态 emoji + <b>标题</b>
- 空一行后，字段行：emoji + <b>标签</b>：值
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


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


def _html_escape(value: Any) -> str:
    """转义 HTML 特殊字符，避免文件名中的 <>& 破坏 Telegram HTML。"""
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _format_bytes(size: Any) -> str:
    """将字节数格式化为可读大小；无效值返回空串。"""
    try:
        n = int(size or 0)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


def _line(emoji: str, label: str, value: Any) -> str:
    """构建统一字段行：emoji + 加粗标签 + 值。"""
    return f"{emoji} <b>{_html_escape(label)}</b>：{_html_escape(value)}"


def format_share_add_notify(
    success: bool,
    *,
    share_name: str = "",
    file_count: int = 0,
    total_size: Any = 0,
    source_id: Any = None,
    share_code: str = "",
    error: str = "",
) -> str:
    """格式化「115 分享链接添加」通知，与离线转存模板字段风格一致。"""
    if not success:
        lines = [
            "❌ <b>分享添加失败</b>",
            "",
            _line("📝", "原因", error or "未知错误"),
        ]
        if share_name:
            lines.append(_line("📦", "名称", share_name))
        if share_code:
            lines.append(_line("🔗", "分享码", share_code))
        return "\n".join(lines)

    lines = [
        "✅ <b>分享添加成功</b>",
        "",
        _line("📦", "名称", share_name or "-"),
        _line("📁", "文件数", f"{int(file_count or 0)} 个"),
    ]
    size_str = _format_bytes(total_size)
    if size_str:
        lines.append(_line("💾", "大小", size_str))
    lines.append(_line("🔗", "类型", "115 分享"))
    if source_id is not None and str(source_id) != "":
        lines.append(_line("🆔", "来源 ID", source_id))
    if share_code:
        lines.append(_line("🔖", "分享码", share_code))
    return "\n".join(lines)


def format_offline_add_notify(
    success: bool,
    *,
    accepted: int = 0,
    total: int = 0,
    exists: int = 0,
    failed: int = 0,
    save_path: str = "",
    items: Optional[Sequence[Dict[str, Any]]] = None,
    error: str = "",
) -> str:
    """格式化「ed2k / magnet 离线转存」通知，与分享添加模板字段风格一致。"""
    items = list(items or [])
    exists = int(exists or 0)
    accepted = int(accepted or 0)
    total = int(total or 0) or len(items)
    failed = int(failed or 0)

    if not success:
        # 任务已存在类错误，用中性提示而非失败红叉
        err = error or "未知错误"
        if any(k in str(err) for k in ("任务已存在", "重复的链接", "请勿输入重复")):
            title = "ℹ️ <b>离线任务已存在</b>"
        else:
            title = "❌ <b>离线转存失败</b>"
        lines = [title, "", _line("📝", "原因", err)]
        if save_path:
            lines.append(_line("📂", "保存路径", save_path))
        return "\n".join(lines)

    if exists and exists == accepted and failed == 0:
        title = f"ℹ️ <b>离线任务已存在</b> {accepted}/{total}"
    elif exists:
        title = f"✅ <b>离线转存已提交</b> {accepted}/{total}（其中已存在 {exists}）"
    else:
        title = f"✅ <b>离线转存已提交</b> {accepted}/{total}"

    lines = [title, ""]

    # 单条时突出名称，与分享添加「名称」行对齐
    if total == 1 and items:
        only = items[0]
        name = only.get("name") or only.get("url_type") or "link"
        if only.get("renamed"):
            name = f"{name}（已恢复空格文件名）"
        elif only.get("rename_pending"):
            name = f"{name}（下载完成后将尝试恢复文件名）"
        elif only.get("status") == "exists":
            name = f"{name}（任务已存在）"
        lines.append(_line("📦", "名称", name))
    else:
        lines.append(_line("📦", "数量", f"{accepted}/{total}"))

    if save_path:
        lines.append(_line("📂", "保存路径", save_path or "-"))

    types = sorted({
        str(x.get("url_type") or "").lower()
        for x in items
        if x.get("url_type")
    })
    if types:
        lines.append(_line("🔗", "类型", " / ".join(types)))
    else:
        lines.append(_line("🔗", "类型", "离线转存"))

    if failed:
        lines.append(_line("⚠️", "失败", f"{failed} 条"))

    # 多条时输出明细；单条失败时也补一行错误，避免只有标题
    show_detail = total > 1 or (
        total == 1 and items and not items[0].get("ok")
    )
    if show_detail and items:
        lines.append("")
        lines.append("📄 <b>明细</b>：")
        for item in items[:5]:
            name = _html_escape(item.get("name") or item.get("url_type") or "link")
            extra = ""
            if item.get("renamed"):
                extra = "（已恢复空格文件名）"
            elif item.get("rename_pending"):
                extra = "（下载完成后将尝试恢复文件名）"
            if item.get("status") == "exists":
                lines.append(f"  • 已存在 {name}{extra}")
            elif item.get("ok"):
                lines.append(f"  ✓ {name}{extra}")
            else:
                err = _html_escape(item.get("error") or "失败")
                lines.append(f"  ✗ {name}: {err}")
        if len(items) > 5:
            lines.append(f"  … 共 {len(items)} 条")

    return "\n".join(lines)

def format_task_summary_notify(
    *,
    task_name: str,
    success: bool,
    result: Optional[Dict[str, Any]] = None,
) -> str:
    """格式化定时任务结束汇总通知。

    视觉与手动整理通知（format_organize_notify）保持一致：
    首行状态标题 + 空行 + emoji 加粗字段行。
    云盘整理成功项本身走 format_organize_notify，通常不再调用本函数。
    """
    data = result or {}
    name = (task_name or "定时任务").strip() or "定时任务"
    trigger = str(data.get("trigger") or "manual")
    trigger_label = {
        "manual": "手动执行",
        "scheduled": "定时调度",
        "cron": "定时调度",
    }.get(trigger, trigger)

    # 与 format_organize_notify 一致的标题风格
    if success:
        msg = f"✅ <b>{_html_escape(name)}完成</b>\n\n"
    else:
        msg = (
            f"━━━━━━━━━━━━━━━━\n"
            f"  ❌  {_html_escape(name)}失败\n"
            f"━━━━━━━━━━━━━━━━\n\n"
        )

    message = data.get("message") or ("完成" if success else "执行失败")
    msg += f"📋 <b>结果</b>：{_html_escape(message)}\n"
    msg += f"⏱ <b>触发</b>：{_html_escape(trigger_label)}\n"

    success_count = data.get("success_count")
    skipped = data.get("skipped")
    failed = data.get("failed")
    scanned = data.get("scanned")

    if success_count is not None:
        msg += f"✅ <b>成功</b>：{int(success_count or 0)} 个\n"
    if skipped is not None and int(skipped or 0) > 0:
        msg += f"⏭ <b>跳过</b>：{int(skipped or 0)} 个\n"
    if failed is not None and int(failed or 0) > 0:
        msg += f"⚠️ <b>失败</b>：{int(failed or 0)} 个\n"
    if scanned is not None:
        msg += f"🔍 <b>扫描</b>：{int(scanned or 0)} 个视频\n"

    source_path = data.get("source_path")
    media_path = data.get("media_library_path")
    if source_path:
        msg += f"📁 <b>来源</b>：{_html_escape(source_path)}\n"
    if media_path:
        msg += f"📚 <b>媒体库</b>：{_html_escape(media_path)}\n"

    # 整理方式（与手动整理字段对齐，有则显示）
    organize_mode = data.get("organize_mode")
    if organize_mode:
        mode_label = {"move": "移动", "copy": "复制"}.get(str(organize_mode), str(organize_mode))
        msg += f"📦 <b>整理方式</b>：{_html_escape(mode_label)}\n"

    errors = data.get("errors") or []
    if isinstance(errors, list) and errors:
        msg += "\n📎 <b>明细</b>：\n"
        for item in errors[:5]:
            if isinstance(item, dict):
                n = _html_escape(item.get("name") or "-")
                reason = _html_escape(item.get("reason") or item.get("error") or "未知")
                msg += f"  • {n}: {reason}\n"
            else:
                msg += f"  • {_html_escape(item)}\n"
        if len(errors) > 5:
            msg += f"  … 共 {len(errors)} 条\n"

    return msg.rstrip()
