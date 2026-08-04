"""
STRM 文件生成 API 路由 - 提供设置读写、授权路径查询和生成接口

接口列表：
- GET  /api/strm/settings               获取 STRM 配置
- POST /api/strm/settings               保存 STRM 配置
- GET  /api/strm/accessible-paths       获取飞牛授权目录列表
- POST /api/strm/generate               生成分享 STRM 文件（同步兼容）
- GET  /api/strm/generate-stream        流式生成分享 STRM（SSE，正式环境推荐）
- POST /api/strm/generate-cloud         生成云盘 STRM 文件（同步兼容）
- GET  /api/strm/generate-cloud-stream  流式生成云盘 STRM（SSE，正式环境推荐）
"""
import asyncio
import json
import queue
import threading
from typing import Callable, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..models.schemas import ApiResponse
from ..services.strm_service import get_strm_service
from ..exceptions import AppError
from ..logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/strm", tags=["STRM"])

# 与分享洗版/检测一致：禁止缓冲，并靠注释心跳保活飞牛统一网关
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


class StrmSettingsRequest(BaseModel):
    """STRM 配置请求"""
    direct_link_base_url: str = "http://127.0.0.1:11580"
    output_path: str = ""
    cloud_output_path: str = ""
    video_extensions: str = ""


@router.get("/settings", summary="获取 STRM 配置")
async def get_settings():
    """获取 STRM 直链基地址、分享输出路径、云盘输出路径配置"""
    service = get_strm_service()
    settings = await asyncio.to_thread(service.get_settings)
    return ApiResponse(code=0, message="success", data=settings)


@router.post("/settings", summary="保存 STRM 配置")
async def save_settings(req: StrmSettingsRequest):
    """保存 STRM 直链基地址和输出路径

    保存时会校验：
    - 基地址必须以 http:// 或 https:// 开头
    - 分享/云盘输出路径非空时必须位于飞牛授权目录下
    """
    service = get_strm_service()
    # 数据库写入为同步 I/O，放到线程池避免阻塞事件循环
    settings = await asyncio.to_thread(
        service.save_settings,
        direct_link_base_url=req.direct_link_base_url,
        output_path=req.output_path,
        cloud_output_path=req.cloud_output_path,
        video_extensions=req.video_extensions,
    )
    return ApiResponse(code=0, message="设置已保存", data=settings)


@router.get("/accessible-paths", summary="获取飞牛授权目录列表")
async def get_accessible_paths():
    """获取飞牛授权的可访问路径列表（TRIM_DATA_ACCESSIBLE_PATHS）"""
    service = get_strm_service()
    paths = await asyncio.to_thread(service.get_accessible_paths)
    return ApiResponse(code=0, message="success", data={"paths": paths})


@router.get("/accessible-paths/children", summary="列出授权目录下的子目录")
async def list_accessible_children(path: str = ""):
    """列出指定授权目录下的子目录（一层）

    前端选择 STRM 存储路径时，先选授权目录，再逐级浏览子目录，
    最终路径 = 授权目录 + 选中的子目录路径。

    Args:
        path: 要列出的目录路径，为空时返回所有授权目录
    """
    from pathlib import Path
    service = get_strm_service()

    # path 为空：返回所有授权目录
    if not path:
        paths = await asyncio.to_thread(service.get_accessible_paths)
        return ApiResponse(code=0, message="success", data={"dirs": paths})

    # 校验 path 在授权范围内
    accessible = await asyncio.to_thread(service.get_accessible_paths)
    if not service._is_path_authorized(path, accessible):
        logger.warning(f"[子目录] 路径不在授权范围内: path={path}, accessible={accessible}")
        return ApiResponse(code=0, message="success", data={"dirs": [], "error": "路径不在授权范围内"})

    # 列出子目录
    def _list_subdirs(p: str):
        result = []
        try:
            for entry in sorted(Path(p).iterdir(), key=lambda x: x.name.lower()):
                if entry.is_dir():
                    path_str = str(entry)
                    # 跳过包含代理对的路径（非 UTF-8 文件名），避免 JSON 序列化失败
                    # Linux 文件系统允许任意字节作为文件名，Python 用 surrogateescape 解码
                    # 产生代理对（U+D800-U+DFFF），FastAPI 用 UTF-8 编码 JSON 时会报错
                    try:
                        path_str.encode('utf-8')
                    except UnicodeEncodeError:
                        continue
                    result.append(path_str)
        except (PermissionError, FileNotFoundError, OSError) as e:
            logger.warning(f"[子目录] 列出子目录失败: path={p}, error={type(e).__name__}: {e}")
        return result

    dirs = await asyncio.to_thread(_list_subdirs, path)
    return ApiResponse(code=0, message="success", data={"dirs": dirs})


def _sse_generate_stream(
    *,
    kind: str,
    worker_fn: Callable,
    thread_name: str,
):
    """通用 STRM SSE 生成器：后台线程执行 + 队列推送 + 注释心跳保活。

    事件：
    - start / progress / done / error
    - 注释行 `: heartbeat` 防止飞牛统一网关空闲断连
    """
    label = "分享" if kind == "share" else "云盘"
    logger.info(f"[STRM SSE] 开始生成{label} STRM")

    async def event_generator():
        yield "data: " + json.dumps(
            {"type": "start", "kind": kind, "message": f"开始生成{label} STRM…"},
            ensure_ascii=False,
        ) + "\n\n"

        q: queue.Queue = queue.Queue()
        done_flag = {"ok": False}

        def on_progress(evt: dict) -> None:
            q.put(evt)

        def worker() -> None:
            try:
                data = worker_fn(on_progress)
                created = int((data or {}).get("created") or 0)
                total = int((data or {}).get("total") or 0)
                q.put({
                    "type": "done",
                    "kind": kind,
                    "message": f"生成完成：成功 {created}/{total}",
                    "total": total,
                    "created": created,
                    "skipped": int((data or {}).get("skipped") or 0),
                    "failed": int((data or {}).get("failed") or 0),
                    "errors": (data or {}).get("errors") or [],
                    "truncated": bool((data or {}).get("truncated")),
                })
            except AppError as e:
                logger.warning(f"[STRM SSE] {label}业务失败: {e.message}")
                q.put({"type": "error", "kind": kind, "message": e.message})
            except Exception as e:
                logger.error(f"[STRM SSE] {label}生成异常: {e}", exc_info=True)
                q.put({"type": "error", "kind": kind, "message": str(e)})
            finally:
                done_flag["ok"] = True

        thread = threading.Thread(target=worker, name=thread_name, daemon=True)
        thread.start()

        while True:
            try:
                evt = q.get(timeout=2.0)
            except queue.Empty:
                # 注释心跳：保持统一网关/反向代理不因空闲断开
                yield ": heartbeat\n\n"
                if done_flag["ok"] and q.empty() and not thread.is_alive():
                    yield "data: " + json.dumps(
                        {"type": "error", "kind": kind, "message": f"{label} STRM 生成线程异常结束"},
                        ensure_ascii=False,
                    ) + "\n\n"
                    break
                continue

            yield "data: " + json.dumps(evt, ensure_ascii=False) + "\n\n"
            if evt.get("type") in ("done", "error"):
                break

        thread.join(timeout=1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/generate", summary="生成分享 STRM 文件")
async def generate():
    """根据已整理的分享文件生成 STRM 文件到配置的输出目录

    生成前会再次校验输出路径是否在飞牛授权目录内。
    正式环境（飞牛统一网关）大库请改用 GET /generate-stream，
    避免 axios 默认 30s 超时或网关空闲切断。
    """
    service = get_strm_service()
    # 内部含数据库查询 + 文件 I/O，可能耗时数十秒到数分钟，必须放到线程池
    result = await asyncio.to_thread(service.generate)
    return ApiResponse(code=0, message="生成完成", data=result)


@router.get("/generate-stream", summary="流式生成分享 STRM（SSE）")
async def generate_stream():
    """SSE 流式生成分享 STRM：绕过 axios 超时，并周期性心跳保持飞牛网关连接。"""
    service = get_strm_service()

    def _run(progress: Optional[Callable] = None):
        return service.generate(progress=progress)

    return _sse_generate_stream(
        kind="share",
        worker_fn=_run,
        thread_name="strm-generate-share",
    )


@router.post("/generate-cloud", summary="生成云盘 STRM 文件")
async def generate_cloud():
    """根据云盘媒体库目录生成 STRM 文件到配置的输出目录

    遍历 media_library_path 配置指定的云盘目录，为其中所有视频文件
    生成 STRM 文件，目录结构与云盘结构一致（剥离媒体库前缀）。
    直链使用 pickcode 格式：{base_url}/d115/{filename}?pickcode=xxx

    正式环境（飞牛统一网关）大库请改用 GET /generate-cloud-stream。
    """
    service = get_strm_service()
    # 内部含数据库查询 + 文件 I/O，可能耗时数十秒到数分钟，必须放到线程池
    result = await asyncio.to_thread(service.generate_cloud)
    return ApiResponse(code=0, message="生成完成", data=result)


@router.get("/generate-cloud-stream", summary="流式生成云盘 STRM（SSE）")
async def generate_cloud_stream():
    """SSE 流式生成云盘 STRM：绕过 axios 超时，并周期性心跳保持飞牛网关连接。

    事件格式：
    - {"type":"start","kind":"cloud"}
    - {"type":"progress","stage":"...","percent":N,"message":"..."}
    - {"type":"done","total":N,"created":N,...}
    - {"type":"error","message":"..."}
    - 注释行 `: heartbeat` 保活
    """
    service = get_strm_service()

    def _run(progress: Optional[Callable] = None):
        return service.generate_cloud(progress=progress)

    return _sse_generate_stream(
        kind="cloud",
        worker_fn=_run,
        thread_name="strm-generate-cloud",
    )
