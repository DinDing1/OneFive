"""
日志 API 路由

提供日志查看接口：
- GET /api/logs: 获取最近日志（支持行数限制和关键词过滤）
- GET /api/logs/stream: SSE 实时日志流
"""
import os
import re
import json
import asyncio
from pathlib import Path
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from ..paths import LOG_FILE
from ..logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/logs", tags=["日志"])


def _read_logs(log_file: Path, lines: int, level: str, keyword: str) -> dict:
    """读取日志文件并按级别/关键词过滤（同步函数，供 asyncio.to_thread 调用）

    大日志文件 readlines() 会阻塞事件循环，提取为独立同步函数后可在线程池中执行。

    Args:
        log_file: 日志文件路径
        lines: 返回的行数（从末尾截取）
        level: 日志级别筛选（INFO/WARNING/ERROR），空串表示不过滤
        keyword: 关键词筛选，空串表示不过滤

    Returns:
        {"lines": [parsed_dict, ...], "total": 原始行数}
        文件不存在或读取异常时返回 {"lines": [], "total": 0}
    """
    if not log_file.exists():
        return {"lines": [], "total": 0}

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
    except Exception:
        return {"lines": [], "total": 0}

    # 从末尾取指定行数
    result_lines = all_lines[-lines:]

    # 按级别筛选
    if level:
        level_upper = level.upper()
        result_lines = [l for l in result_lines if f"[{level_upper}]" in l]
    # 按关键词筛选
    if keyword:
        result_lines = [l for l in result_lines if keyword in l]

    # 解析每行
    parsed = []
    for line in result_lines:
        parsed.append(_parse_log_line(line.rstrip()))

    return {"lines": parsed, "total": len(all_lines)}


@router.get("", summary="获取最近日志")
async def get_logs(
    lines: int = Query(default=200, ge=1, le=2000, description="返回行数"),
    level: str = Query(default="", description="日志级别筛选：INFO/WARNING/ERROR"),
    keyword: str = Query(default="", description="关键词筛选"),
):
    """获取最近的日志内容

    Args:
        lines: 返回的行数，默认 200，最大 2000
        level: 按日志级别筛选
        keyword: 按关键词筛选
    """
    try:
        # 大文件 readlines 会阻塞事件循环，放到线程池执行
        return await asyncio.to_thread(_read_logs, LOG_FILE, lines, level, keyword)
    except Exception as e:
        logger.error(f"读取日志失败: {e}")
        return {"lines": [], "total": 0}


@router.get("/stream", summary="实时日志流")
async def stream_logs(
    request: Request,
    level: str = Query(default="", description="日志级别筛选"),
    keyword: str = Query(default="", description="关键词筛选"),
):
    """SSE 实时日志流，从日志文件末尾开始追加读取

    支持检测客户端断开连接和日志文件轮转（文件变小时从头开始）。
    """
    async def event_generator():
        if not LOG_FILE.exists():
            yield "data: {\"type\": \"error\", \"message\": \"日志文件不存在\"}\n\n"
            return

        # 从文件末尾开始，只推送连接后的新日志
        last_pos = os.path.getsize(LOG_FILE)
        while True:
            # 检测客户端是否已断开连接，断开则停止生成
            if await request.is_disconnected():
                break
            try:
                current_size = os.path.getsize(LOG_FILE)
                # 文件变小，说明发生了日志轮转，从头开始读
                if current_size < last_pos:
                    last_pos = 0
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    f.seek(last_pos)
                    new_lines = f.readlines()
                    last_pos = f.tell()
                for line in new_lines:
                    line = line.rstrip()
                    # 级别 / 关键词过滤
                    if level and f"[{level.upper()}]" not in line:
                        continue
                    if keyword and keyword not in line:
                        continue
                    parsed = _parse_log_line(line)
                    if parsed:
                        yield f"data: {json.dumps(parsed, ensure_ascii=False, default=str)}\n\n"
            except Exception:
                pass
            await asyncio.sleep(1)
            yield ": heartbeat\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _parse_log_line(line: str) -> dict:
    """解析单行日志

    格式：2026-06-24 09:57:46 [INFO] Auth: 扫码登录成功
    """
    pattern = r'^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) \[(\w+)\] (\w+): (.+)$'
    match = re.match(pattern, line)
    if match:
        return {
            "time": match.group(2),  # 只返回时分秒
            "level": match.group(3),
            "module": match.group(4),
            "message": match.group(5),
            "raw": line,
        }
    return {
        "time": "",
        "level": "",
        "module": "",
        "message": line,
        "raw": line,
    }
