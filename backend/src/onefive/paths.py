"""
路径管理模块 - 统一管理所有文件路径

飞牛 fnOS 环境变量：
- TRIM_PKGVAR  → 数据目录（数据库、日志、运行时配置）

本地开发环境：
- 所有数据存放在项目根目录的 data/ 下
"""
import os
from pathlib import Path
from typing import List

# ==================== 飞牛环境变量 ====================
TRIM_PKGVAR = os.environ.get("TRIM_PKGVAR")   # 数据目录

# ==================== 项目根目录 ====================
# backend/src/onefive/paths.py → 向上 4 级 = d:\OneFive
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# ==================== 数据根目录 ====================
# 飞牛环境：TRIM_PKGVAR
# 本地开发：{PROJECT_ROOT}/data
DATA_DIR = Path(TRIM_PKGVAR) if TRIM_PKGVAR else PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _data_dir(sub: str) -> Path:
    """获取数据子目录路径

    飞牛环境：TRIM_PKGVAR/{sub}
    本地开发：{PROJECT_ROOT}/data/{sub}
    """
    p = DATA_DIR / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


# ==================== 数据库 ====================
DB_PATH = _data_dir("db") / "onefive.db"

# ==================== 日志 ====================
LOG_DIR = _data_dir("logs")
LOG_FILE = LOG_DIR / "onefive.log"

# ==================== 飞牛授权路径 ====================
# 由 onefive/cmd/config_callback 写入，用于后端读取 TRIM_DATA_ACCESSIBLE_PATHS。
# 本地开发时可以手动创建 data/accessible_paths.env 模拟飞牛授权目录。
ACCESSIBLE_PATHS_FILE = DATA_DIR / "accessible_paths.env"


def split_accessible_paths(raw: str) -> List[str]:
    """解析飞牛授权路径列表

    飞牛正式环境用冒号分隔多个 Linux 路径，例如：
        /vol1/media:/vol2/downloads

    本地 Windows 测试时，路径可能是：
        D:\\OneFive\\strm-test
    这里不能直接按冒号拆，否则会被错误拆成 "D" 和 "\\OneFive\\strm-test"。

    本地如需配置多个 Windows 路径，建议每行一个路径，或使用英文分号分隔。
    """
    if not raw:
        return []

    items: List[str] = []
    # 先按行拆，方便本地 accessible_paths.env 一行一个路径。
    for line in raw.replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue

        # Windows 本地测试：D:\xxx 或 D:/xxx 是单个路径，不能按冒号拆盘符。
        is_windows_drive_path = len(line) >= 3 and line[1] == ":" and line[2] in ("\\", "/")
        if is_windows_drive_path:
            parts = line.split(";") if ";" in line else [line]
        else:
            # 飞牛/Linux 正式环境：冒号分隔多个路径；本地也兼容分号。
            separator = ";" if ";" in line else ":"
            parts = line.split(separator)

        for part in parts:
            part = part.strip()
            if part:
                items.append(part)

    # 去重但保持顺序，避免前端重复显示。
    result: List[str] = []
    seen = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


# ==================== 服务端口 ====================
SERVICE_PORT = int(os.environ.get("TRIM_SERVICE_PORT", os.environ.get("ONEFIVE_PORT", "11580")))
