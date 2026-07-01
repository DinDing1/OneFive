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

from importlib import import_module

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
            return {"success": False, "error": f"分享 {share_code} 已存在（source_id={existing['id']}）"}

        # 调用 p115client 获取文件列表
        try:
            from p115client import P115Client
            from p115client.tool import share_iterdir

            # 优先尝试 Open API
            from .token_service import get_token_service
            token_service = get_token_service()
            access_token = token_service.get_access_token()
            
            if access_token:
                # 使用 Open API
                try:
                    open_mod = import_module("p115client.open")
                    P115OpenClient = getattr(open_mod, "P115OpenClient")
                    app_id = token_service.get_app_id()
                    client = P115OpenClient(
                        access_token=access_token,
                        app_id=int(app_id) if app_id else 0,
                    )
                except (ImportError, AttributeError):
                    # p115client 版本不支持 Open API，回退 Web API
                    from .auth_service import get_auth_service
                    cookies = get_auth_service().get_cookies()
                    if not cookies:
                        return {"success": False, "error": "未登录，无法解析分享链接"}
                    client = P115Client(cookies)
            else:
                # 回退 Web API
                from .auth_service import get_auth_service
                cookies = get_auth_service().get_cookies()
                if not cookies:
                    return {"success": False, "error": "未登录，无法解析分享链接"}
                client = P115Client(cookies)

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
            # 清理可能的部分数据
            self.db.execute("DELETE FROM share_source WHERE share_code = ?", (share_code,))
            self.db.commit()
            return {"success": False, "error": str(e)}

    def _insert_files(self, source_id: int, parent_id: str, files: list,
                      share_code: str, receive_code: str, client):
        """递归写入目录和文件"""
        for f in files:
            file_id = str(f.get("id"))
            name = f.get("name", "")
            is_dir = 1 if f.get("is_dir") else 0
            size = f.get("size", 0)
            sha1 = f.get("sha1", "")

            self.db.execute(
                """INSERT OR IGNORE INTO share_file
                   (source_id, share_code, receive_code, file_id, parent_id, name, is_dir, size, sha1)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_id, share_code, receive_code, file_id, parent_id, name, is_dir, size, sha1)
            )

            # 如果是目录，递归获取子文件
            if is_dir:
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

        self.db.commit()

    def list_shares(self) -> List[Dict]:
        """列出所有分享来源"""
        rows = self.db.fetchall(
            "SELECT * FROM share_source ORDER BY created_at DESC"
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

        Returns:
            {"total": int, "success": int, "failed": int}
        """
        total = len(source_ids)
        success = 0
        for sid in source_ids:
            try:
                self.db.execute("DELETE FROM share_file WHERE source_id = ?", (sid,))
                self.db.execute("DELETE FROM share_source WHERE id = ?", (sid,))
                success += 1
            except Exception:
                pass
        self.db.commit()
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
        """更新单个文件的分类路径

        Args:
            source_id: 分享来源 ID
            file_id: 文件 ID
            category: 新的分类路径（如 电影/国产电影）
        """
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

        对于目录，从子文件中提取整理信息（title/year/tmdb_id）。
        """
        condition = "f.parent_id = '0'"
        if organized_only:
            condition += " AND f.organized = 1"
        elif unorganized_only:
            condition += " AND f.organized = 0"

        rows = self.db.fetchall(
            f"""SELECT f.*, s.share_name,
                (SELECT COUNT(*) FROM share_file WHERE source_id = s.id AND is_dir = 0) as file_count,
                (SELECT title FROM share_file WHERE source_id = f.source_id AND parent_id = f.file_id AND organized = 1 AND title != '' LIMIT 1) as child_title,
                (SELECT year FROM share_file WHERE source_id = f.source_id AND parent_id = f.file_id AND organized = 1 AND title != '' LIMIT 1) as child_year,
                (SELECT tmdb_id FROM share_file WHERE source_id = f.source_id AND parent_id = f.file_id AND organized = 1 AND title != '' LIMIT 1) as child_tmdb_id
                FROM share_file f
                JOIN share_source s ON f.source_id = s.id
                WHERE {condition}
                ORDER BY f.is_dir DESC, f.name ASC"""
        )

        result = []
        for r in rows:
            d = dict(r)
            # 目录：用子文件的整理信息补充
            if d.get("is_dir") and d.get("organized") and not d.get("title"):
                d["title"] = d.get("child_title") or ""
                d["year"] = d.get("child_year") or ""
                d["tmdb_id"] = d.get("child_tmdb_id") or 0
            result.append(d)
        return result

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
        """搜索分享文件"""
        rows = self.db.fetchall(
            """SELECT f.*, s.share_code, s.share_name
               FROM share_file f
               JOIN share_source s ON f.source_id = s.id
               WHERE f.name LIKE ?
               ORDER BY f.updated_at DESC
               LIMIT 100""",
            (f"%{keyword}%",)
        )
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

    def update_file_organize(self, source_id: int, file_id: str, data: Dict):
        """更新文件整理信息"""
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
        self.db.commit()


# 单例
_share_service: Optional[ShareService] = None


def get_share_service() -> ShareService:
    """获取分享服务实例"""
    global _share_service
    if _share_service is None:
        _share_service = ShareService()
    return _share_service
