"""
配置管理服务 - 管理应用配置的读写

原理说明：
- 使用 SQLite setting 表存储配置
- 提供配置的增删改查操作
- 支持配置的批量操作
- 自动处理配置的序列化/反序列化

执行步骤：
1. 从数据库读取配置
2. 进行数据验证
3. 返回配置值或执行配置操作
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
    
    def get(self, name: str) -> Optional[str]:
        """获取配置值
        
        Args:
            name: 配置名称
            
        Returns:
            配置值，如果不存在返回 None
        """
        row = self.db.fetchone(
            "SELECT value FROM setting WHERE name = ?",
            (name,)
        )
        return row["value"] if row else None
    
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
        """设置配置值（如果存在则更新，否则创建）
        
        Args:
            name: 配置名称
            value: 配置值
            description: 配置说明
            
        Returns:
            配置详情
        """
        # 检查配置是否已存在
        existing = self.get_with_info(name)
        
        if existing:
            # 更新现有配置
            self.db.execute(
                "UPDATE setting SET value = ?, description = COALESCE(?, description), updated_at = datetime('now', 'localtime') WHERE name = ?",
                (value, description, name)
            )
        else:
            # 创建新配置
            self.db.execute(
                "INSERT INTO setting (name, value, description) VALUES (?, ?, ?)",
                (name, value, description)
            )
        
        self.db.commit()
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
        """批量设置配置
        
        Args:
            settings: 配置字典 {name: value}
            description: 配置说明（应用于所有配置）
            
        Returns:
            成功设置的配置数量
        """
        count = 0
        for name, value in settings.items():
            self.set(name, value, description)
            count += 1
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
