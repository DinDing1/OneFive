"""离线转存服务（ed2k / magnet）

通过 115 云下载接口提交链接到指定保存目录。
默认保存目录复用整理设置中的 source_path（保存路径）。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from p115client import check_response
from p115client.exception import P115BusyOSError
from p115client.tool.attr import dir_getid

from ..exceptions import ConfigError, NotLoggedInError
from ..logger import get_logger
from .config_service import get_config_service
from .file_service import get_file_service
from .offline_link_parser import (
    OfflineLink,
    build_ed2k_variants,
    compact_filename,
    describe_offline_link,
    extract_ed2k_hash,
    parse_offline_links,
    prefer_ed2k_submit_url,
)
from .p115_client_factory import get_p115_client_factory

logger = get_logger(__name__)


class OfflineDownloadService:
    """115 离线转存服务。"""

    def __init__(self):
        self.config_service = get_config_service()
        self.client_factory = get_p115_client_factory()

    # ---------------- 配置 / 路径 ----------------

    def get_save_path(self) -> str:
        """默认保存路径：与分享/整理的保存路径 source_path 一致。"""
        return (self.config_service.get("source_path") or "").strip()

    def get_settings(self) -> Dict[str, Any]:
        save_path = self.get_save_path()
        source_cid = (self.config_service.get("source_cid") or "").strip()
        return {
            "save_path": save_path,
            "source_cid": source_cid,
            "save_path_source": "source_path",
            "supported_types": ["ed2k", "magnet"],
            "note": "默认保存目录与设置页「保存路径」一致",
        }

    def resolve_save_cid(self, wp_path_id: str | int | None = None) -> int:
        """解析保存目录 cid。

        优先级：
        1. 请求显式传入 wp_path_id
        2. 配置 source_cid（设置页选择保存路径时写入）
        3. 配置 source_path 通过 dir_getid 解析
        """
        if wp_path_id is not None and str(wp_path_id).strip() != "":
            try:
                return int(str(wp_path_id).strip())
            except ValueError as e:
                raise ConfigError(f"无效的保存目录 ID: {wp_path_id}") from e

        source_cid = (self.config_service.get("source_cid") or "").strip()
        if source_cid:
            try:
                cid = int(source_cid)
                if cid >= 0:
                    return cid
            except ValueError:
                logger.warning(f"配置 source_cid 无效，将回退路径解析: {source_cid}")

        save_path = self.get_save_path()
        if not save_path or save_path in ("/", "\\", "."):
            # 未配置时落到根目录不合适，强制要求配置
            raise ConfigError("未配置保存路径，请先在设置页配置「保存路径」")

        client = self.client_factory.get_web_client()
        path = save_path.replace("\\", "/").strip("/")
        if not path:
            raise ConfigError("保存路径无效，请重新选择「保存路径」")

        try:
            cid = dir_getid(client, path)
        except Exception as e:
            logger.error(f"解析保存路径失败: path={save_path}, err={e}")
            raise ConfigError(f"无法解析保存路径「{save_path}」为目录 ID: {e}") from e

        if cid is None or int(cid) < 0:
            raise ConfigError(f"保存路径「{save_path}」不存在或无法访问")

        # 解析成功后回写 source_cid，减少后续 dir_getid 调用
        try:
            self.config_service.set("source_cid", str(int(cid)), "保存路径 CID")
        except Exception as e:
            logger.warning(f"回写 source_cid 失败: {e}")
        return int(cid)

    # ---------------- 提交任务 ----------------

    def add_urls(
        self,
        urls: str | List[str],
        wp_path_id: str | int | None = None,
        source: str = "api",
    ) -> Dict[str, Any]:
        """提交 ed2k / magnet 离线任务。

        参数：
            urls: 单条文本、多行文本或链接列表
            wp_path_id: 可选，覆盖默认保存目录
            source: 调用来源（api / bot）
        """
        links = parse_offline_links(urls)
        if not links:
            return {
                "success": False,
                "error": "未识别到 ed2k / magnet 链接",
                "total": 0,
                "accepted": 0,
                "failed": 0,
                "items": [],
            }

                # 诊断日志：不打印完整链接，只打印结构摘要，便于定位“错误的链接”
        for idx, link in enumerate(links[:10]):
            logger.info(
                f"离线链接规范化[{idx}]: {describe_offline_link(link)}"
            )
        if len(links) > 10:
            logger.info(f"离线链接规范化: 其余 {len(links) - 10} 条已省略")

        try:
            save_cid = self.resolve_save_cid(wp_path_id)
        except (ConfigError, NotLoggedInError) as e:
            return {
                "success": False,
                "error": str(e),
                "total": len(links),
                "accepted": 0,
                "failed": len(links),
                "items": [
                    {
                        "url": link.url,
                        "url_type": link.url_type,
                        "name": link.name,
                        "ok": False,
                        "error": str(e),
                    }
                    for link in links
                ],
                "save_path": self.get_save_path(),
            }

        save_path = self.get_save_path()
        logger.info(
            f"离线转存提交: source={source}, count={len(links)}, "
            f"save_path={save_path}, cid={save_cid}"
        )

        items: List[Dict[str, Any]] | None = None
        try:
            resp = self._submit_urls(links, save_cid)
            items = self._normalize_add_result(links, resp)
        except NotLoggedInError as e:
            return {
                "success": False,
                "error": str(e),
                "total": len(links),
                "accepted": 0,
                "failed": len(links),
                "items": [],
                "save_path": save_path,
                "wp_path_id": str(save_cid),
            }
        except Exception as e:
            # 兜底：若最终异常仍是「任务已存在」，按成功返回
            if self._is_already_exists_error(e):
                logger.info(f"离线转存提交: {e}（视为已存在/成功）")
                items = [
                    {
                        "url": link.url,
                        "url_type": link.url_type,
                        "name": link.name,
                        "ok": True,
                        "status": "exists",
                        "error": "",
                        "info_hash": "",
                    }
                    for link in links
                ]
            elif len(links) > 1:
                # 多条批量失败：逐条提交，避免一条坏链拖垮整批
                logger.warning(
                    f"离线转存批量提交失败，改逐条提交: count={len(links)}, err={e}"
                )
                items = []
                for link in links:
                    try:
                        one_resp = self._submit_urls([link], save_cid)
                        items.extend(self._normalize_add_result([link], one_resp))
                    except Exception as one_err:
                        if self._is_already_exists_error(one_err):
                            items.append(
                                {
                                    "url": link.url,
                                    "url_type": link.url_type,
                                    "name": link.name,
                                    "ok": True,
                                    "status": "exists",
                                    "error": "",
                                    "info_hash": "",
                                }
                            )
                        else:
                            logger.error(
                                f"离线转存单条失败: name={link.name!r}, err={one_err}"
                            )
                            items.append(
                                {
                                    "url": link.url,
                                    "url_type": link.url_type,
                                    "name": link.name,
                                    "ok": False,
                                    "status": "failed",
                                    "error": str(one_err),
                                }
                            )
            else:
                logger.error(f"离线转存提交失败: {e}")
                return {
                    "success": False,
                    "error": f"提交失败: {e}",
                    "total": len(links),
                    "accepted": 0,
                    "exists": 0,
                    "failed": len(links),
                    "items": [
                        {
                            "url": link.url,
                            "url_type": link.url_type,
                            "name": link.name,
                            "ok": False,
                            "status": "failed",
                            "error": str(e),
                        }
                        for link in links
                    ],
                    "save_path": save_path,
                    "wp_path_id": str(save_cid),
                }

        if items is None:
            items = []

        # 115 可能把文件名空格删掉：尽量按原始 name 回改（多条互斥 file_id）
        try:
            items = self._restore_original_filenames(links, items, save_cid)
        except Exception as e:
            logger.warning(f"离线转存后恢复文件名失败（不影响提交结果）: {e}")

        accepted = sum(1 for x in items if x.get("ok"))
        exists_count = sum(1 for x in items if x.get("status") == "exists")
        failed = len(items) - accepted
        success = accepted > 0
        error = ""
        if not success:
            error = next((x.get("error") for x in items if x.get("error")), "全部提交失败")
        elif failed:
            error = f"部分失败: 成功 {accepted}，失败 {failed}"

        return {
            "success": success,
            "error": error,
            "total": len(items),
            "accepted": accepted,
            "exists": exists_count,
            "failed": failed,
            "items": items,
            "save_path": save_path,
            "wp_path_id": str(save_cid),
            "raw": resp if isinstance(resp, dict) else None,
        }

    def _is_open_enabled(self) -> bool:
        """是否启用 Open API 且可拿到 Open 客户端。"""
        return self.client_factory.get_open_client() is not None

    def _is_false_state(self, resp: Any) -> bool:
        if not isinstance(resp, dict):
            return True
        state = resp.get("state", True)
        return state in (0, "0", False, "false", "False")

    def _extract_error_message(self, resp: Any, default: str = "请求失败") -> str:
        if not isinstance(resp, dict):
            return f"{default}: {type(resp)}"
        errno = resp.get("errno") or resp.get("errNo") or resp.get("code")
        msg = (
            resp.get("error")
            or resp.get("error_msg")
            or resp.get("message")
            or resp.get("msg")
            or ""
        )
        if msg:
            return str(msg)
        if errno not in (None, "", 0, "0"):
            return f"errno={errno}"
        return default

    def _is_already_exists_error(self, err: Exception | str | None) -> bool:
        """判断是否为 115「任务已存在/重复链接」。

        该情况说明链接此前已成功加入离线队列，业务上视为成功（幂等）。
        """
        msg = str(err or "")
        if not msg:
            return False
        keywords = (
            "任务已存在",
            "重复的链接",
            "请勿输入重复",
            "重复添加",
            "已存在该任务",
            "already exists",
            "duplicate",
            "task exists",
        )
        lower = msg.lower()
        return any(k.lower() in lower for k in keywords)

    def _as_already_exists_response(
        self,
        *,
        links: list | None = None,
        message: str = "任务已存在",
        source_resp=None,
        strategy: str = "",
    ) -> dict:
        """构造「任务已存在」的统一成功响应，供结果归一化使用。"""
        items = []
        for link in links or []:
            items.append(
                {
                    "url": link.url,
                    "url_type": link.url_type,
                    "name": link.name,
                    "state": 1,
                    "status": "exists",
                    "error": "",
                    "error_msg": "",
                    "message": message,
                    "info_hash": "",
                }
            )
        resp = {
            "state": 1,
            "error": "",
            "message": message,
            "already_exists": True,
            "data": {"result": items} if items else {},
            "result": items,
        }
        if strategy:
            resp["strategy"] = strategy
        if isinstance(source_resp, dict):
            resp["raw_source"] = source_resp
        return resp

    def _call_with_channel(
        self,
        *,
        open_caller,
        web_caller,
        action: str,
        max_busy_retries: int = 3,
    ) -> Any:
        """按项目原则选择通道。

        - 开启 Open API：优先 Open，失败回退普通 Web
        - 关闭 Open API：只走普通 Web
        """
        channels: list[tuple[str, Any]] = []
        if self._is_open_enabled():
            channels.append(("open", open_caller))
        channels.append(("web", web_caller))

        last_err: Exception | None = None
        for idx, (name, caller) in enumerate(channels):
            for attempt in range(max_busy_retries):
                try:
                    resp = caller()
                    if self._is_false_state(resp):
                        msg = self._extract_error_message(resp, f"{action}失败")
                        # 离线任务重复提交：115 返回失败文案，但业务上等同已受理
                        if action.startswith("离线转存") and self._is_already_exists_error(msg):
                            logger.info(f"{action} {name}: {msg}（视为已存在/成功）")
                            return self._as_already_exists_response(
                                message=msg,
                                source_resp=resp,
                                strategy=name,
                            )
                        last_err = RuntimeError(f"[{name}] {msg}")
                        logger.warning(f"{action} {name} 业务失败: {msg}")
                        break  # 换下一通道

                    # 成功时尽量 check_response；结构不标准且 state 为真则接受
                    if isinstance(resp, dict):
                        try:
                            check_response(resp)
                        except Exception:
                            pass
                    return resp
                except P115BusyOSError as e:
                    last_err = e
                    wait = 2 * (attempt + 1)
                    logger.warning(f"{action} busy({name})，{wait}s 后重试: {e}")
                    time.sleep(wait)
                except NotLoggedInError:
                    raise
                except Exception as e:
                    last_err = e
                    # Open 失败则回退 Web；Web 失败则结束
                    if name == "open" and idx + 1 < len(channels):
                        logger.warning(f"{action} Open API 调用失败，回退普通接口: {e}")
                    else:
                        logger.warning(f"{action} {name} 调用失败: {e}")
                    break

        if last_err:
            raise last_err
        raise RuntimeError(f"{action}失败")

    def _is_retryable_link_error(self, err: Exception | str) -> bool:
        """判断是否为可通过切换提交策略重试的“链接错误”。"""
        msg = str(err or "")
        keywords = (
            "错误的链接",
            "无效的链接",
            "链接无效",
            "非法链接",
            "url is invalid",
            "invalid url",
            "invalid link",
            "link is invalid",
        )
        lower = msg.lower()
        return any(k.lower() in lower for k in keywords)

    def _submit_urls(self, links: List[OfflineLink], save_cid: int) -> Dict[str, Any]:
        """提交链接到 115 云下载。

        通道原则：
        - 开启 Open API：Open 优先，失败回退 Web
        - 关闭 Open API：仅 Web

        Web 侧对“错误的链接”做多策略回退：
        1) add_task_urls + type=ssp
        2) add_task_urls + type=web
        3) 单条时 add_task_url + ssp/web
        """
        # 提交用优先形态（ed2k 空格→%20），显示名仍在 link.name 中保留空格
        url_list = []
        for link in links:
            if link.url_type == "ed2k":
                url_list.append(prefer_ed2k_submit_url(link.url))
            else:
                url_list.append(link.url)

        def _call_open():
            open_client = self.client_factory.get_open_client()
            if open_client is None:
                raise RuntimeError("Open API 未启用或 token 无效")
            payload = {
                "urls": "\n".join(url_list),
                "wp_path_id": str(save_cid),
            }
            return open_client.clouddownload_task_add_urls(payload)

        def _call_web():
            client = self.client_factory.get_web_client()
            return self._submit_urls_web_with_fallback(client, url_list, save_cid)

        return self._call_with_channel(
            open_caller=_call_open,
            web_caller=_call_web,
            action="离线转存提交",
        )

    def _submit_urls_web_with_fallback(
        self,
        client,
        url_list: List[str],
        save_cid: int,
    ) -> Dict[str, Any]:
        """Web 通道多策略提交，降低 115 对不同接口的兼容差异。

        策略顺序：
        1) 链接变体（ed2k 原样 / URL 编码文件名）
        2) add_task_urls + ssp/web
        3) 单条 add_task_url + ssp/web
        """
        # 为每条链接生成变体；单条时依次尝试，多条时仅用首个变体组合
        variant_groups: List[List[str]] = []
        for u in url_list:
            if u.lower().startswith("ed2k://"):
                variant_groups.append(build_ed2k_variants(u) or [u])
            else:
                variant_groups.append([u])

        if len(url_list) == 1:
            candidate_lists = [[v] for v in variant_groups[0]]
        else:
            candidate_lists = [[group[0] for group in variant_groups]]

        last_err: Exception | None = None
        last_resp: Any = None

        for urls in candidate_lists:
            def _urls_payload(curr: List[str] = urls) -> Dict[str, Any]:
                payload: Dict[str, Any] = {
                    f"url[{i}]": url for i, url in enumerate(curr)
                }
                payload["wp_path_id"] = str(save_cid)
                return payload

            strategies: List[tuple[str, Any]] = [
                (
                    "urls/ssp",
                    lambda curr=urls: client.clouddownload_task_add_urls(
                        _urls_payload(curr), type="ssp"
                    ),
                ),
                (
                    "urls/web",
                    lambda curr=urls: client.clouddownload_task_add_urls(
                        _urls_payload(curr), type="web"
                    ),
                ),
            ]
            if len(urls) == 1:
                strategies.extend(
                    [
                        (
                            "url/ssp",
                            lambda curr=urls: client.clouddownload_task_add_url(
                                {"url": curr[0], "wp_path_id": str(save_cid)},
                                type="ssp",
                            ),
                        ),
                        (
                            "url/web",
                            lambda curr=urls: client.clouddownload_task_add_url(
                                {"url": curr[0], "wp_path_id": str(save_cid)},
                                type="web",
                            ),
                        ),
                    ]
                )

            for name, caller in strategies:
                try:
                    resp = caller()
                    last_resp = resp
                    if self._is_false_state(resp):
                        msg = self._extract_error_message(resp, "提交失败")
                        # 任务已存在 = 幂等成功，直接返回
                        if self._is_already_exists_error(msg):
                            logger.info(
                                f"离线转存 Web 策略: strategy={name}, {msg}（视为已存在/成功）"
                            )
                            return self._as_already_exists_response(
                                message=msg,
                                source_resp=resp,
                                strategy=name,
                            )
                        last_err = RuntimeError(f"[{name}] {msg}")
                        logger.warning(
                            f"离线转存 Web 策略失败: strategy={name}, err={msg}"
                        )
                        if self._is_retryable_link_error(msg):
                            continue
                        raise last_err
                    logger.info(f"离线转存 Web 策略成功: strategy={name}")
                    return resp if isinstance(resp, dict) else {"state": True, "data": resp}
                except Exception as e:
                    last_err = e
                    # 异常信息里也可能带“任务已存在”
                    if self._is_already_exists_error(e):
                        logger.info(
                            f"离线转存 Web 策略: strategy={name}, {e}（视为已存在/成功）"
                        )
                        return self._as_already_exists_response(
                            message=str(e),
                            strategy=name,
                        )
                    logger.warning(
                        f"离线转存 Web 策略异常: strategy={name}, err={e}"
                    )
                    if self._is_retryable_link_error(e):
                        continue
                    raise

        if last_err is not None:
            if self._is_already_exists_error(last_err):
                logger.info(f"离线转存 Web: {last_err}（视为已存在/成功）")
                return self._as_already_exists_response(message=str(last_err))
            raise last_err
        if isinstance(last_resp, dict):
            return last_resp
        raise RuntimeError(
            "离线转存提交失败：所有 Web 策略均未成功"
        )

    def _normalize_add_result(
        self,
        links: List[OfflineLink],
        resp: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """把 115 返回结果尽量对齐到每条链接。"""
        data = resp.get("data")
        # Open/Web 可能返回列表、字典或嵌套结构
        result_list: List[Any] = []
        if isinstance(data, list):
            result_list = data
        elif isinstance(data, dict):
            for key in ("tasks", "list", "result", "items", "data"):
                val = data.get(key)
                if isinstance(val, list):
                    result_list = val
                    break
            if not result_list and data:
                # 单条结果
                result_list = [data]
        elif isinstance(resp.get("tasks"), list):
            result_list = resp.get("tasks") or []

        items: List[Dict[str, Any]] = []
        global_error = ""
        already_exists_global = bool(resp.get("already_exists"))
        state = resp.get("state", True)
        if state in (0, "0", False, "false", "False"):
            global_error = (
                resp.get("error")
                or resp.get("error_msg")
                or resp.get("message")
                or resp.get("msg")
                or "提交失败"
            )
            # 整体返回“任务已存在”时，按成功处理
            if self._is_already_exists_error(global_error):
                already_exists_global = True
                global_error = ""

        for idx, link in enumerate(links):
            detail: Dict[str, Any] = {}
            if idx < len(result_list) and isinstance(result_list[idx], dict):
                detail = result_list[idx]
            elif len(result_list) == 1 and isinstance(result_list[0], dict) and len(links) == 1:
                detail = result_list[0]

            item_error = ""
            ok = True
            status = "accepted"
            if detail:
                item_state = detail.get("state", detail.get("status", 1))
                if item_state in (0, "0", False, "false", "False", -1, "-1"):
                    ok = False
                # status=exists 时视为成功
                if str(detail.get("status") or "").lower() in ("exists", "exist", "duplicate"):
                    ok = True
                    status = "exists"
                item_error = str(
                    detail.get("error")
                    or detail.get("error_msg")
                    or detail.get("msg")
                    or detail.get("message")
                    or ""
                )
                # 115 常见：单链接级 errno
                if detail.get("errno") not in (None, 0, "0"):
                    ok = False
                    if not item_error:
                        item_error = f"errno={detail.get('errno')}"
                # 明细里是“任务已存在” → 成功
                if self._is_already_exists_error(item_error) or already_exists_global:
                    ok = True
                    status = "exists"
                    item_error = ""
            elif already_exists_global:
                ok = True
                status = "exists"
                item_error = ""
            elif global_error:
                # 无明细但整体失败
                ok = False
                item_error = global_error
            elif result_list:
                # 有返回明细但未匹配到当前链接，不冒然标成功
                ok = False
                item_error = "未匹配到该链接的返回结果"

            info_hash = (
                detail.get("info_hash")
                or detail.get("hash")
                or detail.get("infohash")
                or ""
            )
            name = (
                detail.get("name")
                or detail.get("file_name")
                or link.name
                or ""
            )
            items.append(
                {
                    "url": link.url,
                    "url_type": link.url_type,
                    "name": name,
                    "ok": ok,
                    "status": status if ok else "failed",
                    "error": item_error,
                    "info_hash": info_hash,
                }
            )

        # 若接口完全没给明细，但整体成功，则全部视为成功
        if not result_list and not global_error:
            for item in items:
                item["ok"] = True
                item["error"] = ""
        return items

    # ---------------- 文件名恢复（115 删空格） ----------------

    # 常见视频扩展名：115 有时落盘后会丢掉扩展名，匹配时需兼容
    _VIDEO_EXTS = (
        ".mkv", ".mp4", ".ts", ".m2ts", ".iso", ".avi", ".wmv", ".mov",
        ".m4v", ".flv", ".rmvb", ".mpg", ".mpeg", ".vob", ".bdmv",
    )

    def _restore_original_filenames(
        self,
        links: List[OfflineLink],
        items: List[Dict[str, Any]],
        save_cid: int,
    ) -> List[Dict[str, Any]]:
        """提交成功后，尽量把 115 删掉的空格文件名改回原始名。

        适用：
        - 新提交成功且已秒传/完成
        - 任务已存在且文件已落盘
        - 一次多条 ed2k：共享任务列表、共享最新目录页、互斥 file_id，避免串改

        策略：
        1) 离线任务列表按 hash/文件名定位（hash 优先，适配多链）
        2) 任务 file_id 快路径 → 搜索优先 → 最新一页兜底
        3) 短重试，兼容秒传/落盘延迟
        """
        if not links or not items:
            return items

        # 仅处理「期望名含空格」的成功项（主要是 ed2k；magnet 有名也尝试）
        need: List[tuple[int, OfflineLink, Dict[str, Any]]] = []
        for idx, (link, item) in enumerate(zip(links, items)):
            if not item.get("ok"):
                continue
            desired = (link.name or "").strip()
            if not desired or " " not in desired:
                continue
            need.append((idx, link, item))

        if not need:
            return items

        # 若此前误把「保存目录」改成了媒体文件名，先尝试改回配置名
        try:
            self._repair_save_dir_name_if_needed(
                save_cid,
                media_names=[(link.name or "").strip() for _, link, _ in need],
            )
        except Exception as e:
            logger.warning(f"检查/修复保存目录名失败（忽略）: {e}")

        # 多条恢复互斥：同一批内已被占用的 file_id / 任务键，禁止后条抢同一文件
        claimed_ids: set[str] = set()
        used_task_keys: set[str] = set()

        # 提交后落盘可能有短暂延迟：0.8s / 2.5s / 6s 共 3 轮
        delays = (0.8, 2.5, 6.0)
        pending = list(need)
        for attempt, delay in enumerate(delays, 1):
            if delay > 0:
                time.sleep(delay)

            tasks = self._list_recent_tasks(max_pages=3)
            # 多条时只拉一次最新目录页，供本轮所有 pending 复用
            recent_rows = self._list_recent_save_dir_files(save_cid, limit=max(80, len(pending) * 5))
            logger.info(
                f"离线文件名恢复第{attempt}/{len(delays)}轮: "
                f"pending={len(pending)}, tasks={len(tasks)}, "
                f"recent={len(recent_rows)}, save_cid={save_cid}"
            )

            next_pending: List[tuple[int, OfflineLink, Dict[str, Any]]] = []
            for idx, link, item in pending:
                updated = self._restore_one_filename(
                    link=link,
                    item=item,
                    save_cid=save_cid,
                    tasks=tasks,
                    claimed_ids=claimed_ids,
                    used_task_keys=used_task_keys,
                    recent_rows=recent_rows,
                )
                items[idx] = updated
                if updated.get("renamed"):
                    continue
                desired = (link.name or "").strip()
                if updated.get("name") == desired and not updated.get("rename_pending"):
                    continue
                if updated.get("rename_pending"):
                    next_pending.append((idx, link, updated))

            pending = next_pending
            if not pending:
                break

        if pending:
            for idx, link, item in pending:
                desired = (link.name or "").strip()
                logger.info(
                    f"离线文件名最终未恢复: desired={desired!r}, "
                    f"err={item.get('rename_error') or '未找到文件'}"
                )
                items[idx] = item
        return items

    def _list_recent_save_dir_files(
        self,
        save_cid: int,
        *,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """拉取保存目录最新一页文件（多条恢复时本轮只拉一次）。"""
        try:
            fs = get_file_service()
            result = fs.list_files(
                cid=int(save_cid),
                limit=max(20, int(limit or 80)),
                offset=0,
                order="user_ptime",
                asc=0,
            )
            rows = result.get("items") or []
            return rows if isinstance(rows, list) else []
        except Exception as e:
            logger.warning(f"离线恢复预取最新目录失败: cid={save_cid}, err={e}")
            return []

    def _repair_save_dir_name_if_needed(
        self,
        save_cid: int,
        *,
        media_names: List[str] | None = None,
    ) -> None:
        """若保存目录被误重命名为媒体文件名，则改回配置中的目录名。

        115 离线任务 file_id 常等于保存目录 cid，旧逻辑会误改文件夹名。
        使用 fs_file_skim 轻量读取目录名，避免 get_info 扫大目录。
        """
        expected_path = (self.get_save_path() or "").replace(chr(92), "/").strip().strip("/")
        if not expected_path:
            return
        expected_name = expected_path.split("/")[-1].strip()
        if not expected_name:
            return

        current_name = self._skim_name(save_cid)
        if not current_name:
            logger.info(f"无法读取保存目录当前名，跳过自动修复: cid={save_cid}")
            return
        if current_name == expected_name:
            return

        # 仅当当前名像「媒体文件名」时才自动改回，避免误伤用户主动改名
        looks_like_media = False
        for media in media_names or []:
            if media and self._names_loosely_match(current_name, media):
                looks_like_media = True
                break
        if not looks_like_media:
            lower = current_name.lower()
            if any(lower.endswith(ext) for ext in self._VIDEO_EXTS):
                looks_like_media = True
            elif any(
                tag in lower
                for tag in (
                    "2160p",
                    "1080p",
                    "720p",
                    "remux",
                    "bluray",
                    "web-dl",
                    "webdl",
                    "hdr",
                    "dolby",
                    "atmos",
                )
            ):
                looks_like_media = True

        if not looks_like_media:
            logger.info(
                f"保存目录名与配置不同但非媒体名，不自动改回: "
                f"current={current_name!r}, expected={expected_name!r}"
            )
            return

        try:
            fs = get_file_service()
            # 目录重命名：目标是目录本身，名称无扩展名
            fs.rename_file(str(save_cid), expected_name)
            logger.warning(
                f"已自动修复被误改的保存目录名: id={save_cid}, "
                f"{current_name!r} -> {expected_name!r}"
            )
        except Exception as e:
            logger.warning(
                f"自动修复保存目录名失败，请手动改回 {expected_name!r}: "
                f"current={current_name!r}, err={e}"
            )

    def _restore_one_filename(
        self,
        *,
        link: OfflineLink,
        item: Dict[str, Any],
        save_cid: int,
        tasks: List[Dict[str, Any]],
        claimed_ids: set[str] | None = None,
        used_task_keys: set[str] | None = None,
        recent_rows: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """尝试恢复单条链接对应文件的原始空格文件名。

        重要安全约束：
        - 115 离线任务里的 file_id 经常是「保存目录 cid」，不是文件 id
        - 因此 rename 的目标 id 必须来自保存目录内的「文件」枚举/搜索
        - 严禁对 save_cid 本身或任何目录执行重命名
        - 多条时：claimed_ids / used_task_keys 防止两条抢同一文件/任务
        """
        desired = (link.name or "").strip()
        desired_compact = compact_filename(desired)
        file_hash = extract_ed2k_hash(link.url) if link.url_type == "ed2k" else ""
        size_hint = self._extract_size_from_link(link)
        save_cid_str = str(save_cid)
        claimed_ids = claimed_ids if claimed_ids is not None else set()
        used_task_keys = used_task_keys if used_task_keys is not None else set()

        current_name = ""
        task_file_id: str | None = None
        matched_task_key: str | None = None

        # 1) 离线任务只用于确认「当前名/hash」，不直接拿来 rename
        task = self._find_task_for_link(
            tasks, link, item, file_hash, used_task_keys=used_task_keys
        )
        if task:
            current_name = self._task_name(task)
            raw_task_id = self._task_file_id(task, save_cid=save_cid)
            task_file_id = raw_task_id
            matched_task_key = self._task_match_key(task)
            logger.info(
                f"离线恢复命中任务: name={current_name!r}, "
                f"task_file_id={raw_task_id!r}, save_cid={save_cid_str}, "
                f"hash={(file_hash or item.get('info_hash') or '')[:8]}"
            )
            # 若任务声称的 file_id 就是保存目录，明确忽略
            if raw_task_id and raw_task_id == save_cid_str:
                logger.warning(
                    f"忽略任务 file_id（与保存目录 cid 相同，避免误改文件夹）: {raw_task_id}"
                )
                task_file_id = None

        # 任务名已是期望名：无需改（也不碰目录）
        if current_name and current_name == desired:
            item["name"] = desired
            item["renamed"] = False
            item.pop("rename_pending", None)
            item.pop("rename_error", None)
            if matched_task_key:
                used_task_keys.add(matched_task_key)
            return item

        # 2) 定位真正的文件 id（绝不用未校验的任务 file_id 盲 rename）
        #    优先级：任务 file_id 快路径(skim 校验) → 搜索优先 → 最新一页兜底
        file_id: str | None = None

        # 2.1 任务 file_id 快路径：与 save_cid 不同且未被其他链接占用
        if (
            task_file_id
            and str(task_file_id) != save_cid_str
            and str(task_file_id) not in claimed_ids
        ):
            skim = self._skim_attr(task_file_id)
            skim_name = str(skim.get("name") or "").strip()
            skim_is_dir = skim.get("is_dir")
            if skim_is_dir is False and skim_name and self._names_loosely_match(skim_name, desired):
                file_id = str(task_file_id)
                current_name = skim_name or current_name
                logger.info(
                    f"任务 file_id 校验通过: id={file_id}, name={current_name!r}"
                )
            else:
                logger.info(
                    f"任务 file_id 不可用，改走搜索: task_file_id={task_file_id}, "
                    f"is_dir={skim_is_dir}, name={skim_name!r}"
                )

        # 2.2 搜索优先（多条时复用 recent_rows，并排除已占用 id）
        if not file_id:
            found_id, found_name = self._find_file_id_in_dir(
                save_cid,
                desired=desired,
                desired_compact=desired_compact,
                size_hint=size_hint,
                exclude_ids=claimed_ids,
                recent_rows=recent_rows,
            )
            if (
                found_id
                and str(found_id) != save_cid_str
                and str(found_id) not in claimed_ids
            ):
                file_id = str(found_id)
                current_name = found_name or current_name
                logger.info(
                    f"离线恢复命中文件: id={file_id}, name={current_name!r}"
                )

        if not self._is_digit_id(file_id) or str(file_id) == save_cid_str:
            item["rename_pending"] = True
            item["rename_error"] = "未找到可重命名的文件（可能仍在下载）"
            logger.info(
                f"离线文件名待恢复: desired={desired!r}, current={current_name!r}, "
                f"save_cid={save_cid_str}"
            )
            return item

        # 安全校验：当前名应与期望名是同一资源
        if current_name and not self._names_loosely_match(current_name, desired):
            item["rename_pending"] = True
            item["rename_error"] = f"文件名不匹配，跳过: {current_name}"
            logger.warning(
                f"离线恢复跳过（名不匹配）: current={current_name!r}, desired={desired!r}"
            )
            return item

        if current_name == desired:
            item["name"] = desired
            item["renamed"] = False
            item["file_id"] = str(file_id)
            item.pop("rename_pending", None)
            item.pop("rename_error", None)
            claimed_ids.add(str(file_id))
            if matched_task_key:
                used_task_keys.add(matched_task_key)
            return item

        # 3) 最终兜底：再次确认不是 save_cid
        if str(file_id) == save_cid_str or str(file_id) in claimed_ids:
            item["rename_pending"] = True
            item["rename_error"] = "拒绝重命名保存目录或已占用文件"
            logger.warning(f"离线恢复拒绝目标 id: {file_id}")
            return item

        rename_to = desired
        # 文件名必须带扩展名（115 限制）；若 desired 意外无扩展名则补上当前扩展名
        if "." not in rename_to and "." in (current_name or ""):
            ext = current_name.rsplit(".", 1)[-1]
            if ext and len(ext) <= 8:
                rename_to = f"{rename_to}.{ext}"

        # 最终硬闸：必须是文件，且绝不是 save_cid
        if not self._ensure_rename_target_is_file(str(file_id), save_cid=save_cid):
            item["rename_pending"] = True
            item["rename_error"] = "重命名目标不是文件（已拒绝，防止误改目录）"
            logger.warning(
                f"离线恢复拒绝重命名非文件目标: id={file_id}, "
                f"current={current_name!r}, desired={desired!r}"
            )
            return item

        try:
            fs = get_file_service()
            fs.rename_file(str(file_id), rename_to)
            item["name"] = rename_to
            item["renamed"] = True
            item["file_id"] = str(file_id)
            item.pop("rename_pending", None)
            item.pop("rename_error", None)
            claimed_ids.add(str(file_id))
            if matched_task_key:
                used_task_keys.add(matched_task_key)
            logger.info(
                f"已恢复离线文件名: id={file_id}, {current_name!r} -> {rename_to!r}"
            )
        except Exception as e:
            item["rename_pending"] = True
            item["rename_error"] = str(e)
            logger.warning(f"恢复离线文件名异常: id={file_id}, err={e}")
        return item

    def _skim_name(self, file_id: int | str) -> str:
        """轻量读取文件/目录名（fs_file_skim，不扫子树）。"""
        info = self._skim_attr(file_id)
        return str(info.get("name") or "").strip()

    def _skim_attr(self, file_id: int | str) -> Dict[str, Any]:
        """轻量读取文件/目录属性。

        优先 web client.fs_file_skim：
        - 目录：sha1 为空，is_dir=True
        - 文件：有 sha1/size，is_dir=False
        避免 get_info 对大目录做递归统计。
        """
        fid = str(file_id or "").strip()
        if not fid or not fid.isdigit() or fid == "0":
            return {"id": fid, "name": "", "is_dir": True, "size": 0, "sha1": ""}

        try:
            client = self.client_factory.get_web_client()
            resp = client.fs_file_skim(int(fid))
            check_response(resp)
        except Exception as e:
            logger.debug(f"fs_file_skim 失败: id={fid}, err={e}")
            return {
                "id": fid,
                "name": "",
                "is_dir": None,
                "size": 0,
                "sha1": "",
                "error": str(e),
            }

        data = resp.get("data") if isinstance(resp, dict) else None
        row: Dict[str, Any] = {}
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                row = first
        elif isinstance(data, dict):
            # 兼容 list 包装或单对象
            if isinstance(data.get("list"), list) and data["list"]:
                first = data["list"][0]
                row = first if isinstance(first, dict) else data
            else:
                row = data

        name = str(
            row.get("file_name")
            or row.get("n")
            or row.get("fn")
            or row.get("name")
            or ""
        ).strip()
        sha1 = str(row.get("sha1") or row.get("sha") or "").strip()
        try:
            size = int(row.get("file_size") or row.get("s") or row.get("size") or 0)
        except Exception:
            size = 0
        # 115 规则：目录无 sha1；文件有 sha1
        if "sha1" in row or "sha" in row:
            is_dir = not bool(sha1)
        elif "fc" in row:
            is_dir = str(row.get("fc")) == "0"
        elif "file_category" in row:
            is_dir = str(row.get("file_category")) in ("0", "folder", "dir")
        else:
            # 无法判断时返回 None，由调用方决定是否冒险
            is_dir = None

        return {
            "id": str(row.get("file_id") or row.get("fid") or row.get("cid") or fid),
            "name": name,
            "is_dir": is_dir,
            "size": size,
            "sha1": sha1,
            "raw": row,
        }

    @staticmethod
    def _is_digit_id(value: Any) -> bool:
        text = str(value or "").strip()
        return bool(text) and text.isdigit()

    @classmethod
    def _strip_video_ext(cls, name: str) -> str:
        """去掉末尾常见视频扩展名（大小写不敏感）。"""
        text = (name or "").strip()
        lower = text.lower()
        for ext in cls._VIDEO_EXTS:
            if lower.endswith(ext):
                return text[: -len(ext)]
        return text

    @classmethod
    def _names_loosely_match(cls, current: str, desired: str) -> bool:
        """判断两个文件名是否指向同一资源（兼容 115 删空格/丢扩展名）。"""
        cur = (current or "").strip()
        des = (desired or "").strip()
        if not cur or not des:
            return False
        if cur == des:
            return True

        c_compact = compact_filename(cur)
        d_compact = compact_filename(des)
        if c_compact and d_compact and c_compact == d_compact:
            return True

        c_stem = compact_filename(cls._strip_video_ext(cur))
        d_stem = compact_filename(cls._strip_video_ext(des))
        if c_stem and d_stem and c_stem == d_stem:
            return True

        # 115 偶发截断：一方是另一方前缀，且足够长
        if c_stem and d_stem:
            shorter, longer = sorted([c_stem, d_stem], key=len)
            if len(shorter) >= 24 and longer.startswith(shorter):
                return True
        return False

    def _extract_size_from_link(self, link: OfflineLink) -> int | None:
        """从 ed2k 链接提取 size（优先正则，避免 split 误伤）。"""
        if link.url_type != "ed2k":
            return None
        try:
            from .offline_link_parser import _ED2K_RE
            m = _ED2K_RE.search(link.url or "")
            if m:
                return int(m.group("size"))
        except Exception:
            pass
        try:
            parts = (link.url or "").split("|")
            # ed2k://|file|name|size|hash|/
            if len(parts) >= 5 and parts[3].isdigit():
                return int(parts[3])
        except Exception:
            return None
        return None

    def _task_name(self, task: Dict[str, Any]) -> str:
        return str(
            task.get("name")
            or task.get("file_name")
            or task.get("n")
            or task.get("fn")
            or ""
        ).strip()

    def _task_file_id(
        self,
        task: Dict[str, Any],
        *,
        save_cid: int | str | None = None,
    ) -> str | None:
        """从离线任务中提取可能的文件 id（仍不可直接用于 rename）。

        115 实测：
        - file_id 经常等于保存目录 cid（wp_path_id），不是文件
        - delete_file_id 在完成后更可能是真实文件 id
        因此优先 delete_file_id，并过滤与 save_cid / wp_path_id 相同的值。
        """
        if not isinstance(task, dict):
            return None

        save_cid_str = str(save_cid).strip() if save_cid is not None else ""
        banned: set[str] = set()
        if save_cid_str and save_cid_str.isdigit():
            banned.add(save_cid_str)
        for key in ("wp_path_id", "path_id", "cid", "parent_id", "pid"):
            val = task.get(key)
            if self._is_digit_id(val):
                banned.add(str(val).strip())

        # 优先 delete_file_id（完成后常为真实文件），再 file_id/fid
        for key in ("delete_file_id", "file_id", "fid"):
            val = task.get(key)
            if not self._is_digit_id(val):
                continue
            text_id = str(val).strip()
            if text_id in banned:
                logger.debug(
                    f"任务字段 {key}={text_id} 与目录 id 相同，已忽略"
                )
                continue
            return text_id

        # 嵌套结构兜底
        for key in ("file", "data", "info"):
            nested = task.get(key)
            if isinstance(nested, dict):
                found = self._task_file_id(nested, save_cid=save_cid)
                if found:
                    return found
        return None

    def _ensure_rename_target_is_file(
        self,
        file_id: str,
        *,
        save_cid: int | str | None = None,
    ) -> bool:
        """重命名前确认目标是文件，绝不是保存目录/普通目录。

        使用 fs_file_skim 轻量判断，避免 get_info 扫大目录。
        """
        fid = str(file_id or "").strip()
        if not fid.isdigit():
            return False
        if save_cid is not None and fid == str(save_cid).strip():
            logger.warning(f"rename 目标与 save_cid 相同，拒绝: {fid}")
            return False

        info = self._skim_attr(fid)
        is_dir = info.get("is_dir")
        name = str(info.get("name") or "")
        if is_dir is True:
            logger.warning(f"rename 目标是目录，拒绝: id={fid}, name={name!r}")
            return False
        if is_dir is None:
            # 无法确认时拒绝，宁可不改名也不误改目录
            logger.warning(
                f"无法确认 rename 目标类型，拒绝重命名: id={fid}, name={name!r}, "
                f"err={info.get('error') or ''}"
            )
            return False
        # is_dir is False -> 文件
        return True

    def _list_recent_tasks(self, max_pages: int = 3) -> List[Dict[str, Any]]:
        """拉取最近离线任务（默认列表 + 已完成），用于匹配 hash / 文件名。"""
        tasks: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def _add_batch(batch: List[Any]) -> int:
            added = 0
            for t in batch or []:
                if not isinstance(t, dict):
                    continue
                # 去重键：info_hash 优先，否则用 name+size
                key = str(
                    t.get("info_hash")
                    or t.get("hash")
                    or t.get("infohash")
                    or ""
                ).upper()
                if not key:
                    key = f"{self._task_name(t)}|{t.get('size') or t.get('file_size') or ''}"
                if key in seen:
                    continue
                seen.add(key)
                tasks.append(t)
                added += 1
            return added

        # stat: None=默认, 11=已完成, 12=进行中
        for stat in (None, 11, 12):
            for page in range(1, max(1, max_pages) + 1):
                try:
                    result = self.list_tasks(page=page, stat=stat)
                except Exception as e:
                    logger.warning(f"拉取离线任务失败: page={page}, stat={stat}, err={e}")
                    break
                if not result.get("success"):
                    logger.info(
                        f"拉取离线任务未成功: page={page}, stat={stat}, "
                        f"err={result.get('error')}"
                    )
                    break
                batch = result.get("tasks") or []
                if not isinstance(batch, list) or not batch:
                    break
                added = _add_batch(batch)
                logger.info(
                    f"离线任务页: page={page}, stat={stat}, raw={len(batch)}, "
                    f"added={added}, total={len(tasks)}"
                )
                page_count = result.get("page_count")
                if page_count is not None:
                    try:
                        if page >= int(page_count):
                            break
                    except Exception:
                        pass
                # 不足一页则结束该 stat
                if len(batch) < 15:
                    break
        return tasks

    def _task_match_key(self, task: Dict[str, Any]) -> str:
        """离线任务去重键：优先 hash，其次 name+size。"""
        if not isinstance(task, dict):
            return ""
        key = str(
            task.get("info_hash")
            or task.get("hash")
            or task.get("infohash")
            or ""
        ).upper()
        if key:
            return f"h:{key}"
        name = self._task_name(task)
        size = str(task.get("size") or task.get("file_size") or "")
        return f"n:{name}|{size}"

    def _find_task_for_link(
        self,
        tasks: List[Dict[str, Any]],
        link: OfflineLink,
        item: Dict[str, Any],
        file_hash: str,
        used_task_keys: set[str] | None = None,
    ) -> Dict[str, Any] | None:
        """在离线任务中匹配当前链接。

        多条时：已占用的任务键（used_task_keys）不会再次匹配，避免串任务。
        优先 hash 精确匹配，文件名仅作回退。
        """
        if not tasks:
            return None

        used_task_keys = used_task_keys or set()
        info_hash_item = str(item.get("info_hash") or "").upper()
        desired = (link.name or "").strip()
        desired_compact = compact_filename(desired)
        hash_upper = (file_hash or "").upper()

        def _available(t: Dict[str, Any]) -> bool:
            key = self._task_match_key(t)
            return (not key) or (key not in used_task_keys)

        # 1) info_hash / url 内嵌 hash 精确匹配
        for t in tasks:
            if not _available(t):
                continue
            th = str(
                t.get("info_hash") or t.get("hash") or t.get("infohash") or ""
            ).upper()
            task_url = str(
                t.get("url") or t.get("ed2k") or t.get("magnet") or t.get("path") or ""
            )
            if info_hash_item and th and th == info_hash_item:
                return t
            if hash_upper and th and th == hash_upper:
                return t
            if hash_upper and hash_upper.lower() in task_url.lower():
                return t

        # 2) 文件名（含去空格 / 去扩展名）匹配
        for t in tasks:
            if not _available(t):
                continue
            name = self._task_name(t)
            if not name:
                continue
            if self._names_loosely_match(name, desired):
                return t
            if desired_compact and compact_filename(name) == desired_compact:
                return t
        return None

    def _find_file_id_in_dir(
        self,
        save_cid: int,
        *,
        desired: str,
        desired_compact: str,
        size_hint: int | None = None,
        exclude_ids: set[str] | None = None,
        recent_rows: List[Dict[str, Any]] | None = None,
    ) -> tuple[str | None, str]:
        """在保存目录中按文件名查找 file_id。

        策略（大目录友好，避免深翻页）：
        1. 搜索优先：关键词优先用 115 实际落盘的 compact（去空格）名
        2. 仅最新一页兜底：按 user_ptime 倒序；多条时可传入 recent_rows 复用
        3. 候选按 精确名 / compact / 宽松名 / size 评分择优
        4. exclude_ids：多条恢复时跳过已被其他链接占用的 file_id

        复用 FileService.search_files / list_files（Open 优先，失败回退 Web）。
        """
        fs = get_file_service()
        candidates: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        save_cid_str = str(save_cid)
        exclude_ids = exclude_ids or set()

        def _has_name_match() -> bool:
            return any(
                self._names_loosely_match(str(c.get("name") or ""), desired)
                for c in candidates
            )

        def _add_items(rows: List[Dict[str, Any]], source: str) -> None:
            added = 0
            skipped_dir = 0
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                if row.get("is_dir"):
                    skipped_dir += 1
                    continue
                fid = str(row.get("file_id") or "").strip()
                name = str(row.get("name") or "").strip()
                if not fid or not name or not fid.isdigit():
                    continue
                # 绝不能把保存目录自身当文件
                if fid == save_cid_str:
                    continue
                # 多条恢复：跳过已被其他链接占用的 id
                if fid in exclude_ids:
                    continue
                parent_id = str(row.get("parent_id") or "").strip()
                # 搜索结果可能跨目录：跨目录仍收候选，评分阶段降权
                if parent_id and parent_id not in ("0", "") and parent_id != save_cid_str:
                    row = dict(row)
                    row["_off_save_dir"] = True
                if fid in seen_ids:
                    continue
                seen_ids.add(fid)
                candidates.append(row)
                added += 1
            if added or skipped_dir:
                logger.info(
                    f"离线恢复候选来自{source}: +{added}, skip_dir={skipped_dir}, "
                    f"total={len(candidates)}"
                )

        # ---- 1) 搜索优先：关键词顺序很关键 ----
        # 115 离线落盘常把空格去掉，所以 compact 名应优先于带空格原名
        keywords: List[str] = []
        desired_stem = self._strip_video_ext(desired)
        compact_stem = compact_filename(desired_stem) if desired_stem else ""
        compact_full = desired_compact or compact_filename(desired)

        for raw in (
            # 实际落盘名（去空格）优先
            compact_full[:60] if compact_full else "",
            compact_stem[:60] if compact_stem else "",
            # 特征中段，避免前缀过于通用
            compact_stem[8:48] if len(compact_stem) > 28 else "",
            # 带空格原名兜底（个别接口/场景仍可能保留空格）
            desired[:60],
            desired_stem[:60] if desired_stem else "",
        ):
            kw = (raw or "").strip()
            if len(kw) >= 4 and kw not in keywords:
                keywords.append(kw)

        for kw in keywords:
            try:
                result = fs.search_files(kw, cid=int(save_cid) if save_cid else 0)
                rows = result.get("items") or []
                logger.info(
                    f"离线恢复搜索: kw={kw!r}, cid={save_cid}, hits={len(rows)}"
                )
                _add_items(rows, f"search:{kw[:24]}")
                # 已有名匹配则立刻结束搜索，不再试后续关键词
                if _has_name_match():
                    break
            except Exception as e:
                logger.warning(f"离线恢复搜索失败: kw={kw!r}, err={e}")

        # ---- 2) 仅最新一页兜底（不深翻页；多条时可复用预取 recent_rows）----
        if not _has_name_match():
            rows: List[Dict[str, Any]] = []
            if recent_rows is not None:
                rows = list(recent_rows)
                logger.info(
                    f"离线恢复最新一页兜底(复用): cid={save_cid}, n={len(rows)}"
                )
            else:
                try:
                    result = fs.list_files(
                        cid=int(save_cid),
                        limit=50,
                        offset=0,
                        order="user_ptime",
                        asc=0,
                    )
                    rows = result.get("items") or []
                    logger.info(
                        f"离线恢复最新一页兜底: cid={save_cid}, n={len(rows)}, "
                        f"count={result.get('count')}"
                    )
                except Exception as e:
                    logger.warning(f"离线恢复最新一页失败: cid={save_cid}, err={e}")
                    rows = []
            if rows:
                preview = [
                    f"{(r.get('name') or '')[:48]}#{r.get('size') or 0}"
                    for r in rows[:5]
                    if not r.get("is_dir")
                ]
                if preview:
                    logger.info(f"离线恢复目录预览: {preview}")
                _add_items(rows, "recent@0")

        # ---- 3) 候选择优 ----
        best_id: str | None = None
        best_name = ""
        best_score = -1
        size_only: List[tuple[str, str]] = []

        for row in candidates:
            name = str(row.get("name") or "").strip()
            fid = str(row.get("file_id") or "").strip()
            if not name or not fid:
                continue
            try:
                sz = int(row.get("size") or 0)
            except Exception:
                sz = 0

            score = 0
            if name == desired:
                score = 100
            elif compact_filename(name) == desired_compact:
                score = 90
            elif self._names_loosely_match(name, desired):
                score = 80
            else:
                # 仅 size 命中：稍后若唯一再采用
                if size_hint and sz and sz == int(size_hint):
                    size_only.append((fid, name))
                continue

            if size_hint and sz and sz == int(size_hint):
                score += 15
            elif size_hint and sz and sz != int(size_hint):
                # 名已匹配时 size 不一致不直接否决（字段偶发异常），略降权
                score -= 5

            # 同保存目录加分；跨目录降权
            if row.get("_off_save_dir"):
                score -= 20
            else:
                parent_id = str(row.get("parent_id") or "").strip()
                if parent_id and parent_id == save_cid_str:
                    score += 10

            if score > best_score:
                best_score = score
                best_id = fid
                best_name = name

        def _safe_file_id(fid: str | None, name: str = "") -> tuple[str | None, str]:
            """确保返回的是文件 id，绝不是保存目录本身。"""
            if not fid or not str(fid).isdigit():
                return None, ""
            if str(fid) == save_cid_str:
                logger.warning(
                    f"目录匹配结果等于 save_cid，已丢弃: id={fid}, name={name!r}"
                )
                return None, ""
            return str(fid), name

        if best_id:
            return _safe_file_id(best_id, best_name)

        # 名字都没匹配时：若 size 唯一命中，谨慎采用
        if size_hint and len(size_only) == 1:
            fid, name = size_only[0]
            logger.info(
                f"离线恢复仅按 size 唯一命中: id={fid}, name={name!r}, size={size_hint}"
            )
            return _safe_file_id(fid, name)

        if candidates:
            preview = [
                f"{(c.get('name') or '')[:48]}#{c.get('size') or 0}"
                for c in candidates[:8]
            ]
            logger.info(
                f"离线恢复未匹配: desired={desired!r}, compact={desired_compact!r}, "
                f"size={size_hint}, candidates={preview}"
            )
        return None, ""

    # ---------------- 查询辅助 ----------------

    def get_quota(self) -> Dict[str, Any]:
        """查询离线配额。

        开启 Open API 时优先 Open，失败回退 Web；否则仅 Web。
        """
        def _call_open():
            open_client = self.client_factory.get_open_client()
            if open_client is None:
                raise RuntimeError("Open API 未启用或 token 无效")
            return open_client.clouddownload_quota_info()

        def _call_web():
            client = self.client_factory.get_web_client()
            return client.clouddownload_quota_info()

        try:
            resp = self._call_with_channel(
                open_caller=_call_open,
                web_caller=_call_web,
                action="查询离线配额",
            )
            if isinstance(resp, dict):
                data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
                return {"success": True, "quota": data, "raw": resp}
            return {"success": True, "quota": resp, "raw": resp}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_tasks(self, page: int = 1, stat: int | None = None) -> Dict[str, Any]:
        """分页获取离线任务列表。

        开启 Open API 时优先 Open，失败回退 Web；否则仅 Web。
        Web 侧依次尝试 type=web / ssp，兼容不同端点。
        stat: 9=失败, 11=已完成, 12=进行中；None 表示默认列表。
        """
        page = max(1, int(page or 1))

        def _call_open():
            open_client = self.client_factory.get_open_client()
            if open_client is None:
                raise RuntimeError("Open API 未启用或 token 无效")
            payload: Dict[str, Any] = {"page": page}
            # Open 文档主要是 page；若后续支持 stat 再透传
            if stat is not None:
                payload["stat"] = stat
            return open_client.clouddownload_task_list(payload)

        def _call_web():
            client = self.client_factory.get_web_client()
            payload: Dict[str, Any] = {"page": page, "page_size": 30}
            if stat is not None:
                payload["stat"] = stat
            last_err: Exception | None = None
            last_resp: Any = None
            for t in ("web", "ssp"):
                try:
                    resp = client.clouddownload_task_list(dict(payload), type=t)
                    last_resp = resp
                    if isinstance(resp, dict) and not self._is_false_state(resp):
                        if isinstance(resp, dict):
                            resp = dict(resp)
                            resp["_list_type"] = t
                        return resp
                    # state 失败也记录，继续试另一 type
                    msg = self._extract_error_message(resp, f"task_list/{t} 失败")
                    last_err = RuntimeError(msg)
                    logger.debug(f"离线任务列表 {t} 业务失败: {msg}")
                except Exception as e:
                    last_err = e
                    logger.debug(f"离线任务列表 {t} 调用失败: {e}")
            if last_err:
                raise last_err
            return last_resp if last_resp is not None else {}

        try:
            resp = self._call_with_channel(
                open_caller=_call_open,
                web_caller=_call_web,
                action="获取离线任务",
            )
            if not isinstance(resp, dict):
                return {"success": False, "error": f"异常返回: {type(resp)}", "page": page}

            tasks = self._extract_task_list(resp)
            count = None
            page_count = None
            # 兼容 data 嵌套与顶层字段
            data = resp.get("data") if isinstance(resp.get("data"), dict) else None
            for src in (data, resp):
                if not isinstance(src, dict):
                    continue
                if count is None and src.get("count") is not None:
                    count = src.get("count")
                if page_count is None and src.get("page_count") is not None:
                    page_count = src.get("page_count")
            return {
                "success": True,
                "page": page,
                "stat": stat,
                "count": count,
                "page_count": page_count,
                "tasks": tasks,
                "raw": resp,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "page": page, "stat": stat}

    @staticmethod
    def _extract_task_list(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从 Open/Web 多种返回结构中提取 tasks 列表。"""
        if not isinstance(resp, dict):
            return []
        # 顶层 tasks（Web 常见）
        for key in ("tasks", "list", "result", "items"):
            val = resp.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
        data = resp.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("tasks", "list", "result", "items", "data"):
                val = data.get(key)
                if isinstance(val, list):
                    return [x for x in val if isinstance(x, dict)]
        return []


_service: Optional[OfflineDownloadService] = None


def get_offline_download_service() -> OfflineDownloadService:
    global _service
    if _service is None:
        _service = OfflineDownloadService()
    return _service
