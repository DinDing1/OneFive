"""SSE 公共工具：统一心跳、线程任务推送与短时任务缓存。

飞牛 OS 应用中心统一网关会对空闲 HTTP 长连接断连；前端 axios 默认 30s 超时。
长耗时任务统一走 SSE（text/event-stream）+ 注释心跳 `: heartbeat`，
不要依赖拉长 axios timeout。
"""
from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from typing import Any, AsyncIterator, Callable, Dict, Optional

from fastapi.responses import StreamingResponse

from .exceptions import AppError
from .logger import get_logger

logger = get_logger(__name__)

# 禁止反向代理缓冲，保持长连接
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

# 任务缓存默认 10 分钟（仅用于 POST 建任务 → GET 拉流的两段式 SSE）
_DEFAULT_JOB_TTL_SEC = 600


class SseJobStore:
    """进程内短时任务缓存：解决 EventSource 仅支持 GET、复杂参数需 POST 的问题。"""

    def __init__(self, ttl_sec: int = _DEFAULT_JOB_TTL_SEC) -> None:
        self._ttl = max(60, int(ttl_sec))
        self._lock = threading.Lock()
        self._items: Dict[str, Dict[str, Any]] = {}

    def create(self, payload: Any) -> str:
        self._cleanup()
        job_id = uuid.uuid4().hex
        with self._lock:
            self._items[job_id] = {"payload": payload, "created_at": time.time()}
        return job_id

    def pop(self, job_id: str) -> Optional[Any]:
        self._cleanup()
        with self._lock:
            item = self._items.pop(str(job_id or ""), None)
        if not item:
            return None
        return item.get("payload")

    def _cleanup(self) -> None:
        now = time.time()
        with self._lock:
            expired = [k for k, v in self._items.items() if now - float(v.get("created_at") or 0) > self._ttl]
            for k in expired:
                self._items.pop(k, None)


# 模块级默认任务缓存（各 API 可共用）
job_store = SseJobStore()


def _json_data(evt: Dict[str, Any]) -> str:
    return "data: " + json.dumps(evt, ensure_ascii=False) + "\n\n"


def thread_worker_stream(
    worker: Callable[[Callable[[Dict[str, Any]], None]], None],
    *,
    start_event: Optional[Dict[str, Any]] = None,
    thread_name: str = "sse-worker",
    heartbeat_sec: float = 2.0,
) -> Callable[[], AsyncIterator[str]]:
    """把同步 worker 放到后台线程，经队列推送 SSE 事件，并周期性心跳保活。

    worker 签名：worker(on_progress) -> None
    - 通过 on_progress(dict) 推送中间事件
    - 最终应自行 put type=done/error；若抛异常则自动转 error
    - 若 worker 正常返回且未发 done/error，自动补一条 done
    """

    async def event_generator() -> AsyncIterator[str]:
        if start_event is not None:
            yield _json_data(start_event)

        q: queue.Queue = queue.Queue()
        state = {"done": False, "emitted_terminal": False}

        def on_progress(evt: Dict[str, Any]) -> None:
            if not isinstance(evt, dict):
                return
            if evt.get("type") in ("done", "error"):
                state["emitted_terminal"] = True
            q.put(evt)

        def runner() -> None:
            try:
                worker(on_progress)
                if not state["emitted_terminal"]:
                    q.put({"type": "done"})
            except AppError as e:
                logger.warning(f"[SSE] 业务失败 ({thread_name}): {e.message}")
                q.put({"type": "error", "message": e.message, "code": e.code})
            except Exception as e:
                logger.error(f"[SSE] 异常 ({thread_name}): {e}", exc_info=True)
                q.put({"type": "error", "message": str(e)})
            finally:
                state["done"] = True

        thread = threading.Thread(target=runner, name=thread_name, daemon=True)
        thread.start()

        while True:
            try:
                evt = q.get(timeout=max(0.5, float(heartbeat_sec)))
            except queue.Empty:
                yield ": heartbeat\n\n"
                if state["done"] and q.empty() and not thread.is_alive():
                    if not state["emitted_terminal"]:
                        yield _json_data({"type": "error", "message": "任务线程异常结束"})
                    break
                continue

            yield _json_data(evt)
            if evt.get("type") in ("done", "error"):
                state["emitted_terminal"] = True
                break

        thread.join(timeout=1.0)

    return event_generator


def streaming_response_from_thread(
    worker: Callable[[Callable[[Dict[str, Any]], None]], None],
    *,
    start_event: Optional[Dict[str, Any]] = None,
    thread_name: str = "sse-worker",
    heartbeat_sec: float = 2.0,
) -> StreamingResponse:
    """便捷封装：线程 worker → StreamingResponse。"""
    gen = thread_worker_stream(
        worker,
        start_event=start_event,
        thread_name=thread_name,
        heartbeat_sec=heartbeat_sec,
    )
    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


async def aiter_with_heartbeat(
    source: AsyncIterator[Dict[str, Any]],
    *,
    heartbeat_sec: float = 2.0,
) -> AsyncIterator[str]:
    """给已有 async 事件迭代器加心跳（用于 organize_batch_stream 等）。"""
    agen = source.__aiter__()
    while True:
        try:
            evt = await __import__("asyncio").wait_for(agen.__anext__(), timeout=max(0.5, float(heartbeat_sec)))
        except __import__("asyncio").TimeoutError:
            yield ": heartbeat\n\n"
            continue
        except StopAsyncIteration:
            break
        yield _json_data(evt)
        if isinstance(evt, dict) and evt.get("type") in ("done", "error"):
            break


async def await_with_heartbeat(coro, *, heartbeat_sec: float = 2.0):
    """等待一个协程，期间以异步生成器形式产出心跳；最终产出 ("result", value) 或 ("error", exc)。

    用法：
        async for kind, payload in await_with_heartbeat(asyncio.to_thread(fn)):
            if kind == "heartbeat": yield payload
            elif kind == "result": ...
            elif kind == "error": ...
    """
    import asyncio

    task = asyncio.create_task(coro)
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=max(0.5, float(heartbeat_sec)))
            if not done:
                yield "heartbeat", ": heartbeat\n\n"
        yield "result", task.result()
    except Exception as e:
        yield "error", e
