"""自定义异常类

异常层级：
- AppError：应用级业务错误基类（前端可展示给用户）
  - ConfigError：配置相关错误（路径未配置、参数非法等）
  - PathNotAuthorizedError：路径不在授权目录内
  - NotLoggedInError：未登录或登录过期
- 系统异常（Exception 子类）：不直接展示给用户，走全局异常处理器
"""


class AppError(Exception):
    """应用级业务错误基类

    所有前端需要展示给用户的业务错误都应继承此类。
    全局异常处理器会捕获 AppError 并返回友好的 ApiResponse。
    """
    def __init__(self, message: str, code: int = -1):
        self.message = message
        self.code = code
        super().__init__(message)


class ConfigError(AppError):
    """配置相关错误（路径未配置、参数非法、配置缺失等）

    前端可据此引导用户去设置页修改配置。
    """
    def __init__(self, message: str):
        super().__init__(message, code=-1)


class PathNotAuthorizedError(AppError):
    """路径不在飞牛授权目录内

    前端可据此提示用户去飞牛应用设置中授权目录。
    """
    def __init__(self, path: str, path_type: str = ""):
        prefix = f"{path_type}路径" if path_type else "路径"
        message = f"{prefix}不在飞牛授权目录内: {path}，请在飞牛应用设置中授权对应目录"
        super().__init__(message, code=-1)
        self.path = path


class NotLoggedInError(AppError):
    """未登录或登录过期

    前端收到 code=401 时应跳转登录页。
    """
    def __init__(self, message: str = "未登录或登录已过期，请重新登录"):
        super().__init__(message, code=401)
