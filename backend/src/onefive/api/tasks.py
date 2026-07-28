"""定时任务 API。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..models.schemas import ApiResponse
from ..scheduler import get_scheduler_service
from ..scheduler.cronutil import preset_to_cron, validate_cron
from ..logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["定时任务"])


class TaskUpdateRequest(BaseModel):
    """更新任务配置（仅开关与调度，整理参数走全局设置）。"""
    enabled: Optional[bool] = None
    cron: Optional[str] = None
    # UI 预设（若提供且无 cron，则生成 cron）
    frequency: Optional[str] = None  # minutely | hourly | daily | weekly
    hour: Optional[int] = None
    minute: Optional[int] = None
    interval: Optional[int] = None  # minutely=每N分钟 / hourly=每N小时
    weekday: Optional[int] = None


@router.get("", summary="任务列表")
@router.get("/", summary="任务列表")
async def list_tasks():
    service = get_scheduler_service()
    return ApiResponse(code=0, message="ok", data={"tasks": service.list_tasks()})


@router.get("/{task_id}", summary="任务详情")
async def get_task(task_id: str):
    service = get_scheduler_service()
    try:
        data = service.get_task_status(task_id)
    except KeyError:
        return ApiResponse(code=-1, message=f"未知任务: {task_id}")
    return ApiResponse(code=0, message="ok", data=data)


@router.put("/{task_id}", summary="更新任务")
async def update_task(task_id: str, req: TaskUpdateRequest):
    service = get_scheduler_service()
    try:
        cron = req.cron
        if (not cron) and req.frequency:
            cron = preset_to_cron(
                req.frequency,
                hour=req.hour if req.hour is not None else 3,
                minute=req.minute if req.minute is not None else 0,
                interval=req.interval if req.interval is not None else 6,
                weekday=req.weekday if req.weekday is not None else 1,
            )
        if cron is not None:
            cron = validate_cron(cron)

        data = service.update_task(
            task_id,
            enabled=req.enabled,
            cron=cron,
        )
        return ApiResponse(code=0, message="已更新", data=data)
    except KeyError:
        return ApiResponse(code=-1, message=f"未知任务: {task_id}")
    except ValueError as e:
        return ApiResponse(code=-1, message=str(e))
    except Exception as e:
        logger.exception(f"更新任务失败: {task_id}")
        return ApiResponse(code=-1, message=str(e))


@router.post("/{task_id}/run", summary="立即执行")
async def run_task(task_id: str):
    service = get_scheduler_service()
    try:
        # 校验存在
        service.get_task_status(task_id)
    except KeyError:
        return ApiResponse(code=-1, message=f"未知任务: {task_id}")

    result = await service.run_task_background(task_id, trigger_type="manual")
    if not result.get("success") and result.get("running"):
        return ApiResponse(code=-1, message=result.get("message") or "任务运行中", data=result)
    return ApiResponse(code=0, message=result.get("message") or "已开始", data=result)
