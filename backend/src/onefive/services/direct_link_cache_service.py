"""
直链缓存服务 - 管理 302 直链的本地缓存

原理说明：
- 使用 SQLite direct_link_cache 表缓存 302 重定向 URL
- 通过 pickcode（文件标识）作为主键，支持按 file_id 查询
- 缓存默认 2 小时过期，过期后自动判定为无效
- 提供定期清理过期缓存的能力

执行步骤：
1. 读取/写入缓存时，先检查过期时间
2. 过期的缓存不会被返回，视为未命中
3. cleanup() 可批量清理已过期的记录
"""
from datetime import datetime
from typing import Optional

from ..db.database import get_db
from ..logger import get_logger

logger = get_logger(__name__)


class DirectLinkCacheService:
    """直链缓存服务类

    职责：
    - 管理 direct_link_cache 表的增删改查
    - 提供缓存命中/过期判断
    - 支持按 pickcode 和 file_id 查询
    """

    def __init__(self):
        """初始化直链缓存服务"""
        self.db = get_db()

    def get_url(self, pickcode: str) -> Optional[str]:
        """根据 pickcode 获取缓存的直链 URL

        Args:
            pickcode: 文件的 pickcode 标识

        Returns:
            未过期的 URL，过期或不存在则返回 None
        """
        row = self.db.fetchone(
            "SELECT url, expires_at FROM direct_link_cache WHERE pickcode = ?",
            (pickcode,)
        )
        if not row:
            return None

        # 判断缓存是否过期
        expires_at = row["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if datetime.now() >= expires_at:
            return None

        return row["url"]

    def get_url_by_file_id(self, file_id: str) -> Optional[str]:
        """根据 file_id 获取缓存的直链 URL

        注意：同一个 file_id 可能有多条缓存记录，取第一条未过期的

        Args:
            file_id: 文件 ID

        Returns:
            未过期的 URL，过期或不存在则返回 None
        """
        row = self.db.fetchone(
            "SELECT url, expires_at FROM direct_link_cache WHERE file_id = ? ORDER BY created_at DESC",
            (file_id,)
        )
        if not row:
            return None

        # 判断缓存是否过期
        expires_at = row["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if datetime.now() >= expires_at:
            return None

        return row["url"]

    def set_url(self, pickcode: str, file_id: str, url: str, expires_in: int = 7200):
        """写入或更新直链缓存

        Args:
            pickcode: 文件的 pickcode 标识
            file_id: 文件 ID
            url: 302 重定向 URL
            expires_in: 过期时间（秒），默认 7200（2 小时）
        """
        expires_at = datetime.now().timestamp() + expires_in
        expires_at_str = datetime.fromtimestamp(expires_at).isoformat()

        self.db.execute(
            """INSERT INTO direct_link_cache (pickcode, file_id, url, expires_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(pickcode) DO UPDATE SET
                   file_id = excluded.file_id,
                   url = excluded.url,
                   expires_at = excluded.expires_at""",
            (pickcode, file_id, url, expires_at_str)
        )
        self.db.commit()

    def invalidate(self, pickcode: str):
        """删除指定 pickcode 的缓存

        Args:
            pickcode: 文件的 pickcode 标识
        """
        self.db.execute(
            "DELETE FROM direct_link_cache WHERE pickcode = ?",
            (pickcode,)
        )
        self.db.commit()

    def cleanup(self) -> int:
        """清理所有过期的缓存记录

        Returns:
            清理的记录数量
        """
        now_str = datetime.now().isoformat()
        cursor = self.db.execute(
            "DELETE FROM direct_link_cache WHERE expires_at < ?",
            (now_str,)
        )
        self.db.commit()
        count = cursor.rowcount
        if count > 0:
            logger.info(f"清理过期直链缓存 {count} 条")
        return count


# 全局直链缓存服务实例（单例模式）
_direct_link_cache_service: Optional[DirectLinkCacheService] = None


def get_direct_link_cache_service() -> DirectLinkCacheService:
    """获取直链缓存服务实例（单例模式）

    Returns:
        直链缓存服务实例
    """
    global _direct_link_cache_service
    if _direct_link_cache_service is None:
        _direct_link_cache_service = DirectLinkCacheService()
    return _direct_link_cache_service
