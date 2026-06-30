"""
数据模型定义 - 使用 Pydantic 进行数据验证

原理说明：
- 使用 Pydantic 定义请求/响应的数据结构
- 自动进行数据验证和序列化
- 提供清晰的 API 文档
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class SettingBase(BaseModel):
    """配置基础模型"""
    name: str = Field(..., description="配置名称", min_length=1, max_length=100)
    value: Optional[str] = Field(None, description="配置值")
    description: Optional[str] = Field(None, description="配置说明")


class SettingCreate(SettingBase):
    """创建配置请求模型"""
    pass


class SettingUpdate(BaseModel):
    """更新配置请求模型"""
    value: Optional[str] = Field(None, description="配置值")
    description: Optional[str] = Field(None, description="配置说明")


class SettingResponse(SettingBase):
    """配置响应模型"""
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    
    class Config:
        from_attributes = True


class LoginStatus(BaseModel):
    """登录状态响应模型"""
    is_logged_in: bool = Field(..., description="是否已登录")
    user_id: Optional[str] = Field(None, description="用户ID")
    user_name: Optional[str] = Field(None, description="用户名")
    vip: int = Field(0, description="VIP状态，0表示非VIP，1表示VIP")
    vip_type: str = Field("none", description="VIP类型: none/vip/forever")
    face: str = Field("", description="用户头像URL")
    message: str = Field(..., description="状态消息")


class QRCodeResponse(BaseModel):
    """二维码响应模型"""
    qr_code_url: str = Field(..., description="二维码图片URL")
    session_id: str = Field(..., description="登录会话ID")
    message: str = Field("请使用115客户端扫描二维码登录", description="提示消息")


class LoginCheckResponse(BaseModel):
    """登录检查响应模型"""
    status: str = Field(..., description="状态: pending/scanned/confirmed/failed")
    cookies: Optional[str] = Field(None, description="登录成功后的cookies")
    user_name: Optional[str] = Field(None, description="用户名")
    message: str = Field(..., description="状态消息")


class ApiResponse(BaseModel):
    """通用API响应模型"""
    code: int = Field(0, description="状态码，0表示成功")
    message: str = Field("success", description="响应消息")
    data: Optional[dict] = Field(None, description="响应数据")
