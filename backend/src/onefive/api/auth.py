"""
认证 API 路由 - 处理登录相关的接口

扫码登录流程：
1. POST /api/auth/qrcode - 获取二维码
2. GET /api/auth/qrcode/check/{session_id} - 轮询检查状态（确认后自动获取并保存 cookies）
3. GET /api/auth/status - 检查登录状态（重启后从数据库读取 cookies）
"""
from fastapi import APIRouter
from pydantic import BaseModel
from ..models.schemas import ApiResponse, LoginStatus, LoginCheckResponse
from ..services.auth_service import get_auth_service
from ..logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["认证"])


class QRLoginRequest(BaseModel):
    """扫码登录请求"""
    device: str = "web"


class CookieLoginRequest(BaseModel):
    """手动 cookies 登录请求"""
    cookies: str


@router.get("/status", response_model=LoginStatus, summary="获取登录状态")
async def get_login_status():
    """获取当前登录状态"""
    auth_service = get_auth_service()
    status = auth_service.get_login_status()
    return LoginStatus(**status)


@router.get("/devices", summary="获取可用设备列表")
async def get_devices():
    """获取可用的登录设备列表"""
    auth_service = get_auth_service()
    devices = auth_service.get_available_devices()
    return ApiResponse(
        code=0,
        message="success",
        data={"devices": devices}
    )


@router.post("/qrcode", response_model=ApiResponse, summary="获取扫码登录二维码")
async def get_qrcode(req: QRLoginRequest):
    """获取扫码登录的二维码"""
    auth_service = get_auth_service()
    result = await auth_service.start_qr_login(device=req.device)

    if not result.get("success"):
        return ApiResponse(
            code=-1,
            message=result.get("message", "获取二维码失败"),
            data=None
        )

    return ApiResponse(
        code=0,
        message="success",
        data={
            "session_id": result["session_id"],
            "qr_code_url": result["qr_code_url"],
            "device": result.get("device"),
            "device_name": result.get("device_name"),
            "tip": result.get("message", "")
        }
    )


@router.get("/qrcode/check/{session_id}", response_model=LoginCheckResponse, summary="检查扫码登录状态")
async def check_qrcode_status(session_id: str):
    """检查扫码登录状态，确认后自动获取并保存 cookies"""
    auth_service = get_auth_service()
    result = await auth_service.check_login_status(session_id)
    return LoginCheckResponse(**result)


@router.post("/login/cookies", response_model=ApiResponse, summary="手动设置cookies登录")
async def login_with_cookies(req: CookieLoginRequest):
    """手动设置 cookies 进行登录"""
    auth_service = get_auth_service()
    success = auth_service.save_cookies(req.cookies)

    if success:
        return ApiResponse(
            code=0,
            message="登录成功",
            data={"is_logged_in": True}
        )
    else:
        return ApiResponse(
            code=-1,
            message="保存cookies失败",
            data=None
        )


@router.post("/logout", response_model=ApiResponse, summary="登出")
async def logout():
    """登出当前账号"""
    auth_service = get_auth_service()
    success = auth_service.logout()

    if success:
        return ApiResponse(
            code=0,
            message="登出成功",
            data={"is_logged_in": False}
        )
    else:
        return ApiResponse(
            code=-1,
            message="登出失败",
            data=None
        )
