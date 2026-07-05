"""
通知管理器

统一调度所有已注册的通知渠道。
"""
import asyncio
from typing import Dict, Any, Optional, List
from .base import NotificationChannel
from ..logger import get_logger

logger = get_logger(__name__)


class NotificationManager:
    """通知管理器"""

    def __init__(self):
        self._channels: Dict[str, NotificationChannel] = {}

    def register(self, channel: NotificationChannel) -> None:
        """注册通知渠道

        注意：注册只是把渠道加入管理器，不代表启用。
        实际发送通知时 send_all 会检查 is_enabled()，未启用的渠道会跳过。
        用 debug 级别避免 info 日志误导用户以为通知已启用。
        """
        self._channels[channel.name] = channel
        logger.debug(f"注册通知渠道: {channel.display_name}")

    def get_channel(self, name: str) -> Optional[NotificationChannel]:
        """获取指定渠道"""
        return self._channels.get(name)

    def list_channels(self) -> List[Dict[str, Any]]:
        """列出所有渠道及状态（同步）"""
        result = []
        for channel in self._channels.values():
            status = channel.get_status()
            result.append({
                "name": channel.name,
                "display_name": channel.display_name,
                "settings_schema": channel.get_settings_schema(),
                **status,
            })
        return result

    async def list_channels_async(self) -> List[Dict[str, Any]]:
        """列出所有渠道及状态（异步，支持获取连接详情）"""
        result = []
        for channel in self._channels.values():
            if hasattr(channel, 'get_connection_info'):
                status = await channel.get_connection_info()
            else:
                status = channel.get_status()
            result.append({
                "name": channel.name,
                "display_name": channel.display_name,
                "settings_schema": channel.get_settings_schema(),
                **status,
            })
        return result

    async def send_all(self, message: str, image_url: Optional[str] = None) -> Dict[str, bool]:
        """向所有已启用且已连接的渠道发送通知

        Returns:
            {"telegram": True, "wechat": False, ...}
        """
        results = {}
        tasks = []
        channel_names = []

        for name, channel in self._channels.items():
            try:
                # 先检查渠道启用开关，未启用的渠道直接跳过
                if not await channel.is_enabled():
                    continue
                if await channel.is_configured() and await channel.is_connected():
                    tasks.append(channel.send_message(message, image_url))
                    channel_names.append(name)
            except Exception as e:
                logger.warning(f"检查渠道 {name} 状态失败: {e}")
                results[name] = False

        if tasks:
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            for name, outcome in zip(channel_names, outcomes):
                if isinstance(outcome, Exception):
                    logger.error(f"发送通知到 {name} 失败: {outcome}")
                    results[name] = False
                else:
                    results[name] = outcome

        return results

    async def send_to(self, channel_name: str, message: str,
                      image_url: Optional[str] = None) -> bool:
        """向指定渠道发送通知"""
        channel = self._channels.get(channel_name)
        if not channel:
            logger.warning(f"通知渠道不存在: {channel_name}")
            return False
        return await channel.send_message(message, image_url)

    async def auto_connect_all(self) -> None:
        """启动时自动连接所有已配置的渠道"""
        for name, channel in self._channels.items():
            if hasattr(channel, 'auto_connect'):
                try:
                    await channel.auto_connect()
                except Exception as e:
                    logger.warning(f"自动连接 {name} 失败: {e}")


# 全局单例
_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """获取通知管理器实例"""
    global _manager
    if _manager is None:
        _manager = NotificationManager()
        _init_channels(_manager)
    return _manager


def _init_channels(manager: NotificationManager) -> None:
    """初始化并注册所有通知渠道"""
    from .telegram.channel import TelegramChannel
    manager.register(TelegramChannel())
    # 后续扩展：manager.register(WechatChannel())
