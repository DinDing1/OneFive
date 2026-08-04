"""
文件名质量评分模块（分享洗版）

100 分制，与整理重命名字段对齐（file_info_service / rename_service）：
  分辨率 videoFormat     0~40
  片源   source(edition) 0~35
  动态范围 effects       0~12
  音频   audioCodec      0~8
  编码微调 videoCodec等  0~5
  合计                   0~100

规则：
- 不考虑文件体积
- 词表复用 extract_tech_info / _extract_source 等，避免与重命名漂移
- REMUX 缺编码/音轨时给缺省分，保证同分辨率原盘压 WEB
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .file_info_service import (
    _extract_audio_codec,
    _extract_edition,
    _extract_effects,
    _extract_release_group,
    _extract_source,
    _extract_video_codec,
    _extract_video_format,
    extract_tech_info,
)


# ==================== 分值表（满分 100） ====================

_RESOLUTION_SCORES: Dict[str, int] = {
    "4320p": 40,
    "2160p": 38,
    "1440p": 30,
    "1080p": 26,
    "720p": 18,
    "576p": 12,
    "480p": 10,
    "360p": 10,
}

_SOURCE_SCORES: Dict[str, int] = {
    "UHD BluRay REMUX": 35,
    "BluRay REMUX": 34,
    "UHD BluRay": 28,
    "BluRay": 26,
    "UHD": 20,
    "WEB-DL": 15,
    "WEBRip": 11,
    "HDTV": 7,
    "DVD": 4,
}

_SOURCE_DEFAULT = 1  # 无法识别片源

# 动态范围：取最高一档，不叠爆
_HDR_SCORES: List[Tuple[str, int]] = [
    ("DV", 12),
    ("HDR10+", 10),
    ("HDR10", 8),
    ("HDR", 6),
    ("HLG", 4),
]

_REMUX_SOURCES = frozenset({"UHD BluRay REMUX", "BluRay REMUX"})


@dataclass
class QualityBreakdown:
    """百分制分项，便于调试/展示。"""
    resolution: int = 0
    source: int = 0
    hdr: int = 0
    audio: int = 0
    codec_extra: int = 0
    total: int = 0
    video_format: str = ""
    source_name: str = ""
    effects: str = ""
    video_codec: str = ""
    audio_codec: str = ""
    release_group: str = ""


def _basename(path: str) -> str:
    if not path:
        return ""
    parts = [p for p in re.split(r"[/\\]", path) if p]
    return parts[-1] if parts else path


def _base_no_ext(filename: str) -> str:
    if not filename:
        return ""
    if "." in filename and not filename.startswith("."):
        return filename.rsplit(".", 1)[0]
    return filename


def parse_quality_fields(path: str) -> Dict[str, str]:
    """从整理后路径/文件名解析与重命名一致的技术字段。"""
    name = _basename(path)
    if not name:
        return {
            "videoFormat": "",
            "source": "",
            "effects": "",
            "videoCodec": "",
            "audioCodec": "",
            "editionFlags": "",
            "releaseGroup": "",
            "webSource": "",
            "fileExt": "",
        }

    tech = extract_tech_info(name)
    base = _base_no_ext(name)
    # 目录段也可能带质量词（少见）；拼上 basename 再抽一次片源/特效更稳
    scan = base
    parent_parts = [p for p in re.split(r"[/\\]", path or "") if p]
    if len(parent_parts) >= 2:
        scan = f"{parent_parts[-2]} {base}"

    source = _extract_source(scan) or _extract_source(base)
    effects = _extract_effects(scan) or _extract_effects(base)
    edition_flags = _extract_edition(scan) or _extract_edition(base)

    video_format = tech.get("videoFormat") or _extract_video_format(scan) or _extract_video_format(base)
    video_codec = tech.get("videoCodec") or _extract_video_codec(scan) or _extract_video_codec(base)
    audio_codec = tech.get("audioCodec") or _extract_audio_codec(scan) or _extract_audio_codec(base)
    release_group = tech.get("releaseGroup") or _extract_release_group(base) or ""

    return {
        "videoFormat": video_format or "",
        "source": source or "",
        "effects": effects or "",
        "videoCodec": video_codec or "",
        "audioCodec": audio_codec or "",
        "editionFlags": edition_flags or "",
        "releaseGroup": release_group or "",
        "webSource": tech.get("webSource") or "",
        "fileExt": tech.get("fileExt") or "",
    }


def _score_resolution(video_format: str) -> int:
    if not video_format:
        return 0
    return int(_RESOLUTION_SCORES.get(video_format, 0))


def _score_source(source: str) -> int:
    if not source:
        return _SOURCE_DEFAULT
    return int(_SOURCE_SCORES.get(source, _SOURCE_DEFAULT))


def _score_hdr(effects: str) -> int:
    if not effects:
        return 0
    text = effects.upper().replace(" ", "")
    # DV 优先，命中后不再叠 HDR
    if re.search(r"\bDV\b|DOVI|DOLBY.?VISION", effects, re.I):
        return 12
    if "HDR10+" in text or "HDR10PLUS" in text:
        return 10
    if "HDR10" in text:
        return 8
    if re.search(r"\bHDR\b", effects, re.I):
        return 6
    if re.search(r"\bHLG\b", effects, re.I):
        return 4
    return 0


def _score_audio(audio_codec: str) -> int:
    if not audio_codec:
        return 0
    ac = audio_codec.upper()
    if ac.startswith("TRUEHD.ATMOS") or "TRUEHD.ATMOS" in ac:
        return 8
    if ac.startswith("TRUEHD"):
        return 7
    if "DTS-HD.MA.ATMOS" in ac or ac.startswith("DTS.ATMOS"):
        return 7
    if ac.startswith("DTS-HD.MA") or "DTS-HD.MA" in ac:
        return 6
    if ac.startswith("DDP.ATMOS") or "DDP.ATMOS" in ac:
        return 5
    if ac.startswith("DDP") or ac.startswith("DTS"):
        return 3
    if ac.startswith("AAC") or ac.startswith("FLAC"):
        return 2
    return 1


def _score_codec_extra(video_codec: str, edition_flags: str, source: str) -> int:
    pts = 0
    vc = (video_codec or "").upper()
    if vc in ("AV1", "H265"):
        pts += 3
    elif vc in ("H264",):
        pts += 2
    elif vc:
        pts += 1

    flags = edition_flags or ""
    extra = 0
    if re.search(r"\bIMAX\b", flags, re.I):
        extra += 2
    if re.search(r"\bPROPER\b", flags, re.I):
        extra += 1
    if re.search(r"\bREPACK\b", flags, re.I):
        extra += 1
    pts += min(2, extra)
    return min(5, pts)


def _apply_remux_defaults(
    source: str,
    video_codec: str,
    audio_codec: str,
    codec_pts: int,
    audio_pts: int,
) -> Tuple[int, int]:
    """原盘缺编码/音轨时给地板分，避免被写全标签的 WEB 反超。"""
    if source not in _REMUX_SOURCES:
        return codec_pts, audio_pts
    if not video_codec and codec_pts < 3:
        codec_pts = 3  # 默认按 H265
    if not audio_codec and audio_pts < 3:
        audio_pts = 3  # 音轨地板，非 TrueHD 满分
    return min(5, codec_pts), min(8, audio_pts)


def score_quality_breakdown(path: str) -> QualityBreakdown:
    """计算百分制分项。"""
    fields = parse_quality_fields(path)
    video_format = fields["videoFormat"]
    source = fields["source"]
    effects = fields["effects"]
    video_codec = fields["videoCodec"]
    audio_codec = fields["audioCodec"]
    edition_flags = fields["editionFlags"]

    res_pts = _score_resolution(video_format)
    src_pts = _score_source(source)
    hdr_pts = _score_hdr(effects)
    audio_pts = _score_audio(audio_codec)
    codec_pts = _score_codec_extra(video_codec, edition_flags, source)
    codec_pts, audio_pts = _apply_remux_defaults(
        source, video_codec, audio_codec, codec_pts, audio_pts
    )

    total = res_pts + src_pts + hdr_pts + audio_pts + codec_pts
    total = max(0, min(100, int(total)))

    return QualityBreakdown(
        resolution=res_pts,
        source=src_pts,
        hdr=hdr_pts,
        audio=audio_pts,
        codec_extra=codec_pts,
        total=total,
        video_format=video_format,
        source_name=source,
        effects=effects,
        video_codec=video_codec,
        audio_codec=audio_codec,
        release_group=fields.get("releaseGroup") or "",
    )


def calculate_quality_score(path: str, size: int = 0) -> int:
    """计算 0~100 画质分。

    size 参数保留兼容，**不参与计分**。
    """
    _ = size  # 明确忽略体积
    return score_quality_breakdown(path).total


def get_quality_level(score: int) -> str:
    """百分制档位文案。"""
    s = int(score or 0)
    if s >= 90:
        return "优秀"
    if s >= 75:
        return "良好"
    if s >= 60:
        return "一般"
    return "较差"


def generate_video_tags(path: str) -> List[str]:
    """生成展示标签（与整理重命名词表一致）。"""
    b = score_quality_breakdown(path)
    tags: List[str] = []
    if b.video_format:
        tags.append(b.video_format)
    if b.source_name:
        tags.append(b.source_name)
    if b.effects:
        # effects 可能是 "DV HDR10"，收成一段
        tags.append(b.effects)
    if b.video_codec:
        tags.append(b.video_codec)
    if b.audio_codec:
        tags.append(b.audio_codec)
    if b.release_group:
        tags.append(b.release_group)
    return tags


def extract_release_group(path: str) -> str:
    """从路径提取发布组（复用整理模块）。"""
    name = _basename(path)
    base = _base_no_ext(name)
    if not base:
        return ""
    return _extract_release_group(base) or ""


def aggregate_quality_scores(scores: List[int]) -> int:
    """样本聚合：≤2 用 max，否则 P75。"""
    if not scores:
        return 0
    if len(scores) == 1:
        return int(scores[0])
    if len(scores) == 2:
        return int(max(scores))
    ordered = sorted(int(s) for s in scores)
    # 线性插值 75 分位
    idx = 0.75 * (len(ordered) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return int(round(ordered[lo] * (1.0 - frac) + ordered[hi] * frac))


# 兼容旧调用名（若外部仍引用）
def extract_video_info(path: str):
    """兼容旧接口：返回简单命名空间。"""
    b = score_quality_breakdown(path)
    return b

