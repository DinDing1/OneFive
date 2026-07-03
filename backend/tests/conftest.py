"""pytest 共享配置和 fixture

职责：
1. 将 src 目录加入 Python 路径，使 onefive 包可被测试文件导入
2. 提供可复用的 mock fixture，隔离数据库等外部依赖

设计说明：
- rename_service / classify_service 在函数内部调用 get_config_service()，
  该函数会触发数据库连接。为隔离数据库，需用 monkeypatch 替换模块内
  的 get_config_service 引用（注意：patch 目标是使用方模块，而非定义方模块）。
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

# 将 src 目录加入 Python 路径，使 onefive 包可被导入
BACKEND_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT / "src"))

import pytest


@pytest.fixture
def mock_config_service():
    """提供 mock 的 config_service，用于隔离数据库依赖

    默认 get() 返回 None，模拟"配置未设置"的场景，
    使被测服务回退到内置默认值（如默认模板、默认分类策略）。

    使用方式：
        def test_xxx(mock_config_service):
            mock_config_service.get.return_value = "自定义模板"
            # 此时被测服务调用 get_config_service().get(...) 会返回上述值
    """
    mock = MagicMock()
    mock.get.return_value = None
    return mock


@pytest.fixture
def patch_rename_config_service(monkeypatch, mock_config_service):
    """patch rename_service 中的 get_config_service 引用

    rename_service._generate_path 在函数内部调用 get_config_service()，
    该函数来源于 `from .config_service import get_config_service`，
    因此 patch 目标是 onefive.services.rename_service.get_config_service。

    Returns:
        mock_config_service 对象，可在测试中配置返回值
    """
    monkeypatch.setattr(
        "onefive.services.rename_service.get_config_service",
        lambda: mock_config_service,
    )
    return mock_config_service


@pytest.fixture
def patch_classify_config_service(monkeypatch, mock_config_service):
    """patch classify_service 中的 get_config_service 引用

    classify_service._get_custom_strategy 会调用 get_config_service()，
    patch 后默认返回 None，使 classify_media 使用 DEFAULT_STRATEGY。

    Returns:
        mock_config_service 对象，可在测试中配置返回值
    """
    monkeypatch.setattr(
        "onefive.services.classify_service.get_config_service",
        lambda: mock_config_service,
    )
    return mock_config_service
