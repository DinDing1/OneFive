"""
配置管理 API 路由 - 处理配置相关的接口

提供配置的增删改查接口，以及 115 开放平台设置。
"""
import time
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
    token = config_service.get("open_access_token")
    expire_str = config_service.get("open_token_expire")

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

    # 启用且有 AppID 时，自动获取 token
    token_valid = False
    if req.enabled and req.app_id:
        token = token_service.get_access_token()
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
    """获取所有配置列表
    
    Returns:
        配置列表
    """
    config_service = get_config_service()
    return config_service.list_all()


@router.get("/settings/{name}", response_model=SettingResponse, summary="获取单个配置")
async def get_setting(name: str):
    """获取指定配置
    
    Args:
        name: 配置名称
        
    Returns:
        配置详情
    """
    config_service = get_config_service()
    setting = config_service.get_with_info(name)
    
    if setting is None:
        raise HTTPException(
            status_code=404,
            detail=f"配置 '{name}' 不存在"
        )
    
    return setting


@router.post("/settings", response_model=SettingResponse, summary="创建配置")
async def create_setting(setting: SettingCreate):
    """创建新配置
    
    Args:
        setting: 配置信息
        
    Returns:
        创建的配置
    """
    config_service = get_config_service()
    
    # 检查配置是否已存在
    if config_service.exists(setting.name):
        raise HTTPException(
            status_code=409,
            detail=f"配置 '{setting.name}' 已存在"
        )
    
    return config_service.set(
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
    
    # 检查配置是否存在
    if not config_service.exists(name):
        raise HTTPException(
            status_code=404,
            detail=f"配置 '{name}' 不存在"
        )
    
    return config_service.set(
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
    
    # 检查配置是否存在
    if not config_service.exists(name):
        raise HTTPException(
            status_code=404,
            detail=f"配置 '{name}' 不存在"
        )
    
    success = config_service.delete(name)
    
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
