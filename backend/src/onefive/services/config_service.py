"""
配置服务 - 管理应用配置的读写

原理说明：
- 配置以字符串形式存储在 SQLite setting 表（name/value/description）
- 复杂数据结构（如 JSON）由调用方自行序列化和解析
- 采用单例模式，提供 get/set/has/delete 四个核心方法
"""
from typing import Optional, List, Dict, Any
from ..db.database import get_db
from ..models.schemas import SettingCreate, SettingUpdate, SettingResponse


class ConfigService:
    """配置管理服务类
    
    职责：
    - 管理应用配置的读写
    - 提供配置的增删改查操作
    - 支持配置的批量操作
    """
    
    def __init__(self):
        """初始化配置服务"""
        self.db = get_db()
        # 内存缓存：避免频繁读取数据库（配置项变更不频繁，但读取非常频繁）
        # 缓存 value 字符串，未命中时查库并写入缓存；set/delete/set_many 同步更新缓存。
        # 注意：None 也作为合法缓存值（表示该配置不存在），避免反复查库确认不存在。
        self._cache: Dict[str, Optional[str]] = {}

    def get(self, name: str) -> Optional[str]:
        """获取配置值（带内存缓存）

        批量整理时该方法会被调用数百次（每次分类都要读 classify_rules），
        加内存缓存后只在首次查库，后续直接命中缓存。

        Args:
            name: 配置名称

        Returns:
            配置值，如果不存在返回 None
        """
        # 命中缓存直接返回（None 也算命中，表示配置不存在）
        if name in self._cache:
            return self._cache[name]
        # 未命中查数据库并写入缓存
        row = self.db.fetchone(
            "SELECT value FROM setting WHERE name = ?",
            (name,)
        )
        value = row["value"] if row else None
        self._cache[name] = value
        return value
    
    def get_with_info(self, name: str) -> Optional[SettingResponse]:
        """获取配置详情
        
        Args:
            name: 配置名称
            
        Returns:
            配置详情，如果不存在返回 None
        """
        row = self.db.fetchone(
            "SELECT name, value, description, created_at, updated_at FROM setting WHERE name = ?",
            (name,)
        )
        if row is None:
            return None
        return SettingResponse(
            name=row["name"],
            value=row["value"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
    
    def set(self, name: str, value: str, description: Optional[str] = None) -> SettingResponse:
        """设置配置值（UPSERT：存在则更新，不存在则创建）

        使用 INSERT ON CONFLICT DO UPDATE 原子化完成“先查后写”，
        避免并发场景下的竞态条件和多余查询。

        Args:
            name: 配置名称
            value: 配置值
            description: 配置说明（为 None 时保留原值）

        Returns:
            配置详情
        """
        self.db.execute(
            """INSERT INTO setting (name, value, description, updated_at)
               VALUES (?, ?, ?, datetime('now', 'localtime'))
               ON CONFLICT(name) DO UPDATE SET
                   value = excluded.value,
                   description = COALESCE(?, description),
                   updated_at = datetime('now', 'localtime')""",
            (name, value, description, description)
        )
        self.db.commit()
        # 同步更新缓存，保证后续 get 命中缓存
        self._cache[name] = value
        return self.get_with_info(name)
    
    def delete(self, name: str) -> bool:
        """删除配置
        
        Args:
            name: 配置名称
            
        Returns:
            是否删除成功
        """
        cursor = self.db.execute(
            "DELETE FROM setting WHERE name = ?",
            (name,)
        )
        self.db.commit()
        if cursor.rowcount > 0:
            # 同步删除缓存，保证后续 get 重新查库
            self._cache.pop(name, None)
        return cursor.rowcount > 0
    
    def list_all(self) -> List[SettingResponse]:
        """获取所有配置
        
        Returns:
            配置列表
        """
        rows = self.db.fetchall(
            "SELECT name, value, description, created_at, updated_at FROM setting ORDER BY name"
        )
        return [
            SettingResponse(
                name=row["name"],
                value=row["value"],
                description=row["description"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
            for row in rows
        ]
    
    def get_many(self, names: List[str]) -> Dict[str, str]:
        """批量获取配置
        
        Args:
            names: 配置名称列表
            
        Returns:
            配置字典 {name: value}
        """
        if not names:
            return {}
        
        placeholders = ",".join(["?"] * len(names))
        rows = self.db.fetchall(
            f"SELECT name, value FROM setting WHERE name IN ({placeholders})",
            tuple(names)
        )
        return {row["name"]: row["value"] for row in rows}
    
    def set_many(self, settings: Dict[str, str], description: Optional[str] = None) -> int:
        """批量设置配置（单次 commit，减少 IO 往返）

        Args:
            settings: 配置字典 {name: value}
            description: 配置说明（应用于所有配置）

        Returns:
            成功设置的配置数量
        """
        count = 0
        for name, value in settings.items():
            # 复用 UPSERT 语句，但不在此处 commit，统一在末尾提交一次
            self.db.execute(
                """INSERT INTO setting (name, value, description, updated_at)
                   VALUES (?, ?, ?, datetime('now', 'localtime'))
                   ON CONFLICT(name) DO UPDATE SET
                       value = excluded.value,
                       description = COALESCE(?, description),
                       updated_at = datetime('now', 'localtime')""",
                (name, value, description, description)
            )
            # 批量更新缓存，与数据库保持一致
            self._cache[name] = value
            count += 1
        if count:
            self.db.commit()
        return count
    
    def exists(self, name: str) -> bool:
        """检查配置是否存在
        
        Args:
            name: 配置名称
            
        Returns:
            配置是否存在
        """
        row = self.db.fetchone(
            "SELECT 1 FROM setting WHERE name = ?",
            (name,)
        )
        return row is not None


# 全局配置服务实例
_config_service: Optional[ConfigService] = None


def get_config_service() -> ConfigService:
    """获取配置服务实例（单例模式）
    
    Returns:
        配置服务实例
    """
    global _config_service
    if _config_service is None:
        _config_service = ConfigService()
    return _config_service
