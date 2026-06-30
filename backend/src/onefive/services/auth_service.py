"""
认证服务 - 处理115网盘的登录认证

扫码登录流程：
1. 调用 passportapi.115.com/api/1.0/{app}/1.0/token/ 获取二维码 token
2. 前端轮询 qrcodeapi.115.com/get/status/ 检查扫码状态
3. 当 data.status === 2（已确认）时，调用 login/qrcode/ 接口获取 cookies
4. 将 cookies 持久化到数据库，重启后自动登录
5. 用户信息通过 P115Client.user_my() 实时获取
"""
import time
import uuid
import base64
import io
from typing import Optional, Dict, Any

import qrcode
import requests

from p115client import P115Client

from ..services.config_service import get_config_service
from ..logger import get_logger

logger = get_logger(__name__)

# 支持的登录设备列表
AVAILABLE_DEVICES = {
    "web": "网页端",
    "ios": "苹果端",
    "115ios": "115苹果端",
    "android": "安卓端",
    "115android": "115安卓端",
    "115ipad": "苹果平板端",
    "tv": "安卓电视端",
    "qandroid": "115管理安卓端",
    "wechatmini": "微信小程序端",
    "alipaymini": "支付宝小程序",
    "harmony": "鸿蒙端",
}

# 115 API 基础地址
PASSPORT_API_BASE = "https://passportapi.115.com"
QRCODE_API_BASE = "https://qrcodeapi.115.com"

# 通用请求头
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://115.com/",
    "Origin": "https://115.com",
}


class AuthService:
    """认证服务类"""

    def __init__(self):
        self.config_service = get_config_service()
        # 内存中的登录会话（扫码流程中间状态）
        self._login_sessions: Dict[str, Dict[str, Any]] = {}

    # ==================== Cookie 持久化 ====================

    def get_cookies(self) -> Optional[str]:
        """获取已保存的 cookies（从数据库读取）"""
        return self.config_service.get("cookie115")

    def save_cookies(self, cookies: str) -> bool:
        """保存 cookies 到数据库"""
        if not cookies:
            logger.warning("尝试保存空的 cookies，已跳过")
            return False
        try:
            self.config_service.set("cookie115", cookies, "115云盘cookie")
            logger.info("保存 cookies 成功")
            return True
        except Exception as e:
            logger.error(f"保存 cookies 失败: {e}")
            return False

    # ==================== 登录状态检查 ====================

    def is_logged_in(self) -> bool:
        """检查是否已登录（cookies 是否存在且非空）"""
        cookies = self.get_cookies()
        return cookies is not None and len(cookies) > 0

    def get_login_status(self) -> Dict[str, Any]:
        """获取登录状态，通过 P115Client.user_my() 获取用户信息

        VIP 类型判断逻辑：
        - vip=0 → 非VIP
        - vip=1, forever=0 → 普通VIP（有到期时间）
        - vip=1, forever=1 → 终身VIP
        """
        cookies = self.get_cookies()
        if not cookies:
            return {
                "is_logged_in": False, "user_id": None, "user_name": None,
                "vip": 0, "vip_type": "none", "face": "", "message": "未登录"
            }

        # 用 p115client 获取用户信息
        user_name = ""
        user_id = self._extract_user_id(cookies)
        vip = 0
        vip_type = "none"  # none / vip / forever
        face = ""
        try:
            client = P115Client(cookies)
            user_info = client.user_my()
            if user_info and user_info.get("state"):
                data = user_info.get("data", {})
                user_name = data.get("user_name", "")
                vip = data.get("vip", 0)
                face = data.get("face", "")
                forever = data.get("forever", 0)
                if not user_id:
                    user_id = str(data.get("user_id", ""))
                # 判断 VIP 类型
                if vip == 1:
                    vip_type = "forever" if forever == 1 else "vip"
        except Exception as e:
            logger.warning(f"获取用户信息失败: {e}")

        return {
            "is_logged_in": True,
            "user_id": user_id,
            "user_name": user_name,
            "vip": vip,
            "vip_type": vip_type,
            "face": face,
            "message": "已登录"
        }

    def _extract_user_id(self, cookies: str) -> Optional[str]:
        """从 cookies 中提取用户 ID"""
        try:
            for item in cookies.split(";"):
                item = item.strip()
                if item.startswith("UID="):
                    return item[4:]
        except Exception:
            pass
        return None

    # ==================== 扫码登录流程 ====================

    async def start_qr_login(self, device: str = "web") -> Dict[str, Any]:
        """开始扫码登录流程

        步骤1：调用 passportapi.115.com 获取二维码 token
        返回二维码图片和 session_id 给前端
        """
        try:
            if device not in AVAILABLE_DEVICES:
                return {"success": False, "message": f"不支持的设备类型: {device}"}

            logger.info(f"开始扫码登录，设备: {device}")

            # 调用 115 passport API 获取二维码 token
            token_url = f"{PASSPORT_API_BASE}/api/1.0/{device}/1.0/token/"
            response = requests.get(token_url, headers=COMMON_HEADERS, timeout=30)

            if not response.ok:
                logger.error(f"获取二维码token请求失败，HTTP状态: {response.status_code}")
                return {"success": False, "message": f"获取二维码token失败，状态码: {response.status_code}"}

            token_result = response.json()

            if token_result.get("state") != 1 or not token_result.get("data"):
                error_msg = token_result.get("error") or token_result.get("msg") or "获取二维码token失败"
                logger.error(f"获取二维码token失败: {error_msg}")
                return {"success": False, "message": error_msg}

            data = token_result["data"]
            uid = data.get("uid")
            sign = data.get("sign")
            token_time = data.get("time")
            scan_url = data.get("qrcode", f"https://115.com/scan/dg-{uid}")

            if not uid:
                logger.error("二维码数据中缺少 uid")
                return {"success": False, "message": "二维码数据异常"}

            # 生成二维码图片
            qr = qrcode.QRCode(version=1, box_size=8, border=2)
            qr.add_data(scan_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            qr_base64 = base64.b64encode(buffer.getvalue()).decode()

            # 生成会话 ID 并存储关键信息
            session_id = str(uuid.uuid4())
            self._login_sessions[session_id] = {
                "uid": uid,
                "sign": sign,
                "time": token_time,
                "device": device,
                "status": "pending",
                "created_at": time.time(),
                "cookies": None,
            }

            logger.info(f"二维码生成成功，session_id: {session_id}")

            return {
                "success": True,
                "session_id": session_id,
                "qr_code_url": f"data:image/png;base64,{qr_base64}",
                "device": device,
                "device_name": AVAILABLE_DEVICES[device],
                "message": f"请使用115{AVAILABLE_DEVICES[device]}扫描二维码登录"
            }

        except requests.Timeout:
            logger.error("获取二维码超时")
            return {"success": False, "message": "获取二维码超时，请重试"}
        except Exception as e:
            logger.error(f"获取二维码异常: {e}")
            return {"success": False, "message": f"启动扫码登录失败: {str(e)}"}

    async def check_login_status(self, session_id: str) -> Dict[str, Any]:
        """检查扫码登录状态

        步骤2：轮询 qrcodeapi.115.com/get/status/ 检查扫码状态
        步骤3：当 status=2（已确认）时，调用 login/qrcode/ 获取 cookies
        """
        if session_id not in self._login_sessions:
            logger.warning(f"无效的会话ID: {session_id}")
            return {"status": "invalid", "message": "无效的会话ID"}

        session = self._login_sessions[session_id]

        # 检查会话是否过期（5分钟）
        if time.time() - session["created_at"] > 300:
            del self._login_sessions[session_id]
            logger.info(f"会话已过期: {session_id}")
            return {"status": "expired", "message": "登录会话已过期，请重新扫码"}

        # 如果已经确认且获取了 cookies，直接返回
        if session["status"] == "confirmed" and session["cookies"]:
            return {"status": "confirmed", "cookies": session["cookies"], "message": "登录成功"}

        try:
            uid = session["uid"]
            sign = session["sign"]
            token_time = session["time"]
            device = session["device"]

            # 调用 qrcodeapi 检查扫码状态
            status_url = f"{QRCODE_API_BASE}/get/status/"
            status_params = {
                "uid": uid,
                "time": token_time,
                "sign": sign,
            }
            status_headers = {
                "User-Agent": COMMON_HEADERS["User-Agent"],
                "Referer": "https://115.com/",
            }

            response = requests.get(
                status_url,
                params=status_params,
                headers=status_headers,
                timeout=5
            )

            if not response.ok:
                logger.warning(f"检查状态请求失败，HTTP状态: {response.status_code}")
                return {"status": "pending", "message": "等待扫码中..."}

            status_result = response.json()

            # 解析状态
            state = status_result.get('state', 0)
            data = status_result.get('data', {})
            login_status = data.get('status', 0)

            # data.status: 2 = 已确认登录 → 获取 cookies
            if login_status == 2:
                logger.info("用户已确认登录，开始获取 cookies...")

                # 关键步骤：调用 login/qrcode/ 接口获取 cookies
                cookies = self._fetch_login_cookies(uid=uid, device=device)

                if cookies:
                    self.save_cookies(cookies)
                    session["status"] = "confirmed"
                    session["cookies"] = cookies
                    logger.info("登录成功，cookies 已保存")
                    return {"status": "confirmed", "cookies": cookies, "message": "登录成功"}
                else:
                    logger.error("获取 cookies 失败")
                    session["status"] = "confirmed"
                    session["cookies"] = None
                    return {"status": "error", "message": "获取 cookies 失败，请重试"}

            # data.status: 1 = 已扫描等待确认
            elif login_status == 1:
                session["status"] = "scanned"
                return {"status": "scanned", "message": "已扫码，请在手机上确认"}

            # data.status: 0 = 等待扫码
            return {"status": "pending", "message": "等待扫码中..."}

        except requests.Timeout:
            logger.warning("检查登录状态超时")
            return {"status": "pending", "message": "等待扫码中..."}
        except Exception as e:
            logger.error(f"检查状态异常: {e}")
            return {"status": "error", "message": f"检查登录状态失败: {str(e)}"}

    def _fetch_login_cookies(self, uid: str, device: str) -> Optional[str]:
        """扫码确认后，调用 login/qrcode/ 接口获取 cookies

        POST https://passportapi.115.com/app/1.0/{app}/1.0/login/qrcode/
        请求体: app={app}&account={uid}
        响应中的 data.cookie 包含 UID、CID、SEID、KID
        """
        try:
            login_url = f"{PASSPORT_API_BASE}/app/1.0/{device}/1.0/login/qrcode/"
            form_data = {
                "app": device,
                "account": uid,
            }
            login_headers = {
                **COMMON_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded",
            }

            response = requests.post(
                login_url,
                data=form_data,
                headers=login_headers,
                timeout=30
            )

            if not response.ok:
                logger.error(f"获取登录cookies请求失败，HTTP状态: {response.status_code}")
                return None

            result = response.json()

            if result.get("state") != 1:
                error_msg = result.get("error") or result.get("msg") or "获取cookies失败"
                logger.error(f"获取登录cookies失败: {error_msg}")
                return None

            # 从响应中提取 cookies
            data = result.get("data", {})
            cookie_obj = data.get("cookie", {})

            cookie_parts = []
            if cookie_obj.get("UID"):
                cookie_parts.append(f"UID={cookie_obj['UID']}")
            if cookie_obj.get("CID"):
                cookie_parts.append(f"CID={cookie_obj['CID']}")
            if cookie_obj.get("SEID"):
                cookie_parts.append(f"SEID={cookie_obj['SEID']}")
            if cookie_obj.get("KID"):
                cookie_parts.append(f"KID={cookie_obj['KID']}")

            cookie_str = "; ".join(cookie_parts)

            if cookie_str:
                logger.info(f"获取 cookies 成功，用户: {data.get('user_name', '未知')}")
                return cookie_str
            else:
                logger.error("cookies 为空")
                return None

        except requests.Timeout:
            logger.error("获取登录cookies超时")
            return None
        except Exception as e:
            logger.error(f"获取登录cookies异常: {e}")
            return None

    # ==================== 登出 ====================

    def logout(self) -> bool:
        """登出：删除数据库中的 cookie 记录"""
        try:
            self.config_service.delete("cookie115")
            logger.info("登出成功")
            return True
        except Exception as e:
            logger.error(f"登出失败: {e}")
            return False

    # ==================== 设备列表 ====================

    def get_available_devices(self) -> Dict[str, str]:
        """获取可用设备列表"""
        return AVAILABLE_DEVICES.copy()


# 全局认证服务实例
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """获取认证服务实例"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
