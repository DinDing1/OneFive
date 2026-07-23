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
        3. 写入 share_source 和 share_file 表（单事务：成功才 commit，失败 rollback 全清）
        """
        info = parse_share_url(share_url)
        if not info:
            return {"success": False, "error": "不是有效的 115 分享链接"}

        share_code = info["share_code"]
        if not receive_code:
            receive_code = info.get("receive_code", "")

        existing = self.db.fetchone(
            "SELECT id FROM share_source WHERE share_code = ?", (share_code,)
        )
        if existing:
            return {"success": False, "error": f"分享 {share_code} 已存在"}

        try:
            from p115client.tool import share_iterdir
            from .file_service import get_file_service
            client = get_file_service()._get_client()

            root_files = list(share_iterdir(client, share_code=share_code, receive_code=receive_code))
            if not root_files:
                return {"success": False, "error": "分享链接无文件"}

            root = root_files[0]
            share_name = root.get("name", "")

            # 整棵树同一事务：不在中途 commit，避免半截孤儿数据
            cursor = self.db.execute(
                """INSERT INTO share_source (share_code, receive_code, share_name, share_url, source_type, status)
                   VALUES (?, ?, ?, ?, ?, 'parsed')""",
                (share_code, receive_code, share_name, share_url, source_type)
            )
            source_id = int(cursor.lastrowid or 0)
            if not source_id:
                row = self.db.fetchone(
                    "SELECT id FROM share_source WHERE share_code = ?", (share_code,)
                )
                source_id = int(row["id"]) if row else 0
            if not source_id:
                raise RuntimeError("写入 share_source 后无法获取 source_id")

            # 子目录拉取失败会抛错，触发整体回滚
            self._insert_files(source_id, "0", root_files, share_code, receive_code, client)

            count_row = self.db.fetchone(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(size), 0) as total FROM share_file WHERE source_id = ? AND is_dir = 0",
                (source_id,)
            )
            file_count = count_row["cnt"] if count_row else 0
            total_size = count_row["total"] if count_row else 0

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
            try:
                self.db.rollback()
            except Exception:
                pass
            # 兜底：若曾被部分提交，按 share_code 清掉孤儿
            try:
                row = self.db.fetchone(
                    "SELECT id FROM share_source WHERE share_code = ?", (share_code,)
                )
                if row:
                    sid = row["id"]
                    self.db.execute("DELETE FROM share_file WHERE source_id = ?", (sid,))
                    self.db.execute("DELETE FROM share_source WHERE id = ?", (sid,))
                    self.db.commit()
            except Exception as cleanup_err:
                logger.warning(f"清理分享数据失败: {cleanup_err}")
                try:
                    self.db.rollback()
                except Exception:
                    pass
            return {"success": False, "error": str(e)}

    def _insert_files(self, source_id: int, parent_id: str, files: list,
                      share_code: str, receive_code: str, client):
        """递归写入目录和文件（当前层级 executemany 批量插入）。

        不在此 commit：由 add_share 统一提交。
        任一子目录在线拉取失败会抛出异常，保证不会静默写入残缺树。
        """
        batch = []
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

        if batch:
            self.db.executemany(
                """INSERT OR IGNORE INTO share_file
                   (source_id, share_code, receive_code, file_id, parent_id, name, is_dir, size, sha1)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                batch
            )

        errors: List[str] = []
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
                msg = f"{name}: {e}"
                errors.append(msg)
                logger.warning(f"获取子目录失败 ({name}): {e}")

        if errors:
            preview = "; ".join(errors[:3])
            more = f" 等{len(errors)}处" if len(errors) > 3 else ""
            raise RuntimeError(f"获取子目录失败: {preview}{more}")

    def list_shares(self, limit: Optional[int] = None, offset: int = 0) -> Dict:
        """列出分享源（强制分页，默认 50/页）。

        正式环境分享数可达数千，禁止 limit<=0 全量返回。
        """
        count_row = self.db.fetchone("SELECT COUNT(*) AS cnt FROM share_source")
        total = int(count_row["cnt"]) if count_row else 0

        lim = 50 if (limit is None or int(limit) <= 0) else min(int(limit), 500)
        off = max(0, int(offset or 0))
        rows = self.db.fetchall(
            """SELECT id, share_code, receive_code, share_name, share_url,
                      source_type, file_count, total_size, status, link_valid,
                      error_msg, created_at, updated_at
               FROM share_source
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (lim, off),
        )
        return {
            "shares": [dict(r) for r in rows],
            "total": total,
            "limit": lim,
            "offset": off,
        }

    def has_any_share(self) -> bool:
        """是否存在至少一个分享源（空态判断，O(1)）"""
        row = self.db.fetchone("SELECT 1 AS ok FROM share_source LIMIT 1")
        return bool(row)


    def check_link_valid(self, source_id: int) -> Dict[str, Any]:
        """检测分享链接是否有效（抗风控）。

        使用 p115client 官方接口：
        1) 优先 share_snap_app（登录态 proapi，适合批量）
        2) 回退 share_snap（webapi）
        仅 115 明确业务结果才写 link_valid；405/频控/网络问题标记 skipped。
        """
        row = self.db.fetchone(
            "SELECT share_code, receive_code, share_name FROM share_source WHERE id = ?",
            (source_id,),
        )
        if not row:
            return {"source_id": source_id, "valid": False, "error": "分享记录不存在"}

        share_code = row["share_code"] or ""
        receive_code = row["receive_code"] or ""
        share_name = row["share_name"] or ""

        try:
            from ..exceptions import NotLoggedInError

            payload = {
                "share_code": share_code,
                "receive_code": receive_code,
                "cid": 0,
                "offset": 0,
                "limit": 1,
            }
            resp = self._call_share_snap(payload)
            valid, error_msg = self._parse_share_snap_response(resp)
        except NotLoggedInError as e:
            logger.warning(f"检测分享链接跳过（未登录）: {share_name} ({share_code})")
            return {
                "source_id": source_id,
                "share_code": share_code,
                "share_name": share_name,
                "valid": False,
                "error": str(e),
                "skipped": True,
            }
        except Exception as e:
            error_msg = str(e)[:200]
            if self._is_transient_share_error(e):
                logger.warning(
                    f"检测分享链接跳过（频控/网络）: {share_name} ({share_code}): {error_msg}"
                )
            else:
                logger.warning(
                    f"detect share link error (not updating link_valid): {share_name} ({share_code}): {error_msg}"
                )
            return {
                "source_id": source_id,
                "share_code": share_code,
                "share_name": share_name,
                "valid": False,
                "error": error_msg,
                "skipped": True,
            }

        self.db.execute(
            """UPDATE share_source
               SET link_valid = ?, error_msg = ?,
                   updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (1 if valid else 0, error_msg, source_id),
        )
        self.db.commit()
        logger.info(
            f"检测分享链接: {share_name} ({share_code}) → "
            f"{'有效' if valid else '无效: ' + error_msg}"
        )
        return {
            "source_id": source_id,
            "share_code": share_code,
            "share_name": share_name,
            "valid": valid,
            "error": error_msg,
        }

    @staticmethod
    def _is_transient_share_error(exc: BaseException) -> bool:
        s = str(exc).lower()
        keys = (
            "405", "429", "method not allowed", "too many", "rate", "busy",
            "timeout", "timed out", "频繁", "封禁", "风控", "try again",
            "temporarily", "connection", "connect",
        )
        return any(k in s for k in keys)

    def _call_share_snap(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """抗风控调用 share snap。

        p115client 说明：
        - share_snap：可不登录但频繁封 IP
        - share_snap_app：需登录，更适合账号态批量探测
        """
        import time
        from p115client.exception import P115BusyOSError
        from .p115_client_factory import get_p115_client_factory

        factory = get_p115_client_factory()
        client = factory.create_web_client()
        app = factory.get_client_app() or "web"
        snap_app = app if app in ("android", "ios") else "android"
        params = {
            "share_code": str(payload.get("share_code") or ""),
            "receive_code": str(payload.get("receive_code") or ""),
            "cid": payload.get("cid", 0),
            "offset": int(payload.get("offset") or 0),
            "limit": int(payload.get("limit") or 1),
        }

        last_err: Exception | None = None
        attempts = [("app", snap_app), ("web", "web"), ("app", snap_app)]
        for idx, (mode, mode_app) in enumerate(attempts):
            try:
                if mode == "app":
                    resp = client.share_snap_app(params, app=mode_app)
                else:
                    resp = client.share_snap(params)
                if not isinstance(resp, dict):
                    raise RuntimeError(f"share snap unexpected type: {type(resp)}")
                return resp
            except P115BusyOSError as e:
                last_err = e
                wait = 2 * (idx + 1)
                logger.warning(f"share snap busy, retry in {wait}s ({mode}/{mode_app})")
                time.sleep(wait)
            except Exception as e:
                last_err = e
                if idx >= len(attempts) - 1:
                    raise
                wait = 2 * (idx + 1) if self._is_transient_share_error(e) else 0.8
                logger.warning(f"share snap {mode}/{mode_app} failed: {e}; next in {wait}s")
                time.sleep(wait)

        if last_err:
            raise last_err
        raise RuntimeError("share snap failed")

    @staticmethod
    def _parse_share_snap_response(resp: Dict[str, Any]) -> tuple:
        if not isinstance(resp, dict):
            return False, "响应格式错误"

        def _msg() -> str:
            for key in ("error", "message", "msg", "error_msg"):
                val = resp.get(key)
                if val:
                    return str(val)
            return "分享无效或已失效"

        state = resp.get("state", False)
        if state in (1, "1", "true", "True"):
            state = True
        if not state:
            errno = resp.get("errno", resp.get("errNo", resp.get("code")))
            msg = _msg()
            if errno is not None and str(errno) not in ("", "0"):
                return False, f"[{errno}] {msg}"
            return False, msg

        errno = resp.get("errno", resp.get("errNo", resp.get("code", 0)))
        try:
            errno_i = int(errno)
        except (TypeError, ValueError):
            errno_i = 0 if errno in (None, "") else -1
        if errno_i != 0:
            return False, f"[{errno_i}] {_msg()}"
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
                    JOIN children c ON f.parent_id = c.file_id AND f.source_id = ?
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
        """列出分享目录内容（分页，JOIN 附带 share_name / link_valid）"""
        count_row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM share_file WHERE source_id = ? AND parent_id = ?",
            (source_id, parent_id)
        )
        total = int(count_row["cnt"]) if count_row else 0

        rows = self.db.fetchall(
            """SELECT f.id, f.source_id, f.share_code, f.receive_code, f.file_id, f.parent_id,
                      f.name, f.is_dir, f.size, f.sha1, f.media_type, f.title, f.year, f.tmdb_id,
                      f.category, f.organized_dir, f.organized_name, f.organized,
                      f.created_at, f.updated_at,
                      s.share_name, s.file_count, s.link_valid
               FROM share_file f
               JOIN share_source s ON f.source_id = s.id
               WHERE f.source_id = ? AND f.parent_id = ?
               ORDER BY f.is_dir DESC, f.name ASC
               LIMIT ? OFFSET ?""",
            (source_id, parent_id, int(limit), max(0, int(offset)))
        )

        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_root_file_counts(self) -> Dict[str, int]:
        """根目录各筛选维度计数（单次聚合，O(根目录行数)）。

        正式环境根目录可达数万，前端筛选角标不能再依赖全量列表本地 count。
        """
        row = self.db.fetchone(
            """SELECT
                   COUNT(*) AS all_count,
                   COALESCE(SUM(CASE WHEN f.organized = 1 THEN 1 ELSE 0 END), 0) AS organized_count,
                   COALESCE(SUM(CASE WHEN f.organized = 0 THEN 1 ELSE 0 END), 0) AS unorganized_count,
                   COALESCE(SUM(CASE WHEN s.link_valid = 1 THEN 1 ELSE 0 END), 0) AS valid_count,
                   COALESCE(SUM(CASE WHEN s.link_valid = 0 THEN 1 ELSE 0 END), 0) AS invalid_count
               FROM share_file f
               JOIN share_source s ON f.source_id = s.id
               WHERE f.parent_id = '0'"""
        )
        if not row:
            return {
                "all_count": 0,
                "organized_count": 0,
                "unorganized_count": 0,
                "valid_count": 0,
                "invalid_count": 0,
            }
        return {
            "all_count": int(row["all_count"] or 0),
            "organized_count": int(row["organized_count"] or 0),
            "unorganized_count": int(row["unorganized_count"] or 0),
            "valid_count": int(row["valid_count"] or 0),
            "invalid_count": int(row["invalid_count"] or 0),
        }

    def get_all_root_files(
        self,
        filter_type: str = "all",
        limit: int = 50,
        offset: int = 0,
        include_counts: bool = True,
    ) -> Dict:
        """分页获取所有分享源的根目录文件（目录在前）。

        Args:
            filter_type: all | organized | unorganized | valid | invalid
            limit: 每页条数（强制分页，最大 200）
            offset: 偏移
            include_counts: 是否附带各筛选维度总数（角标用）

        Returns:
            { files, total, limit, offset, filter, counts? }
        """
        ft = (filter_type or "all").lower()

        condition = "f.parent_id = '0'"
        if ft == "organized":
            condition += " AND f.organized = 1"
        elif ft == "unorganized":
            condition += " AND f.organized = 0"
        elif ft == "valid":
            condition += " AND s.link_valid = 1"
        elif ft == "invalid":
            condition += " AND s.link_valid = 0"

        count_row = self.db.fetchone(
            f"""SELECT COUNT(*) AS cnt
                FROM share_file f
                JOIN share_source s ON f.source_id = s.id
                WHERE {condition}"""
        )
        total = int(count_row["cnt"]) if count_row else 0

        lim = 50 if (limit is None or int(limit) <= 0) else min(int(limit), 200)
        off = max(0, int(offset or 0))

        sql = f"""SELECT f.id, f.source_id, f.share_code, f.receive_code, f.file_id,
                         f.parent_id, f.name, f.is_dir, f.size, f.sha1,
                         f.media_type, f.title, f.year, f.tmdb_id, f.category,
                         f.organized_dir, f.organized_name, f.organized,
                         f.created_at, f.updated_at,
                         s.share_name, s.file_count, s.link_valid
                  FROM share_file f
                  JOIN share_source s ON f.source_id = s.id
                  WHERE {condition}
                  ORDER BY f.is_dir DESC, f.name ASC
                  LIMIT ? OFFSET ?"""
        rows = self.db.fetchall(sql, (lim, off))
        result = [dict(r) for r in rows]

        need_ids = [
            (d["source_id"], d["file_id"])
            for d in result
            if d.get("is_dir") and d.get("organized") and not d.get("title")
        ]
        if need_ids:
            media_map = self._batch_first_organized_descendants(need_ids)
            for d in result:
                if not (d.get("is_dir") and d.get("organized") and not d.get("title")):
                    continue
                child = media_map.get((d["source_id"], d["file_id"]))
                if child:
                    d["title"] = child.get("title", "") or ""
                    d["year"] = child.get("year", "") or ""
                    d["tmdb_id"] = child.get("tmdb_id", 0) or 0
                    if not d.get("media_type"):
                        d["media_type"] = child.get("media_type", "") or ""
                    if not d.get("category"):
                        d["category"] = child.get("category", "") or ""

        out: Dict = {
            "files": result,
            "total": total,
            "limit": lim,
            "offset": off,
            "filter": ft,
        }
        if include_counts:
            out["counts"] = self.get_root_file_counts()
        return out

    def _batch_first_organized_descendants(
        self, roots: List[tuple]
    ) -> Dict[tuple, Dict]:
        """一次递归 CTE 批量查找多个根目录下第一个已整理文件的媒体信息。"""
        if not roots:
            return {}

        values_sql = " UNION ALL ".join(
            "SELECT %d AS source_id, '%s' AS root_id"
            % (int(sid), str(fid).replace("'", "''"))
            for sid, fid in roots
        )

        rows = self.db.fetchall(
            f"""WITH RECURSIVE
                roots(source_id, root_id) AS (
                    {values_sql}
                ),
                tree AS (
                    SELECT r.source_id, r.root_id, sf.file_id, sf.parent_id,
                           sf.is_dir, sf.organized, sf.title, sf.year, sf.tmdb_id,
                           sf.media_type, sf.category, sf.organized_name, sf.name,
                           0 AS depth
                    FROM roots r
                    JOIN share_file sf
                      ON sf.source_id = r.source_id AND sf.parent_id = r.root_id
                    UNION ALL
                    SELECT t.source_id, t.root_id, sf.file_id, sf.parent_id,
                           sf.is_dir, sf.organized, sf.title, sf.year, sf.tmdb_id,
                           sf.media_type, sf.category, sf.organized_name, sf.name,
                           t.depth + 1
                    FROM share_file sf
                    JOIN tree t
                      ON sf.source_id = t.source_id AND sf.parent_id = t.file_id
                    WHERE t.depth < 32
                ),
                ranked AS (
                    SELECT source_id, root_id, title, year, tmdb_id, media_type,
                           category, organized_name, name, depth,
                           ROW_NUMBER() OVER (
                               PARTITION BY source_id, root_id
                               ORDER BY depth, name
                           ) AS rn
                    FROM tree
                    WHERE organized = 1 AND is_dir = 0 AND title != ''
                )
                SELECT source_id, root_id, title, year, tmdb_id, media_type,
                       category, organized_name, name
                FROM ranked
                WHERE rn = 1"""
        )

        out: Dict[tuple, Dict] = {}
        for r in rows:
            out[(r["source_id"], r["root_id"])] = dict(r)
        return out

    @staticmethod
    def _organized_full_dir_sql(alias: str = "f") -> str:
        """SQL expression: category/organized_dir virtual path."""
        return (
            f"CASE "
            f"WHEN {alias}.category != '' AND {alias}.organized_dir != '' "
            f"THEN {alias}.category || '/' || {alias}.organized_dir "
            f"WHEN {alias}.category != '' THEN {alias}.category "
            f"ELSE {alias}.organized_dir END"
        )

    def list_organized_entries(
        self,
        path: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> Dict:
        """服务端浏览整理视图虚拟目录（不加载全量已整理文件）。

        虚拟路径 = category + '/' + organized_dir（与前端 buildOrganizedEntries 一致）。
        返回当前层：子目录聚合 + 当前层文件，目录在前、文件在后，统一 limit/offset 分页。

        Returns:
            {
              path, entries: [{name, path, is_dir, file_count?, total_size?, file?}],
              total, dir_count, file_count, limit, offset
            }
        """
        path = (path or "").strip().strip("/")
        limit = 50 if (limit is None or int(limit) <= 0) else min(int(limit), 200)
        offset = max(0, int(offset or 0))
        fd = self._organized_full_dir_sql("f")

        # ---- child directories (GROUP BY next path segment) ----
        if not path:
            dir_rows = self.db.fetchall(
                f"""
                SELECT seg AS name,
                       COUNT(*) AS file_count,
                       COALESCE(SUM(sz), 0) AS total_size
                FROM (
                    SELECT
                        CASE
                            WHEN instr(full_dir, '/') > 0
                                THEN substr(full_dir, 1, instr(full_dir, '/') - 1)
                            ELSE full_dir
                        END AS seg,
                        size AS sz
                    FROM (
                        SELECT {fd} AS full_dir, f.size
                        FROM share_file f
                        WHERE f.organized = 1 AND f.is_dir = 0
                          AND f.organized_dir != ''
                    )
                )
                WHERE seg != ''
                GROUP BY seg
                ORDER BY seg COLLATE NOCASE
                """
            )
        else:
            # full_dir LIKE 'path/%' ; remaining after 'path/'
            like_pat = path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
            prefix_len = len(path) + 2  # 1-based substr start after "path/"
            dir_rows = self.db.fetchall(
                f"""
                SELECT name,
                       COUNT(*) AS file_count,
                       COALESCE(SUM(sz), 0) AS total_size
                FROM (
                    SELECT
                        CASE
                            WHEN instr(remaining, '/') > 0
                                THEN substr(remaining, 1, instr(remaining, '/') - 1)
                            ELSE remaining
                        END AS name,
                        sz
                    FROM (
                        SELECT substr(full_dir, ?) AS remaining, size AS sz
                        FROM (
                            SELECT {fd} AS full_dir, f.size
                            FROM share_file f
                            WHERE f.organized = 1 AND f.is_dir = 0
                              AND f.organized_dir != ''
                              AND ({fd}) LIKE ? ESCAPE '\\'
                        )
                        WHERE full_dir != ?
                    )
                )
                WHERE name != ''
                GROUP BY name
                ORDER BY name COLLATE NOCASE
                """,
                (prefix_len, like_pat, path),
            )

        dirs = []
        for r in dir_rows:
            name = r["name"]
            full_path = name if not path else f"{path}/{name}"
            dirs.append({
                "name": name,
                "path": full_path,
                "is_dir": 1,
                "file_count": int(r["file_count"] or 0),
                "total_size": int(r["total_size"] or 0),
            })

        # ---- files exactly at this virtual path ----
        file_count_row = self.db.fetchone(
            f"""
            SELECT COUNT(*) AS cnt
            FROM share_file f
            WHERE f.organized = 1 AND f.is_dir = 0 AND f.organized_dir != ''
              AND ({fd}) = ?
            """,
            (path,),
        )
        file_total = int(file_count_row["cnt"]) if file_count_row else 0

        dir_total = len(dirs)
        total = dir_total + file_total

        # Combined pagination: dirs first, then files
        entries: list = []
        end = offset + limit

        # slice dirs
        if offset < dir_total:
            dir_slice = dirs[offset:end]
            entries.extend(dir_slice)
            files_needed = limit - len(dir_slice)
            file_offset = 0
        else:
            files_needed = limit
            file_offset = offset - dir_total

        if files_needed > 0 and file_total > 0:
            file_rows = self.db.fetchall(
                f"""
                SELECT f.id, f.source_id, f.share_code, f.receive_code, f.file_id,
                       f.parent_id, f.name, f.is_dir, f.size, f.sha1,
                       f.media_type, f.title, f.year, f.tmdb_id, f.category,
                       f.organized_dir, f.organized_name, f.organized,
                       f.created_at, f.updated_at,
                       s.share_name, s.link_valid
                FROM share_file f
                JOIN share_source s ON f.source_id = s.id
                WHERE f.organized = 1 AND f.is_dir = 0 AND f.organized_dir != ''
                  AND ({fd}) = ?
                ORDER BY f.organized_name COLLATE NOCASE, f.name COLLATE NOCASE
                LIMIT ? OFFSET ?
                """,
                (path, files_needed, file_offset),
            )
            for r in file_rows:
                d = dict(r)
                disp = d.get("organized_name") or d.get("name") or ""
                entries.append({
                    "name": disp,
                    "path": (path + "/" + disp) if path else disp,
                    "is_dir": 0,
                    "file_count": 0,
                    "total_size": int(d.get("size") or 0),
                    "file": d,
                })

        return {
            "path": path,
            "entries": entries,
            "total": total,
            "dir_count": dir_total,
            "file_count": file_total,
            "limit": limit,
            "offset": offset,
        }

    def search_files(
        self,
        keyword: str,
        limit: int = 50,
        offset: int = 0,
        scope: str = "all",
    ) -> Dict:
        """分页搜索分享文件。

        Args:
            keyword: 关键字（匹配 name/title/organized_name/organized_dir；纯数字额外匹配 tmdb_id）
            limit/offset: 分页
            scope: all | organized | original
                   original = 未整理文件/目录（organized=0）
                   organized = 已整理文件
        """
        keyword = (keyword or "").strip()
        limit = 50 if (limit is None or int(limit) <= 0) else min(int(limit), 200)
        offset = max(0, int(offset or 0))
        scope = (scope or "all").lower()
        if scope not in ("all", "organized", "original"):
            scope = "all"

        if not keyword:
            return {
                "files": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "keyword": keyword,
                "scope": scope,
            }

        scope_clause = ""
        if scope == "organized":
            scope_clause = " AND f.organized = 1 AND f.is_dir = 0"
        elif scope == "original":
            # 原始视图搜索：全部条目（含目录），不限 organized
            scope_clause = ""

        # Prefer FTS when available; fall back to LIKE on error or empty
        # (FTS unicode61 is weak for Chinese substring matches like "剧" in "电视剧")
        files = None
        total = None
        used_fts = False
        if self._fts_available():
            try:
                files, total = self._search_files_fts(keyword, limit, offset, scope_clause)
                used_fts = True
            except Exception:
                files, total = None, None
                used_fts = False

        if files is None:
            files, total = self._search_files_like(keyword, limit, offset, scope_clause)
            used_fts = False
        elif int(total or 0) == 0:
            like_files, like_total = self._search_files_like(keyword, limit, offset, scope_clause)
            if int(like_total or 0) > 0:
                files, total = like_files, like_total
                used_fts = False

        return {
            "files": files,
            "total": total,
            "limit": limit,
            "offset": offset,
            "keyword": keyword,
            "scope": scope,
            "engine": "fts" if used_fts else "like",
        }

    def _fts_available(self) -> bool:
        try:
            row = self.db.fetchone(
                "SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name='share_file_fts'"
            )
            return bool(row)
        except Exception:
            return False

    def _search_files_like(
        self, keyword: str, limit: int, offset: int, scope_clause: str
    ):
        like_fields = ["f.name", "f.title", "f.organized_name", "f.organized_dir", "f.category"]
        like_pattern = f"%{keyword}%"
        where_clauses = [f"{field} LIKE ? ESCAPE '\\'" for field in like_fields]
        # escape LIKE wildcards in user input
        esc = (
            keyword.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        like_pattern = f"%{esc}%"
        params: list = [like_pattern] * len(like_fields)

        try:
            tmdb_id_val = int(keyword)
            where_clauses.append("f.tmdb_id = ?")
            params.append(tmdb_id_val)
        except (ValueError, TypeError):
            pass

        where_sql = "(" + " OR ".join(where_clauses) + ")" + scope_clause

        count_row = self.db.fetchone(
            f"""SELECT COUNT(*) AS cnt
                FROM share_file f
                WHERE {where_sql}""",
            tuple(params),
        )
        total = int(count_row["cnt"]) if count_row else 0

        rows = self.db.fetchall(
            f"""SELECT f.id, f.source_id, f.share_code, f.receive_code, f.file_id,
                       f.parent_id, f.name, f.is_dir, f.size, f.sha1,
                       f.media_type, f.title, f.year, f.tmdb_id, f.category,
                       f.organized_dir, f.organized_name, f.organized,
                       f.created_at, f.updated_at,
                       s.share_name, s.link_valid
                FROM share_file f
                JOIN share_source s ON f.source_id = s.id
                WHERE {where_sql}
                ORDER BY f.is_dir DESC, f.updated_at DESC
                LIMIT ? OFFSET ?""",
            tuple(params + [limit, offset]),
        )
        return [dict(r) for r in rows], total

    def _search_files_fts(
        self, keyword: str, limit: int, offset: int, scope_clause: str
    ):
        """FTS5 search; keyword sanitized to phrase/token query."""
        # Build MATCH query: quote phrase, strip FTS operators
        raw = keyword.strip()
        # Escape double quotes
        safe = raw.replace('"', '""')
        # Phrase match for multi-char; also allow prefix
        match_q = f'"{safe}"'

        # Also try tmdb exact via OR outside FTS if numeric
        tmdb_extra = ""
        tmdb_params: list = []
        try:
            tmdb_id_val = int(raw)
            tmdb_extra = " OR f.tmdb_id = ?"
            tmdb_params.append(tmdb_id_val)
        except (ValueError, TypeError):
            pass

        # Ensure FTS index has rows (lazy rebuild if empty)
        cnt = self.db.fetchone("SELECT COUNT(*) AS c FROM share_file_fts")
        if cnt and int(cnt["c"] or 0) == 0:
            self.rebuild_search_index()

        base_where = f"(share_file_fts MATCH ?{tmdb_extra}){scope_clause}"
        params = [match_q] + tmdb_params

        count_row = self.db.fetchone(
            f"""SELECT COUNT(*) AS cnt
                FROM share_file f
                JOIN share_file_fts ON share_file_fts.rowid = f.id
                WHERE {base_where}""",
            tuple(params),
        )
        total = int(count_row["cnt"]) if count_row else 0

        rows = self.db.fetchall(
            f"""SELECT f.id, f.source_id, f.share_code, f.receive_code, f.file_id,
                       f.parent_id, f.name, f.is_dir, f.size, f.sha1,
                       f.media_type, f.title, f.year, f.tmdb_id, f.category,
                       f.organized_dir, f.organized_name, f.organized,
                       f.created_at, f.updated_at,
                       s.share_name, s.link_valid
                FROM share_file f
                JOIN share_file_fts ON share_file_fts.rowid = f.id
                JOIN share_source s ON f.source_id = s.id
                WHERE {base_where}
                ORDER BY f.is_dir DESC, f.updated_at DESC
                LIMIT ? OFFSET ?""",
            tuple(params + [limit, offset]),
        )
        return [dict(r) for r in rows], total

    def rebuild_search_index(self) -> int:
        """全量重建 FTS 索引，返回索引条数。"""
        if not self._fts_available():
            return 0
        self.db.execute("DELETE FROM share_file_fts")
        self.db.execute(
            """INSERT INTO share_file_fts(rowid, name, title, organized_name, organized_dir)
               SELECT id,
                      IFNULL(name, ''),
                      IFNULL(title, ''),
                      IFNULL(organized_name, ''),
                      IFNULL(organized_dir, '')
               FROM share_file"""
        )
        self.db.commit()
        row = self.db.fetchone("SELECT COUNT(*) AS c FROM share_file_fts")
        return int(row["c"]) if row else 0

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
