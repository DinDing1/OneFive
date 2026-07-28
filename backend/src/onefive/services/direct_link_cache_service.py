"""
直链 URL 数据库缓存服务

职责：
- 将 115 下载直链持久化到 SQLite，跨重启复用
- 在 URL 仍有效时直接命中缓存，避免重复请求 115 触发风控
- 与 p115nano302 内存缓存（L1）互补：本服务提供 L0 热缓存 + L2 持久层
- L0 有上限，专供 Emby 播放期高频 302，避免反复抢 SQLite 全局锁抬高 RSS

缓存键策略（与 STRM / p115nano302 请求参数对齐）：
- pickcode 查询:  pc:{pickcode}
- 文件 id 查询:  id:{file_id}
- sha1 查询:     sha1:{sha1}
- 分享文件查询:  share:{share_code}:{file_id}

UA 敏感链接：
- 115 部分下载 URL 与 User-Agent 绑定（URL 中不含 &c=0&f=&）
- 此类链接缓存键追加 |ua:{sha1(ua)[:16]}
- 与 p115nano302 的内存缓存策略一致

有效期：
- 优先解析 URL 查询参数 t（unix 时间戳），并提前 5 分钟过期
- 解析失败时使用默认 2 小时有效期
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import parse_qsl, urlsplit

from ..db.database import get_db
from ..logger import get_logger

logger = get_logger(__name__)

# 默认有效期（秒）：无法从 URL 解析 t 时使用
DEFAULT_TTL_SECONDS = 2 * 60 * 60
# 提前失效缓冲（秒），与 p115nano302 一致
EXPIRE_BUFFER_SECONDS = 5 * 60
# 惰性清理：每 N 次写入触发一次过期清理
_CLEANUP_EVERY_N_WRITES = 50
# L0 进程内热缓存上限（条）：覆盖 Emby 并发播放热路径，避免每次 302 打 SQLite
# 单条约几百字节 URL，1024 条峰值通常 < 1MB
_L0_MAXSIZE = 1024


class DirectLinkCacheService:
    """直链 URL 数据库缓存（L2）+ 进程内热缓存（L0）

    层级：
    - L0：进程内 OrderedDict LRU，服务 Emby 高频 302 命中
    - L2：SQLite 持久化，跨重启、降风控
    - L1：由 p115nano302 自身维护（有界 cache_size）
    """

    def __init__(self):
        self.db = get_db()
        self._write_count = 0
        # key -> (url, expires_at)
        self._l0: OrderedDict[str, Tuple[str, float]] = OrderedDict()
        self._l0_lock = threading.Lock()

    def _write_with_retry(self, sql: str, params: tuple = (), *, action: str = "write") -> int:
        """原子写入；遇到 readonly/locked 时重连重试一次。

        Returns:
            cursor.rowcount（失败时 -1 不抛到调用方时由上层处理）
        """
        last_err = None
        for attempt in range(2):
            try:
                cur = self.db.execute_write(sql, params)
                return cur.rowcount if cur is not None else 0
            except Exception as e:
                last_err = e
                if attempt == 0 and self.db.is_recoverable_write_error(e):
                    logger.warning(
                        f"直链缓存{action}失败，尝试重连数据库后重试: {e}"
                    )
                    try:
                        self.db.reconnect()
                    except Exception as re:
                        logger.warning(f"数据库重连失败: {re}")
                        break
                    continue
                break
        assert last_err is not None
        raise last_err

    # ==================== 键构建 ====================

    @staticmethod
    def build_base_key(
        pickcode: str = "",
        file_id: str = "",
        share_code: str = "",
        sha1: str = "",
    ) -> Optional[str]:
        """根据请求参数构建基础缓存键（不含 UA）

        优先级：分享 > pickcode > id > sha1
        """
        share_code = (share_code or "").strip()
        file_id = (file_id or "").strip()
        pickcode = (pickcode or "").strip()
        sha1 = (sha1 or "").strip().upper()

        if share_code and file_id:
            return f"share:{share_code}:{file_id}"
        if pickcode:
            return f"pc:{pickcode}"
        if file_id:
            return f"id:{file_id}"
        if sha1:
            return f"sha1:{sha1}"
        return None

    @staticmethod
    def ua_suffix(user_agent: str = "") -> str:
        """User-Agent 哈希后缀（缩短键长）"""
        ua = (user_agent or "").strip()
        if not ua:
            return ""
        digest = hashlib.sha1(ua.encode("utf-8", errors="ignore")).hexdigest()[:16]
        return f"|ua:{digest}"

    @staticmethod
    def is_ua_independent_url(url: str) -> bool:
        """判断下载 URL 是否与 User-Agent 无关

        p115nano302 约定：URL 含 "&c=0&f=&" 时可跨 UA 复用。
        """
        return "&c=0&f=&" in (url or "")

    @classmethod
    def build_store_key(cls, base_key: str, url: str, user_agent: str = "") -> str:
        """写入缓存时的最终键"""
        if cls.is_ua_independent_url(url):
            return base_key
        suffix = cls.ua_suffix(user_agent)
        return f"{base_key}{suffix}" if suffix else base_key

    @classmethod
    def candidate_keys(cls, base_key: str, user_agent: str = "") -> List[str]:
        """查询时的候选键：先 UA 绑定，再通用键"""
        keys: List[str] = []
        suffix = cls.ua_suffix(user_agent)
        if suffix:
            keys.append(f"{base_key}{suffix}")
        keys.append(base_key)
        # 去重保序
        seen = set()
        result = []
        for k in keys:
            if k not in seen:
                seen.add(k)
                result.append(k)
        return result

    # ==================== 有效期 ====================

    @staticmethod
    def parse_expire_ts(url: str) -> float:
        """从下载 URL 解析过期时间戳（提前 EXPIRE_BUFFER_SECONDS）"""
        now = time.time()
        try:
            query = urlsplit(url).query
            for k, v in parse_qsl(query):
                if k == "t" and v.isdigit():
                    return float(int(v) - EXPIRE_BUFFER_SECONDS)
        except Exception:
            pass
        return now + DEFAULT_TTL_SECONDS - EXPIRE_BUFFER_SECONDS

    # ==================== L0 热缓存 ====================

    def _l0_get(self, cache_key: str) -> Optional[str]:
        """读取 L0；过期则剔除。"""
        if not cache_key:
            return None
        now = time.time()
        with self._l0_lock:
            item = self._l0.get(cache_key)
            if item is None:
                return None
            url, expires_at = item
            if expires_at <= now:
                self._l0.pop(cache_key, None)
                return None
            self._l0.move_to_end(cache_key)
            return url

    def _l0_set(self, cache_key: str, url: str, expires_at: float) -> None:
        """写入 L0，超出上限淘汰最久未用项。"""
        if not cache_key or not url or expires_at <= time.time():
            return
        with self._l0_lock:
            self._l0[cache_key] = (url, float(expires_at))
            self._l0.move_to_end(cache_key)
            while len(self._l0) > _L0_MAXSIZE:
                self._l0.popitem(last=False)

    def _l0_invalidate(self, cache_key: str) -> None:
        if not cache_key:
            return
        with self._l0_lock:
            self._l0.pop(cache_key, None)

    def _l0_drop_prefix(self, base_key: str) -> None:
        """按 base_key 清除 L0（含 UA 变体）。"""
        if not base_key:
            return
        prefix = f"{base_key}|ua:"
        with self._l0_lock:
            dead = [k for k in self._l0 if k == base_key or k.startswith(prefix)]
            for k in dead:
                self._l0.pop(k, None)

    # ==================== CRUD ====================

    def get_url(self, cache_key: str) -> Optional[str]:
        """按精确键查询未过期缓存 URL（先 L0，再 SQLite）"""
        if not cache_key:
            return None

        # L0 热路径：Emby 播放/探测高频命中，避免全局 DB 锁
        hot = self._l0_get(cache_key)
        if hot:
            return hot

        now = time.time()
        row = self.db.fetchone(
            "SELECT url, expires_at FROM direct_link_cache WHERE cache_key = ?",
            (cache_key,),
        )
        if not row:
            return None
        expires_at = float(row["expires_at"] or 0)
        if expires_at <= now:
            # 过期则删除，避免表膨胀
            self._l0_invalidate(cache_key)
            try:
                self._write_with_retry(
                    "DELETE FROM direct_link_cache WHERE cache_key = ?",
                    (cache_key,),
                    action="删除过期",
                )
            except Exception as e:
                logger.debug(f"删除过期直链缓存失败: {e}")
            return None

        url = row["url"]
        # 回填 L0，后续同键直出
        self._l0_set(cache_key, url, expires_at)
        return url

    def get_valid_url(
        self,
        pickcode: str = "",
        file_id: str = "",
        share_code: str = "",
        sha1: str = "",
        user_agent: str = "",
    ) -> Optional[str]:
        """按请求参数查找有效缓存 URL"""
        base_key = self.build_base_key(
            pickcode=pickcode,
            file_id=file_id,
            share_code=share_code,
            sha1=sha1,
        )
        if not base_key:
            return None
        for key in self.candidate_keys(base_key, user_agent):
            url = self.get_url(key)
            if url:
                return url
        return None

    def set_url(
        self,
        url: str,
        pickcode: str = "",
        file_id: str = "",
        share_code: str = "",
        sha1: str = "",
        user_agent: str = "",
        expires_at: Optional[float] = None,
    ) -> bool:
        """写入/更新直链缓存

        Returns:
            是否写入成功
        """
        if not url:
            return False
        base_key = self.build_base_key(
            pickcode=pickcode,
            file_id=file_id,
            share_code=share_code,
            sha1=sha1,
        )
        if not base_key:
            return False

        cache_key = self.build_store_key(base_key, url, user_agent)
        if expires_at is None:
            expires_at = self.parse_expire_ts(url)

        # 已过期则不写
        if expires_at <= time.time():
            logger.debug(f"直链已过期，跳过缓存: key={cache_key}")
            return False

        try:
            self._write_with_retry(
                """
                INSERT INTO direct_link_cache (
                    cache_key, pickcode, file_id, share_code, sha1,
                    user_agent, url, expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
                ON CONFLICT(cache_key) DO UPDATE SET
                    pickcode = excluded.pickcode,
                    file_id = excluded.file_id,
                    share_code = excluded.share_code,
                    sha1 = excluded.sha1,
                    user_agent = excluded.user_agent,
                    url = excluded.url,
                    expires_at = excluded.expires_at,
                    updated_at = datetime('now', 'localtime')
                """,
                (
                    cache_key,
                    (pickcode or "").strip(),
                    (file_id or "").strip(),
                    (share_code or "").strip(),
                    (sha1 or "").strip().upper(),
                    (user_agent or "").strip() if not self.is_ua_independent_url(url) else "",
                    url,
                    float(expires_at),
                ),
                action="写入",
            )
            # 同步 L0，播放期立刻可热命中
            self._l0_set(cache_key, url, float(expires_at))
            self._write_count += 1
            if self._write_count % _CLEANUP_EVERY_N_WRITES == 0:
                self.cleanup_expired()
            return True
        except Exception as e:
            logger.warning(
                f"写入直链缓存失败: key={cache_key}, db={self.db.db_path}, err={e}"
            )
            return False

    def invalidate(
        self,
        pickcode: str = "",
        file_id: str = "",
        share_code: str = "",
        sha1: str = "",
    ) -> int:
        """按资源标识清除相关缓存（含所有 UA 变体）

        Returns:
            删除行数
        """
        base_key = self.build_base_key(
            pickcode=pickcode,
            file_id=file_id,
            share_code=share_code,
            sha1=sha1,
        )
        if not base_key:
            return 0
        self._l0_drop_prefix(base_key)
        try:
            return max(
                0,
                self._write_with_retry(
                    "DELETE FROM direct_link_cache WHERE cache_key = ? OR cache_key LIKE ?",
                    (base_key, f"{base_key}|ua:%"),
                    action="清除",
                ),
            )
        except Exception as e:
            logger.warning(f"清除直链缓存失败: {e}")
            return 0

    def cleanup_expired(self) -> int:
        """清理全部过期缓存

        Returns:
            删除行数
        """
        try:
            now = time.time()
            # 顺带收缩 L0 过期项，避免热表挂死链
            with self._l0_lock:
                dead = [k for k, (_, exp) in self._l0.items() if exp <= now]
                for k in dead:
                    self._l0.pop(k, None)

            count = max(
                0,
                self._write_with_retry(
                    "DELETE FROM direct_link_cache WHERE expires_at <= ?",
                    (now,),
                    action="清理过期",
                ),
            )
            if count:
                logger.info(f"清理过期直链缓存: {count} 条")
            return count
        except Exception as e:
            logger.warning(f"清理过期直链缓存失败: {e}")
            return 0

    def stats(self) -> Dict[str, Any]:
        """缓存统计信息"""
        now = time.time()
        total_row = self.db.fetchone("SELECT COUNT(*) AS c FROM direct_link_cache")
        valid_row = self.db.fetchone(
            "SELECT COUNT(*) AS c FROM direct_link_cache WHERE expires_at > ?",
            (now,),
        )
        with self._l0_lock:
            l0_size = len(self._l0)
        return {
            "total": int(total_row["c"]) if total_row else 0,
            "valid": int(valid_row["c"]) if valid_row else 0,
            "l0": l0_size,
            "l0_max": _L0_MAXSIZE,
        }


_cache_service: Optional[DirectLinkCacheService] = None


def get_direct_link_cache_service() -> DirectLinkCacheService:
    """获取直链缓存服务单例"""
    global _cache_service
    if _cache_service is None:
        _cache_service = DirectLinkCacheService()
    return _cache_service
