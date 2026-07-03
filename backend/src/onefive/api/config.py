"""
配置管理 API 路由 - 处理配置相关的接口

提供配置的增删改查接口，以及 115 开放平台设置。
"""
import time
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict
from ..models.schemas import (
    ApiResponse, SettingCreate, SettingUpdate, SettingResponse
)
from ..services.config_service import get_config_service
from ..services.token_service import get_token_service

# 创建配置路由
router = APIRouter(prefix="/api/config", tags=["配置"])

# 敏感配置键集合：读取接口返回时对 value 脱敏，避免明文回显凭据
# 注意：写入接口（set/update）仍可正常写入，仅读取时不回显明文
SENSITIVE_KEYS = {
    "cookie115", "open_access_token", "open_refresh_token",
    "tg_bot_token", "tg_api_hash", "tg_session_string", "tg_bot_session",
}


def _mask_setting(setting: SettingResponse) -> SettingResponse:
    """对敏感配置的 value 字段做脱敏处理

    非空值替换为 "******"，空值保持空串，避免泄漏凭据明文。
    """
    if setting.name in SENSITIVE_KEYS:
        masked_value = "******" if setting.value else ""
        return setting.model_copy(update={"value": masked_value})
    return setting


# ==================== 115 开放平台设置 ====================

class OpenApiSettingsRequest(BaseModel):
    """Open API 设置请求"""
    enabled: bool
    app_id: str = ""


@router.get("/open-api", summary="获取 Open API 设置")
async def get_open_api_settings():
    """获取 115 开放平台设置（开关、AppID、Token 状态）"""
    token_service = get_token_service()
    config_service = get_config_service()

    enabled = token_service.is_open_api_enabled()
    app_id = token_service.get_app_id() or ""
    # 数据库读取为同步 I/O，放到线程池避免阻塞事件循环
    token = await asyncio.to_thread(config_service.get, "open_access_token")
    expire_str = await asyncio.to_thread(config_service.get, "open_token_expire")

    # 判断 token 是否有效
    token_valid = False
    if token and expire_str:
        try:
            token_valid = time.time() < int(expire_str)
        except (ValueError, TypeError):
            pass

    return ApiResponse(
        code=0,
        message="success",
        data={
            "enabled": enabled,
            "app_id": app_id,
            "token_valid": token_valid,
        }
    )


@router.post("/open-api", summary="更新 Open API 设置")
async def update_open_api_settings(req: OpenApiSettingsRequest):
    """更新 115 开放平台设置

    切换开关或更换 AppID 后，自动尝试获取 token。
    """
    token_service = get_token_service()
    token_service.set_open_api_enabled(req.enabled)

    if req.app_id:
        token_service.set_app_id(req.app_id)

    # 启用且有 AppID 时，自动获取 token（同步方法用 asyncio.to_thread 包裹，避免阻塞事件循环）
    token_valid = False
    if req.enabled and req.app_id:
        token = await asyncio.to_thread(token_service.get_access_token)
        token_valid = token is not None

    return ApiResponse(
        code=0,
        message="设置已保存",
        data={
            "enabled": req.enabled,
            "app_id": req.app_id,
            "token_valid": token_valid,
        }
    )


# ==================== 通用配置 CRUD ====================


@router.get("/settings", response_model=List[SettingResponse], summary="获取所有配置")
async def list_settings():
    """获取所有配置列表（敏感配置的 value 字段做脱敏处理）

    Returns:
        配置列表
    """
    config_service = get_config_service()
    # 数据库读取为同步 I/O，放到线程池避免阻塞事件循环
    settings = await asyncio.to_thread(config_service.list_all)
    return [_mask_setting(s) for s in settings]


@router.get("/settings/{name}", response_model=SettingResponse, summary="获取单个配置")
async def get_setting(name: str):
    """获取指定配置（敏感配置的 value 字段做脱敏处理）

    Args:
        name: 配置名称

    Returns:
        配置详情
    """
    config_service = get_config_service()
    # 数据库读取为同步 I/O，放到线程池避免阻塞事件循环
    setting = await asyncio.to_thread(config_service.get_with_info, name)

    if setting is None:
        raise HTTPException(
            status_code=404,
            detail=f"配置 '{name}' 不存在"
        )

    return _mask_setting(setting)


@router.post("/settings", response_model=SettingResponse, summary="创建配置")
async def create_setting(setting: SettingCreate):
    """创建新配置
    
    Args:
        setting: 配置信息
        
    Returns:
        创建的配置
    """
    config_service = get_config_service()

    # 检查配置是否已存在（同步数据库查询，放到线程池避免阻塞事件循环）
    if await asyncio.to_thread(config_service.exists, setting.name):
        raise HTTPException(
            status_code=409,
            detail=f"配置 '{setting.name}' 已存在"
        )

    # 数据库写入为同步 I/O，放到线程池避免阻塞事件循环
    return await asyncio.to_thread(
        config_service.set,
        setting.name,
        setting.value,
        setting.description
    )


@router.put("/settings/{name}", response_model=SettingResponse, summary="更新配置")
async def update_setting(name: str, setting: SettingUpdate):
    """更新配置
    
    Args:
        name: 配置名称
        setting: 更新的配置信息
        
    Returns:
        更新后的配置
    """
    config_service = get_config_service()

    # 检查配置是否存在（同步数据库查询，放到线程池避免阻塞事件循环）
    if not await asyncio.to_thread(config_service.exists, name):
        raise HTTPException(
            status_code=404,
            detail=f"配置 '{name}' 不存在"
        )

    # 数据库写入为同步 I/O，放到线程池避免阻塞事件循环
    return await asyncio.to_thread(
        config_service.set,
        name,
        setting.value,
        setting.description
    )


@router.delete("/settings/{name}", response_model=ApiResponse, summary="删除配置")
async def delete_setting(name: str):
    """删除配置
    
    Args:
        name: 配置名称
        
    Returns:
        删除结果
    """
    config_service = get_config_service()

    # 检查配置是否存在（同步数据库查询，放到线程池避免阻塞事件循环）
    if not await asyncio.to_thread(config_service.exists, name):
        raise HTTPException(
            status_code=404,
            detail=f"配置 '{name}' 不存在"
        )

    # 数据库删除为同步 I/O，放到线程池避免阻塞事件循环
    success = await asyncio.to_thread(config_service.delete, name)
    
    if success:
        return ApiResponse(
            code=0,
            message=f"配置 '{name}' 已删除"
        )
    else:
        raise HTTPException(
            status_code=500,
            detail="删除配置失败"
        )
