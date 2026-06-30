"""
通知模块

模块化架构，支持多渠道通知。
"""
from .manager import get_notification_manager
from .base import NotificationChannel

__all__ = ["get_notification_manager", "NotificationChannel"]
