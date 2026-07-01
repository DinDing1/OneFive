"""
壹伍（OneFive）启动入口 - 专门用于 Nuitka 打包

为什么要这个文件：
- Nuitka --onefile 模式下，入口文件被当作顶层 __main__ 执行
- 此时 __package__ 为空，onefive/main.py 中的相对导入（from .xxx import）会失败
- 通过这个独立入口脚本，从外部用绝对导入调用 onefive.main
- Python 导入 onefive.main 时会正确设置 __package__ = "onefive"
- main.py 中的所有相对导入就能正常工作

执行流程：
1. Nuitka 编译 run.py 为 onefive-server 二进制
2. 二进制启动时执行 run.py 的 __main__ 块
3. run.py 修复 HOME 环境变量（飞牛环境下 onefive 用户可能没有主目录）
4. run.py 调用 onefive.main.start_server()
5. start_server() 根据 ONEFIVE_SOCKET 环境变量选择 Unix Socket 或 HTTP 模式
"""
import os
import time

# ==================== 设置时区为北京时间 ====================
# 必须在任何 import 之前执行，确保 datetime.now() 和 SQLite 的 localtime 都使用北京时区
os.environ['TZ'] = 'Asia/Shanghai'
try:
    time.tzset()
except AttributeError:
    pass  # Windows 不支持 time.tzset()，依赖系统时区设置

# ==================== 修复 HOME 环境变量 ====================
# 飞牛 fnOS 下，onefive 用户可能没有 /home/onefive 目录，
# 导致 p115client 等第三方库在模块级执行以下代码时崩溃：
#   Path("~/.p115client.cache.d").expanduser().mkdir(exist_ok=True)
# expanduser("~") 依赖 HOME 环境变量，如果 HOME 指向不存在的目录，
# mkdir 会因父目录不存在而抛出 FileNotFoundError。
#
# 修复策略：
# - 飞牛环境（有 TRIM_PKGVAR）：把 HOME 重定向到 TRIM_PKGVAR（一定存在且可写）
# - 本地开发：不做任何修改，保持原 HOME
#
# 注意：必须在 import onefive 之前执行，因为 import 链会触发 p115client 的模块级代码。
_TRIM_PKGVAR = os.environ.get("TRIM_PKGVAR")
if _TRIM_PKGVAR:
    os.environ["HOME"] = _TRIM_PKGVAR

from onefive.main import start_server

if __name__ == "__main__":
    start_server()
