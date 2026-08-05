"""SSE 公共工具：统一心跳、线程任务推送与短时任务缓存。

飞牛 OS 应用中心统一网关会对空闲 HTTP 长连接断连；前端 axios 默认 30s 超时。
长耗时任务统一走 SSE（text/event-stream）+ 注释心跳 `: heartbeat`，
不要依赖拉长 axios timeout。

两段式 SSE（POST 建任务 → GET 拉流）支持：
1. 同一 job_id 可被多个 EventSource 连接订阅（网关/浏览器自动重连）
2. 仅第一个连接 claim 后启动 worker，后续连接重放历史并订阅后续进度
3. 任务结束后仍保留一段时间，避免“后台已在跑，前端却提示任务不存在”
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import uuid
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

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
# 完成后额外保留，方便重连拿到最终结果
_DEFAULT_DONE_KEEP_SEC = 120
# 单任务最多缓存的历史事件数，防止内存膨胀
_MAX_HISTORY = 500


def _json_data(evt: Dict[str, Any]) -> str:
    """把事件字典编码成 SSE data 行。"""
    return "data: " + json.dumps(evt, ensure_ascii=False) + "\n\n"


class _SseJob:
    """单个 SSE 任务：payload + 状态 + 历史事件 + 订阅者队列。"""

    __slots__ = (
        "payload",
        "status",
        "created_at",
        "finished_at",
        "history",
        "subscribers",
        "claimed",
        "lock",
    )

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        # pending | running | done | error
        self.status = "pending"
        self.created_at = time.time()
        self.finished_at: Optional[float] = None
        self.history: List[Dict[str, Any]] = []
        self.subscribers: List[queue.Queue] = []
        self.claimed = False
        self.lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        """订阅后续事件；队列会先塞入当前历史，方便重连重放。"""
        q: queue.Queue = queue.Queue()
        with self.lock:
            for evt in self.history:
                q.put(evt)
            # 已结束但历史缺终态时，补一条，保证新订阅者能退出
            if self.status in ("done", "error") and (
                not self.history or self.history[-1].get("type") not in ("done", "error")
            ):
                q.put({"type": self.status, "message": "任务已结束"})
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """取消订阅，避免结束后队列泄漏。"""
        with self.lock:
            try:
                self.subscribers.remove(q)
            except ValueError:
                pass

    def publish(self, evt: Dict[str, Any]) -> None:
        """广播事件给所有订阅者，并写入历史。"""
        if not isinstance(evt, dict):
            return
        with self.lock:
            self.history.append(evt)
            if len(self.history) > _MAX_HISTORY:
                self.history = self.history[-_MAX_HISTORY:]
            if evt.get("type") in ("done", "error"):
                self.status = "done" if evt.get("type") == "done" else "error"
                self.finished_at = time.time()
            for sub in list(self.subscribers):
                try:
                    sub.put(evt)
                except Exception:
                    pass

    def try_claim(self) -> bool:
        """首次 claim 成功返回 True，后续连接返回 False（只旁路订阅）。"""
        with self.lock:
            if self.claimed:
                return False
            self.claimed = True
            self.status = "running"
            return True


class SseJobStore:
    """进程内短时任务缓存：解决 EventSource 仅支持 GET、复杂参数需 POST 的问题。

    新能力：
    - create(payload) -> job_id
    - get(job_id) -> job 或 None（不删除，支持重连）
    - claim 由 streaming_response_from_job 内部完成
    - 兼容旧 pop()：一次性取出 payload（仅遗留场景，新代码勿用）
    """

    def __init__(
        self,
        ttl_sec: int = _DEFAULT_JOB_TTL_SEC,
        done_keep_sec: int = _DEFAULT_DONE_KEEP_SEC,
    ) -> None:
        self._ttl = max(60, int(ttl_sec))
        self._done_keep = max(10, int(done_keep_sec))
        self._lock = threading.Lock()
        self._items: Dict[str, _SseJob] = {}

    def create(self, payload: Any) -> str:
        """创建短时任务，返回 job_id。"""
        self._cleanup()
        job_id = uuid.uuid4().hex
        with self._lock:
            self._items[job_id] = _SseJob(payload)
        return job_id

    def get(self, job_id: str) -> Optional[_SseJob]:
        """按 id 获取任务（不删除），供多连接订阅。"""
        self._cleanup()
        with self._lock:
            return self._items.get(str(job_id or ""))

    def pop(self, job_id: str) -> Optional[Any]:
        """兼容旧接口：一次性取出并删除 payload。

        注意：EventSource 会自动重连，新代码请改用 streaming_response_from_job。
        """
        self._cleanup()
        with self._lock:
            job = self._items.pop(str(job_id or ""), None)
        if not job:
            return None
        return job.payload

    def _cleanup(self) -> None:
        """清理过期/完成后超时的任务。

        规则：
        - pending：超过 TTL 未 claim 才删除（避免建了任务却永不拉流）
        - running：不按 TTL 删除。大文件夹整理可能远超 10 分钟；
          连接断开后 worker 仍持有 job 继续 publish，store 必须保留供重连订阅
        - done/error：结束后再保留 done_keep，方便重连拿到终态
        """
        now = time.time()
        with self._lock:
            expired: List[str] = []
            for k, job in self._items.items():
                age = now - float(job.created_at or 0)
                status = job.status
                if status in ("done", "error"):
                    finished = float(job.finished_at or job.created_at or 0)
                    if now - finished > self._done_keep:
                        expired.append(k)
                elif status == "running":
                    # 运行中永不因 TTL 删除，否则重连会报“任务不存在或已过期”
                    continue
                elif age > self._ttl:
                    # pending 超时
                    expired.append(k)
            for k in expired:
                self._items.pop(k, None)


# 模块级默认任务缓存（各 API 可共用）
job_store = SseJobStore()


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

    说明：此函数适合「单连接即开即用」场景。
    两段式 job（POST→GET，可能重连）请用 streaming_response_from_job。
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
    """便捷封装：thread_worker_stream + StreamingResponse。"""
    gen = thread_worker_stream(
        worker,
        start_event=start_event,
        thread_name=thread_name,
        heartbeat_sec=heartbeat_sec,
    )
    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


def streaming_response_from_job(
    job_id: str,
    worker_factory: Callable[[Any], Callable[[Callable[[Dict[str, Any]], None]], None]],
    *,
    start_event: Optional[Dict[str, Any]] = None,
    not_found_message: str = "任务不存在或已过期",
    thread_name: str = "sse-job-worker",
    heartbeat_sec: float = 2.0,
    store: Optional[SseJobStore] = None,
) -> StreamingResponse:
    """两段式 SSE 专用：按 job_id claim/订阅，支持 EventSource 自动重连。

    流程：
    1. 查 job；不存在 → 推送 error
    2. 订阅 job 事件队列（先重放历史）
    3. 若本连接首次 claim 成功：启动 worker，进度写入 job.publish
    4. 本连接只负责读订阅队列并输出 SSE，直到 done/error

    worker_factory(payload) -> worker(on_progress)
    """
    store = store or job_store
    job = store.get(job_id)

    async def event_generator() -> AsyncIterator[str]:
        if job is None:
            yield _json_data({"type": "error", "message": not_found_message})
            return

        # 先订阅，避免 worker 刚启动就丢首包事件
        sub_q = job.subscribe()
        claimed = job.try_claim()

        if claimed:
            # 首连：可选 start 写入共享历史，所有连接（含重连）都能看到
            if start_event is not None:
                job.publish(start_event)

            payload = job.payload
            worker = worker_factory(payload)
            state = {"emitted_terminal": False}

            def on_progress(evt: Dict[str, Any]) -> None:
                if not isinstance(evt, dict):
                    return
                if evt.get("type") in ("done", "error"):
                    state["emitted_terminal"] = True
                job.publish(evt)

            def runner() -> None:
                try:
                    worker(on_progress)
                    if not state["emitted_terminal"]:
                        job.publish({"type": "done"})
                except AppError as e:
                    logger.warning(f"[SSE] 业务失败 ({thread_name}): {e.message}")
                    job.publish({"type": "error", "message": e.message, "code": e.code})
                except Exception as e:
                    logger.error(f"[SSE] 异常 ({thread_name}): {e}", exc_info=True)
                    job.publish({"type": "error", "message": str(e)})

            thread = threading.Thread(target=runner, name=thread_name, daemon=True)
            thread.start()
            logger.info(f"[SSE] job claim 成功，启动 worker job_id={job_id} name={thread_name}")
        else:
            logger.info(
                f"[SSE] job 重连/旁路订阅 job_id={job_id} status={job.status} history={len(job.history)}"
            )

        try:
            while True:
                try:
                    evt = sub_q.get(timeout=max(0.5, float(heartbeat_sec)))
                except queue.Empty:
                    yield ": heartbeat\n\n"
                    # 任务已结束且队列空：退出，避免僵尸连接
                    if job.status in ("done", "error") and sub_q.empty():
                        break
                    continue

                yield _json_data(evt)
                if isinstance(evt, dict) and evt.get("type") in ("done", "error"):
                    break
        finally:
            job.unsubscribe(sub_q)

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=SSE_HEADERS)


async def aiter_with_heartbeat(
    source: AsyncIterator[Dict[str, Any]],
    *,
    heartbeat_sec: float = 2.0,
) -> AsyncIterator[str]:
    """给已有 async 事件迭代器加心跳（用于兼容旧直连参数场景）。"""
    agen = source.__aiter__()
    while True:
        try:
            evt = await asyncio.wait_for(agen.__anext__(), timeout=max(0.5, float(heartbeat_sec)))
        except asyncio.TimeoutError:
            yield ": heartbeat\n\n"
            continue
        except StopAsyncIteration:
            break
        yield _json_data(evt)
        if isinstance(evt, dict) and evt.get("type") in ("done", "error"):
            break


async def await_with_heartbeat(coro, *, heartbeat_sec: float = 2.0):
    """等待一个协程，期间以异步生成器形式产出心跳；最终产出 result/error。

    用法：
        async for kind, payload in await_with_heartbeat(asyncio.to_thread(fn)):
            if kind == "heartbeat": yield payload
            elif kind == "result": ...
            elif kind == "error": ...
    """
    task = asyncio.create_task(coro)
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=max(0.5, float(heartbeat_sec)))
            if not done:
                yield "heartbeat", ": heartbeat\n\n"
        yield "result", task.result()
    except Exception as e:
        yield "error", e

