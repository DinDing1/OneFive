"""定时任务调度服务。

基于 APScheduler AsyncIOScheduler：
- 应用启动时 start（失败不阻塞 HTTP）
- 按 setting 注册/热更新 cron job
- 支持立即执行、互斥、最近结果落库
- 上轮未结束时跳过下次调度，避免重复执行
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, Optional

from ..logger import get_logger
from ..services.config_service import get_config_service
from .cronutil import cron_to_label, cron_to_preset, validate_cron
from .registry import TASK_DEFS, get_task_def, list_task_defs, resolve_runner

logger = get_logger(__name__)

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    HAS_APSCHEDULER = True
except Exception:  # pragma: no cover
    HAS_APSCHEDULER = False
    AsyncIOScheduler = None  # type: ignore
    CronTrigger = None  # type: ignore


def _truthy(value: Optional[str], default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _dt_str(dt: Any) -> str:
    if not dt:
        return ""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


class SchedulerService:
    """进程内单例调度器。"""

    def __init__(self) -> None:
        self._scheduler = None
        self._locks: Dict[str, asyncio.Lock] = {}
        self._running: Dict[str, bool] = {}
        self._last_error: Dict[str, str] = {}
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    # ---------- 生命周期 ----------

    async def start(self) -> None:
        """启动调度器并加载任务（可在 lifespan 后台调用）。"""
        self._main_loop = asyncio.get_running_loop()
        if not HAS_APSCHEDULER:
            logger.warning(
                "未安装 APScheduler，定时任务不可用（pip install apscheduler）"
            )
            return
        if self._scheduler is not None:
            return
        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
        self._scheduler.start()
        self.reload_all_jobs()
        logger.info("定时任务调度器已启动")

    async def shutdown(self) -> None:
        """关闭调度器。"""
        if self._scheduler is None:
            return
        try:
            self._scheduler.shutdown(wait=False)
        except Exception as e:
            logger.debug(f"调度器关闭: {e}")
        self._scheduler = None
        logger.info("定时任务调度器已关闭")

    # ---------- 配置读写 ----------

    def _cfg(self):
        return get_config_service()

    def is_enabled(self, task_id: str) -> bool:
        defn = get_task_def(task_id)
        return _truthy(self._cfg().get(defn["enabled_key"]), False)

    def get_cron(self, task_id: str) -> str:
        defn = get_task_def(task_id)
        raw = self._cfg().get(defn["cron_key"])
        if not raw or not str(raw).strip():
            return defn["default_cron"]
        try:
            return validate_cron(str(raw))
        except ValueError:
            return defn["default_cron"]

    def _save_last(self, task_id: str, result: Dict[str, Any]) -> None:
        defn = get_task_def(task_id)
        cfg = self._cfg()
        finished = result.get("finished_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cfg.set(defn["last_run_key"], str(finished), f"{defn['name']}上次运行时间")
        slim = {
            k: result.get(k)
            for k in (
                "success",
                "message",
                "trigger",
                "started_at",
                "finished_at",
                "scanned",
                "processed",
                "success_count",
                "failed",
                "skipped",
                "errors",
            )
            if k in result
        }
        cfg.set(
            defn["last_result_key"],
            json.dumps(slim, ensure_ascii=False),
            f"{defn['name']}上次运行结果",
        )

    def _load_last_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        defn = get_task_def(task_id)
        raw = self._cfg().get(defn["last_result_key"])
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    # ---------- Job 管理 ----------

    def reload_all_jobs(self) -> None:
        """按当前配置重建全部 job。"""
        if not self._scheduler:
            return
        for task_id in list(TASK_DEFS.keys()):
            try:
                self._upsert_job(task_id, self.get_cron(task_id), self.is_enabled(task_id))
            except Exception as e:
                logger.warning(f"加载定时任务失败 {task_id}: {e}")

    def _upsert_job(self, task_id: str, cron_expr: str, enabled: bool) -> None:
        if not self._scheduler or not HAS_APSCHEDULER:
            return
        job_id = f"task:{task_id}"
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass
        if not enabled:
            logger.info(f"定时任务已禁用: {task_id}")
            return
        fields = validate_cron(cron_expr)
        from .cronutil import parse_cron

        parts = parse_cron(fields)
        trigger = CronTrigger(
            minute=parts["minute"],
            hour=parts["hour"],
            day=parts["day"],
            month=parts["month"],
            day_of_week=parts["day_of_week"],
            timezone="Asia/Shanghai",
        )

        async def _launch(tid: str = task_id) -> None:
            await self.run_task(tid, trigger_type="scheduled")

        self._scheduler.add_job(
            _launch,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        logger.info(
            f"定时任务已注册: {task_id} cron={fields} ({cron_to_label(fields)})"
        )

    def update_task(
        self,
        task_id: str,
        *,
        enabled: Optional[bool] = None,
        cron: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """更新任务开关/cron，并热更新调度。"""
        defn = get_task_def(task_id)
        cfg = self._cfg()

        if enabled is not None:
            cfg.set(
                defn["enabled_key"],
                "1" if enabled else "0",
                f"{defn['name']}启用",
            )

        if cron is not None:
            cron_norm = validate_cron(cron)
            cfg.set(defn["cron_key"], cron_norm, f"{defn['name']}Cron")

        # 预留：未来任务可通过 extra 写入各自 setting
        if extra:
            logger.debug(
                f"update_task extra ignored for {task_id}: {list(extra.keys())}"
            )

        self._upsert_job(task_id, self.get_cron(task_id), self.is_enabled(task_id))
        return self.get_task_status(task_id)

    # ---------- 执行 ----------

    def _lock_for(self, task_id: str) -> asyncio.Lock:
        if task_id not in self._locks:
            self._locks[task_id] = asyncio.Lock()
        return self._locks[task_id]

    def is_running(self, task_id: str) -> bool:
        return bool(self._running.get(task_id))

    async def run_task(self, task_id: str, trigger_type: str = "manual") -> Dict[str, Any]:
        """执行任务（互斥）。长任务在线程池中跑 runner。"""
        get_task_def(task_id)
        lock = self._lock_for(task_id)
        if lock.locked() or self._running.get(task_id):
            # 上轮未结束：跳过本次（含定时触发），避免重复执行
            if trigger_type in {"scheduled", "cron"}:
                msg = "上轮仍在执行，已跳过本次调度"
                logger.info(f"定时任务跳过: {task_id} — {msg}")
            else:
                msg = "任务正在运行中，请等待本轮完成"
                logger.info(f"定时任务拒绝重复触发: {task_id}")
            return {
                "success": True,
                "skipped": True,
                "message": msg,
                "running": True,
                "task_id": task_id,
                "trigger": trigger_type,
            }

        await lock.acquire()
        self._running[task_id] = True
        self._last_error.pop(task_id, None)
        logger.info(f"开始执行定时任务: {task_id} trigger={trigger_type}")

        try:
            try:
                from ..services.organize_service import get_organize_service

                if self._main_loop is None:
                    self._main_loop = asyncio.get_running_loop()
                get_organize_service()._main_loop = self._main_loop
            except Exception:
                pass

            runner = resolve_runner(task_id)
            result = await asyncio.to_thread(runner, trigger_type)
            if not isinstance(result, dict):
                result = {
                    "success": False,
                    "message": "runner 返回无效",
                    "trigger": trigger_type,
                }
            self._save_last(task_id, result)
            await self._send_summary_notify(task_id, result)
            return result
        except Exception as e:
            logger.exception(f"定时任务执行失败: {task_id}: {e}")
            self._last_error[task_id] = str(e)
            result = {
                "success": False,
                "message": str(e),
                "trigger": trigger_type,
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            try:
                self._save_last(task_id, result)
            except Exception:
                pass
            return result
        finally:
            self._running[task_id] = False
            lock.release()

    async def run_task_background(self, task_id: str, trigger_type: str = "manual") -> Dict[str, Any]:
        """立即触发：若空闲则后台跑，API 马上返回。"""
        if self.is_running(task_id) or self._lock_for(task_id).locked():
            return {
                "success": True,
                "skipped": True,
                "message": "任务正在运行中，请等待本轮完成",
                "running": True,
                "task_id": task_id,
            }

        async def _bg() -> None:
            try:
                await self.run_task(task_id, trigger_type=trigger_type)
            except Exception as e:
                logger.error(f"后台任务异常 {task_id}: {e}")

        asyncio.create_task(_bg(), name=f"task-run-{task_id}")
        return {
            "success": True,
            "message": "任务已开始执行",
            "running": True,
            "task_id": task_id,
        }

    async def _send_summary_notify(self, task_id: str, result: Dict[str, Any]) -> None:
        """任务结束汇总通知（跳过仍在运行类结果，避免误报）。"""
        if result.get("skipped"):
            return
        # runner 显式关闭通知：如云盘整理无视频/未发生整理
        if result.get("notify") is False:
            return
        try:
            from ..notification import get_notification_manager
            from ..notification.format import format_task_summary_notify

            defn = get_task_def(task_id)
            msg = format_task_summary_notify(
                task_name=defn["name"],
                success=bool(result.get("success")),
                result=result,
            )
            manager = get_notification_manager()
            await manager.send_all(msg)
        except Exception as e:
            logger.debug(f"任务汇总通知跳过: {e}")

    # ---------- 状态 ----------

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        defn = get_task_def(task_id)
        cfg = self._cfg()
        cron = self.get_cron(task_id)
        enabled = self.is_enabled(task_id)
        last_run = cfg.get(defn["last_run_key"]) or ""
        last_result = self._load_last_result(task_id)
        next_run = ""
        if self._scheduler and enabled:
            job = self._scheduler.get_job(f"task:{task_id}")
            if job and job.next_run_time:
                next_run = _dt_str(job.next_run_time)

        return {
            "id": task_id,
            "name": defn["name"],
            "description": defn.get("description") or "",
            "icon": defn.get("icon") or "task",
            "category": defn.get("category") or "general",
            "category_label": defn.get("category_label") or "通用",
            "enabled": enabled,
            "cron": cron,
            "cron_label": cron_to_label(cron),
            "schedule_preset": cron_to_preset(cron),
            "next_run_time": next_run,
            "last_run_time": last_run,
            "last_result": last_result,
            "running": self.is_running(task_id),
            "last_error": self._last_error.get(task_id) or "",
            "scheduler_ready": bool(self._scheduler) and HAS_APSCHEDULER,
        }

    def list_tasks(self) -> list[Dict[str, Any]]:
        return [self.get_task_status(t["id"]) for t in list_task_defs()]


_scheduler_service: Optional[SchedulerService] = None


def get_scheduler_service() -> SchedulerService:
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
