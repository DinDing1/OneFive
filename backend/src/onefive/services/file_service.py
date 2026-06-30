"""
文件管理服务

职责：
- 封装 p115client.tool 工具函数，提供业务层方法
- Open API 优先，Web API 回退

使用 p115client.tool 工具函数而非直接调用 client 方法，因为：
- tool 函数内部处理了分页、批量、错误重试等逻辑
- batch_move/batch_copy/batch_delete 自动按 batch_size=1000 分批执行
- fs_files 自动分页拉取整个目录
- iter_files/iter_dirs 支持目录树遍历
"""
from typing import Optional, Dict, Any, List

from p115client import P115Client, P115OpenClient
from p115client.tool import (
    fs_files,
    iter_files,
    iter_dirs,
    get_info,
    get_path,
    batch_move,
    batch_copy,
    batch_delete,
)

from .auth_service import get_auth_service
from .token_service import get_token_service
from ..exceptions import NotLoggedInError
from ..logger import get_logger

logger = get_logger(__name__)


class FileService:
    """文件管理服务

    使用 p115client.tool 工具函数封装 115 云盘文件操作。
    所有方法接受 client 实例作为第一个参数，内部由 tool 函数处理。
    """

    def __init__(self):
        self.auth_service = get_auth_service()
        self.token_service = get_token_service()

    def _get_client(self) -> P115Client | P115OpenClient:
        """获取已登录的客户端实例

        优先使用 Open API（P115OpenClient + access_token），
        未启用或 token 无效时回退 Web API（P115Client + cookies）。

        tool 函数根据传入的 client 类型自动选择 API：
        - P115OpenClient → Open API（proapi.115.com，分页上限 7000+）
        - P115Client → Web API（webapi.115.com，分页上限 1150）
        """
        # 优先尝试 Open API
        access_token = self.token_service.get_access_token()
        if access_token:
            app_id = self.token_service.get_app_id()
            return P115OpenClient(
                access_token=access_token,
                app_id=int(app_id) if app_id else 0,
            )

        # 回退 Web API
        cookies = self.auth_service.get_cookies()
        if not cookies:
            raise NotLoggedInError("未登录，请先扫码登录")
        return P115Client(cookies)

    # ==================== 文件列表 ====================

    def list_files(self, cid: int = 0, limit: int = 100, offset: int = 0,
                   order: str = "file_name", asc: int = 1) -> Dict[str, Any]:
        """列出目录内容

        使用 p115client.tool.fs_files 自动分页拉取。

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
        result = fs_files(client, payload, page_size=limit)
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

        # 判断目录
        if "file_name" in f:
            # Open API 搜索结果：file_category=0 且无 file_size 表示目录
            is_dir = f.get("file_category") == 0 and "file_size" not in f
        elif "fn" in f:
            # Open API 列表：fc == "0" 表示目录
            is_dir = f.get("fc") == "0"
        elif "fc" in f:
            # Web API 搜索结果：fc == 0 表示目录
            is_dir = f.get("fc") == 0
        else:
            # Web API 列表：cid 存在且不为 "0" 表示目录
            cid_val = f.get("cid", "0")
            is_dir = cid_val and cid_val != "0"
            if is_dir:
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
        return client.fs_mkdir(name, pid=pid)

    # ==================== 搜索 ====================

    def search_files(self, keyword: str, cid: int = 0) -> Dict[str, Any]:
        """搜索文件

        固定使用 Web API（P115Client），避免 Open API 搜索结果字段名不同导致解析问题。

        Args:
            keyword: 搜索关键词
            cid: 搜索起点目录 ID，0 表示全盘搜索

        Returns:
            {"items": [...], "count": N, ...}
        """
        # 搜索固定用 Web API，字段名统一
        cookies = self.auth_service.get_cookies()
        if not cookies:
            raise NotLoggedInError("未登录，请先扫码登录")
        client = P115Client(cookies)

        result = client.fs_search({"search_value": keyword, "cid": cid, "limit": 100})
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

    def iter_files(self, cid: int = 0) -> List[Dict[str, Any]]:
        """递归遍历目录树，获取所有文件

        使用 p115client.tool.iter_files。
        注意：大目录可能耗时较长。

        Args:
            cid: 目录 ID，0 表示根目录

        Returns:
            文件信息列表
        """
        client = self._get_client()
        result = []
        for f in iter_files(client, cid):
            result.append(self._parse_file_item(f))
        return result

    def iter_dirs(self, cid: int = 0) -> List[Dict[str, Any]]:
        """递归遍历目录树，获取所有目录

        使用 p115client.tool.iter_dirs。

        Args:
            cid: 目录 ID，0 表示根目录

        Returns:
            目录信息列表
        """
        client = self._get_client()
        result = []
        for d in iter_dirs(client, cid):
            result.append(self._parse_file_item(d))
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
        client.fs_rename((file_id, new_name))


# 全局单例
_file_service: Optional[FileService] = None


def get_file_service() -> FileService:
    """获取文件管理服务实例"""
    global _file_service
    if _file_service is None:
        _file_service = FileService()
    return _file_service
