"""云盘整理 runner：设置「保存路径」→ 设置「媒体库路径」。

路径约定（与手动整理一致）：
- 扫描源：settings.source_path / source_cid
- 整理目标：settings.media_library_path（由 organize_service 读取拼接）

策略：
- 仅处理 115 云盘保存路径下的视频，归档到媒体库
- 不设单次数量上限，本轮扫描到的视频全部处理完
- 识别失败仅跳过，不中断整轮
- 连续失败过多时熔断，避免异常循环
- 条目间内置短间隔，降低接口压力
- 运行互斥由调度层保证（上轮未完成则跳过下次）
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Set, Tuple

from ...logger import get_logger
from ...services.config_service import get_config_service
from ...services.file_info_service import get_video_extensions
from ...services.file_service import get_file_service
from ...services.organize_service import get_organize_service
from .base import make_result, now_str, trim_errors

logger = get_logger(__name__)

# 目录递归最大深度（应对多层嵌套）
MAX_SCAN_DEPTH = 32
# 条目处理间隔（秒），不对外配置
ITEM_INTERVAL_SEC = 1.5
# 连续失败熔断次数，防止异常刷接口
MAX_CONSECUTIVE_FAIL = 15


def _is_video(name: str, exts: Set[str]) -> bool:
    if not name or "." not in name:
        return False
    ext = "." + name.rsplit(".", 1)[-1].lower()
    return ext in exts


def _collect_videos_deep(
    file_service,
    cid: int,
    *,
    max_depth: int = MAX_SCAN_DEPTH,
) -> List[Dict[str, Any]]:
    """BFS 深度扫描目录，收集全部视频文件。"""
    video_exts = get_video_extensions()
    results: List[Dict[str, Any]] = []
    queue: List[Tuple[int, int, str]] = [(int(cid), 0, "")]
    seen_dirs: Set[str] = set()

    while queue:
        cur_cid, depth, rel = queue.pop(0)
        key = str(cur_cid)
        if key in seen_dirs:
            continue
        seen_dirs.add(key)

        try:
            items = file_service.iter_all_files(cur_cid)
        except Exception as e:
            logger.warning(f"扫描目录失败: cid={cur_cid}, err={e}")
            continue

        for item in items:
            name = item.get("name") or ""
            if item.get("is_dir"):
                if depth >= max_depth:
                    logger.debug(f"已达最大深度 {max_depth}，跳过子目录: {rel}/{name}")
                    continue
                try:
                    sub_cid = int(item.get("file_id"))
                except (TypeError, ValueError):
                    continue
                sub_rel = f"{rel}/{name}" if rel else name
                queue.append((sub_cid, depth + 1, sub_rel))
            else:
                if not _is_video(name, video_exts):
                    continue
                row = dict(item)
                row["_rel_path"] = f"{rel}/{name}" if rel else name
                # 记录直属父目录，移动整理后用于清理空文件夹
                row["_parent_cid"] = str(cur_cid)
                results.append(row)

    return results


def run(trigger: str = "manual") -> Dict[str, Any]:
    """执行一轮全量整理（无数量上限）。

    扫描 settings 保存路径，识别后整理到 settings 媒体库路径。
    """
    started = now_str()
    cfg = get_config_service()
    file_service = get_file_service()
    organize_service = get_organize_service()

    # 仅使用设置中的两个路径；CID 只为扫描保存路径目录
    source_path = (cfg.get("source_path") or "").strip() or "待整理"
    source_cid = (cfg.get("source_cid") or "").strip()
    media_library_path = (cfg.get("media_library_path") or "").strip()
    organize_mode = (cfg.get("organize_mode") or "move").strip() or "move"

    def _fail(message: str) -> Dict[str, Any]:
        # 配置错误等未发生整理，不发通知
        return make_result(
            success=False,
            message=message,
            trigger=trigger,
            started_at=started,
            finished_at=now_str(),
            source_path=source_path,
            media_library_path=media_library_path or "媒体库",
            notify=False,
        )

    if not source_cid:
        return _fail("未配置保存路径，请先在设置中指定")

    # 落盘由 organize_service 读 media_library_path，这里只做前置校验
    if not media_library_path or media_library_path in {"/", "根目录"}:
        return _fail("未配置媒体库路径，请先在设置中指定")

    try:
        scan_cid = int(source_cid)
    except (TypeError, ValueError):
        return _fail(f"保存路径 CID 无效: {source_cid}")

    # 成功项沿用手动整理同一通知模板（format_organize_notify），不另发任务汇总
    success_count = 0
    failed = 0
    skipped = 0
    errors: List[Dict[str, str]] = []
    consecutive_fail = 0
    total_found = 0

    logger.info(
        f"云盘整理开始: trigger={trigger}, "
        f"保存路径={source_path}({scan_cid}), "
        f"媒体库={media_library_path}, mode={organize_mode}"
    )
    videos = _collect_videos_deep(file_service, scan_cid)
    total_found = len(videos)
    logger.info(f"云盘整理扫描完成: 共 {total_found} 个视频，将全部处理")

    for idx, item in enumerate(videos, 1):
        name = item.get("name") or ""
        rel = item.get("_rel_path") or name
        file_id = item.get("file_id")
        if not file_id:
            skipped += 1
            errors.append({"name": rel, "reason": "缺少 file_id"})
            continue

        logger.info(f"云盘整理进度 [{idx}/{total_found}]: {rel}")

        try:
            file_info = {
                "file_id": file_id,
                "name": name,
                "is_dir": False,
            }
            recog = organize_service.recognize_file(file_info)
            target_path = recog.get("target_path") if isinstance(recog, dict) else None
            tmdb_id = recog.get("tmdb_id") if isinstance(recog, dict) else None

            if not target_path or not tmdb_id:
                skipped += 1
                consecutive_fail = 0
                reason = "未能识别到 TMDB 结果"
                if isinstance(recog, dict) and recog.get("title"):
                    reason = f"未能匹配 TMDB（候选: {recog.get('title')}）"
                logger.info(f"云盘整理跳过: {rel} → {reason}")
                errors.append({"name": rel, "reason": reason})
                if ITEM_INTERVAL_SEC > 0:
                    time.sleep(min(ITEM_INTERVAL_SEC, 0.5))
                continue

            result = organize_service.execute_organize(
                file_id=file_id,
                file_name=name,
                is_dir=False,
                target_path=target_path,
                organize_mode=organize_mode,
                category=recog.get("category") or "",
                target_title=recog.get("title") or "",
                tmdb_id=int(tmdb_id or 0),
                media_info={
                    "media_type": recog.get("media_type") or "",
                    "year": recog.get("year") or "",
                    "season": recog.get("season") or 0,
                    "episode": recog.get("episode") or 0,
                    "tmdb_poster": recog.get("tmdb_poster") or "",
                    "tmdb_backdrop": recog.get("tmdb_backdrop") or "",
                    "tmdb_rating": recog.get("tmdb_rating") or 0,
                    "tech_info": recog.get("tech_info") or {},
                },
                source_parent_id=str(item.get("_parent_cid") or "") or None,
            )
            if result.get("success"):
                success_count += 1
                consecutive_fail = 0
                logger.info(f"云盘整理成功: {rel} → {result.get('message', '')}")
            else:
                failed += 1
                consecutive_fail += 1
                msg = result.get("message") or "整理失败"
                logger.warning(f"云盘整理失败: {rel} → {msg}")
                errors.append({"name": rel, "reason": str(msg)})
        except Exception as e:
            failed += 1
            consecutive_fail += 1
            logger.warning(f"云盘整理异常: {rel} → {e}")
            errors.append({"name": rel, "reason": str(e)})

        if consecutive_fail >= MAX_CONSECUTIVE_FAIL:
            logger.error(
                f"连续失败已达 {consecutive_fail} 次，提前结束本轮以防异常/风控"
            )
            break

        if ITEM_INTERVAL_SEC > 0 and idx < total_found:
            time.sleep(ITEM_INTERVAL_SEC)

    finished = now_str()
    processed = success_count + failed + skipped
    if total_found == 0:
        message = f"保存路径下未发现视频（{source_path}）"
        ok = True
    elif consecutive_fail >= MAX_CONSECUTIVE_FAIL and processed < total_found:
        message = (
            f"连续失败熔断：成功 {success_count}，跳过 {skipped}，失败 {failed}"
            f"（已处理 {processed}/{total_found}）"
        )
        ok = False
    elif success_count == 0 and failed == 0 and skipped > 0:
        message = f"共 {skipped} 个文件识别失败已跳过"
        ok = True
    elif success_count == 0 and failed > 0:
        message = f"本轮无成功：失败 {failed}，跳过 {skipped}"
        ok = False
    else:
        message = (
            f"完成：成功 {success_count}，跳过 {skipped}，失败 {failed}"
            f"（扫描 {total_found} 个）"
        )
        ok = True

    # 移动模式兜底：再清一遍保存路径下残留空目录（不删待整理自身）
    if organize_mode != "copy" and success_count > 0:
        try:
            pruned = organize_service.prune_empty_dirs_under(scan_cid)
            if pruned:
                logger.info(f"云盘整理空目录兜底清理: {pruned} 个")
        except Exception as e:
            logger.warning(f"云盘整理空目录兜底清理失败: {e}")

    logger.info(f"云盘整理结束: {message}")
    # 汇总通知关闭：成功项已按手动整理模板逐条发送
    return make_result(
        success=ok,
        message=message,
        trigger=trigger,
        started_at=started,
        finished_at=finished,
        scanned=total_found,
        processed=processed,
        success_count=success_count,
        failed=failed,
        skipped=skipped,
        source_path=source_path,
        media_library_path=media_library_path,
        errors=trim_errors(errors, 30),
        notify=False,
    )
