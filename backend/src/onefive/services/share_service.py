"""
分享链接解析服务 - 解析 115 分享链接，获取文件信息并存储到数据库

职责：
- 解析分享链接，提取 share_code 和 receive_code
- 调用 p115client share_iterdir 获取文件列表
- 将文件信息写入 share_source 和 share_file 表
- 提供文件列表、搜索、删除等操作
"""
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, parse_qs

from ..db.database import get_db
from ..logger import get_logger

logger = get_logger(__name__)


def parse_share_url(url: str) -> Dict[str, str]:
    """从分享链接提取 share_code 和 receive_code

    支持格式：
    - https://115.com/s/xxx?password=yyy
    - https://115cdn.com/s/xxx?password=yyy
    - https://115.com/s/xxx
    """
    # 提取 share_code（/s/ 后面的部分）
    match = re.search(r'/s/(\w+)', url)
    if not match:
        return {}
    share_code = match.group(1)

    # 提取 receive_code（password 参数）
    receive_code = ""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if "password" in params:
        receive_code = params["password"][0]

    return {"share_code": share_code, "receive_code": receive_code}


class ShareService:
    """分享链接解析服务"""

    def __init__(self):
        self.db = get_db()

    def add_share(self, share_url: str, receive_code: str = "", source_type: str = "manual") -> Dict[str, Any]:
        """添加分享链接

        1. 解析 URL 提取 share_code 和 receive_code
        2. 调用 p115client share_iterdir 获取文件列表
        3. 写入 share_source 和 share_file 表
        """
        # 解析 URL
        info = parse_share_url(share_url)
        if not info:
            return {"success": False, "error": "不是有效的 115 分享链接"}

        share_code = info["share_code"]
        if not receive_code:
            receive_code = info.get("receive_code", "")

        # 检查是否已存在
        existing = self.db.fetchone(
            "SELECT id FROM share_source WHERE share_code = ?", (share_code,)
        )
        if existing:
            # 不暴露内部 source_id，避免泄漏内部 ID
            return {"success": False, "error": f"分享 {share_code} 已存在"}

        # 调用 p115client 获取文件列表
        try:
            from p115client.tool import share_iterdir

            # 复用 file_service._get_client()（统一 Open API 优先 + 动态 app）
            from .file_service import get_file_service
            client = get_file_service()._get_client()

            # 获取根目录
            root_files = list(share_iterdir(client, share_code=share_code, receive_code=receive_code))
            if not root_files:
                return {"success": False, "error": "分享链接无文件"}

            # 写入 share_source
            root = root_files[0]
            share_name = root.get("name", "")

            self.db.execute(
                """INSERT INTO share_source (share_code, receive_code, share_name, share_url, source_type, status)
                   VALUES (?, ?, ?, ?, ?, 'parsed')""",
                (share_code, receive_code, share_name, share_url, source_type)
            )
            self.db.commit()

            # 获取 source_id
            source_row = self.db.fetchone("SELECT id FROM share_source WHERE share_code = ?", (share_code,))
            source_id = source_row["id"]

            # 写入根目录文件
            self._insert_files(source_id, "0", root_files, share_code, receive_code, client)

            # 统计文件数和总大小（仅统计文件，不包含目录）
            count_row = self.db.fetchone(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(size), 0) as total FROM share_file WHERE source_id = ? AND is_dir = 0",
                (source_id,)
            )
            file_count = count_row["cnt"]
            total_size = count_row["total"]

            # 更新 share_source 统计
            self.db.execute(
                "UPDATE share_source SET file_count = ?, total_size = ? WHERE id = ?",
                (file_count, total_size, source_id)
            )
            self.db.commit()

            logger.info(f"分享添加成功: {share_code} → source_id={source_id}, {file_count} 个文件")

            return {
                "success": True,
                "source_id": source_id,
                "share_code": share_code,
                "share_name": share_name,
                "file_count": file_count,
                "total_size": total_size,
            }

        except Exception as e:
            logger.error(f"解析分享链接失败: {e}")
            # 清理可能的部分数据：同时清理 share_file 和 share_source，避免孤儿记录
            try:
                row = self.db.fetchone(
                    "SELECT id FROM share_source WHERE share_code = ?", (share_code,)
                )
                if row:
                    source_id = row["id"]
                    self.db.execute("DELETE FROM share_file WHERE source_id = ?", (source_id,))
                    self.db.execute("DELETE FROM share_source WHERE id = ?", (source_id,))
                    self.db.commit()
            except Exception as cleanup_err:
                logger.warning(f"清理分享数据失败: {cleanup_err}")
                self.db.rollback()
            return {"success": False, "error": str(e)}

    def _insert_files(self, source_id: int, parent_id: str, files: list,
                      share_code: str, receive_code: str, client):
        """递归写入目录和文件（当前层级用 executemany 批量插入，减少数据库往返）

        保留递归结构：目录需要在线获取子文件后递归处理。
        每个层级内：先把所有文件收集到 batch 列表，用一次 executemany 插入，
        再遍历目录递归获取子文件。
        """
        # 收集当前层级的所有文件记录，准备批量插入
        batch = []
        # 同时记录目录项，用于后续递归获取子文件
        dirs_to_recurse = []
        for f in files:
            file_id = str(f.get("id"))
            name = f.get("name", "")
            is_dir = 1 if f.get("is_dir") else 0
            size = f.get("size", 0)
            sha1 = f.get("sha1", "")

            batch.append((source_id, share_code, receive_code, file_id,
                          parent_id, name, is_dir, size, sha1))
            if is_dir:
                dirs_to_recurse.append((file_id, name))

        # 当前层级批量插入（INSERT OR IGNORE 保证重复时不报错）
        if batch:
            self.db.executemany(
                """INSERT OR IGNORE INTO share_file
                   (source_id, share_code, receive_code, file_id, parent_id, name, is_dir, size, sha1)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                batch
            )

        # 递归处理子目录：在线获取子文件后递归写入
        for file_id, name in dirs_to_recurse:
            try:
                from p115client.tool import share_iterdir
                children = list(share_iterdir(
                    client, share_code=share_code,
                    receive_code=receive_code, cid=int(file_id)
                ))
                if children:
                    self._insert_files(source_id, file_id, children, share_code, receive_code, client)
            except Exception as e:
                logger.warning(f"获取子目录失败 ({name}): {e}")

        # 不在此处 commit，由顶层 add_share 统一提交，避免每层递归多次 commit 影响性能

    def list_shares(self) -> List[Dict]:
        """列出所有分享来源"""
        rows = self.db.fetchall(
            "SELECT * FROM share_source ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]

    def check_link_valid(self, source_id: int) -> Dict[str, Any]:
        """检测单个分享链接是否有效

        判断逻辑：调用 share/snap 端点单次请求（limit=1），
        通过返回的 state 和 errno 字段判断链接死活。

        相比 share_iterdir 的优势：
        - share_iterdir 会循环分页拉整个分享根目录所有文件，请求量大、易触发风控
        - share/snap 单次调用，limit=1 只拉 1 条，请求量极小

        客户端选择：始终用 P115Client(app='web') 走 webapi.115.com/share/snap 标准端点。
        源码考证（p115client/client.py）：
        - share_snap 方法（行 25263）内部用 get_request，不会带 cookies → 405
        - 所以用 client.request(url, params=payload) 调用同一端点（和 fs_files 一致），
          自动带上 self.cookies 和 self.headers

        判定条件（全部满足才算有效）：
        - resp.state == True（HTTP 请求成功）
        - resp.errno == 0（业务层成功）

        Args:
            source_id: 分享来源 ID

        Returns:
            {"source_id": int, "share_code": str, "valid": bool, "error": str}
        """
        # 查询分享信息
        row = self.db.fetchone(
            "SELECT share_code, receive_code, share_name FROM share_source WHERE id = ?",
            (source_id,)
        )
        if not row:
            return {"source_id": source_id, "valid": False, "error": "分享记录不存在"}

        share_code = row["share_code"]
        receive_code = row["receive_code"]
        share_name = row["share_name"]

        try:
            from .file_service import get_file_service
            from ..exceptions import NotLoggedInError

            file_svc = get_file_service()
            # share_snap 的最小请求 payload：只拉 1 条根目录文件
            # 注意：share_snap 的 count_folders/count_files 参数在源码中未声明，不传
            payload = {
                "share_code": share_code,
                "receive_code": receive_code,
                "cid": 0,                # 根目录
                "offset": 0,
                "limit": 1,              # 只要 1 条就够判断有效性
            }

            # 调用 share_snap：内部强制用 P115Client(app='web') 走标准端点，
            # 外层 _retry_on_busy 处理 115 繁忙错误
            resp = file_svc._retry_on_busy(
                lambda: self._call_share_snap(file_svc, payload)
            )

            # 解析返回结果，按 state/errno 判定有效性
            valid, error_msg = self._parse_share_snap_response(resp)

        except NotLoggedInError as e:
            valid = False
            error_msg = str(e)
        except Exception as e:
            valid = False
            error_msg = str(e)[:200]  # 截断过长的错误信息

        # 更新数据库
        self.db.execute(
            """UPDATE share_source
               SET link_valid = ?, error_msg = ?,
                   updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (1 if valid else 0, error_msg, source_id)
        )
        self.db.commit()

        logger.info(f"检测分享链接: {share_name} ({share_code}) → {'有效' if valid else '无效: ' + error_msg}")

        return {
            "source_id": source_id,
            "share_code": share_code,
            "share_name": share_name,
            "valid": valid,
            "error": error_msg,
        }

    @staticmethod
    def _call_share_snap(file_svc, payload: Dict[str, Any]) -> Dict[str, Any]:
        """调用 share/snap 端点检测分享有效性，强制使用 Web API（app='web'）并带 cookies

        源码考证（p115client/client.py）：
        - share_snap 方法（行 25324-25325）内部直接用 get_request，不会带上 self.cookies
        - fs_files 方法（行 11508）用 self.request，会自动带上 self.cookies（行 730-732）
        - 所以不能用 client.share_snap(payload)，否则请求不带 cookies 会 405
        - 解决方案：用 client.request(url, params=payload) 调用同一端点，确保带上 cookies

        端点：GET https://webapi.115.com/share/snap
        参数：share_code, receive_code, cid=0, offset=0, limit=1

        Args:
            file_svc: FileService 实例（用于获取 cookies）
            payload: share_snap 请求参数

        Returns:
            share_snap 返回的 dict
        """
        from p115client import P115Client
        from ..exceptions import NotLoggedInError

        cookies = file_svc.auth_service.get_cookies()
        if not cookies:
            raise NotLoggedInError("未登录，请先扫码登录")

        # 强制 app='web'，走 webapi.115.com/share/snap 标准端点
        web_client = P115Client(cookies, app='web')
        # 关键：用 client.request 而非 client.share_snap
        # client.request 会自动带上 self.cookies 和 self.headers（和 fs_files 一致）
        # client.share_snap 内部用 get_request，不会带 cookies，导致 405
        api = "https://webapi.115.com/share/snap"
        return web_client.request(url=api, params=payload)

    @staticmethod
    def _parse_share_snap_response(resp: Dict[str, Any]) -> tuple:
        """解析 share_snap 返回结果，判定分享是否有效

        share_snap 返回结构（源码考证）：
        {
            "state": True | False,    # 顶层状态：True=请求成功
            "errno": int,             # 错误码：0=成功，其它=失败
            "error": str,             # 错误消息（失败时）
            "data": {
                "count": int,         # 目录内文件+子目录总数
                "list": [...]         # 当前页文件/目录列表
            }
        }

        注意：share_snap 返回中没有 shareinfo/sharestate 字段
        （shareinfo 是另一个独立方法 share_info 的端点 /share/shareinfo）

        判定逻辑：
        1. resp.state == True（HTTP 请求成功）
        2. resp.errno == 0（业务层成功）

        常见错误码（来自 p115client check_response）：
        - 10004: 错误的链接
        - 50003: 提取码不存在
        - 99: 请重新登录
        - 911: 请验证账号
        - 1001: 参数错误

        Args:
            resp: share_snap 返回的 dict

        Returns:
            (is_valid: bool, error_msg: str)
        """
        # 1. state 字段判定（HTTP 层）
        if not resp.get("state", False):
            return False, resp.get("error", "请求失败")

        # 2. errno 字段判定（业务层）
        errno = resp.get("errno", -1)
        if errno != 0:
            return False, f"errno={errno}: {resp.get('error', '分享失效')}"

        # state==True 且 errno==0 即视为有效
        # （share_snap 能正常返回数据说明链接可访问、提取码正确）
        return True, ""

    def get_all_shares_for_check(self) -> List[Dict]:
        """获取所有分享记录（用于批量检测）"""
        rows = self.db.fetchall(
            "SELECT id, share_code, share_name FROM share_source ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]

    def delete_share(self, source_id: int) -> bool:
        """删除分享来源及其所有文件"""
        self.db.execute("DELETE FROM share_file WHERE source_id = ?", (source_id,))
        self.db.execute("DELETE FROM share_source WHERE id = ?", (source_id,))
        self.db.commit()
        return True

    def delete_shares_batch(self, source_ids: List[int]) -> Dict:
        """批量删除分享来源及其所有文件

        每条删除独立事务：成功才 commit，失败立即 rollback，
        避免部分删除被统一 commit 留下不一致状态。

        Returns:
            {"total": int, "success": int, "failed": int}
        """
        total = len(source_ids)
        success = 0
        for sid in source_ids:
            try:
                self.db.execute("DELETE FROM share_file WHERE source_id = ?", (sid,))
                self.db.execute("DELETE FROM share_source WHERE id = ?", (sid,))
                self.db.commit()
                success += 1
            except Exception:
                # 异常时回滚当前 sid 的删除，不影响其它 sid
                self.db.rollback()
        return {"total": total, "success": success, "failed": total - success}

    def update_share_source(self, source_id: int, share_name: str = None,
                            share_code: str = None, receive_code: str = None) -> bool:
        """更新分享来源信息，并同步 share_file 表中的冗余字段

        Args:
            source_id: 分享来源 ID
            share_name: 分享名称（None 表示不修改）
            share_code: 分享码（None 表示不修改）
            receive_code: 提取码（None 表示不修改）
        """
        # 构建 share_source 的 SET 子句
        sets = []
        params = []
        if share_name is not None:
            sets.append("share_name = ?")
            params.append(share_name)
        if share_code is not None:
            sets.append("share_code = ?")
            params.append(share_code)
        if receive_code is not None:
            sets.append("receive_code = ?")
            params.append(receive_code)
        if not sets:
            return False
        sets.append("updated_at = datetime('now', 'localtime')")
        params.append(source_id)
        self.db.execute(
            f"UPDATE share_source SET {', '.join(sets)} WHERE id = ?",
            params
        )
        # 同步 share_file 表中的 share_code / receive_code 冗余字段
        file_sets = []
        file_params = []
        if share_code is not None:
            file_sets.append("share_code = ?")
            file_params.append(share_code)
        if receive_code is not None:
            file_sets.append("receive_code = ?")
            file_params.append(receive_code)
        if file_sets:
            file_sets.append("updated_at = datetime('now', 'localtime')")
            file_params.append(source_id)
            self.db.execute(
                f"UPDATE share_file SET {', '.join(file_sets)} WHERE source_id = ?",
                file_params
            )
        self.db.commit()
        return True

    def update_file_category(self, source_id: int, file_id: str, category: str) -> bool:
        """更新文件/目录的分类路径

        对于文件：直接更新该文件的分类
        对于目录：递归更新所有子文件的分类（目录本身不存 category）
        """
        # 查询目标是否为目录
        row = self.db.fetchone(
            "SELECT is_dir FROM share_file WHERE source_id = ? AND file_id = ?",
            (source_id, file_id)
        )
        if not row:
            return False

        if row["is_dir"]:
            # 目录：递归更新所有子文件的分类
            self.db.execute(
                """WITH RECURSIVE children(file_id) AS (
                    SELECT file_id FROM share_file
                    WHERE source_id = ? AND parent_id = ?
                    UNION ALL
                    SELECT f.file_id FROM share_file f
                    JOIN children c ON f.parent_id = c.file_id
                    WHERE f.source_id = ?
                )
                UPDATE share_file SET
                   category = ?, updated_at = datetime('now', 'localtime')
                   WHERE source_id = ? AND file_id IN (SELECT file_id FROM children)
                     AND is_dir = 0""",
                (source_id, file_id, source_id, category, source_id)
            )
        else:
            # 文件：直接更新
            self.db.execute(
                """UPDATE share_file SET
                   category = ?, updated_at = datetime('now', 'localtime')
                   WHERE source_id = ? AND file_id = ? AND is_dir = 0""",
                (category, source_id, file_id)
            )
        self.db.commit()
        return True

    def reset_file_organize(self, source_id: int, file_id: str) -> bool:
        """重置单个文件的整理信息（仅针对文件，不处理目录）"""
        self.db.execute(
            """UPDATE share_file SET
               media_type = '', title = '', year = '', tmdb_id = 0, category = '',
               organized_dir = '', organized_name = '', organized = 0,
               updated_at = datetime('now', 'localtime')
               WHERE source_id = ? AND file_id = ? AND is_dir = 0""",
            (source_id, file_id)
        )
        self.db.commit()
        return True

    def list_files(self, source_id: int, parent_id: str = "0",
                   limit: int = 100, offset: int = 0) -> Dict:
        """列出分享目录内容"""
        count_row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM share_file WHERE source_id = ? AND parent_id = ?",
            (source_id, parent_id)
        )
        total = count_row["cnt"]

        rows = self.db.fetchall(
            """SELECT * FROM share_file
               WHERE source_id = ? AND parent_id = ?
               ORDER BY is_dir DESC, name ASC
               LIMIT ? OFFSET ?""",
            (source_id, parent_id, limit, offset)
        )

        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_organized_files(self, source_id: int) -> Dict:
        """获取整理后的分类目录（仅文件，不包含目录）"""
        # 已整理的文件，按 category 分组
        rows = self.db.fetchall(
            """SELECT * FROM share_file
               WHERE source_id = ? AND organized = 1 AND category != '' AND is_dir = 0
               ORDER BY category, name""",
            (source_id,)
        )

        # 按 category 分组
        categories = {}
        for r in rows:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = {
                    "path": cat,
                    "name": cat.split("/")[-1] if "/" in cat else cat,
                    "files": [],
                }
            categories[cat]["files"].append(dict(r))

        # 未整理的文件（排除目录）
        unorganized_rows = self.db.fetchall(
            """SELECT * FROM share_file
               WHERE source_id = ? AND (organized = 0 OR category = '') AND is_dir = 0
               ORDER BY name""",
            (source_id,)
        )

        return {
            "categories": list(categories.values()),
            "unorganized": [dict(r) for r in unorganized_rows],
        }

    def get_all_root_files(self, organized_only: bool = False, unorganized_only: bool = False) -> List[Dict]:
        """获取所有分享来源的根目录文件（目录排前面）

        对于目录，递归查找后代文件中第一个已整理的，提取其 title/year/tmdb_id。
        这样即使目录结构含季子目录（如 剧名/Season 01/第一集.mp4）也能正确显示整理名称。
        """
        condition = "f.parent_id = '0'"
        if organized_only:
            condition += " AND f.organized = 1"
        elif unorganized_only:
            condition += " AND f.organized = 0"

        rows = self.db.fetchall(
            f"""SELECT f.*, s.share_name,
                (SELECT COUNT(*) FROM share_file WHERE source_id = s.id AND is_dir = 0) as file_count
                FROM share_file f
                JOIN share_source s ON f.source_id = s.id
                WHERE {condition}
                ORDER BY f.is_dir DESC, f.name ASC"""
        )

        result = []
        for r in rows:
            d = dict(r)
            # 目录：递归查找后代中第一个已整理文件，补充整理信息
            if d.get("is_dir") and d.get("organized") and not d.get("title"):
                child = self._get_first_organized_descendant(d["source_id"], d["file_id"])
                if child:
                    d["title"] = child.get("title", "") or ""
                    d["year"] = child.get("year", "") or ""
                    d["tmdb_id"] = child.get("tmdb_id", 0) or 0
            result.append(d)
        return result

    def _get_first_organized_descendant(self, source_id: int, dir_file_id: str) -> Optional[Dict]:
        """递归查找目录下第一个已整理且有 title 的后代文件（不限层级，单条 SQL）

        用于目录整理名称显示：当目录含季子目录时，直接子项是目录无 title，
        需要深入到叶子文件层才能取到整理信息。

        优化：用 WITH RECURSIVE 一次查出所有后代，避免深层目录触发 N+1 查询。
        """
        row = self.db.fetchone(
            """WITH RECURSIVE descendants(file_id, depth) AS (
                   SELECT file_id, 0 FROM share_file
                   WHERE source_id = ? AND parent_id = ?
                   UNION ALL
                   SELECT f.file_id, d.depth + 1 FROM share_file f
                   JOIN descendants d ON f.parent_id = d.file_id
                   WHERE f.source_id = ?
               )
               SELECT sf.file_id, sf.title, sf.year, sf.tmdb_id, sf.media_type,
                      sf.category, sf.organized_dir, sf.organized_name
               FROM share_file sf
               JOIN descendants d ON sf.file_id = d.file_id
               WHERE sf.organized = 1 AND sf.title != '' AND sf.is_dir = 0
               ORDER BY d.depth, sf.name
               LIMIT 1""",
            (source_id, dir_file_id, source_id)
        )
        return dict(row) if row else None

    def get_all_organized_files(self) -> Dict:
        """获取所有分享来源的已整理文件，用于构建统一的虚拟目录树"""
        # 已整理文件，附带来源信息
        organized_rows = self.db.fetchall(
            """SELECT f.*, s.share_code, s.share_name
               FROM share_file f
               JOIN share_source s ON f.source_id = s.id
               WHERE f.organized = 1 AND f.organized_dir != ''
               ORDER BY f.organized_dir, f.name"""
        )

        # 未整理文件
        unorganized_rows = self.db.fetchall(
            """SELECT f.*, s.share_code, s.share_name
               FROM share_file f
               JOIN share_source s ON f.source_id = s.id
               WHERE f.organized = 0 OR f.organized_dir = ''
               ORDER BY f.name"""
        )

        return {
            "organized": [dict(r) for r in organized_rows],
            "unorganized": [dict(r) for r in unorganized_rows],
        }

    def search_files(self, keyword: str) -> List[Dict]:
        """搜索分享文件

        匹配范围：
        - 模糊匹配：原始文件名 name、识别后标题 title、整理后目录 organized_dir、整理后文件名 organized_name
        - 精确匹配：TMDB ID（keyword 为数字时）
        """
        # 模糊匹配的名称字段
        like_fields = ["f.name", "f.title", "f.organized_name", "f.organized_dir"]
        like_pattern = f"%{keyword}%"
        where_clauses = [f"{field} LIKE ?" for field in like_fields]
        params: list = [like_pattern] * len(like_fields)

        # keyword 是数字时，额外精确匹配 tmdb_id
        try:
            tmdb_id_val = int(keyword)
            where_clauses.append("f.tmdb_id = ?")
            params.append(tmdb_id_val)
        except (ValueError, TypeError):
            pass

        sql = f"""SELECT f.*, s.share_code, s.share_name
                  FROM share_file f
                  JOIN share_source s ON f.source_id = s.id
                  WHERE {' OR '.join(where_clauses)}
                  ORDER BY f.is_dir DESC, f.updated_at DESC
                  LIMIT 100"""
        rows = self.db.fetchall(sql, tuple(params))
        return [dict(r) for r in rows]

    def get_share_info(self, source_id: int) -> Optional[Dict]:
        """获取分享来源详情"""
        row = self.db.fetchone("SELECT * FROM share_source WHERE id = ?", (source_id,))
        return dict(row) if row else None

    def get_file(self, source_id: int, file_id: str) -> Optional[Dict]:
        """获取文件详情"""
        row = self.db.fetchone(
            "SELECT * FROM share_file WHERE source_id = ? AND file_id = ?",
            (source_id, file_id)
        )
        return dict(row) if row else None

    def get_file_with_media_info(self, source_id: int, file_id: str) -> Optional[Dict]:
        """获取文件详情，目录自动从子文件补充媒体信息

        整理时媒体信息（title/year/tmdb_id/media_type/category）存储在文件记录上，
        不是目录记录上。对于目录，需要递归查找子文件来补充这些字段。
        """
        file_info = self.get_file(source_id, file_id)
        if not file_info:
            return None

        # 目录：从子文件补充媒体信息（递归查找，兼容 Season 子目录结构）
        if file_info.get("is_dir"):
            child = self.db.fetchone(
                """WITH RECURSIVE children(file_id) AS (
                    SELECT file_id FROM share_file
                    WHERE source_id = ? AND parent_id = ?
                    UNION ALL
                    SELECT f.file_id FROM share_file f
                    JOIN children c ON f.parent_id = c.file_id
                    WHERE f.source_id = ?
                )
                SELECT media_type, title, year, tmdb_id, category
                FROM share_file
                WHERE source_id = ? AND file_id IN (SELECT file_id FROM children)
                  AND organized = 1 AND title != '' AND is_dir = 0
                LIMIT 1""",
                (source_id, file_id, source_id, source_id)
            )
            if child:
                file_info["media_type"] = child["media_type"] or ""
                file_info["title"] = child["title"] or ""
                file_info["year"] = child["year"] or ""
                file_info["tmdb_id"] = child["tmdb_id"] or 0
                file_info["category"] = child["category"] or ""

        return file_info

    def update_file_organize(self, source_id: int, file_id: str, data: Dict, commit: bool = True):
        """更新文件整理信息

        Args:
            commit: 是否立即提交事务。批量场景（如批量整理同一目录的多集）
                传 False，由调用方在循环结束后统一 commit，避免每条记录都
                触发一次 fsync 影响性能（40 集剧从 40 次 fsync 降到 1 次）。
        """
        self.db.execute(
            """UPDATE share_file SET
               media_type = ?, title = ?, year = ?, tmdb_id = ?, category = ?,
               organized_dir = ?, organized_name = ?,
               organized = 1, updated_at = datetime('now', 'localtime')
               WHERE source_id = ? AND file_id = ? AND is_dir = 0""",
            (
                data.get("media_type", ""),
                data.get("title", ""),
                data.get("year", ""),
                data.get("tmdb_id", 0),
                data.get("category", ""),
                data.get("organized_dir", ""),
                data.get("organized_name", ""),
                source_id,
                file_id,
            )
        )
        if commit:
            self.db.commit()


# 单例
_share_service: Optional[ShareService] = None


def get_share_service() -> ShareService:
    """获取分享服务实例"""
    global _share_service
    if _share_service is None:
        _share_service = ShareService()
    return _share_service
