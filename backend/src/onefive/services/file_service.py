"""
文件管理服务

职责：
- 封装 p115client.tool 工具函数，提供业务层方法
- Open API 优先，Web API 回退

使用 p115client.tool 工具函数而非直接调用 client 方法，因为：
- tool 函数内部处理了批量、错误重试等逻辑
- batch_move/batch_copy/batch_delete 自动按 batch_size=1000 分批执行
- fs_files_iter 支持自动分页目录列表
- list_files 例外：直接调用 client.fs_files 原生 API 以保证分页语义准确
"""
import threading
import time
from typing import Optional, Dict, Any, List, Iterator, Callable

from p115client import P115Client, P115OpenClient
from p115client.exception import P115BusyOSError
from p115client.tool import (
    fs_files_iter,
    get_info,
    get_path,
    batch_move,
    batch_copy,
    batch_delete,
    makedir,
    update_name,
)
from p115client.tool.attr import get_ancestors

from .p115_client_factory import get_p115_client_factory
from ..logger import get_logger

logger = get_logger(__name__)


class FileService:
    """文件管理服务

    使用 p115client.tool 工具函数封装 115 云盘文件操作。
    所有方法接受 client 实例作为第一个参数，内部由 tool 函数处理。
    """

    def __init__(self):
        self.client_factory = get_p115_client_factory()

    @staticmethod
    def _get_tool_app() -> str:
        """返回 p115client tool 函数的 app 参数

        p115client tool 函数（fs_files_iter/makedir/update_name 等）的 app 参数
        决定走哪个 API 端点：
        - app="web" → 标准端点 fs_files/fs_mkdir/fs_rename（稳定可靠）
        - app="android" → 专用端点 fs_files_app(app="android")（部分返回 405）

        实测结论：专用端点（android/ios）不稳定，统一用 "web" 走标准端点。
        P115Client 初始化的 app 参数（决定 cookie 身份）与 tool 函数的 app 参数
        （决定 API 端点）是两个独立概念，互不影响。
        """
        return "web"

    def _get_client(self) -> P115Client | P115OpenClient:
        """获取已登录的客户端实例

        优先使用 Open API（P115OpenClient + access_token），
        未启用或 token 无效时回退 Web API（P115Client + cookies）。

        tool 函数根据传入的 client 类型自动选择 API：
        - P115OpenClient → Open API（proapi.115.com，分页上限 7000+）
        - P115Client → Web API（webapi.115.com，分页上限 1150）

        app 参数根据登录设备动态选择，保证与 cookie 身份一致。
        """
        return self.client_factory.create_client()

    def _call_with_fallback(self, method_name: str, client, *args, **kwargs):
        """调用 client 方法，Open API 失败时自动回退 Web API

        115 Open API 部分端点可能返回 405（接口变更或权限不足），
        此方法在 Open API 调用失败时自动回退到 Web API 重试。

        P115BusyOSError（115 正忙）不触发回退，直接向上抛出，
        由 _retry_on_busy 统一重试同一 API，避免双重浪费请求。

        Args:
            method_name: client 方法名（如 "fs_files"）
            client: 初始 client 实例
            *args, **kwargs: 传给方法的参数

        Returns:
            方法调用的返回值
        """
        try:
            return getattr(client, method_name)(*args, **kwargs)
        except P115BusyOSError:
            # 115 正忙：不回退，由 _retry_on_busy 统一重试
            raise
        except Exception as e:
            if isinstance(client, P115OpenClient):
                logger.warning(f"Open API {method_name} 调用失败，回退 Web API: {e}")
                web_client = self.client_factory.create_web_client()
                return getattr(web_client, method_name)(*args, **kwargs)
            raise

    @staticmethod
    def _retry_on_busy(func, *args, max_retries=3, delay=2, **kwargs):
        """115 忙时自动重试

        115 云盘在高并发或高峰期经常返回 P115BusyOSError，
        这是暂时性错误，等一会儿重试同一 API 即可恢复。

        Args:
            func: 要调用的函数
            max_retries: 最大重试次数
            delay: 基础等待秒数（实际等待 = delay × 重试序号）
        """
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except P115BusyOSError:
                if attempt == max_retries - 1:
                    raise
                wait = delay * (attempt + 1)
                logger.warning(f"115 系统繁忙，{wait}秒后重试 ({attempt+1}/{max_retries})")
                time.sleep(wait)

    # ==================== 文件列表 ====================

    def list_files(self, cid: int = 0, limit: int = 100, offset: int = 0,
                   order: str = "file_name", asc: int = 1) -> Dict[str, Any]:
        """列出目录内容

        直接调用 client.fs_files 原生 API（不走 tool 的自动翻页），
        以确保 limit / offset 分页语义准确，只返回当前页数据。

        Open API 的 fs_files 端点可能返回 405（接口变更或权限不足），
        此时自动回退到 Web API。

        Args:
            cid: 目录 ID，0 表示根目录
            limit: 分页大小
            offset: 分页偏移
            order: 排序字段 (file_name/file_size/file_type/user_utime/user_ptime)
            asc: 排序方向 (1=升序 0=降序)

        Returns:
            {"items": [...], "count": N, "offset": N, "limit": N, "parent_id": "xxx"}
        """
        client = self._get_client()

        payload = {
            "cid": cid,
            "limit": limit,
            "offset": offset,
            "o": order,
            "asc": asc,
        }
        # 直接调用 client 方法，避免 tool.fs_files 自动翻页导致 limit/offset 失效
        # Open API 可能 405，_call_with_fallback 自动回退 Web API
        # P115BusyOSError 自动重试
        result = self._retry_on_busy(
            lambda: self._call_with_fallback("fs_files", client, payload)
        )
        file_list = result.get("data") or []
        items = [self._parse_file_item(f) for f in file_list]

        return {
            "items": items,
            "count": result.get("count", len(items)),
            "offset": result.get("offset", offset),
            "limit": result.get("limit", limit),
            "parent_id": str(cid),
        }

    @staticmethod
    def _detect_is_dir(f: Dict) -> bool:
        """统一判断是否为目录，兼容 Web API 和 Open API

        各来源的目录判定规则：
        - Open API 搜索结果：含 file_name 字段，file_category=0 且无 file_size 表示目录
        - Open API 列表 / Web API 搜索：含 fc 字段，fc == "0" 表示目录
          （统一用 str() 比较，兼容字符串 "0" 与整数 0）
        - Web API 列表：cid 存在且不为 "0" 表示目录
        """
        # Open API 搜索结果：file_category=0 且无 file_size 表示目录
        if "file_name" in f:
            return f.get("file_category") == 0 and "file_size" not in f
        # Open API 列表和 Web API：fc == "0" 表示目录
        if "fc" in f:
            return str(f.get("fc")) == "0"
        # Web API 列表：cid 存在且不为 "0" 表示目录
        cid_val = f.get("cid", "0")
        return bool(cid_val) and str(cid_val) != "0"

    @staticmethod
    def _parse_file_item(f: Dict) -> Dict[str, Any]:
        """将 115 返回的文件数据转为统一格式

        兼容三种字段命名：

        1. Web API（列表）：cid / fid / n / s / pc / te / tp / pid
        2. Open API（列表）：fid / fn / fc / pc / uet / upt / pid / fs
        3. Open API（搜索）：file_id / file_name / parent_id / pick_code / user_ptime / user_utime
        """
        # 文件名：file_name > fn > n
        name = f.get("file_name") or f.get("fn") or f.get("n") or ""

        # 文件 ID：file_id > cid > fid
        file_id = f.get("file_id") or f.get("fid") or f.get("cid") or "0"

        # 统一判断是否为目录
        is_dir = FileService._detect_is_dir(f)

        # Web API 列表分支（既无 file_name 也无 fc）：目录的 ID 取自 cid 字段
        if is_dir and "file_name" not in f and "fc" not in f:
            cid_val = f.get("cid", "0")
            if cid_val and str(cid_val) != "0":
                file_id = cid_val

        # 文件大小
        size = f.get("fs") or f.get("s") or f.get("file_size") or 0

        # 时间字段：user_ptime > uet > te
        created_at = f.get("user_ptime") or f.get("uet") or f.get("te") or ""

        # 时间字段：user_utime > upt > tp
        updated_at = f.get("user_utime") or f.get("upt") or f.get("tp") or ""

        return {
            "file_id": str(file_id),
            "name": name,
            "is_dir": bool(is_dir),
            "size": int(size) if size else 0,
            "file_type": f.get("file_type") or f.get("file_category") or 0,
            "pick_code": f.get("pick_code") or f.get("pc") or "",
            "parent_id": str(f.get("parent_id") or f.get("pid") or "0"),
            "created_at": str(created_at),
            "updated_at": str(updated_at),
        }

    # ==================== 文件详情 ====================

    def get_file_info(self, file_id: str) -> Dict[str, Any]:
        """获取文件/目录详情

        使用 p115client.tool.get_info。
        注意：如果是目录，会计算子目录树下所有文件数和目录数，数量越多响应越久。

        Args:
            file_id: 文件或目录的 ID 或 pickcode

        Returns:
            文件/目录详细信息
        """
        client = self._get_client()
        return get_info(client, file_id)

    # ==================== 获取路径 ====================

    def get_file_path(self, file_id: str) -> str:
        """获取文件/目录的完整路径

        使用 p115client.tool.get_path，从当前节点向上遍历到根目录拼接路径。

        Args:
            file_id: 文件或目录的 ID 或 pickcode

        Returns:
            完整路径，如 "/云下载/电影/xxx.mp4"
        """
        client = self._get_client()
        return get_path(client, file_id)

    # ==================== 创建目录 ====================

    def create_folder(self, name: str, pid: int = 0) -> Dict[str, Any]:
        """创建目录

        直接调用 client.fs_mkdir，不使用 tool.makedir。
        tool.makedir 内部会做额外操作（可能触发登录错误），但文件夹已创建成功。

        Args:
            name: 目录名
            pid: 父目录 ID，0 表示根目录

        Returns:
            115 API 响应结果
        """
        client = self._get_client()
        # P115BusyOSError 自动重试
        return self._retry_on_busy(
            lambda: self._call_with_fallback("fs_mkdir", client, name, pid=pid)
        )

    def create_folder_path(self, path: str, pid: int = 0) -> int:
        """一次性创建多级目录路径，返回最终目录的 cid

        使用 p115client.tool.makedir(contain_dir=True)，
        一次 API 调用创建整条路径，替代逐级创建+sleep 的低效方式。
        makedir 内部已自带 P115BusyOSError 自动重试。

        Args:
            path: 多级目录路径，如 "媒体库/电影/国产电影"
            pid: 根父目录 ID，0 表示云盘根目录

        Returns:
            最终目录的 cid（int）
        """
        client = self._get_client()
        return makedir(client, path, pid=pid, contain_dir=True, app=self._get_tool_app())

    # ==================== 搜索 ====================

    def search_files(self, keyword: str, cid: int = 0) -> Dict[str, Any]:
        """搜索文件

        使用 _get_client() 获取客户端（Open API 优先，Web API 回退），
        Open API 用户也能正常搜索。_parse_file_item 已兼容 Open API 搜索
        结果字段（file_name / file_id / pick_code），无需额外处理。

        Args:
            keyword: 搜索关键词
            cid: 搜索起点目录 ID，0 表示全盘搜索

        Returns:
            {"items": [...], "count": N, ...}
        """
        # 统一走 _get_client：Open API 优先，Web API 回退
        client = self._get_client()
        # P115BusyOSError 自动重试
        result = self._retry_on_busy(
            lambda: self._call_with_fallback(
                "fs_search", client,
                {"search_value": keyword, "cid": cid, "limit": 100}
            )
        )
        file_list = result.get("data") or []
        items = [self._parse_file_item(f) for f in file_list] if isinstance(file_list, list) else []

        return {
            "items": items,
            "count": result.get("count", len(items)),
            "offset": 0,
            "limit": len(items),
            "parent_id": str(cid),
        }

    # ==================== 目录树遍历 ====================

    def iter_all_files(self, cid: int = 0) -> List[Dict[str, Any]]:
        """自动分页遍历目录下全部文件（含子目录中的文件）

        使用 p115client.tool.fs_files_iter，自动分页、自带 P115BusyOSError 重试。
        替代手动 limit+offset 分页，避免大目录文件遗漏。

        注意：
        - fs_files_iter 每次迭代返回一整页响应（含 data/count/cid 等），
          需要从 page["data"] 提取文件列表，而非把整页当作单个文件
        - 只返回当前目录直属文件，不递归子目录
        - 用 max_workers=0 强制串行拉取，避免并发请求触发 115 风控返回 401

        Args:
            cid: 目录 ID，0 表示根目录

        Returns:
            文件信息列表
        """
        client = self._get_client()
        result = []
        # max_workers=0 强制串行拉取，避免并发请求触发 115 风控
        for page in fs_files_iter(client, cid, app=self._get_tool_app(), max_workers=0):
            for f in page.get("data", []):
                result.append(self._parse_file_item(f))
        return result







    @staticmethod
    def _is_http_method_not_allowed(exc: BaseException) -> bool:
        """识别 HTTP 405 / Method Not Allowed（含包装异常）。"""
        cur: BaseException | None = exc
        seen: set[int] = set()
        while cur is not None and id(cur) not in seen:
            seen.add(id(cur))
            code = getattr(cur, "code", None) or getattr(cur, "status", None)
            try:
                if int(code) == 405:
                    return True
            except (TypeError, ValueError):
                pass
            msg = str(cur).lower()
            if "405" in msg and (
                "method not allowed" in msg or "not allowed" in msg
            ):
                return True
            cur = cur.__cause__ or cur.__context__
        return False

    def _install_download_list_retry(
        self,
        client: P115Client,
        *,
        max_retries: int = 5,
        base_sleep: float = 1.5,
    ):
        """给 download_folders_app / download_files_app 包 405/忙 退避重试。

        云盘 STRM 自管分页仍走这两类接口；此处统一加固。
        返回还原函数，务必在 finally 调用。
        """
        method_names = ("download_folders_app", "download_files_app")
        originals: dict[str, Any] = {}
        for name in method_names:
            originals[name] = getattr(client, name)

        def _make_wrapper(method_name: str):
            bound = originals[method_name]

            def _wrapped(payload, /, *args, **kwargs):
                last_exc: BaseException | None = None
                attempts = max(0, int(max_retries)) + 1
                for attempt in range(attempts):
                    try:
                        return bound(payload, *args, **kwargs)
                    except P115BusyOSError as e:
                        last_exc = e
                        if attempt >= attempts - 1:
                            raise
                        sleep_s = base_sleep * (attempt + 1)
                        logger.warning(
                            f"云盘 STRM {method_name} 忙，"
                            f"{sleep_s:.1f}s 后重试 ({attempt + 1}/{attempts - 1})"
                        )
                        time.sleep(sleep_s)
                    except Exception as e:
                        last_exc = e
                        retryable = self._is_http_method_not_allowed(e) or any(
                            x in str(e).lower()
                            for x in ("429", "502", "503", "504", "timeout")
                        )
                        if not retryable or attempt >= attempts - 1:
                            raise
                        sleep_s = base_sleep * (2 ** attempt) + 0.2 * attempt
                        logger.warning(
                            f"云盘 STRM {method_name} 遇可重试错误，"
                            f"{sleep_s:.1f}s 后重试 ({attempt + 1}/{attempts - 1}): "
                            f"{type(e).__name__}: {e}"
                        )
                        time.sleep(sleep_s)
                assert last_exc is not None
                raise last_exc

            return _wrapped

        for name in method_names:
            setattr(client, name, _make_wrapper(name))

        def _restore() -> None:
            for name, orig in originals.items():
                try:
                    setattr(client, name, orig)
                except Exception:
                    pass

        return _restore




    def _iter_chrome_download_folders(
        self,
        client: P115Client,
        cid: int,
        id_to_dirnode: Dict[int, tuple],
        *,
        page_size: int = 3000,
        cooldown: float = 0.6,
        timeout: float = 60,
    ):
        """安全分页拉取 chrome downfolders，写入 id_to_dirnode，并 yield 目录节点。

        不使用 iter_download_nodes 的分页器：concurrenttools 在 has_next_page=False
        时可能不 break，导致同一页死循环（dirs 暴涨、map 不变，最终 405）。

        停止条件（任一满足即结束）：
        1) 本页 list 为空
        2) has_next_page 明确为假
        3) 本页没有任何「新目录 id」（重复页）
        4) 本页条数 < page_size（通常已是末页）
        """
        # 解析目录 pickcode
        try:
            pickcode = client.to_pickcode(cid)
        except Exception:
            pickcode = ""
        if not pickcode and cid:
            # 兜底：部分版本用 to_pickcode 失败时再试属性
            try:
                from p115client.tool.attr import get_attr
                attr = get_attr(client, cid, app="web", timeout=timeout)
                pickcode = (
                    (attr or {}).get("pickcode")
                    or (attr or {}).get("pick_code")
                    or ""
                )
            except Exception as e:
                raise RuntimeError(f"无法解析目录 pickcode: cid={cid}, {e}") from e
        if not pickcode and cid:
            raise RuntimeError(f"目录无 pickcode，无法拉 downfolders: cid={cid}")

        page = 1
        last_call_ts = 0.0
        total_yielded = 0
        while True:
            if cooldown > 0 and last_call_ts > 0:
                delta = last_call_ts + cooldown - time.time()
                if delta > 0:
                    time.sleep(delta)

            payload = {
                "pickcode": pickcode,
                "page": page,
                "per_page": page_size,
            }
            last_call_ts = time.time()
            resp = client.download_folders_app(
                payload,
                app="chrome",
                timeout=timeout,
            )
            if not isinstance(resp, dict):
                raise RuntimeError(f"downfolders 响应异常: type={type(resp)}")

            if resp.get("state") is False:
                err = resp.get("error") or resp.get("message") or resp
                raise RuntimeError(f"downfolders 业务失败: {err}")

            data = resp.get("data")
            if isinstance(data, dict):
                raw_list = data.get("list") or []
                has_next_src = data
            elif isinstance(data, list):
                raw_list = data
                has_next_src = resp
            else:
                raw_list = resp.get("list") or []
                has_next_src = resp
                data = resp
            if not isinstance(raw_list, list):
                raw_list = []

            has_next = None
            if isinstance(has_next_src, dict):
                has_next = has_next_src.get("has_next_page")
            if has_next is None:
                has_next = resp.get("has_next_page")

            new_in_page = 0
            for info in raw_list:
                if not isinstance(info, dict):
                    continue
                # 原始 chrome 字段 fid/fn/pid 或已规范化
                try:
                    fid = int(info.get("fid") or info.get("id") or 0)
                except (TypeError, ValueError):
                    continue
                if not fid:
                    continue
                name = str(info.get("fn") or info.get("name") or "")
                try:
                    pid = int(info.get("pid") or info.get("parent_id") or 0)
                except (TypeError, ValueError):
                    pid = 0

                is_new = fid not in id_to_dirnode
                id_to_dirnode[fid] = (name, pid)
                if is_new:
                    new_in_page += 1
                total_yielded += 1
                yield {
                    "is_dir": True,
                    "id": fid,
                    "name": name,
                    "parent_id": pid,
                }

            # 分页明细仅 debug，正式环境 INFO 只保留起止摘要
            logger.debug(
                f"云盘 STRM downfolders 页: page={page}, raw={len(raw_list)}, "
                f"new={new_in_page}, map={len(id_to_dirnode)}, "
                f"has_next={has_next}"
            )

            # 停止条件
            if not raw_list:
                break
            if has_next is False or has_next == 0 or has_next == "0":
                break
            if new_in_page == 0:
                # 本页无新 id，视为重复/空转，防止死循环
                logger.warning(
                    f"云盘 STRM downfolders 第 {page} 页无新增目录，停止分页 "
                    f"(map={len(id_to_dirnode)})"
                )
                break
            if len(raw_list) < page_size:
                break

            page += 1
            # 硬顶：防止异常 has_next 一直为真
            if page > 100000:
                logger.warning("云盘 STRM downfolders 页数超过硬顶，停止")
                break


    def _iter_chrome_download_files(
        self,
        client: P115Client,
        cid: int,
        id_to_dirnode: Dict[int, tuple],
        *,
        page_size: int = 3000,
        cooldown: float = 0.6,
        timeout: float = 60,
    ):
        """安全分页拉取 chrome downfiles，拼 path 后 yield 文件。

        与目录侧相同：不用 iter_download_nodes / skim 内部分页器，
        避免 has_next_page 异常时死循环（files 涨到十几万仍不结束）。

        停止条件：空页 / has_next 假 / 本页无新 pickcode / 条数 < page_size。
        """
        try:
            pickcode = client.to_pickcode(cid)
        except Exception:
            pickcode = ""
        if not pickcode and cid:
            try:
                from p115client.tool.attr import get_attr
                attr = get_attr(client, cid, app="web", timeout=timeout)
                pickcode = (
                    (attr or {}).get("pickcode")
                    or (attr or {}).get("pick_code")
                    or ""
                )
            except Exception as e:
                raise RuntimeError(f"无法解析目录 pickcode: cid={cid}, {e}") from e
        if not pickcode and cid:
            raise RuntimeError(f"目录无 pickcode，无法拉 downfiles: cid={cid}")

        # 路径绑定
        try:
            from p115client.tool.iterdir import make_path_binder
            bind = make_path_binder(
                id_to_dirnode, escape=None, with_ancestors=False
            )
        except Exception:
            bind = None

        top_id = int(cid or 0)
        top_prefix_len = 0
        seen_pc: set[str] = set()

        def _build_path(parent_id: int, name: str, item_for_bind: dict | None = None) -> str:
            nonlocal top_prefix_len
            if bind is not None and item_for_bind is not None:
                try:
                    if not top_prefix_len:
                        if top_id:
                            top_path = bind.get_path(top_id) or ""
                            top_prefix_len = (
                                1 if top_path == "/" else len(str(top_path)) + 1
                            )
                        else:
                            top_prefix_len = 1
                    bind(item_for_bind)
                    path_full = str(item_for_bind.get("path") or "")
                    if path_full and top_prefix_len:
                        return path_full[top_prefix_len:].strip("/") or name
                    return path_full.strip("/") or name
                except Exception:
                    pass
            # 手工拼相对路径
            parts = [name]
            seen: set[int] = set()
            pid = int(parent_id or 0)
            while pid and pid != top_id and pid not in seen:
                seen.add(pid)
                node = id_to_dirnode.get(pid)
                if not node:
                    break
                parts.append(str(node[0]))
                pid = int(node[1])
            parts.reverse()
            return "/".join(p for p in parts if p)

        page = 1
        last_call_ts = 0.0
        # ensure_name：批量用 fs_file_skim 补文件名（与 p115 ensure_name 类似，按页）
        while True:
            if cooldown > 0 and last_call_ts > 0:
                delta = last_call_ts + cooldown - time.time()
                if delta > 0:
                    time.sleep(delta)

            payload = {
                "pickcode": pickcode,
                "page": page,
                "per_page": page_size,
            }
            last_call_ts = time.time()
            resp = client.download_files_app(
                payload,
                app="chrome",
                timeout=timeout,
            )
            if not isinstance(resp, dict):
                raise RuntimeError(f"downfiles 响应异常: type={type(resp)}")
            if resp.get("state") is False:
                err = resp.get("error") or resp.get("message") or resp
                raise RuntimeError(f"downfiles 业务失败: {err}")

            data = resp.get("data")
            if isinstance(data, dict):
                raw_list = data.get("list") or []
                has_next_src = data
            elif isinstance(data, list):
                raw_list = data
                has_next_src = resp
            else:
                raw_list = resp.get("list") or []
                has_next_src = resp

            has_next = None
            if isinstance(has_next_src, dict):
                has_next = has_next_src.get("has_next_page")
            if has_next is None:
                has_next = resp.get("has_next_page")

            # 规范化本页节点
            page_items: list[dict] = []
            for info in raw_list:
                if not isinstance(info, dict):
                    continue
                pc = str(info.get("pc") or info.get("pickcode") or info.get("pick_code") or "")
                if not pc:
                    continue
                try:
                    pid = int(info.get("pid") or info.get("parent_id") or 0)
                except (TypeError, ValueError):
                    pid = 0
                try:
                    size = int(info.get("fs") or info.get("size") or 0)
                except (TypeError, ValueError):
                    size = 0
                # id 常由 pickcode 推导；先占位
                try:
                    from p115pickcode import to_id as _to_id
                    fid = int(_to_id(pc))
                except Exception:
                    try:
                        fid = int(info.get("id") or info.get("file_id") or 0)
                    except (TypeError, ValueError):
                        fid = 0
                page_items.append({
                    "is_dir": False,
                    "id": fid,
                    "pickcode": pc,
                    "parent_id": pid,
                    "size": size,
                    "name": str(info.get("fn") or info.get("name") or info.get("file_name") or ""),
                    "sha1": info.get("sha1") or "",
                })

            # 补文件名（chrome downfiles 常无 name）
            need_name = [x for x in page_items if not x.get("name") and x.get("id")]
            if need_name:
                try:
                    ids = [x["id"] for x in need_name if x["id"]]
                    # 分批 1000
                    for off in range(0, len(ids), 1000):
                        batch_ids = ids[off: off + 1000]
                        skim = client.fs_file_skim(batch_ids, method="POST", timeout=timeout)
                        if not isinstance(skim, dict):
                            continue
                        rows = skim.get("data") or []
                        if not isinstance(rows, list):
                            continue
                        by_pc = {}
                        for node in rows:
                            if not isinstance(node, dict):
                                continue
                            k = str(node.get("pick_code") or node.get("pc") or "")
                            if k:
                                by_pc[k] = node
                        for it in need_name:
                            node = by_pc.get(it["pickcode"])
                            if not node:
                                continue
                            fn = node.get("file_name") or node.get("fn") or node.get("name")
                            if fn:
                                it["name"] = str(fn)
                            if not it.get("sha1") and node.get("sha1"):
                                it["sha1"] = node.get("sha1")
                except Exception as e:
                    logger.warning(
                        f"云盘 STRM fs_file_skim 补名失败(页 {page}): {e}"
                    )

            new_in_page = 0
            for it in page_items:
                pc = it["pickcode"]
                if pc in seen_pc:
                    continue
                seen_pc.add(pc)
                new_in_page += 1
                name = it.get("name") or pc
                path_s = _build_path(
                    int(it.get("parent_id") or 0),
                    name,
                    {
                        "id": it.get("id"),
                        "name": name,
                        "parent_id": it.get("parent_id"),
                        "is_dir": False,
                    },
                )
                if not path_s:
                    path_s = name
                yield {
                    "id": it.get("id") or "",
                    "name": name,
                    "pickcode": pc,
                    "pick_code": pc,
                    "parent_id": it.get("parent_id") or 0,
                    "path": path_s,
                    "size": it.get("size") or 0,
                }

            logger.debug(
                f"云盘 STRM downfiles 页: page={page}, raw={len(raw_list)}, "
                f"new={new_in_page}, seen={len(seen_pc)}, has_next={has_next}"
            )

            if not raw_list:
                break
            if has_next is False or has_next == 0 or has_next == "0":
                break
            if new_in_page == 0:
                logger.warning(
                    f"云盘 STRM downfiles 第 {page} 页无新增文件，停止分页 "
                    f"(seen={len(seen_pc)})"
                )
                break
            if len(raw_list) < page_size:
                break
            page += 1
            if page > 100000:
                logger.warning("云盘 STRM downfiles 页数超过硬顶，停止")
                break

    def iter_all_files_strm(
        self,
        cid: int = 0,
        on_scan_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """流式遍历云盘文件，供云盘 STRM 生成。

        正确用法（对照 p115client iterdir/download 实现）：

        1) 先自管分页 ``download_folders_app(app=chrome)`` 拉全量目录表（防 nodes 分页死循环）
           填入 ``id_to_dirnode``（可 progress：目录数）。
        2) 再自管分页 ``download_files_app(app=chrome)`` 拉文件并拼 path
           （同样不用 nodes 分页器，避免文件侧死循环不结束）。

        固定 app=chrome；对 download_* 做 405/忙退避；串行 + 分页冷却 + 超时。
        """
        client = self.client_factory.get_web_client()
        if not isinstance(client, P115Client):
            raise RuntimeError(
                "云盘 STRM 需要 P115Client（Web Cookie）。"
                "download 清单不支持纯 OpenAPI 客户端。"
            )

        def _progress(payload: Dict[str, Any]) -> None:
            if not on_scan_progress:
                return
            try:
                on_scan_progress(payload)
            except Exception:
                pass

        app = "chrome"
        request_timeout = 60
        # 批量接口 per_page 上限 5000；略降 + 冷却，降低连翻页 405
        page_size = 3000
        page_cooldown = 0.6
        strategy = f"chrome_downfolders_downfiles"

        restore_retry = self._install_download_list_retry(client)
        id_to_dirnode: Dict[int, tuple] = {}
        t0 = time.time()

        stop_hb = threading.Event()
        stat = {"phase": "dirs", "dirs": 0, "files": 0}

        def _heartbeat() -> None:
            while not stop_hb.wait(2.0):
                _progress({
                    "strategy": strategy,
                    "phase": stat["phase"],
                    "dirs": stat["dirs"],
                    "files": stat["files"],
                    "map_size": len(id_to_dirnode),
                    "elapsed": time.time() - t0,
                    "waiting": stat["dirs"] == 0 and stat["files"] == 0,
                    "app": app,
                })

        threading.Thread(
            target=_heartbeat,
            name=f"strm-chrome-hb-{cid}",
            daemon=True,
        ).start()

        logger.debug(
            f"云盘 STRM 扫描参数: cid={cid}, page_size={page_size}, "
            f"cooldown={page_cooldown}, timeout={request_timeout}"
        )
        _progress({
            "strategy": strategy,
            "phase": "dirs",
            "dirs": 0,
            "files": 0,
            "elapsed": 0.0,
            "waiting": True,
            "app": app,
            "message": "start_dirs",
        })

        dir_count = 0
        last_dir_log = 0.0
        try:
            try:
                _ = client.pickcode_stable_point
            except Exception:
                # 预热失败不影响主流程，不打 INFO 噪音
                pass

            # ---------- 阶段1：chrome 目录清单（自管分页，防死循环）----------
            for _node in self._iter_chrome_download_folders(
                client,
                cid,
                id_to_dirnode,
                page_size=page_size,
                cooldown=page_cooldown,
                timeout=request_timeout,
            ):
                dir_count += 1
                stat["dirs"] = dir_count
                now = time.time()
                # 进度只走 SSE，避免目录树刷屏日志
                if (
                    dir_count == 1
                    or dir_count % 5000 == 0
                    or now - last_dir_log >= 3.0
                ):
                    _progress({
                        "strategy": strategy,
                        "phase": "dirs",
                        "dirs": dir_count,
                        "files": 0,
                        "map_size": len(id_to_dirnode),
                        "elapsed": now - t0,
                        "waiting": False,
                        "app": app,
                    })
                    last_dir_log = now

            # 补祖先，保证相对 path 可绑定
            try:
                get_ancestors(
                    client,
                    cid,
                    id_to_dirnode=id_to_dirnode,
                    ensure_file=False,
                    app="web",
                    timeout=request_timeout,
                )
            except Exception as e:
                logger.warning(
                    f"云盘 STRM get_ancestors 失败（继续）: cid={cid}, {e}"
                )

            t_dirs = time.time() - t0
            logger.debug(
                f"云盘 STRM 目录树完成: cid={cid}, dirs={dir_count}, "
                f"map={len(id_to_dirnode)}, elapsed={t_dirs:.1f}s"
            )
            stat["phase"] = "files"
            _progress({
                "strategy": strategy,
                "phase": "dirs_done",
                "dirs": dir_count,
                "files": 0,
                "map_size": len(id_to_dirnode),
                "elapsed": t_dirs,
                "app": app,
            })

            # ---------- 阶段2：chrome downfiles 自管分页（防死循环）----------
            yielded = 0
            last_log = 0.0

            for item in self._iter_chrome_download_files(
                client,
                cid,
                id_to_dirnode,
                page_size=page_size,
                cooldown=page_cooldown,
                timeout=request_timeout,
            ):
                name = item.get("name", "") or ""
                pick_code = (
                    item.get("pickcode", "")
                    or item.get("pick_code", "")
                    or ""
                )
                path_s = str(item.get("path") or name).strip("/")
                if not name or not pick_code or not path_s:
                    continue

                yielded += 1
                stat["files"] = yielded
                now = time.time()
                # 进度只走 SSE，避免文件清单刷屏日志
                if (
                    yielded == 1
                    or yielded % 2000 == 0
                    or now - last_log >= 3.0
                ):
                    _progress({
                        "strategy": strategy,
                        "phase": "files",
                        "dirs": dir_count,
                        "files": yielded,
                        "elapsed": now - t0,
                        "waiting": False,
                        "app": app,
                    })
                    last_log = now

                yield {
                    "file_id": str(item.get("id") or item.get("file_id") or ""),
                    "name": name,
                    "pick_code": pick_code,
                    "path": path_s,
                }

            logger.info(
                f"云盘 STRM 扫描完成: 目录 {dir_count}，文件 {yielded}，"
                f"耗时 {time.time() - t0:.1f}s"
            )
        except Exception as e:
            logger.error(
                f"云盘 STRM 失败: cid={cid}, "
                f"phase={stat.get('phase')}, dirs={stat.get('dirs')}, "
                f"files={stat.get('files')}, "
                f"elapsed={time.time() - t0:.1f}s, "
                f"err={type(e).__name__}: {e}"
            )
            raise
        finally:
            stop_hb.set()
            id_to_dirnode.clear()
            restore_retry()


    def is_dir_empty(self, cid: int | str) -> bool:
        """判断目录是否为空（无任何直属文件/子目录）。

        不确定或列举失败时返回 False，避免误删。
        """
        try:
            cid_i = int(cid)
        except (TypeError, ValueError):
            return False
        if cid_i == 0:
            return False
        try:
            page = self.list_files(cid=cid_i, limit=1, offset=0)
            items = page.get("items") or []
            return len(items) == 0
        except Exception as e:
            logger.warning(f"检查目录是否为空失败: cid={cid}, err={e}")
            return False

    def get_parent_id(self, file_id: str | int) -> Optional[str]:
        """获取文件/目录的父目录 ID。

        使用 p115client.tool.attr.get_attr（含 parent_id），
        比 get_info 更轻，且不统计整棵子树。
        """
        try:
            from p115client.tool.attr import get_attr
            client = self._get_client()
            info = get_attr(client, file_id)
            pid = info.get("parent_id")
            if pid is None:
                return None
            return str(pid)
        except Exception as e:
            logger.warning(f"获取父目录失败: id={file_id}, err={e}")
            return None

    def move_files(self, file_ids: List[str], to_cid: str) -> None:
        """批量移动文件/目录到目标目录

        使用 p115client.tool.batch_move，内部自动按 batch_size=1000 分批执行。

        注意事项：
        - 不要并发执行，必须串行调用
        - 单次操作限制 5 万个文件/目录以内

        Args:
            file_ids: 文件/目录 ID 列表，如 ["123", "456", "789"]
            to_cid: 目标目录 ID
        """
        client = self._get_client()
        batch_move(client, file_ids, pid=int(to_cid))

    def copy_files(self, file_ids: List[str], to_cid: str) -> None:
        """批量复制文件/目录到目标目录

        使用 p115client.tool.batch_copy，内部自动按 batch_size=1000 分批执行。

        注意事项：
        - 不要并发执行，必须串行调用
        - 单次操作限制 5 万个文件/目录以内

        Args:
            file_ids: 文件/目录 ID 列表
            to_cid: 目标目录 ID
        """
        client = self._get_client()
        batch_copy(client, file_ids, pid=int(to_cid))

    def delete_files(self, file_ids: List[str]) -> None:
        """批量删除文件/目录（移入回收站）

        使用 p115client.tool.batch_delete，内部自动按 batch_size=1000 分批执行。

        注意事项：
        - 不要并发执行，必须串行调用
        - 单次操作限制 5 万个文件/目录以内
        - 删除后进入回收站，可通过回收站恢复

        Args:
            file_ids: 文件/目录 ID 列表
        """
        client = self._get_client()
        batch_delete(client, file_ids)

    def rename_file(self, file_id: str, new_name: str) -> None:
        """重命名单个文件/目录

        直接调用 client.fs_rename，不使用 tool.renamefile。
        tool.renamefile 可能触发额外操作导致失败。

        注意事项：
        - 仅支持单个文件，不支持批量
        - 改名时不能修改扩展名，但必须带上扩展名
          例如：rename_file("123", "新名字.mp4") ✅
                rename_file("123", "新名字")     ❌ 会截断为 "新名字"
        - 如需批量重命名，需循环调用此方法

        Args:
            file_id: 文件/目录 ID
            new_name: 新文件名（必须包含扩展名）
        """
        client = self._get_client()
        # P115BusyOSError 自动重试
        self._retry_on_busy(
            lambda: self._call_with_fallback("fs_rename", client, (file_id, new_name))
        )

    def batch_rename(self, id_name_pairs: List[tuple]) -> None:
        """批量重命名文件/目录

        使用 p115client.tool.update_name，一次请求处理大量文件，
        内部自带 P115BusyOSError 自动重试。
        替代循环调用 rename_file 的低效方式（40集剧从40次API降到1次）。

        注意：update_name 不支持 Open API，仅 Web API 可用。

        Args:
            id_name_pairs: (file_id, new_name) 元组列表
        """
        if not id_name_pairs:
            return
        client = self._get_client()
        update_name(client, id_name_pairs, app=self._get_tool_app())


# 全局单例
_file_service: Optional[FileService] = None


def get_file_service() -> FileService:
    """获取文件管理服务实例"""
    global _file_service
    if _file_service is None:
        _file_service = FileService()
    return _file_service
