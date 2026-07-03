"""
通知 API 路由

提供通知渠道的配置、状态查询、测试发送等接口。
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional
from ..models.schemas import ApiResponse
from ..notification import get_notification_manager
from ..services.auth_service import get_auth_service
from ..exceptions import NotLoggedInError

router = APIRouter(prefix="/api/notification", tags=["通知"])


class SettingsRequest(BaseModel):
    """通知配置请求"""
    channel: str  # 渠道名（telegram/wechat/...）
    settings: Dict[str, Any]


class ConnectRequest(BaseModel):
    """连接请求"""
    channel: str


class TestRequest(BaseModel):
    """测试请求"""
    channel: str
    message: str = "这是一条测试消息，来自 OneFive 通知模块"


@router.get("/channels", summary="获取所有通知渠道")
async def list_channels():
    """列出所有已注册的通知渠道及状态（含连接信息）"""
    manager = get_notification_manager()
    channels = await manager.list_channels_async()
    return ApiResponse(code=0, message="success", data={"channels": channels})


# ==================== Telegram 登录 API ====================

class SendCodeRequest(BaseModel):
    """发送验证码请求"""
    phone: str
    api_id: str
    api_hash: str


class SignInRequest(BaseModel):
    """验证码登录请求"""
    phone: str
    code: str
    password: str = ""


@router.post("/telegram/send-code", summary="发送验证码")
async def telegram_send_code(req: SendCodeRequest):
    """Telegram 用户模式：发送手机验证码"""
    manager = get_notification_manager()
    channel = manager.get_channel("telegram")
    if not channel:
        return ApiResponse(code=-1, message="Telegram 渠道不存在")
    result = await channel.send_code(req.phone, req.api_id, req.api_hash)
    if result["success"]:
        return ApiResponse(code=0, message=result["message"])
    return ApiResponse(code=-1, message=result["message"])


@router.post("/telegram/sign-in", summary="验证码登录")
async def telegram_sign_in(req: SignInRequest):
    """Telegram 用户模式：验证码登录"""
    manager = get_notification_manager()
    channel = manager.get_channel("telegram")
    if not channel:
        return ApiResponse(code=-1, message="Telegram 渠道不存在")
    result = await channel.sign_in(req.phone, req.code, req.password)
    if result["success"]:
        return ApiResponse(code=0, message=result["message"], data=result)
    return ApiResponse(code=-1, message=result["message"], data=result)


@router.post("/telegram/check-login", summary="检查登录状态")
async def telegram_check_login():
    """检查 Telegram 用户模式登录状态"""
    manager = get_notification_manager()
    channel = manager.get_channel("telegram")
    if not channel:
        return ApiResponse(code=-1, message="Telegram 渠道不存在")
    result = await channel.check_login()
    return ApiResponse(code=0, message=result["message"], data=result)


@router.get("/settings/{channel_name}", summary="获取渠道配置")
async def get_channel_settings(channel_name: str):
    """获取指定渠道的当前配置"""
    manager = get_notification_manager()
    channel = manager.get_channel(channel_name)
    if not channel:
        return ApiResponse(code=-1, message=f"渠道不存在: {channel_name}")
    settings = await channel.get_current_settings()
    return ApiResponse(code=0, message="success", data={
        "schema": channel.get_settings_schema(),
        "values": settings,
    })


@router.put("/settings", summary="更新渠道配置")
async def update_channel_settings(req: SettingsRequest):
    """更新指定渠道的配置"""
    manager = get_notification_manager()
    channel = manager.get_channel(req.channel)
    if not channel:
        return ApiResponse(code=-1, message=f"渠道不存在: {req.channel}")

    # 更新配置前检查 115 登录态，未登录则拒绝
    if not get_auth_service().get_login_status()["is_logged_in"]:
        raise NotLoggedInError("未登录，请先扫码登录")

    await channel.update_settings(req.settings)
    return ApiResponse(code=0, message="配置已保存")


@router.post("/connect", summary="连接通知渠道")
async def connect_channel(req: ConnectRequest):
    """建立指定渠道的连接"""
    manager = get_notification_manager()
    channel = manager.get_channel(req.channel)
    if not channel:
        return ApiResponse(code=-1, message=f"渠道不存在: {req.channel}")
    success = await channel.connect()
    status = channel.get_status()
    if success:
        return ApiResponse(code=0, message="连接成功", data=status)
    return ApiResponse(code=-1, message=status.get("message", "连接失败"), data=status)


@router.post("/test", summary="发送测试消息")
async def test_notification(req: TestRequest):
    """向指定渠道发送测试消息"""
    manager = get_notification_manager()
    channel = manager.get_channel(req.channel)
    if not channel:
        return ApiResponse(code=-1, message=f"渠道不存在: {req.channel}")
    success = await channel.send_message(req.message)
    if success:
        return ApiResponse(code=0, message="测试消息已发送")
    return ApiResponse(code=-1, message="发送失败，请检查配置和连接状态")
