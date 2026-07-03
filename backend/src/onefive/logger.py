"""
日志模块 - 统一管理应用日志

功能：
- 控制台输出（带颜色）
- 文件输出（自动轮转）
- 模块名称映射（简短易读）
- 支持日志级别配置
- 路径由 paths 模块统一管理，自动适配飞牛环境

使用方式：
    from onefive.logger import get_logger
    logger = get_logger(__name__)
    logger.info("信息")

新增模块时，在 MODULE_NAMES 中注册简短名称即可：
    MODULE_NAMES["onefive.services.xxx"] = "Xxx"
"""
import os
import logging
import logging.handlers

from .paths import LOG_DIR, LOG_FILE

# ==================== 模块名称映射 ====================
MODULE_NAMES = {
    "onefive": "应用",
    "onefive.main": "应用",
    "onefive.logger": "日志",
    "onefive.api.auth": "认证",
    "onefive.api.config": "配置",
    "onefive.api.files": "文件",
    "onefive.api.logs": "日志",
    "onefive.api.organize": "整理",
    "onefive.api.share": "分享",
    "onefive.services.auth_service": "认证",
    "onefive.services.config_service": "配置",
    "onefive.services.file_service": "文件",
    "onefive.services.token_service": "令牌",
    "onefive.services.tmdb_service": "TMDB",
    "onefive.services.file_info_service": "解析",
    "onefive.services.classify_service": "分类",
    "onefive.services.rename_service": "重命名",
    "onefive.services.organize_service": "整理",
    "onefive.services.share_service": "分享",
    "onefive.services.share_organize_service": "分享整理",
    "onefive.services.strm_service": "STRM",
    "onefive.api.strm": "STRM",
    "onefive.api.notification": "通知",
    "onefive.api.direct_link": "直链",
    "onefive.services.direct_link_service": "直链",
    "onefive.notification": "通知",
    "onefive.notification.manager": "通知",
    "onefive.notification.telegram.channel": "Telegram",
    "onefive.db.database": "数据库",
}


# 默认日志配置
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5MB
DEFAULT_BACKUP_COUNT = 3


def get_log_level() -> str:
    """获取日志级别，优先使用环境变量 ONEFIVE_LOG_LEVEL"""
    return os.environ.get("ONEFIVE_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()


def _resolve_name(module_name: str) -> str:
    """将模块路径转换为简短名称"""
    if module_name in MODULE_NAMES:
        return MODULE_NAMES[module_name]
    return module_name.rsplit(".", 1)[-1]


class _ModuleNameFilter(logging.Filter):
    """日志过滤器 - 将 logger 名称替换为 MODULE_NAMES 中的简短名称"""

    def filter(self, record):
        record.name = _resolve_name(record.name)
        return True


def setup_logging():
    """初始化日志配置，在应用启动时调用一次"""
    log_level = get_log_level()
    numeric_level = getattr(logging, log_level, logging.INFO)

    # 名称替换过滤器（所有 handler 共用）
    name_filter = _ModuleNameFilter()

    # 根日志器（onefive 的所有子 logger 都会传播到这里）
    root_logger = logging.getLogger("onefive")
    root_logger.setLevel(numeric_level)

    # 清除已有的处理器（避免重复添加）
    root_logger.handlers.clear()

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.addFilter(name_filter)
    console_formatter = logging.Formatter(
        DEFAULT_LOG_FORMAT,
        datefmt=DEFAULT_LOG_DATE_FORMAT
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器（轮转）
    file_handler = logging.handlers.RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=DEFAULT_MAX_BYTES,
        backupCount=DEFAULT_BACKUP_COUNT,
        encoding="utf-8"
    )
    file_handler.setLevel(numeric_level)
    file_handler.addFilter(name_filter)
    file_formatter = logging.Formatter(
        DEFAULT_LOG_FORMAT,
        datefmt=DEFAULT_LOG_DATE_FORMAT
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 让 onefive 下所有子 logger 的日志都传播到根 logger 处理
    logging.getLogger().setLevel(numeric_level)

    root_logger.info(f"日志初始化完成，级别: {log_level}，目录: {LOG_DIR}")


def get_logger(name: str) -> logging.Logger:
    """获取日志器

    传入 __name__（如 onefive.services.auth_service），
    内部通过 MODULE_NAMES 映射为简短名称（如 Auth）显示在日志中。

    Args:
        name: 日志器名称，通常使用 __name__

    Returns:
        日志器实例
    """
    # 确保 logger 在 onefive 层级下
    if not name.startswith("onefive"):
        name = f"onefive.{name}"
    return logging.getLogger(name)
