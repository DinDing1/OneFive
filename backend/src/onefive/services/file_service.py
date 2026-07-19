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
import time
from typing import Optional, Dict, Any, List

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
from p115client.tool.iterdir import iter_files_with_path_skim

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

    def iter_all_files_strm(self, cid: int = 0) -> List[Dict[str, Any]]:
        """使用 p115client.tool.iterdir.iter_files_with_path_skim 遍历云盘 STRM 文件

        该函数通过下载清单接口一次返回 name/pickcode/path，适合生成云盘 STRM。
        需要 P115Client（Web Cookie），OpenAPI 客户端不支持。
        """
        client = self._get_client()
        if not isinstance(client, P115Client):
            raise RuntimeError("iter_files_with_path_skim 需要 P115Client，请关闭 OpenAPI 后重试")

        result: List[Dict[str, Any]] = []
        # max_workers=0 强制串行，降低并发风控概率
        app = "chrome"
        logger.info(
            f"云盘 STRM 使用 iter_files_with_path_skim: cid={cid}, "
            f"client={type(client).__name__}, app={app}"
        )
        for item in iter_files_with_path_skim(
            client,
            cid,
            escape=None,
            max_workers=0,
            app=app,
        ):
            name = item.get("name", "") or item.get("file_name", "")
            pick_code = item.get("pickcode", "") or item.get("pick_code", "")
            path = str(item.get("path") or item.get("relpath") or name).strip("/")
            if not name or not pick_code or not path:
                continue
            result.append({
                "file_id": str(item.get("id") or item.get("file_id") or ""),
                "name": name,
                "is_dir": False,
                "size": int(item.get("size") or item.get("file_size") or 0),
                "file_type": item.get("file_type") or 0,
                "pick_code": pick_code,
                "parent_id": str(item.get("parent_id") or "0"),
                "created_at": str(item.get("created_at") or ""),
                "updated_at": str(item.get("updated_at") or ""),
                "path": path,
            })
        logger.info(f"云盘 STRM iter_files_with_path_skim 完成: cid={cid}, files={len(result)}")
        return result

    # ==================== 批量操作 ====================

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
