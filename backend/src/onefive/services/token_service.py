"""
Open API Token 管理服务

职责：
- 管理 115 开放平台的 access_token 和 refresh_token
- 通过 Cookie 模拟扫码自动获取 token
- token 过期自动刷新（提前 5 分钟）

Token 获取流程（Cookie 模拟扫码）：
1. 调用 /open/authDeviceCode 获取 uid + code_verifier
2. Cookie 请求 /api/2.0/prompt.php?uid=xxx 自动扫描
3. Cookie 请求 /api/2.0/slogin.php?key=xxx&uid=xxx 确认
4. 调用 /open/deviceCodeToToken 换取 access_token + refresh_token

存储（setting 表）：
- open_api_enabled: 是否启用 Open API（"1" / "0"）
- open_app_id: 选择的 AppID
- open_access_token: access_token
- open_refresh_token: refresh_token
- open_token_expire: 过期时间戳（秒）
"""
import time
import hashlib
import base64
import os
from typing import Optional, Dict, Any

import requests

from .config_service import get_config_service
from ..logger import get_logger

logger = get_logger(__name__)

# 115 QR Code API 基础地址
QRCODEAPI_BASE = "https://qrcodeapi.115.com"

# 通用请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
}

# 提前刷新时间（秒）
REFRESH_AHEAD = 300

# 默认 token 有效期（秒），API 未返回 expires_in 时使用
DEFAULT_TOKEN_EXPIRES_IN = 7200


class TokenService:
    """Open API Token 管理服务"""

    def __init__(self):
        self.config_service = get_config_service()

    # ==================== 配置读写 ====================

    def is_open_api_enabled(self) -> bool:
        """检查 Open API 是否启用"""
        return self.config_service.get("open_api_enabled") == "1"

    def get_app_id(self) -> Optional[str]:
        """获取配置的 AppID"""
        return self.config_service.get("open_app_id")

    def set_open_api_enabled(self, enabled: bool):
        """设置 Open API 开关"""
        self.config_service.set("open_api_enabled", "1" if enabled else "0", "是否启用Open API")

    def set_app_id(self, app_id: str):
        """设置 AppID"""
        self.config_service.set("open_app_id", app_id, "115开放平台AppID")

    # ==================== Token 获取 ====================

    def get_access_token(self) -> Optional[str]:
        """获取有效的 access_token

        如果 token 不存在或即将过期，自动刷新。
        如果没有 token 且 Open API 已启用，自动通过 Cookie 获取。

        Returns:
            access_token 字符串，获取失败返回 None
        """
        if not self.is_open_api_enabled():
            return None

        # 检查现有 token
        token = self.config_service.get("open_access_token")
        expire_str = self.config_service.get("open_token_expire")

        if token and expire_str:
            try:
                expire_ts = int(expire_str)
                # token 有效且未到提前刷新时间，直接返回
                if time.time() < expire_ts - REFRESH_AHEAD:
                    return token
                # 即将过期或已过期，提前刷新
                logger.info("Token 即将过期，尝试刷新")
                if self._refresh_token():
                    return self.config_service.get("open_access_token")
            except (ValueError, TypeError):
                pass

        # 没有 token 或刷新失败，尝试通过 Cookie 获取
        return self._authorize_by_cookie()

    def _refresh_token(self) -> bool:
        """用 refresh_token 刷新 access_token

        Returns:
            是否刷新成功
        """
        refresh_token = self.config_service.get("open_refresh_token")
        if not refresh_token:
            logger.info("没有 refresh_token，无法刷新")
            return False

        try:
            response = requests.post(
                f"{QRCODEAPI_BASE}/open/refreshToken",
                data={"refresh_token": refresh_token},
                headers=HEADERS,
                timeout=30,
            )

            if not response.ok:
                logger.warning(f"刷新 token 请求失败: {response.status_code}")
                return False

            result = response.json()
            if result.get("code"):
                logger.warning(f"刷新 token 失败: {result.get('error') or result.get('msg')}")
                return False

            data = result.get("data") or result
            self._save_token(
                data["access_token"],
                data["refresh_token"],
                data.get("expires_in", DEFAULT_TOKEN_EXPIRES_IN),
            )
            logger.info("刷新 access_token 成功")
            return True

        except Exception as e:
            logger.error(f"刷新 token 异常: {e}")
            return False

    def _authorize_by_cookie(self) -> Optional[str]:
        """通过 Cookie 模拟扫码获取 access_token

        流程：
        1. 获取二维码 uid + code_verifier
        2. Cookie 自动扫描
        3. Cookie 确认
        4. 换取 access_token

        Returns:
            access_token 字符串，失败返回 None
        """
        app_id = self.get_app_id()
        if not app_id:
            logger.warning("未配置 AppID，无法获取 Open API token")
            return None

        # 从数据库获取 Cookie
        cookie = self.config_service.get("cookie115")
        if not cookie:
            logger.warning("未登录，无法通过 Cookie 获取 token")
            return None

        try:
            # 步骤1：本地生成 code_verifier，调用 API 获取二维码 uid
            code_verifier = self._generate_code_verifier()
            code_challenge = self._generate_code_challenge(code_verifier)

            resp = requests.post(
                f"{QRCODEAPI_BASE}/open/authDeviceCode",
                data={
                    "client_id": app_id,
                    "code_challenge": code_challenge,
                    "code_challenge_method": "md5",
                },
                headers=HEADERS,
                timeout=30,
            )

            if not resp.ok:
                logger.error(f"获取二维码 token 失败: {resp.status_code}")
                return None

            result = resp.json()
            if result.get("code"):
                logger.error(f"获取二维码 token 失败: {result.get('error') or result.get('msg')}")
                return None

            data = result.get("data") or result
            uid = data["uid"]

            # 步骤2：Cookie 自动扫描
            scan_resp = requests.get(
                f"{QRCODEAPI_BASE}/api/2.0/prompt.php",
                params={"uid": uid},
                headers={"User-Agent": HEADERS["User-Agent"], "Cookie": cookie},
                timeout=15,
            )

            if not scan_resp.ok:
                logger.error(f"自动扫描请求失败: {scan_resp.status_code}")
                return None

            scan_result = scan_resp.json()
            if not (scan_result.get("state") == 1 and scan_result.get("data")):
                logger.error(f"自动扫描失败: {scan_result.get('error', '未知错误')}")
                return None

            # 步骤3：Cookie 确认
            confirm_resp = requests.get(
                f"{QRCODEAPI_BASE}/api/2.0/slogin.php",
                params={"key": uid, "uid": uid, "client": "0"},
                headers={"User-Agent": HEADERS["User-Agent"], "Cookie": cookie},
                timeout=15,
            )

            if not confirm_resp.ok:
                logger.error(f"确认扫描请求失败: {confirm_resp.status_code}")
                return None

            confirm_result = confirm_resp.json()
            if not (confirm_result.get("state") is True or confirm_result.get("state") == 1):
                logger.error(f"确认扫描失败: {confirm_result.get('error') or confirm_result.get('msg')}")
                return None

            # 步骤4：换取 access_token
            token_resp = requests.post(
                f"{QRCODEAPI_BASE}/open/deviceCodeToToken",
                data={"uid": uid, "code_verifier": code_verifier},
                headers=HEADERS,
                timeout=30,
            )

            if not token_resp.ok:
                logger.error(f"换取 token 请求失败: {token_resp.status_code}")
                return None

            token_result = token_resp.json()
            if token_result.get("code"):
                logger.error(f"换取 token 失败: {token_result.get('error') or token_result.get('msg')}")
                return None

            token_data = token_result.get("data") or token_result
            access_token = token_data["access_token"]
            refresh_token = token_data["refresh_token"]
            expires_in = token_data.get("expires_in", DEFAULT_TOKEN_EXPIRES_IN)

            self._save_token(access_token, refresh_token, expires_in)
            logger.info("通过 Cookie 自动获取 Open API token 成功")
            return access_token

        except Exception as e:
            logger.error(f"通过 Cookie 获取 token 异常: {e}")
            return None

    # ==================== 内部工具 ====================

    def _save_token(self, access_token: str, refresh_token: str, expires_in: int):
        """保存 token 到数据库"""
        expire_ts = int(time.time()) + expires_in
        self.config_service.set("open_access_token", access_token, "Open API access_token")
        self.config_service.set("open_refresh_token", refresh_token, "Open API refresh_token")
        self.config_service.set("open_token_expire", str(expire_ts), "Open API token 过期时间戳")

    @staticmethod
    def _generate_code_verifier() -> str:
        """生成 code_verifier（43-128位随机字符串）"""
        return base64.urlsafe_b64encode(os.urandom(48)).decode().replace("=", "")

    @staticmethod
    def _generate_code_challenge(code_verifier: str) -> str:
        """生成 code_challenge（base64(md5(code_verifier))）"""
        md5_hash = hashlib.md5(code_verifier.encode()).digest()
        return base64.b64encode(md5_hash).decode()


# 全局单例
_token_service: Optional[TokenService] = None


def get_token_service() -> TokenService:
    """获取 Token 服务实例"""
    global _token_service
    if _token_service is None:
        _token_service = TokenService()
    return _token_service
