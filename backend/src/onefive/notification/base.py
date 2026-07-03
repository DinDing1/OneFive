"""
通知渠道抽象基类

所有通知渠道（Telegram、微信等）都需要继承此基类并实现抽象方法。
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class NotificationChannel(ABC):
    """通知渠道抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """渠道名称，如 'telegram'、'wechat'"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """渠道显示名称，如 'Telegram'、'微信'"""
        ...

    @abstractmethod
    async def send_message(self, message: str, image_url: Optional[str] = None) -> bool:
        """发送通知消息

        Args:
            message: 消息文本（支持 HTML 格式）
            image_url: 可选的图片 URL

        Returns:
            是否发送成功
        """
        ...

    @abstractmethod
    async def is_configured(self) -> bool:
        """检查是否已配置（必要的配置项是否已填写）"""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        """检查是否已连接"""
        ...

    async def is_enabled(self) -> bool:
        """检查渠道是否启用（默认启用，子类可按需覆盖）

        Returns:
            是否启用，未覆盖时默认返回 True
        """
        return True

    @abstractmethod
    async def connect(self) -> bool:
        """建立连接

        Returns:
            是否连接成功
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
        ...

    @abstractmethod
    def get_settings_schema(self) -> List[Dict[str, Any]]:
        """返回该渠道的配置项定义

        Returns:
            配置项列表，每项包含：
            - key: 配置键名
            - label: 显示名称
            - type: 输入类型（text/password/toggle/select）
            - placeholder: 占位提示
            - options: 选项列表（select 类型时使用）
        """
        ...

    @abstractmethod
    async def get_current_settings(self) -> Dict[str, Any]:
        """获取当前配置值"""
        ...

    @abstractmethod
    async def update_settings(self, settings: Dict[str, Any]) -> None:
        """更新配置"""
        ...

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取连接状态

        Returns:
            {"configured": bool, "connected": bool, "message": str}
        """
        ...
