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

from p115client import P115Client

from ..db.database import get_db
from ..paths import ACCESSIBLE_PATHS_FILE, split_accessible_paths
from ..services.auth_service import get_auth_service
from ..services.config_service import get_config_service
from ..services.file_info_service import get_video_extensions, invalidate_video_extensions_cache, VIDEO_EXTENSIONS
from ..services.file_service import get_file_service
from ..exceptions import NotLoggedInError
from ..logger import get_logger

logger = get_logger(__name__)

# ==================== 配置键 ====================
# STRM 直链基地址，例如 http://127.0.0.1:11581
CONFIG_STRM_BASE_URL = "strm_direct_link_base_url"
# 分享 STRM 输出根目录，必须是飞牛授权路径之一
CONFIG_STRM_OUTPUT_PATH = "strm_output_path"
# 云盘 STRM 输出根目录，必须是飞牛授权路径之一
CONFIG_STRM_CLOUD_OUTPUT_PATH = "strm_cloud_output_path"
# 视频扩展名配置（逗号分隔，如 ".mp4,.mkv,.avi"）
CONFIG_VIDEO_EXTENSIONS = "video_extensions"

# 默认直链基地址（本地默认端口 11581）
DEFAULT_STRM_BASE_URL = "http://127.0.0.1:11581"
# 默认视频扩展名（与 file_info_service.VIDEO_EXTENSIONS 保持一致）
DEFAULT_VIDEO_EXTENSIONS = ".mp4,.mkv,.avi,.mov,.wmv,.flv,.webm,.m4v,.ts,.m2ts"


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
            包含 direct_link_base_url、output_path、cloud_output_path、video_extensions 的字典
        """
        base_url = self.config_service.get(CONFIG_STRM_BASE_URL)
        output_path = self.config_service.get(CONFIG_STRM_OUTPUT_PATH)
        cloud_output_path = self.config_service.get(CONFIG_STRM_CLOUD_OUTPUT_PATH)
        video_extensions = self.config_service.get(CONFIG_VIDEO_EXTENSIONS)
        return {
            "direct_link_base_url": base_url or DEFAULT_STRM_BASE_URL,
            "output_path": output_path or "",
            "cloud_output_path": cloud_output_path or "",
            "video_extensions": video_extensions or DEFAULT_VIDEO_EXTENSIONS,
        }

    def save_settings(self, direct_link_base_url: str, output_path: str,
                      cloud_output_path: str = "",
                      video_extensions: str = "") -> Dict:
        """保存 STRM 配置

        Args:
            direct_link_base_url: 直链基地址，必须以 http:// 或 https:// 开头
            output_path: 分享 STRM 输出根目录；为空允许保存（生成时会拒绝），
                         非空时必须位于飞牛授权目录下
            cloud_output_path: 云盘 STRM 输出根目录；校验规则同 output_path
            video_extensions: 视频扩展名（逗号分隔，如 ".mp4,.mkv,.avi"）；
                              为空时回退到默认值

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

        # 分享 STRM 输出路径校验
        out_path = (output_path or "").strip()
        if out_path:
            accessible = self.get_accessible_paths()
            if not accessible:
                raise ValueError("尚未获取到飞牛授权路径，请先在飞牛应用设置中授权目录")
            if not self._is_path_authorized(out_path, accessible):
                raise ValueError(f"分享 STRM 输出路径不在飞牛授权目录内: {out_path}")

        # 云盘 STRM 输出路径校验（规则同上）
        cloud_path = (cloud_output_path or "").strip()
        if cloud_path:
            accessible = self.get_accessible_paths()
            if not accessible:
                raise ValueError("尚未获取到飞牛授权路径，请先在飞牛应用设置中授权目录")
            if not self._is_path_authorized(cloud_path, accessible):
                raise ValueError(f"云盘 STRM 输出路径不在飞牛授权目录内: {cloud_path}")

        # 视频扩展名校验：为空回退默认，非空则规范化（补点前缀）
        exts_raw = (video_extensions or "").strip()
        if not exts_raw:
            exts_raw = DEFAULT_VIDEO_EXTENSIONS
        else:
            # 规范化：每个扩展名补点前缀，转小写
            normalized = []
            for ext in exts_raw.split(","):
                ext = ext.strip().lower()
                if not ext:
                    continue
                if not ext.startswith("."):
                    ext = "." + ext
                normalized.append(ext)
            if not normalized:
                exts_raw = DEFAULT_VIDEO_EXTENSIONS
            else:
                exts_raw = ",".join(normalized)

        # 写入配置
        self.config_service.set(CONFIG_STRM_BASE_URL, base_url, "STRM 直链基地址")
        self.config_service.set(CONFIG_STRM_OUTPUT_PATH, out_path, "分享 STRM 输出根目录")
        self.config_service.set(CONFIG_STRM_CLOUD_OUTPUT_PATH, cloud_path, "云盘 STRM 输出根目录")
        self.config_service.set(CONFIG_VIDEO_EXTENSIONS, exts_raw, "视频扩展名")

        # 配置变更后刷新缓存，确保后续读取使用新值
        invalidate_video_extensions_cache()

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

    # ==================== 云盘 STRM 生成 ====================

    def _iter_cloud_files_with_path(self, cid: int, current_path: str):
        """递归遍历云盘目录，生成带完整路径的文件信息

        用 file_service.list_files（内部用 fs_files 列表 API）逐目录拉取，
        递归处理子目录，自己构建文件完整路径。

        不使用 p115client 的 iter_files_with_path_skim，因为后者内部
        依赖 download_files_app 下载接口获取路径，该接口对部分 cookies
        会返回"请重新登录"错误。fs_files 列表接口更稳定。

        Args:
            cid: 起始目录 ID
            current_path: 起始目录对应的路径（用于拼接子文件路径）

        Yields:
            dict: 包含 name、pick_code、file_id、path 字段的文件信息
        """
        file_service = get_file_service()
        try:
            result = file_service.list_files(cid, limit=5000)
        except Exception as e:
            logger.error(f"列出云盘目录失败: cid={cid}, {e}")
            return

        for item in result.get("items", []):
            name = item.get("name", "")
            if not name:
                continue

            if item.get("is_dir"):
                # 递归处理子目录
                child_cid = int(item["file_id"])
                child_path = f"{current_path}/{name}" if current_path else name
                yield from self._iter_cloud_files_with_path(child_cid, child_path)
            else:
                # 文件：构建完整路径
                file_path = f"{current_path}/{name}" if current_path else name
                yield {
                    "name": name,
                    "pick_code": item.get("pick_code", ""),
                    "file_id": item.get("file_id", ""),
                    "path": file_path,
                }

    def _resolve_cid_by_path(self, path: str) -> Optional[int]:
        """将云盘路径字符串转为 cid

        逐级用 file_service.list_files 查找子目录（仅查找不创建）。
        区别于 organize_service._ensure_directory 的创建逻辑。

        Args:
            path: 云盘内路径，如 "/媒体库" 或 "媒体库/电影"

        Returns:
            目录 cid；空路径或 "/" 返回 0（根目录）；找不到返回 None
        """
        if not path or not path.strip() or path.strip() == "/":
            return 0

        # 拆分路径片段，过滤空段和 "根目录"
        parts = [p.strip() for p in path.split("/") if p.strip() and p.strip() not in ("根目录", "/")]
        if not parts:
            return 0

        file_service = get_file_service()
        current_cid = 0
        for part in parts:
            found_cid = None
            try:
                result = file_service.list_files(current_cid, limit=200)
                for item in result.get("items", []):
                    if item.get("is_dir") and item.get("name") == part:
                        found_cid = int(item["file_id"])
                        break
            except Exception as e:
                logger.warning(f"查找子目录失败: {current_cid}/{part}, {e}")
                return None

            if found_cid is None:
                logger.warning(f"云盘路径不存在: {path}（在 {part} 处中断）")
                return None
            current_cid = found_cid

        return current_cid

    def _build_cloud_strm_url(self, base_url: str, filename: str, pick_code: str) -> str:
        """构建云盘 STRM 的直链 URL（pickcode 模式）

        格式：{base_url}/d115/{filename}?pickcode={pick_code}

        filename 保持原文不编码，原因：
        - 与分享 STRM 一致
        - STRM 是给 Emby 读取的普通文本，保留中文更直观
        - 直链服务和 PathStripMiddleware 已按原始路径处理中文文件名

        Args:
            base_url: 直链基地址
            filename: 文件名（用于 URL 路径段，保持原文）
            pick_code: 115 文件的 pickcode

        Returns:
            完整直链 URL
        """
        return f"{base_url.rstrip('/')}/d115/{filename}?pickcode={pick_code}"

    def _build_cloud_relative_path(self, file_path: str, media_library_path: str) -> Optional[Path]:
        """构建云盘 STRM 文件的相对路径

        规则：
        - 从云盘完整路径剥离 media_library_path 前缀
        - 每段经 _sanitize_segment 清洗，防止目录穿越
        - 文件名去原扩展名后追加 .strm

        Args:
            file_path: 云盘完整路径，如 "/媒体库/电影/xxx.mp4"
            media_library_path: 媒体库根路径，如 "/媒体库"

        Returns:
            相对路径 Path 对象；剥离前缀后为空则返回 None
        """
        if not file_path:
            return None

        # 标准化路径：去掉首尾空白和斜杠
        full = file_path.strip().strip("/")
        prefix = (media_library_path or "").strip().strip("/")

        # 剥离 media_library_path 前缀
        if prefix and full.startswith(prefix + "/"):
            rel = full[len(prefix) + 1:]
        elif prefix and full == prefix:
            # 文件正好在 media_library_path 根下，不可能（file_path 是文件）
            return None
        else:
            # 前缀不匹配，直接用完整路径（理论上不应发生）
            rel = full

        if not rel:
            return None

        # 拆分段并清洗
        parts: List[str] = []
        for p in rel.split("/"):
            cleaned = self._sanitize_segment(p)
            if cleaned:
                parts.extend(cleaned.split("/"))

        if not parts:
            return None

        # 最后一段是文件名，去原扩展名加 .strm
        stem = Path(parts[-1]).stem
        parts[-1] = f"{stem}.strm"

        return Path(*parts)

    def generate_cloud(self) -> Dict:
        """基于云盘目录生成 STRM 文件

        遍历 media_library_path 配置指定的云盘目录，为其中所有视频文件
        生成 STRM 文件到 cloud_output_path 配置的输出目录。

        流程：
        1. 读取并校验 cloud_output_path 配置
        2. 读取 media_library_path 配置
        3. 解析 media_library_path 为 cid
        4. 递归遍历云盘目录（用 fs_files 列表 API，不依赖下载接口）
        5. 对每个视频文件生成 STRM 文件

        Returns:
            {
                "total": 视频文件总数,
                "created": 成功生成数,
                "skipped": 跳过数,
                "failed": 失败数,
                "errors": [{"file_id": "...", "name": "...", "error": "..."}]
            }

        Raises:
            ValueError: 输出路径未配置或不在授权目录内
            NotLoggedInError: 未登录
        """
        settings = self.get_settings()
        base_url = settings["direct_link_base_url"]
        cloud_output_path = settings["cloud_output_path"]

        if not cloud_output_path:
            raise ValueError("尚未配置云盘 STRM 输出路径，请先在设置页选择授权目录")

        # 二次校验授权
        accessible = self.get_accessible_paths()
        if not accessible or not self._is_path_authorized(cloud_output_path, accessible):
            raise ValueError("云盘 STRM 输出路径不在飞牛授权目录内，请重新选择")

        # 读取媒体库路径
        media_library_path = self.config_service.get("media_library_path") or ""

        # 解析 media_library_path 为 cid
        root_cid = self._resolve_cid_by_path(media_library_path)
        if root_cid is None:
            raise ValueError(f"云盘媒体库路径不存在: {media_library_path}")

        output_root = Path(cloud_output_path)

        logger.info(
            f"开始生成云盘 STRM：源目录={media_library_path or '/'}(cid={root_cid})，"
            f"输出目录={cloud_output_path}"
        )

        # 读取视频扩展名配置（已缓存，不会频繁读数据库）
        video_exts = get_video_extensions()

        total = 0
        created = 0
        failed = 0
        skipped = 0
        errors: List[Dict] = []

        # 递归遍历云盘目录（用 fs_files 列表 API，不依赖 download_files_app）
        for f in self._iter_cloud_files_with_path(root_cid, media_library_path):
            try:
                name = f.get("name", "")
                pick_code = f.get("pick_code", "")
                file_path = f.get("path", "")

                if not name or not pick_code or not file_path:
                    skipped += 1
                    continue

                # 只处理视频文件
                ext = Path(name).suffix.lower()
                if ext not in video_exts:
                    skipped += 1
                    continue

                total += 1

                # 构建相对路径和 URL
                rel_path = self._build_cloud_relative_path(file_path, media_library_path)
                if rel_path is None:
                    skipped += 1
                    total -= 1
                    continue

                url = self._build_cloud_strm_url(base_url, name, pick_code)

                full_path = output_root / rel_path
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # 写入 URL（覆盖模式）
                full_path.write_text(url, encoding="utf-8")
                created += 1
            except Exception as e:
                failed += 1
                errors.append({
                    "file_id": str(f.get("id") or f.get("fid") or ""),
                    "name": f.get("name") or f.get("n") or "",
                    "error": f"写入失败: {e}",
                })
                if len(errors) >= 50:
                    break

        logger.info(
            f"云盘 STRM 生成完成：视频总数 {total}，成功 {created}，"
            f"跳过 {skipped}，失败 {failed}"
        )

        return {
            "total": total,
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
