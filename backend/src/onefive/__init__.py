# 壹伍（OneFive）- 115 网盘管理应用
from pathlib import Path

# 从项目根目录的 VERSION 文件读取版本号
_version_file = Path(__file__).parent.parent.parent.parent / "VERSION"
__version__ = _version_file.read_text(encoding="utf-8").strip() if _version_file.exists() else "0.0.0"
