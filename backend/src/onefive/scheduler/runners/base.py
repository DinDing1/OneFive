"""定时任务 runner 协议与公共结果结构。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime


def now_str() -> str:
    """本地时间字符串。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_result(
    *,
    success: bool,
    message: str = "",
    trigger: str = "manual",
    started_at: str = "",
    finished_at: str = "",
    **extra: Any,
) -> Dict[str, Any]:
    """统一任务结果字典。"""
    data: Dict[str, Any] = {
        "success": success,
        "message": message,
        "trigger": trigger,
        "started_at": started_at or now_str(),
        "finished_at": finished_at or now_str(),
    }
    data.update(extra)
    return data


def trim_errors(errors: Optional[List[Dict[str, str]]], limit: int = 20) -> List[Dict[str, str]]:
    """截断错误列表，避免 last_result 过大。"""
    if not errors:
        return []
    return errors[:limit]
