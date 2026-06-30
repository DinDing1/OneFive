"""
路径管理模块 - 统一管理所有文件路径

飞牛 fnOS 环境变量：
- TRIM_PKGVAR  → 数据目录（数据库、日志）

本地开发环境：
- 所有数据存放在项目根目录的 data/ 下
"""
import os
from pathlib import Path

# ==================== 飞牛环境变量 ====================
TRIM_PKGVAR = os.environ.get("TRIM_PKGVAR")   # 数据目录

# ==================== 项目根目录 ====================
# backend/src/onefive/paths.py → 向上 4 级 = d:\OneFive
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def _data_dir(sub: str) -> Path:
    """获取数据子目录路径

    飞牛环境：TRIM_PKGVAR/{sub}
    本地开发：{PROJECT_ROOT}/data/{sub}
    """
    if TRIM_PKGVAR:
        p = Path(TRIM_PKGVAR) / sub
    else:
        p = PROJECT_ROOT / "data" / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


# ==================== 数据库 ====================
DB_PATH = _data_dir("db") / "onefive.db"

# ==================== 日志 ====================
LOG_DIR = _data_dir("logs")
LOG_FILE = LOG_DIR / "onefive.log"

# ==================== 服务端口 ====================
SERVICE_PORT = int(os.environ.get("TRIM_SERVICE_PORT", os.environ.get("ONEFIVE_PORT", "11580")))
