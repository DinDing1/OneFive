"""
日志 API 路由

提供日志查看接口：
- GET /api/logs: 获取最近日志（支持行数限制和关键词过滤）
- GET /api/logs/stream: SSE 实时日志流
"""
import re
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from ..paths import LOG_FILE
from ..logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/logs", tags=["日志"])


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
        if not LOG_FILE.exists():
            return {"lines": [], "total": 0}

        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        # 从末尾取指定行数
        result_lines = all_lines[-lines:]

        # 筛选
        if level:
            level_upper = level.upper()
            result_lines = [l for l in result_lines if f"[{level_upper}]" in l]
        if keyword:
            result_lines = [l for l in result_lines if keyword in l]

        # 解析每行
        parsed = []
        for line in result_lines:
            parsed.append(_parse_log_line(line.rstrip()))

        return {"lines": parsed, "total": len(all_lines)}

    except Exception as e:
        logger.error(f"读取日志失败: {e}")
        return {"lines": [], "total": 0}


@router.get("/stream", summary="实时日志流")
async def stream_logs(
    level: str = Query(default="", description="日志级别筛选"),
    keyword: str = Query(default="", description="关键词筛选"),
):
    """SSE 实时日志流，从日志文件末尾开始追加读取"""
    async def event_generator():
        if not LOG_FILE.exists():
            yield "data: {\"type\": \"error\", \"message\": \"日志文件不存在\"}\n\n"
            return

        # 从文件末尾开始
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            f.seek(0, 2)  # 跳到文件末尾
            while True:
                line = f.readline()
                if line:
                    line = line.rstrip()
                    if level and f"[{level.upper()}]" not in line:
                        continue
                    if keyword and keyword not in line:
                        continue
                    parsed = _parse_log_line(line)
                    import json
                    yield f"data: {json.dumps(parsed, ensure_ascii=False)}\n\n"
                else:
                    # 没有新行，发送心跳
                    yield ": heartbeat\n\n"
                    import asyncio
                    await asyncio.sleep(1)

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
