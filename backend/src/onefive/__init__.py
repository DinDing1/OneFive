# 壹伍（OneFive）- 115 网盘管理应用
from pathlib import Path


def _read_version() -> str:
    """读取项目根目录的 VERSION 文件，返回版本号字符串。

    为避免启动阶段因版本文件编码异常而崩溃，这里按原始字节读取，
    依次尝试 UTF-8（兼容 BOM）、UTF-16、UTF-8 三种解码方式；
    全部失败或文件不存在时，降级返回 "0.0.0"。
    """
    # VERSION 文件位于 backend/src/onefive/__init__.py 向上回溯 4 级的项目根目录
    version_file = Path(__file__).parent.parent.parent.parent / "VERSION"
    if not version_file.exists():
        return "0.0.0"

    raw = version_file.read_bytes()
    # utf-8-sig 可兼容带 BOM 的 UTF-8；utf-16 可自动识别 LE/BE 的 BOM
    for encoding in ("utf-8-sig", "utf-16", "utf-8"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return "0.0.0"


__version__ = _read_version()
