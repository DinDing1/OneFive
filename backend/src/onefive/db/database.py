"""
数据库模块 - 提供 SQLite 数据库连接和操作

原理说明：
- 使用 SQLite 作为轻量级数据库，存储应用配置和运行时数据
- 采用单例模式管理数据库连接，避免重复创建连接
- 提供上下文管理器支持，确保连接正确关闭
- 自动创建数据目录和数据库文件
- 路径由 paths 模块统一管理，自动适配飞牛环境
"""
import sqlite3
import threading
from pathlib import Path
from typing import Optional, List

from ..paths import DB_PATH


class Database:
    """SQLite 数据库管理类

    职责：
    - 管理数据库连接生命周期
    - 提供通用的数据库操作方法
    - 自动初始化数据库表结构
    """

    def __init__(self, db_path: Optional[str] = None):
        """初始化数据库连接

        Args:
            db_path: 数据库文件路径，如果为 None 则使用 paths 模块的默认路径
        """
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 线程锁：sqlite3.connect(check_same_thread=False) 允许多线程访问同一连接，
        # 但 SQLite 写入需要串行化，并发写入会抛 "database is locked"。
        # 所有数据库操作都通过 self._lock 串行化，保证线程安全。
        # 注意：所有方法均为单次 acquire-release，不嵌套调用其他加锁方法，避免死锁。
        self._lock = threading.Lock()

        # 建立连接并初始化表结构
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row  # 返回字典形式的结果
        self._init_tables()

    def _init_tables(self):
        """初始化数据库表结构

        创建三张表：
        - setting: 配置变量存储（name/value/description + 时间戳）
        - share_source: 分享链接来源（含 share_code、receive_code、link_valid 等）
        - share_file: 分享文件（含目录和文件，支持整理状态追踪）

        字段含义详见下方 CREATE TABLE 语句的行内注释。
        """
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS setting (
                name TEXT PRIMARY KEY,
                value TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                updated_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
            )
        """)
        # 分享来源表
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS share_source (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                share_code   TEXT NOT NULL UNIQUE,
                receive_code TEXT DEFAULT '',
                share_name   TEXT DEFAULT '',
                share_url    TEXT DEFAULT '',
                source_type  TEXT DEFAULT 'manual',
                file_count   INTEGER DEFAULT 0,
                total_size   INTEGER DEFAULT 0,
                status       TEXT DEFAULT 'pending',
                link_valid   INTEGER DEFAULT 1,              -- 分享链接是否有效：1=有效 0=无效
                error_msg    TEXT DEFAULT '',
                created_at   TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                updated_at   TIMESTAMP DEFAULT (datetime('now', 'localtime'))
            )
        """)
        # 分享文件表（存储目录和文件，目录用于展示层级，文件用于整理）
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS share_file (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id      INTEGER NOT NULL,
                share_code     TEXT DEFAULT '',               -- 所属分享码
                receive_code   TEXT DEFAULT '',               -- 提取码
                file_id        TEXT NOT NULL,
                parent_id      TEXT DEFAULT '0',              -- 父目录 file_id
                name           TEXT NOT NULL,
                is_dir         INTEGER DEFAULT 0,             -- 是否为目录：0=文件 1=目录
                size           INTEGER DEFAULT 0,
                sha1           TEXT DEFAULT '',
                media_type     TEXT DEFAULT '',               -- 媒体类型：movie / tv / 空（整理时由 TMDB 判定）
                title          TEXT DEFAULT '',               -- 识别后的标题
                year           TEXT DEFAULT '',               -- 年份
                tmdb_id        INTEGER DEFAULT 0,             -- TMDB ID
                category       TEXT DEFAULT '',               -- 分类路径（如 剧集/国产剧）
                organized_dir  TEXT DEFAULT '',               -- 整理后的目录路径
                organized_name TEXT DEFAULT '',               -- 整理后的文件名
                organized      INTEGER DEFAULT 0,             -- 是否已整理：0=未整理 1=已整理
                created_at     TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                updated_at     TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                UNIQUE(source_id, file_id)
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_share_file_source ON share_file(source_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_share_file_parent ON share_file(source_id, parent_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_share_file_name ON share_file(name)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_share_file_category ON share_file(category)")
        # 频繁查询 organized + is_dir 的复合索引（get_organized_files 等使用）
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_share_file_organized ON share_file(organized, is_dir)")
        # 直链服务按 share_code + file_id 查询
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_share_file_share_code ON share_file(share_code, file_id)")
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行 SQL 语句（线程安全）"""
        with self._lock:
            return self._conn.execute(sql, params)

    def executemany(self, sql: str, params: list) -> None:
        """批量执行 SQL 语句（线程安全）

        用于一次性插入/更新多条记录，减少数据库往返次数。
        """
        with self._lock:
            self._conn.executemany(sql, params)

    def commit(self):
        """提交事务（线程安全）"""
        with self._lock:
            self._conn.commit()

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """查询单条记录（线程安全）"""
        with self._lock:
            cursor = self._conn.execute(sql, params)
            return cursor.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """查询多条记录（线程安全）"""
        with self._lock:
            cursor = self._conn.execute(sql, params)
            return cursor.fetchall()

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# 全局数据库实例（单例模式）
_db_instance: Optional[Database] = None


def get_db() -> Database:
    """获取数据库实例（单例模式）"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance


def close_db():
    """关闭全局数据库实例"""
    global _db_instance
    if _db_instance is not None:
        _db_instance.close()
        _db_instance = None
