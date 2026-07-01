"""
STRM 文件生成服务 - 基于已整理的分享数据库记录生成本地 .strm 文件供 Emby 播放

原理说明：
- 从 share_file 表查询所有已整理（organized=1）且非目录（is_dir=0）的文件记录
- 按整理视图的路径规则 category/organized_dir/organized_name(去后缀).strm 在本地生成文件
- STRM 文件内容是一行直链 URL，格式：
  {base_url}/d115/{organized_name}?share_code={share_code}&receive_code={receive_code}&id={file_id}

执行步骤：
1. 读取 STRM 配置（直链基地址、输出根目录）
2. 读取飞牛授权路径列表，校验输出根目录必须位于授权目录下
3. 查询已整理分享文件
4. 为每条记录生成直链 URL 和本地 STRM 路径
5. 创建目录并写入 .strm 文件，返回统计结果

关键安全点：
- 不能直接拼 Path(category)，因为 category 可能含 .. 等危险片段
- STRM 内容保留原始文件名，方便 Emby 和直链服务按中文路径直接访问
"""
import os
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urlencode

from ..db.database import get_db
from ..paths import ACCESSIBLE_PATHS_FILE, split_accessible_paths
from ..services.config_service import get_config_service
from ..logger import get_logger

logger = get_logger(__name__)

# ==================== 配置键 ====================
# STRM 直链基地址，例如 http://127.0.0.1:11581
CONFIG_STRM_BASE_URL = "strm_direct_link_base_url"
# STRM 输出根目录，必须是飞牛授权路径之一
CONFIG_STRM_OUTPUT_PATH = "strm_output_path"

# 默认直链基地址（本地默认端口 11581）
DEFAULT_STRM_BASE_URL = "http://127.0.0.1:11581"


class StrmService:
    """STRM 文件生成服务

    职责：
    - 读取/保存 STRM 配置
    - 读取飞牛授权路径列表
    - 校验输出路径合法性
    - 查询已整理分享文件
    - 生成直链 URL 和本地 STRM 文件
    """

    def __init__(self):
        self.db = get_db()
        self.config_service = get_config_service()

    # ==================== 配置 ====================

    def get_settings(self) -> Dict:
        """获取 STRM 配置

        Returns:
            包含 direct_link_base_url、output_path 的字典
        """
        base_url = self.config_service.get(CONFIG_STRM_BASE_URL)
        output_path = self.config_service.get(CONFIG_STRM_OUTPUT_PATH)
        return {
            "direct_link_base_url": base_url or DEFAULT_STRM_BASE_URL,
            "output_path": output_path or "",
        }

    def save_settings(self, direct_link_base_url: str, output_path: str) -> Dict:
        """保存 STRM 配置

        Args:
            direct_link_base_url: 直链基地址，必须以 http:// 或 https:// 开头
            output_path: STRM 输出根目录；为空允许保存（生成时会拒绝），
                         非空时必须位于飞牛授权目录下

        Returns:
            保存后的配置字典

        Raises:
            ValueError: 基地址格式非法或输出路径未授权
        """
        # 基地址校验
        base_url = (direct_link_base_url or "").strip()
        if not base_url:
            base_url = DEFAULT_STRM_BASE_URL
        if not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise ValueError("直链基地址必须以 http:// 或 https:// 开头")

        # 输出路径校验
        out_path = (output_path or "").strip()
        if out_path:
            # 必须位于授权目录下
            accessible = self.get_accessible_paths()
            if not accessible:
                raise ValueError("尚未获取到飞牛授权路径，请先在飞牛应用设置中授权目录")
            if not self._is_path_authorized(out_path, accessible):
                raise ValueError(f"输出路径不在飞牛授权目录内: {out_path}")

        # 写入配置
        self.config_service.set(CONFIG_STRM_BASE_URL, base_url, "STRM 直链基地址")
        self.config_service.set(CONFIG_STRM_OUTPUT_PATH, out_path, "STRM 输出根目录")
        return self.get_settings()

    # ==================== 授权路径 ====================

    def get_accessible_paths(self) -> List[str]:
        """获取飞牛授权的可访问路径列表

        路径文件位置统一由 paths.py 管理：
        - 飞牛环境：${TRIM_PKGVAR}/accessible_paths.env
        - 本地开发：{PROJECT_ROOT}/data/accessible_paths.env

        Returns:
            去重后的授权路径列表
        """
        raw = os.environ.get("TRIM_DATA_ACCESSIBLE_PATHS", "")

        # 环境变量为空时尝试读取落盘文件。
        # 本地 Windows 测试时，accessible_paths.env 可以直接写 D:\OneFive\strm-test。
        if not raw and ACCESSIBLE_PATHS_FILE.exists():
            try:
                raw = ACCESSIBLE_PATHS_FILE.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"读取授权路径文件失败: {e}")
                return []

        return split_accessible_paths(raw)

    def _is_path_authorized(self, path: str, accessible: List[str]) -> bool:
        """校验给定路径是否位于某个授权目录下

        Args:
            path: 待校验路径
            accessible: 授权路径列表

        Returns:
            是否在授权范围内
        """
        try:
            target = Path(path).resolve()
        except Exception:
            return False

        for ap in accessible:
            try:
                base = Path(ap).resolve()
                # 检查 target 是否等于 base 或在 base 之下
                if target == base or base in target.parents:
                    return True
            except Exception:
                continue
        return False

    # ==================== 文件查询 ====================

    def _query_organized_files(self) -> List[Dict]:
        """查询所有可生成 STRM 的已整理分享文件

        条件：
        - organized = 1（已整理）
        - is_dir = 0（仅文件）
        - category、organized_dir、organized_name 均非空

        Returns:
            文件记录列表
        """
        rows = self.db.fetchall(
            """SELECT f.*, s.share_code AS source_share_code, s.share_name
               FROM share_file f
               JOIN share_source s ON f.source_id = s.id
               WHERE f.organized = 1
                 AND f.is_dir = 0
                 AND f.category != ''
                 AND f.organized_dir != ''
                 AND f.organized_name != ''
               ORDER BY f.category, f.organized_dir, f.organized_name"""
        )
        return [dict(r) for r in rows]

    # ==================== 路径与 URL 生成 ====================

    def _sanitize_segment(self, segment: str) -> str:
        """清洗单个路径片段，防止目录穿越

        为什么要清洗：
        - category 和 organized_dir 是识别服务生成的字符串
        - 不能完全信任，必须禁止 ..、绝对路径、空字节等危险字符

        Args:
            segment: 原始路径片段

        Returns:
            清洗后的片段（可能为空字符串）
        """
        if not segment:
            return ""
        # 去除空字节
        s = segment.replace("\x00", "")
        # 去除首尾空白和斜杠
        s = s.strip().strip("/").strip()
        # 禁止 . 和 ..
        if s in (".", ".."):
            return ""
        # 拆分后逐段过滤（处理 category 内嵌 / 的情况）
        parts = []
        for p in s.split("/"):
            p = p.strip()
            if p and p not in (".", ".."):
                parts.append(p)
        return "/".join(parts)

    def _build_relative_path(self, category: str, organized_dir: str, organized_name: str) -> Path:
        """构建 STRM 文件的相对路径

        规则：
        - category/organized_dir/organized_name(去原后缀).strm
        - 每一段都经过 _sanitize_segment 清洗

        Args:
            category: 分类路径，例如 "剧集/国产剧"
            organized_dir: 媒体目录，例如 "三体 (2023) {tmdb=298767}/Season 01"
            organized_name: 文件名，例如 "三体.2023.S01E09.H265.AAC.mp4"

        Returns:
            相对路径 Path 对象
        """
        cat = self._sanitize_segment(category)
        org_dir = self._sanitize_segment(organized_dir)

        # 文件名去原扩展名后追加 .strm
        # 使用 Path.stem 只去掉最后一个扩展名，例如 xxx.mp4 → xxx
        stem = Path(organized_name).stem
        strm_name = f"{stem}.strm"

        parts: List[str] = []
        if cat:
            parts.extend(cat.split("/"))
        if org_dir:
            parts.extend(org_dir.split("/"))
        parts.append(strm_name)

        return Path(*parts)

    def _build_strm_url(self, base_url: str, organized_name: str,
                        share_code: str, receive_code: str, file_id: str) -> str:
        """构建 STRM 文件内容（直链 URL）

        格式：
            {base_url}/d115/{organized_name}?share_code=...&receive_code=...&id=...

        这里特意不编码 organized_name：
        - STRM 文件是给 Emby 读取的普通文本，保留中文更直观
        - 当前直链服务和 PathStripMiddleware 已按原始路径处理中文文件名
        - query 参数仍使用 urlencode，避免分享码、提取码等参数出现特殊字符时错位

        Args:
            base_url: 直链基地址
            organized_name: 文件名（用于 URL 路径段，保持原文）
            share_code: 分享码
            receive_code: 提取码（可能为空）
            file_id: 文件 ID

        Returns:
            完整直链 URL
        """
        query = urlencode({
            "share_code": share_code or "",
            "receive_code": receive_code or "",
            "id": file_id or "",
        })
        return f"{base_url.rstrip('/')}/d115/{organized_name}?{query}"

    # ==================== 生成 ====================

    def generate(self) -> Dict:
        """生成 STRM 文件到配置的输出目录

        Returns:
            {
                "total": 120,
                "created": 118,
                "skipped": 0,
                "failed": 2,
                "errors": [
                    {"file_id": "xxx", "name": "xxx.mp4", "error": "写入失败: ..."}
                ]
            }

        Raises:
            ValueError: 输出路径未配置或不在授权目录内
        """
        settings = self.get_settings()
        base_url = settings["direct_link_base_url"]
        output_path = settings["output_path"]

        if not output_path:
            raise ValueError("尚未配置 STRM 输出路径，请先在设置页选择授权目录")

        # 二次校验授权
        accessible = self.get_accessible_paths()
        if not accessible or not self._is_path_authorized(output_path, accessible):
            raise ValueError("输出路径不在飞牛授权目录内，请重新选择")

        output_root = Path(output_path)
        files = self._query_organized_files()

        created = 0
        failed = 0
        skipped = 0
        errors: List[Dict] = []

        for f in files:
            try:
                rel_path = self._build_relative_path(
                    f.get("category", ""),
                    f.get("organized_dir", ""),
                    f.get("organized_name", ""),
                )
                url = self._build_strm_url(
                    base_url,
                    f.get("organized_name", ""),
                    f.get("share_code", ""),
                    f.get("receive_code", ""),
                    f.get("file_id", ""),
                )

                full_path = output_root / rel_path
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # 写入 URL（覆盖模式）
                full_path.write_text(url, encoding="utf-8")
                created += 1
            except Exception as e:
                failed += 1
                errors.append({
                    "file_id": str(f.get("file_id", "")),
                    "name": f.get("organized_name") or f.get("name", ""),
                    "error": f"写入失败: {e}",
                })
                if len(errors) >= 50:
                    break

        logger.info(
            f"STRM 生成完成：总数 {len(files)}，成功 {created}，失败 {failed}"
        )

        return {
            "total": len(files),
            "created": created,
            "skipped": skipped,
            "failed": failed,
            "errors": errors,
        }


# ==================== 单例 ====================
_strm_service: Optional[StrmService] = None


def get_strm_service() -> StrmService:
    """获取 STRM 服务实例（单例模式）"""
    global _strm_service
    if _strm_service is None:
        _strm_service = StrmService()
    return _strm_service
