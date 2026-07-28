"""定时任务注册表。

扩展新任务：
1. 在 TASK_DEFS 增加定义
2. 在 runners/ 实现 run(trigger) -> dict
3. 前端 Tasks 页按通用字段渲染，无需为每个任务特制 UI
"""
from __future__ import annotations

from typing import Any, Callable, Dict


def _load_auto_organize():
    from .runners.auto_organize import run as run_auto_organize
    return run_auto_organize


TASK_DEFS: Dict[str, Dict[str, Any]] = {
    "auto_organize": {
        "id": "auto_organize",
        "name": "云盘整理",
        "description": "按设置保存路径扫描 115 云盘，识别后归档至媒体库路径。运行中遇调度将自动跳过。",
        "enabled_key": "task_auto_organize_enabled",
        "cron_key": "task_auto_organize_cron",
        "default_cron": "0 3 * * *",
        "last_run_key": "task_auto_organize_last_run",
        "last_result_key": "task_auto_organize_last_result",
        "runner_factory": _load_auto_organize,
        # 通用展示字段，前端按 icon/category 区分任务
        "icon": "organize",
        "category": "media",
        "category_label": "媒体",
    },
}


def get_task_def(task_id: str) -> Dict[str, Any]:
    """获取任务定义；未知 id 抛 KeyError。"""
    if task_id not in TASK_DEFS:
        raise KeyError(f"未知任务: {task_id}")
    return TASK_DEFS[task_id]


def list_task_defs() -> list[Dict[str, Any]]:
    """返回全部任务定义副本。"""
    return [dict(v) for v in TASK_DEFS.values()]


def resolve_runner(task_id: str) -> Callable[..., Dict[str, Any]]:
    """解析并返回可调用 runner。"""
    defn = get_task_def(task_id)
    factory = defn.get("runner_factory")
    if not callable(factory):
        raise RuntimeError(f"任务 {task_id} 未配置 runner")
    runner = factory()
    if not callable(runner):
        raise RuntimeError(f"任务 {task_id} runner 无效")
    return runner
