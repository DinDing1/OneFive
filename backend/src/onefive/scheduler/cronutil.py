"""Cron 工具：校验、解析、人类可读描述、与 UI 预设互转。"""
from __future__ import annotations

from typing import Any, Dict


def parse_cron(expr: str) -> Dict[str, str]:
    """解析 5 段 cron：分 时 日 月 周。"""
    parts = (expr or "").strip().split()
    if len(parts) != 5:
        raise ValueError(f"无效 Cron（需要 5 段）: {expr!r}")
    minute, hour, day, month, day_of_week = parts
    return {
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "day_of_week": day_of_week,
    }


def validate_cron(expr: str) -> str:
    """校验并规范化 cron 表达式，失败抛 ValueError。"""
    parsed = parse_cron(expr)
    for key, value in parsed.items():
        if not value:
            raise ValueError(f"Cron 字段 {key} 为空")
    return " ".join(
        [
            parsed["minute"],
            parsed["hour"],
            parsed["day"],
            parsed["month"],
            parsed["day_of_week"],
        ]
    )


def cron_to_label(expr: str) -> str:
    """把常见 cron 转成中文可读；无法识别则原样返回。"""
    try:
        p = parse_cron(expr)
    except ValueError:
        return (expr or "").strip() or "-"

    minute, hour, day, month, dow = (
        p["minute"],
        p["hour"],
        p["day"],
        p["month"],
        p["day_of_week"],
    )

    def _pad_time() -> str:
        try:
            h = int(hour)
            m = int(minute)
            return f"{h:02d}:{m:02d}"
        except ValueError:
            return f"{hour}:{minute}"

    # 每 N 分钟：*/N * * * * 或 * * * * *
    if hour == "*" and day == "*" and month == "*" and dow == "*":
        if minute == "*":
            return "每分钟"
        if minute.startswith("*/"):
            try:
                n = int(minute[2:])
                if n <= 1:
                    return "每分钟"
                return f"每 {n} 分钟"
            except ValueError:
                pass

    # 每 N 小时：m */N * * *
    if (
        minute.isdigit()
        and hour.startswith("*/")
        and day == "*"
        and month == "*"
        and dow == "*"
    ):
        try:
            n = int(hour[2:])
            m = int(minute)
            if m == 0:
                return f"每 {n} 小时"
            return f"每 {n} 小时（第 {m} 分）"
        except ValueError:
            pass

    # 每天：m h * * *
    if day == "*" and month == "*" and dow == "*" and minute.isdigit() and hour.isdigit():
        return f"每天 {_pad_time()}"

    # 每周某天：m h * * dow
    if day == "*" and month == "*" and minute.isdigit() and hour.isdigit() and dow.isdigit():
        names = ["一", "二", "三", "四", "五", "六", "日"]
        try:
            idx = int(dow)
            if idx == 0 or idx == 7:
                w = "日"
            elif 1 <= idx <= 6:
                w = names[idx - 1]
            else:
                w = str(idx)
            return f"每周{w} {_pad_time()}"
        except ValueError:
            pass

    return expr.strip()


def preset_to_cron(
    frequency: str,
    hour: int = 3,
    minute: int = 0,
    interval: int = 6,
    weekday: int = 1,
) -> str:
    """UI 预设 → cron。

    frequency: minutely | hourly | daily | weekly
    - minutely: interval = 每 N 分钟
    - hourly: interval = 每 N 小时，minute = 整点第几分
    weekday: 1=周一 ... 6=周六, 0=周日
    """
    hour = max(0, min(23, int(hour)))
    minute = max(0, min(59, int(minute)))
    frequency = (frequency or "daily").lower()

    if frequency in {"minutely", "minute", "every_minute"}:
        interval = max(1, min(60, int(interval or 1)))
        if interval <= 1:
            return "* * * * *"
        return f"*/{interval} * * * *"

    if frequency == "hourly":
        interval = max(1, min(24, int(interval or 1)))
        return f"{minute} */{interval} * * *"

    if frequency == "weekly":
        weekday = int(weekday) % 7
        return f"{minute} {hour} * * {weekday}"

    # daily
    return f"{minute} {hour} * * *"


def cron_to_preset(expr: str) -> Dict[str, Any]:
    """cron → UI 预设字段；无法解析时 frequency=custom。"""
    try:
        p = parse_cron(expr)
    except ValueError:
        return {
            "frequency": "custom",
            "hour": 3,
            "minute": 0,
            "interval": 6,
            "weekday": 1,
            "cron": (expr or "").strip(),
        }

    minute, hour, day, month, dow = (
        p["minute"],
        p["hour"],
        p["day"],
        p["month"],
        p["day_of_week"],
    )

    # 每 N 分钟
    if hour == "*" and day == "*" and month == "*" and dow == "*":
        if minute == "*":
            return {
                "frequency": "minutely",
                "hour": 0,
                "minute": 0,
                "interval": 1,
                "weekday": 1,
                "cron": expr.strip(),
            }
        if minute.startswith("*/"):
            try:
                n = max(1, int(minute[2:]))
                return {
                    "frequency": "minutely",
                    "hour": 0,
                    "minute": 0,
                    "interval": n,
                    "weekday": 1,
                    "cron": expr.strip(),
                }
            except ValueError:
                pass

    # 每 N 小时
    if (
        minute.isdigit()
        and hour.startswith("*/")
        and day == "*"
        and month == "*"
        and dow == "*"
    ):
        try:
            return {
                "frequency": "hourly",
                "hour": 0,
                "minute": int(minute),
                "interval": int(hour[2:]),
                "weekday": 1,
                "cron": expr.strip(),
            }
        except ValueError:
            pass

    if day == "*" and month == "*" and minute.isdigit() and hour.isdigit():
        base = {
            "hour": int(hour),
            "minute": int(minute),
            "interval": 6,
            "cron": expr.strip(),
        }
        if dow == "*":
            return {**base, "frequency": "daily", "weekday": 1}
        if dow.isdigit():
            return {**base, "frequency": "weekly", "weekday": int(dow) % 7}

    return {
        "frequency": "custom",
        "hour": 3,
        "minute": 0,
        "interval": 6,
        "weekday": 1,
        "cron": expr.strip(),
    }
