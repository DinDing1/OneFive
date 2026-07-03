"""数据库测试

测试 onefive.db.database.Database 类。

测试策略：
- 使用 tmp_path fixture 传入临时目录路径，避免创建真实数据库文件
- 不使用 :memory: 模式（Database.__init__ 需要 Path 对象且会创建父目录）
- 单例 get_db() 测试需 patch DB_PATH 并重置 _db_instance

测试覆盖：
- 表自动创建（setting / share_source / share_file）
- setting 表 CRUD 流程
- share_source 表插入与查询
- share_file 表插入与查询
- 单例 get_db() 返回同一实例
- close() 后 _conn 为 None
"""
from pathlib import Path

import pytest
from onefive.db.database import Database, get_db
import onefive.db.database as db_module


class TestDatabaseInit:
    """测试数据库初始化"""

    def test_实例化后_三张表自动创建(self, tmp_path):
        # Arrange：使用临时目录
        db_path = str(tmp_path / "test.db")
        # Act：实例化 Database 会自动执行 _init_tables
        db = Database(db_path=db_path)
        # Assert：查询 sqlite_master 确认三张表存在
        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row["name"] for row in cursor.fetchall()]
        assert "setting" in tables
        assert "share_source" in tables
        assert "share_file" in tables
        # 清理
        db.close()


class TestSettingCRUD:
    """测试 setting 表的增删改查流程"""

    def test_setting表_set_get_has_delete完整流程(self, tmp_path):
        # Arrange
        db = Database(db_path=str(tmp_path / "test.db"))
        # Act 1 - set：插入配置
        db.execute(
            "INSERT INTO setting (name, value) VALUES (?, ?)",
            ("test_key", "test_value"),
        )
        db.commit()
        # Assert 1 - get：能查询到刚插入的值
        row = db.fetchone("SELECT value FROM setting WHERE name = ?", ("test_key",))
        assert row["value"] == "test_value"
        # Act 2 - has：检查配置是否存在
        exists_row = db.fetchone("SELECT 1 FROM setting WHERE name = ?", ("test_key",))
        # Assert 2：存在时返回非 None
        assert exists_row is not None
        # Act 3 - delete：删除配置
        db.execute("DELETE FROM setting WHERE name = ?", ("test_key",))
        db.commit()
        # Assert 3：删除后查询返回 None
        deleted_row = db.fetchone("SELECT value FROM setting WHERE name = ?", ("test_key",))
        assert deleted_row is None
        # 清理
        db.close()


class TestShareSourceInsert:
    """测试 share_source 表插入"""

    def test_插入分享来源_能查询到记录(self, tmp_path):
        # Arrange
        db = Database(db_path=str(tmp_path / "test.db"))
        # Act：插入一条分享来源记录
        db.execute(
            "INSERT INTO share_source (share_code, share_name) VALUES (?, ?)",
            ("code123", "测试分享"),
        )
        db.commit()
        # Assert：能按 share_code 查询到记录
        row = db.fetchone(
            "SELECT share_code, share_name FROM share_source WHERE share_code = ?",
            ("code123",),
        )
        assert row["share_code"] == "code123"
        assert row["share_name"] == "测试分享"
        # 清理
        db.close()


class TestShareFileInsert:
    """测试 share_file 表插入"""

    def test_插入分享文件_能查询到记录(self, tmp_path):
        # Arrange
        db = Database(db_path=str(tmp_path / "test.db"))
        # Act：插入一条分享文件记录
        db.execute(
            "INSERT INTO share_file (source_id, file_id, name) VALUES (?, ?, ?)",
            (1, "file001", "movie.mkv"),
        )
        db.commit()
        # Assert：能按 file_id 查询到记录
        row = db.fetchone(
            "SELECT name FROM share_file WHERE file_id = ?",
            ("file001",),
        )
        assert row["name"] == "movie.mkv"
        # 清理
        db.close()


class TestGetDbSingleton:
    """测试单例函数 get_db()"""

    def test_连续调用getDb_返回同一实例(self, monkeypatch, tmp_path):
        # Arrange：重置单例并 patch DB_PATH 到临时路径，避免创建真实数据库
        # 注意：DB_PATH 必须是 Path 对象（Database.__init__ 会调用 .parent.mkdir）
        monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "singleton.db")
        db_module._db_instance = None
        try:
            # Act：连续两次调用 get_db()
            db1 = get_db()
            db2 = get_db()
            # Assert：返回同一实例（单例模式）
            assert db1 is db2
        finally:
            # 清理：关闭连接并重置单例，避免影响其他测试
            if db_module._db_instance is not None:
                db_module._db_instance.close()
                db_module._db_instance = None


class TestDatabaseClose:
    """测试 close() 方法"""

    def test_close后_conn为None(self, tmp_path):
        # Arrange
        db = Database(db_path=str(tmp_path / "test.db"))
        # Act：关闭连接
        db.close()
        # Assert：_conn 被置为 None
        assert db._conn is None
